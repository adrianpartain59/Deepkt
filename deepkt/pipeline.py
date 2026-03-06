"""
Pipeline — Parallel download → analyze → store coordinator.

Three stages connected by queues:
  1. Download pool (ThreadPoolExecutor — I/O-bound)
  2. Analysis pool (ProcessPoolExecutor — CPU-bound)
  3. Storage loop (single thread — serialized SQLite writes)

Deletes MP3s immediately after feature extraction.
"""

import logging
import os
import queue
import signal
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime
from threading import Event

from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, TimeElapsedColumn,
    TimeRemainingColumn, MofNCompleteColumn, SpinnerColumn,
)

from deepkt.config import load_pipeline_config
from deepkt.downloader import download_single
from deepkt.analyzer import analyze_snippet
from deepkt import db as trackdb

console = Console()

# --- Logging setup ---
def _setup_logging(log_file="data/pipeline.log"):
    """Configure file + console logging."""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
        ],
    )
    return logging.getLogger("deepkt.pipeline")


# --- Worker functions (must be top-level for ProcessPoolExecutor pickling) ---

def _download_worker(url, output_dir, rate_limit_pause, max_retries):
    """Download a single track with retries and rate limiting.

    Returns dict with metadata on success, or dict with error on failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            result = download_single(url, output_dir=output_dir)
            time.sleep(rate_limit_pause)
            return {"status": "ok", **result}
        except Exception as e:
            if attempt < max_retries:
                # Exponential backoff: 2s, 4s, 8s
                wait = rate_limit_pause * (2 ** attempt)
                time.sleep(wait)
            else:
                return {"status": "error", "url": url, "error": str(e)}


def _analyze_worker(file_path):
    """Run all feature extractors on a single MP3.

    Returns the feature dict (picklable) or raises.
    """
    return analyze_snippet(file_path)

def _mute_worker():
    import sys
    import os
    # Redirect low-level file descriptors to /dev/null
    # This prevents C-level warnings (like macOS CoreAudio MallocStackLogging)
    # from breaking the rich.progress bar in the main process.
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, sys.stdout.fileno())
    os.dup2(devnull, sys.stderr.fileno())
    os.close(devnull)

# ============================================================
# Main Pipeline
# ============================================================

def run_pipeline(urls=None, links_file=None, resume=False, config_overrides=None):
    """Run the full download → analyze → store pipeline in parallel.

    Args:
        urls: List of URLs to process. Mutually exclusive with links_file.
        links_file: Path to text file with URLs. Mutually exclusive with urls.
        resume: If True, re-queue tracks stuck in DOWNLOADING/ANALYZING state.
        config_overrides: Dict to override pipeline.yaml settings.

    Returns:
        Dict with pipeline results: {downloaded, analyzed, stored, failed, skipped}
    """
    # 1. Load config
    config = load_pipeline_config()
    if config_overrides:
        for section, overrides in config_overrides.items():
            if section in config:
                config[section].update(overrides)

    dl_workers = config["download"]["workers"]
    dl_pause = config["download"]["rate_limit_pause"]
    dl_retries = config["download"]["max_retries"]
    an_workers = config["analysis"]["workers"]
    an_timeout = config["analysis"]["timeout"]
    temp_dir = config["cleanup"]["temp_dir"]
    delete_mp3 = config["cleanup"]["delete_mp3_after"]
    log_file = config["progress"]["log_file"]

    logger = _setup_logging(log_file)
    os.makedirs(temp_dir, exist_ok=True)

    # 2. Load URLs
    if urls is None and links_file:
        with open(links_file, "r") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not urls:
        console.print("[yellow]No URLs to process.[/yellow]")
        return {"downloaded": 0, "analyzed": 0, "stored": 0, "failed": 0, "skipped": 0}

    conn = trackdb.get_db()

    # 3. Handle resume — re-queue stuck tracks
    resume_files = []
    if resume:
        stuck = (
            trackdb.get_tracks(conn, status="DOWNLOADING") 
            + trackdb.get_tracks(conn, status="ANALYZING")
            + trackdb.get_tracks(conn, status="DOWNLOADED")
        )
        for track in stuck:
            mp3_path = os.path.join(temp_dir, track["id"])
            if os.path.exists(mp3_path) and track["status"] != "DOWNLOADED":
                resume_files.append({
                    "file_path": mp3_path,
                    "filename": track["id"],
                    "artist": track["artist"],
                    "title": track["title"],
                    "url": track.get("url", ""),
                })
                logger.info(f"Resuming stuck track: {track['id']}")
            else:
                # MP3 gone or status is DOWNLOADED (already deleted by old pipeline crash), need to re-download
                trackdb.update_status(conn, track["id"], "DISCOVERED")
                logger.info(f"Re-queuing for download: {track['id']}")

    # 4. Filter out already-indexed URLs (only skip INDEXED tracks, not DISCOVERED ones)
    existing_urls = {t.get("url") for t in trackdb.get_tracks(conn, status="INDEXED") if t.get("url")}
    
    original_count = len(urls)
    urls = [u for u in urls if u not in existing_urls]
    
    if len(urls) < original_count:
        skipped = original_count - len(urls)
        logger.info(f"Skipping {skipped} URLs that are already tracked in the database.")
        console.print(f"[green]⏭️  Skipping {skipped} already-indexed tracks...[/green]")

    total_urls = len(urls) + len(resume_files)

    # 5. Run pipeline with progress
    results = {
        "downloaded": 0,
        "analyzed": 0,
        "stored": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    # Shutdown event for graceful interrupt
    shutdown_event = Event()

    def handle_interrupt(signum, frame):
        if shutdown_event.is_set():
            console.print("\n[bold red]🛑 Force quitting immediately![/bold red]")
            os._exit(1)
            
        console.print("\n[yellow]⚠️  Interrupt received. Finishing current tasks... (Press Ctrl+C again to force quit)[/yellow]")
        shutdown_event.set()

    import threading
    is_main_thread = threading.current_thread() is threading.main_thread()
    
    if is_main_thread:
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, handle_interrupt)

    try:
        _run_with_progress(
            urls=urls,
            resume_files=resume_files,
            conn=conn,
            config=config,
            results=results,
            shutdown_event=shutdown_event,
            logger=logger,
        )
    finally:
        if is_main_thread:
            signal.signal(signal.SIGINT, original_handler)
        conn.close()

        # Clean up empty temp dir
        try:
            if os.path.isdir(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
        except OSError:
            pass

    return results


def _run_with_progress(urls, resume_files, conn, config, results, shutdown_event, logger):
    """Execute the pipeline stages with rich progress bars."""
    dl_workers = config["download"]["workers"]
    dl_pause = config["download"]["rate_limit_pause"]
    dl_retries = config["download"]["max_retries"]
    an_workers = config["analysis"]["workers"]
    an_timeout = config["analysis"]["timeout"]
    temp_dir = config["cleanup"]["temp_dir"]
    delete_mp3 = config["cleanup"]["delete_mp3_after"]

    total = len(urls) + len(resume_files)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        dl_task = progress.add_task("⬇️  Downloading", total=len(urls))
        an_task = progress.add_task("🧬 Analyzing", total=total)
        st_task = progress.add_task("💾 Storing", total=total)

        # Queue: download results → analysis
        analyze_queue = queue.Queue(maxsize=100)

        # --- Stage 1: Download (threads) ---
        with ThreadPoolExecutor(max_workers=dl_workers) as dl_executor:
            dl_futures = {}
            for url in urls:
                if shutdown_event.is_set():
                    break
                future = dl_executor.submit(
                    _download_worker, url, temp_dir, dl_pause, dl_retries
                )
                dl_futures[future] = url

            # Also queue resume files directly for analysis
            active_an = {}
            # --- Stage 2 & 3: Process downloads as they complete ---
            with ProcessPoolExecutor(max_workers=an_workers, initializer=_mute_worker) as an_executor:
                active_dl = dict(dl_futures)

                # Submit resume files for analysis immediately
                for rf in resume_files:
                    if shutdown_event.is_set():
                        break
                    future = an_executor.submit(_analyze_worker, rf["file_path"])
                    active_an[future] = rf

                # Process futures as they complete across both pools
                consecutive_errors = 0
                while active_dl or active_an:
                    if shutdown_event.is_set():
                        break

                    # Wait for at least one future to complete
                    done, _ = wait(
                        list(active_dl.keys()) + list(active_an.keys()),
                        return_when=FIRST_COMPLETED
                    )

                    for future in done:
                        if shutdown_event.is_set():
                            break

                        if future in active_dl:
                            # --- Handle Completed Download ---
                            url = active_dl.pop(future)
                            progress.advance(dl_task)
                            dl_result = future.result()

                            if dl_result["status"] == "error":
                                results["failed"] += 1
                                error_msg = f"Download failed: {dl_result.get('url', '?')}: {dl_result.get('error', '?')}"
                                results["errors"].append(error_msg)
                                logger.error(error_msg)
                                progress.advance(an_task)  # Skip analysis count
                                progress.advance(st_task)  # Skip storage count
                                continue

                            results["downloaded"] += 1
                            logger.info(f"Downloaded: {dl_result['filename']}")

                            # Register in SQLite
                            trackdb.register_track(
                                conn,
                                dl_result["filename"],
                                dl_result["artist"],
                                dl_result["title"],
                                url=dl_result.get("url"),
                                source="pipeline",
                            )
                            trackdb.update_status(conn, dl_result["filename"], "DOWNLOADED")

                            # Check if already analyzed (idempotent)
                            existing = trackdb.get_features(conn, dl_result["filename"])
                            if existing:
                                # Already have features — mark as INDEXED and skip
                                trackdb.update_status(conn, dl_result["filename"], "INDEXED")
                                results["skipped"] += 1
                                progress.advance(an_task)
                                progress.advance(st_task)
                                # Clean up duplicate MP3
                                if delete_mp3:
                                    _safe_delete(dl_result["file_path"], logger)
                                continue

                            # Submit for analysis
                            an_fut = an_executor.submit(_analyze_worker, dl_result["file_path"])
                            active_an[an_fut] = dl_result

                        elif future in active_an:
                            # --- Handle Completed Analysis ---
                            track_info = active_an.pop(future)
                            progress.advance(an_task)

                            try:
                                feature_dict = future.result(timeout=config["analysis"]["timeout"])
                                consecutive_errors = 0
                            except Exception as e:
                                consecutive_errors += 1
                                results["failed"] += 1
                                error_msg = f"Analysis failed: {track_info['filename']}: {e}"
                                results["errors"].append(error_msg)
                                logger.error(error_msg)
                                trackdb.update_status(conn, track_info["filename"], "FAILED", error=str(e))
                                progress.advance(st_task)
                                # Still clean up the MP3
                                if delete_mp3:
                                    _safe_delete(track_info.get("file_path", ""), logger)

                                if consecutive_errors >= 3:
                                    console.print("\n[bold red]🚨 EMERGENCY ABORT: 3 consecutive track failures detected. Neural Network may be frozen or out of memory. Force quitting to protect OS.[/bold red]")
                                    logger.critical("Emergency abort triggered due to 3 consecutive failures.")
                                    os._exit(1)

                                continue

                            # Store features in SQLite
                            trackdb.store_features(conn, track_info["filename"], feature_dict)
                            trackdb.update_status(conn, track_info["filename"], "INDEXED")
                            results["analyzed"] += 1
                            results["stored"] += 1
                            progress.advance(st_task)

                            total_dims = sum(len(v) for v in feature_dict.values())
                            logger.info(f"Stored: {track_info['filename']} ({total_dims} dims)")

                            # Delete MP3 immediately
                            if delete_mp3:
                                _safe_delete(track_info.get("file_path", ""), logger)

                # Clean up if interrupted (mark remaining analyses as DISCOVERED so they aren't stuck locally)
                if shutdown_event.is_set():
                    for fut, track_info in active_an.items():
                        trackdb.update_status(conn, track_info["filename"], "DISCOVERED")
                
                # Force kill pools so they don't block exit on lingering sleep threads
                dl_executor.shutdown(wait=False, cancel_futures=True)
                an_executor.shutdown(wait=False, cancel_futures=True)


def _safe_delete(file_path, logger):
    """Delete a file, logging any errors."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"Deleted: {file_path}")
    except OSError as e:
        logger.warning(f"Failed to delete {file_path}: {e}")


# ============================================================
# Pipeline Status
# ============================================================

def get_pipeline_status():
    """Get current pipeline status from SQLite.

    Returns:
        Dict with counts by status and any recent errors.
    """
    conn = trackdb.get_db()
    stats = trackdb.get_stats(conn)

    # Get recent failures
    failed = trackdb.get_tracks(conn, status="FAILED", limit=10)
    in_progress = (
        trackdb.get_tracks(conn, status="DOWNLOADING")
        + trackdb.get_tracks(conn, status="ANALYZING")
    )

    conn.close()

    return {
        "stats": stats,
        "failed_recent": [
            {"id": t["id"], "error": t.get("error_message", "?")} for t in failed
        ],
        "in_progress": [t["id"] for t in in_progress],
    }
