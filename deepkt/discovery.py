"""
Discovery — Playlist-based audio-gated artist discovery engine.

Searches SoundCloud for playlists matching genre keywords from hashtags.txt,
probes artists through LAION-CLAP for audio similarity, and scrapes full
catalogs (130 tracks) for approved artists into crawled_links.txt.

Flow:
  1. Load keywords from hashtags.txt
  2. Search for playlists, rank by keyword match count
  3. For each playlist, iterate tracks
  4. For each new artist: audio probe → similarity gate
  5. Approved: scrape 130 tracks → crawled_links.txt
  6. Stop when target tracks reached
"""

import os
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    MofNCompleteColumn, TimeElapsedColumn,
)

from deepkt import db as trackdb
from deepkt.crawler import SoundCloudSpider, CRAWLED_LINKS_FILE
from deepkt.config import load_pipeline_config

console = Console()

KEYWORDS_FILE = "hashtags.txt"
EXCLUDE_KEYWORDS_FILE = "exclude_keywords.txt"


# ============================================================
# Step 1: Playlist Search & Ranking
# ============================================================

def load_keywords(keywords_file=KEYWORDS_FILE):
    """Load genre keywords from hashtags.txt.

    Returns:
        List of keyword strings.
    """
    if not os.path.exists(keywords_file):
        console.print(f"[bold red]Error: {keywords_file} not found![/bold red]")
        return []

    with open(keywords_file, "r") as f:
        keywords = [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]

    return keywords


def load_exclude_keywords(exclude_file=EXCLUDE_KEYWORDS_FILE):
    """Load exclusion keywords from exclude_keywords.txt.

    Returns:
        List of lowercase keyword strings to exclude.
    """
    if not os.path.exists(exclude_file):
        return []

    with open(exclude_file, "r") as f:
        return [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]


def score_playlist(playlist, keywords):
    """Score a playlist by how many keywords appear in its title/description.

    Args:
        playlist: Playlist dict from SoundCloud API.
        keywords: List of keyword strings.

    Returns:
        Integer count of keyword matches.
    """
    title = (playlist.get("title") or "").lower()
    description = (playlist.get("description") or "").lower()
    text = f"{title} {description}"

    score = 0
    for keyword in keywords:
        if keyword in text:
            score += 1
    return score


def search_and_rank_playlists(spider, keywords, playlists_per_keyword=20):
    """Search SoundCloud for playlists matching keywords, ranked by match count.

    Args:
        spider: SoundCloudSpider instance.
        keywords: List of keyword strings.
        playlists_per_keyword: Max playlists to fetch per keyword search.

    Returns:
        List of (playlist_dict, score) tuples, sorted by score descending.
    """
    console.print(f"\n[bold cyan]🔍 Step 1:[/bold cyan] Searching for playlists with "
                  f"[bold]{len(keywords)}[/bold] keywords...")

    seen_ids = set()
    scored_playlists = []

    exclude_keywords = load_exclude_keywords()
    skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="cyan"),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Searching playlists...", total=len(keywords))

        for keyword in keywords:
            results = spider.search_playlists(keyword, limit=playlists_per_keyword)
            time.sleep(0.5)

            for playlist in results:
                pid = playlist.get("id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)

                    # Check exclusion list
                    pl_title = (playlist.get("title") or "").lower()
                    if any(ex in pl_title for ex in exclude_keywords):
                        skipped += 1
                        continue

                    s = score_playlist(playlist, keywords)
                    if s > 0:
                        scored_playlists.append((playlist, s))

            progress.advance(task)

    if skipped:
        console.print(f"   [dim]Excluded {skipped} playlists by keyword filter.[/dim]")

    # Sort by likes_count descending (primary), then keyword score descending (secondary)
    scored_playlists.sort(
        key=lambda x: (x[0].get("likes_count", 0), x[1]),
        reverse=True,
    )

    console.print(f"   Found [bold green]{len(scored_playlists)}[/bold green] unique playlists "
                  f"matching keywords.\n")

    return scored_playlists


# ============================================================
# Step 2: Audio Probe
# ============================================================

def audio_probe(spider, candidate_url, probe_count=3, temp_dir="data/discovery_tmp"):
    """Download and analyze a few tracks from a candidate artist.

    Downloads probe_count top tracks as 30-second snippets in parallel,
    runs them through LAION-CLAP, then deletes the MP3s immediately.

    Args:
        spider: SoundCloudSpider instance.
        candidate_url: SoundCloud artist profile URL.
        probe_count: Number of tracks to probe.
        temp_dir: Temporary directory for probe downloads.

    Returns:
        Tuple of (probe_vectors: list of 512-d lists, probe_urls: list of track URLs).
        Returns ([], []) if probing fails.
    """
    from deepkt.downloader import download_single
    from deepkt.analyzer import analyze_snippet

    os.makedirs(temp_dir, exist_ok=True)

    # Resolve the candidate
    user_data = spider.resolve_user(candidate_url)
    if not user_data:
        return [], []

    uid = user_data.get("id")
    permalink = user_data.get("permalink")

    # Get their top tracks via API
    try:
        import requests
        url = f'https://api-v2.soundcloud.com/users/{uid}/toptracks?client_id={spider.client_id}&limit={probe_count}&linked_partitioning=1'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code != 200:
            return [], []

        tracks = res.json().get("collection", [])
    except Exception:
        return [], []

    # Filter valid probe candidates
    probe_candidates = []
    for track in tracks[:probe_count]:
        track_url = track.get("permalink_url")
        if not track_url:
            continue
        if "/sets/" in track_url:
            continue
        duration_ms = track.get("duration", 0)
        if duration_ms and duration_ms > 600000:
            continue
        probe_candidates.append(track_url)

    if not probe_candidates:
        return [], []

    import threading
    analysis_lock = threading.Lock()

    # Download all probes in parallel, but force analysis to be serial
    def _download_and_analyze(track_url):
        """Download a single track and return (embedding, url) or None."""
        try:
            dl_result = download_single(track_url, output_dir=temp_dir)
            file_path = dl_result["file_path"]

            with analysis_lock:
                features = analyze_snippet(file_path)
            
            embedding = features.get("clap_embedding", [])

            # Clean up immediately
            if os.path.exists(file_path):
                os.remove(file_path)

            if embedding and any(v != 0.0 for v in embedding):
                return (embedding, track_url)
        except Exception as e:
            console.print(f"      [dim red]Probe failed for {track_url}: {e}[/dim red]")
        return None

    probe_vectors = []
    probe_urls = []

    # Use threads for parallel I/O (downloads), serial for CLAP (CPU)
    with ThreadPoolExecutor(max_workers=min(len(probe_candidates), 3)) as pool:
        futures = {pool.submit(_download_and_analyze, url): url for url in probe_candidates}
        for future in as_completed(futures):
            result = future.result()
            if result:
                probe_vectors.append(result[0])
                probe_urls.append(result[1])

    return probe_vectors, probe_urls


# ============================================================
# Step 3: Similarity Gate
# ============================================================

def compute_library_centroid(conn):
    """Pre-compute the normalized centroid of all indexed tracks.

    Args:
        conn: SQLite connection.

    Returns:
        Normalized centroid as np.ndarray (512,), or None if no tracks.
    """
    all_features = trackdb.get_all_features(conn)
    if not all_features:
        return None

    from deepkt.analyzer import build_search_vector
    corpus_vectors = []
    for track in all_features:
        vec = build_search_vector(track["feature_data"])
        if vec and len(vec) == 512:
            corpus_vectors.append(vec)

    if not corpus_vectors:
        return None

    corpus_matrix = np.array(corpus_vectors, dtype=np.float32)
    centroid = corpus_matrix.mean(axis=0)
    centroid_norm = np.linalg.norm(centroid)
    if centroid_norm == 0:
        return None, 0
    return centroid / centroid_norm, len(corpus_vectors)


def compute_seed_centroid(conn, seed_urls):
    """Pre-compute the normalized centroid of tracks from seed artists only,
    or load the user-refined solid centroid if it exists.

    Args:
        conn: SQLite connection.
        seed_urls: Set or list of seed artist profile URLs.

    Returns:
        Tuple of (Normalized centroid as np.ndarray (512,), track_count: int),
        or (None, 0) if no seed tracks found in the database.
    """
    import os
    import numpy as np
    
    refined_path = 'data/refined_seed_centroid.npy'
    if os.path.exists(refined_path):
        centroid = np.load(refined_path)
        # Whiten and re-normalize to match the whitened embedding space
        from deepkt.whitening import apply as whiten
        centroid = np.array(whiten(centroid.tolist()), dtype=np.float32)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        return centroid, 380

    if not seed_urls:
        return None, 0

    # Extract clean slugs from seed URLs for matching
    seed_slugs = set()
    for url in seed_urls:
        slug = url.replace('https://soundcloud.com/', '').strip('/').lower()
        seed_slugs.add(slug)

    all_features = trackdb.get_all_features(conn)
    if not all_features:
        return None, 0

    all_metadata = trackdb.get_all_metadata(conn)
    # create a lookup mapping track_id -> artist_slug
    artist_slug_by_id = {}
    for meta in all_metadata:
        url = meta.get("url", "")
        parts = url.replace("https://soundcloud.com/", "").split("/")
        if parts:
            artist_slug_by_id[meta["track_id"]] = parts[0].lower()

    from deepkt.analyzer import build_search_vector
    corpus_vectors = []
    
    for track in all_features:
        track_id = track["track_id"]
        slug = artist_slug_by_id.get(track_id)
        
        if slug in seed_slugs:
            vec = build_search_vector(track["feature_data"])
            if vec and len(vec) == 512:
                corpus_vectors.append(vec)

    if not corpus_vectors:
        return None, 0

    corpus_matrix = np.array(corpus_vectors, dtype=np.float32)
    centroid = corpus_matrix.mean(axis=0)
    centroid_norm = np.linalg.norm(centroid)
    
    if centroid_norm == 0:
        return None, 0
        
    return centroid / centroid_norm, len(corpus_vectors)


def similarity_gate(probe_vectors, probe_urls, candidate_url, conn, threshold=0.85, centroid=None):
    """Compare probe tracks against the library's global centroid.

    Uses a pre-computed centroid if provided, otherwise computes it
    (slower — use compute_library_centroid() at startup for best perf).

    Args:
        probe_vectors: List of 512-d float lists from audio_probe().
        probe_urls: List of track URLs corresponding to probe_vectors.
        candidate_url: The candidate artist's profile URL.
        conn: SQLite connection.
        threshold: Minimum average similarity to pass.
        centroid: Pre-computed normalized centroid vector (optional).

    Returns:
        Tuple of (avg_similarity: float, passed: bool).
    """
    if not probe_vectors:
        return 0.0, False

    # Use pre-computed centroid or compute on the fly
    centroid_normed = centroid
    if centroid_normed is None:
        centroid_normed = compute_library_centroid(conn)
    if centroid_normed is None:
        console.print("      [bold yellow]Warning: No indexed tracks in corpus. Cannot gate.[/bold yellow]")
        return 0.0, False

    # Probe vectors come from analyze_snippet (raw); whiten to match the centroid space
    from deepkt.whitening import apply as whiten
    probe_vectors = [whiten(v) for v in probe_vectors]

    similarities = []

    for probe_vec, probe_url in zip(probe_vectors, probe_urls):
        probe_arr = np.array(probe_vec, dtype=np.float32)
        probe_norm = np.linalg.norm(probe_arr)
        if probe_norm == 0:
            continue
        probe_normed = probe_arr / probe_norm

        # Cosine similarity against global library centroid
        sim = float(probe_normed @ centroid_normed)
        similarities.append(sim)

        # Log this probe result (no specific corpus match, log with None)
        trackdb.log_probe(conn, candidate_url, probe_url, sim, None)

    if not similarities:
        return 0.0, False

    avg_sim = float(np.mean(similarities))
    passed = avg_sim >= threshold

    return avg_sim, passed


# ============================================================
# Step 4: Main Discovery Loop
# ============================================================

def run_discovery(target_tracks=5000, threshold=0.95, probe_count=3,
                  playlists_per_keyword=20):
    """Run the full playlist-based audio-gated discovery pipeline.

    1. Load keywords from hashtags.txt
    2. Search for playlists, rank by keyword matches
    3. For each playlist, iterate tracks
    4. For each new artist: audio probe → similarity gate
    5. Approved: scrape 130 tracks → crawled_links.txt
    6. Stop when target tracks reached

    Args:
        target_tracks: Stop after this many tracks added to crawled_links.txt.
        threshold: Min avg cosine similarity to pass the gate.
        probe_count: Tracks to analyze per candidate.
        playlists_per_keyword: Max playlists per keyword search.

    Returns:
        Dict with discovery results.
    """
    console.print(f"\n[bold magenta]🧬 Playlist-Based Artist Discovery[/bold magenta]")
    console.print(f"   Target: {target_tracks} tracks  |  Threshold: {threshold:.0%}  |  Probes: {probe_count}\n")

    # Initialize
    spider = SoundCloudSpider()
    if not spider.client_id and not spider.extract_client_id():
        console.print("[bold red]Discovery aborted: Could not get SoundCloud Client ID.[/bold red]")
        return {"approved": 0, "rejected": 0, "tracks_added": 0}

    conn = trackdb.get_db()

    results = {
        "approved": 0,
        "rejected": 0,
        "tracks_added": 0,
        "probed": 0,
        "playlists_searched": 0,
    }

    # Step 1: Load keywords and search for playlists
    keywords = load_keywords()
    if not keywords:
        console.print("[bold red]No keywords found in hashtags.txt. Add genre keywords and try again.[/bold red]")
        conn.close()
        return results

    scored_playlists = search_and_rank_playlists(spider, keywords, playlists_per_keyword)

    if not scored_playlists:
        console.print("[yellow]No playlists found matching keywords.[/yellow]")
        conn.close()
        return results

    # Collect existing seeds to skip
    seed_urls = set(spider.get_seed_artists())

    # Build set of artist slugs already in the database
    all_metadata = trackdb.get_all_metadata(conn)
    indexed_artist_slugs = set()
    for t in all_metadata:
        url = t.get("url", "")
        # Extract artist slug from soundcloud.com/<artist>/<track>
        parts = url.replace("https://soundcloud.com/", "").split("/")
        if parts:
            indexed_artist_slugs.add(parts[0].lower())

    console.print(f"   [dim]Skipping {len(indexed_artist_slugs)} artists already in library.[/dim]")

    # Pre-compute reference centroid: prefer seed artists, fallback to full library
    console.print("   [dim]Pre-computing reference centroid...[/dim]")

    # Try seed centroid first
    library_centroid, centroid_count = compute_seed_centroid(conn, seed_urls)
    centroid_source = "seed artists"

    if library_centroid is None:
        # Fallback to full library centroid
        library_centroid, centroid_count = compute_library_centroid(conn)
        centroid_source = "full library"

    if library_centroid is None:
        console.print("[bold red]No indexed tracks found — cannot run similarity gate.[/bold red]")
        conn.close()
        return results
    console.print(f"   [dim]Centroid ready ({centroid_source}, {centroid_count} tracks).[/dim]")

    # Track which artists we've already processed (in-memory + DB)
    processed_artists = {}  # url -> "APPROVED" or "REJECTED"
    for c in trackdb.get_candidates(conn):
        if c["status"] in ("APPROVED", "REJECTED", "PROMOTED"):
            processed_artists[c["artist_url"]] = c["status"]

    # Steps 2-4: Iterate playlists
    console.print(f"[bold cyan]🎵 Step 2-4:[/bold cyan] Processing [bold]{len(scored_playlists)}[/bold] "
                  f"playlists (threshold: {threshold:.0%})...\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="magenta"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        playlist_task = progress.add_task(
            "🎵 Processing playlists...", total=len(scored_playlists)
        )

        for playlist, keyword_score in scored_playlists:
            if results["tracks_added"] >= target_tracks:
                console.print(f"\n[bold green]✅ Reached target of {target_tracks} tracks![/bold green]")
                break

            pl_title = playlist.get("title", "?")
            pl_id = playlist.get("id")
            pl_track_count = playlist.get("track_count", 0)
            pl_likes = playlist.get("likes_count", 0)

            console.print(f"\n   [bold yellow]📋 Playlist:[/bold yellow] {pl_title} "
                          f"({pl_track_count} tracks, {pl_likes} likes, keywords: {keyword_score})")

            # Fetch full track list
            tracks = spider.get_playlist_tracks(pl_id)
            time.sleep(0.5)

            if not tracks:
                console.print(f"      [dim]Empty or inaccessible playlist.[/dim]")
                progress.advance(playlist_task)
                continue

            console.print(f"      [dim]Loaded {len(tracks)}/{pl_track_count} tracks[/dim]")
            results["playlists_searched"] += 1

            consecutive_rejections = 0
            MAX_CONSECUTIVE_REJECTIONS = 10

            for track in tracks:
                if results["tracks_added"] >= target_tracks:
                    break

                # Early exit: too many consecutive rejections in this playlist
                if consecutive_rejections >= MAX_CONSECUTIVE_REJECTIONS:
                    console.print(f"      [yellow]⏩ Skipping rest of playlist ({MAX_CONSECUTIVE_REJECTIONS} consecutive rejections)[/yellow]")
                    break

                track_url = track.get("permalink_url")
                if not track_url or "/sets/" in track_url:
                    continue

                # Skip very long tracks
                duration_ms = track.get("duration", 0)
                if duration_ms and duration_ms > 600000:
                    continue

                # Get the artist info from this track
                track_user = track.get("user", {})
                artist_url = track_user.get("permalink_url")
                permalink = track_user.get("permalink")
                followers = track_user.get("followers_count", 0)

                if not artist_url or not permalink:
                    continue

                # Skip seed artists
                if artist_url in seed_urls:
                    console.print(f"      [dim]⏭ {permalink}[/dim] — seed artist, skipping")
                    continue

                # Skip artists already in the library
                if permalink.lower() in indexed_artist_slugs:
                    console.print(f"      [dim green]⏭ {permalink}[/dim green] — already in library, skipping")
                    continue

                # Check if already processed
                if artist_url in processed_artists:
                    status = processed_artists[artist_url]
                    if status in ("APPROVED", "PROMOTED"):
                        console.print(f"      [dim green]⏭ {permalink}[/dim green] — already approved, skipping")
                    else:
                        console.print(f"      [dim red]⏭ {permalink}[/dim red] — already rejected, skipping")
                    continue

                # New artist — register and probe
                trackdb.register_candidate(conn, artist_url, permalink, followers)
                trackdb.update_candidate_status(conn, artist_url, "PROBING")

                # Audio probe
                probe_vectors, probe_urls = audio_probe(spider, artist_url, probe_count)
                results["probed"] += 1

                if not probe_vectors:
                    trackdb.update_candidate_status(conn, artist_url, "REJECTED", avg_similarity=0.0)
                    processed_artists[artist_url] = "REJECTED"
                    results["rejected"] += 1
                    consecutive_rejections += 1
                    console.print(f"      [dim red]✗ {permalink}[/dim red] — probe failed")
                else:
                    # Similarity gate
                    avg_sim, passed = similarity_gate(
                        probe_vectors, probe_urls, artist_url, conn, threshold,
                        centroid=library_centroid
                    )

                    if passed:
                        trackdb.update_candidate_status(conn, artist_url, "APPROVED", avg_similarity=avg_sim)
                        processed_artists[artist_url] = "APPROVED"
                        results["approved"] += 1

                        console.print(f"      [bold green]✓ {permalink}[/bold green] — "
                                      f"{avg_sim:.1%} [green]APPROVED[/green]")
                        consecutive_rejections = 0  # Reset on approval

                        # Scrape full 130 tracks
                        user_data = spider.resolve_user(artist_url)
                        if user_data:
                            uid = user_data.get("id")
                            plink = user_data.get("permalink")
                            console.print(f"        [cyan]Scraping 130 tracks...[/cyan]")
                            track_urls = spider.scrape_tracks(uid, plink, 130)

                            if track_urls:
                                spider.append_links(track_urls)
                                results["tracks_added"] += len(track_urls)
                                console.print(f"        [green]Added {len(track_urls)} tracks[/green] "
                                              f"(total: {results['tracks_added']}/{target_tracks})")

                                trackdb.update_candidate_status(
                                    conn, artist_url, "PROMOTED", avg_similarity=avg_sim
                                )
                                processed_artists[artist_url] = "PROMOTED"
                    else:
                        trackdb.update_candidate_status(conn, artist_url, "REJECTED", avg_similarity=avg_sim)
                        processed_artists[artist_url] = "REJECTED"
                        results["rejected"] += 1
                        consecutive_rejections += 1
                        console.print(f"      [dim red]✗ {permalink}[/dim red] — "
                                      f"{avg_sim:.1%} [red]REJECTED[/red]")

                # Rate limit between probes
                time.sleep(1.0)

            progress.advance(playlist_task)

    # Summary
    console.print(f"\n[bold magenta]{'═' * 50}[/bold magenta]")
    console.print(f"[bold magenta]🧬 Discovery Complete[/bold magenta]")
    console.print(f"   Playlists searched:  [bold]{results['playlists_searched']}[/bold]")
    console.print(f"   Artists probed:      [bold]{results['probed']}[/bold]")
    console.print(f"   Approved:            [bold green]{results['approved']}[/bold green]")
    console.print(f"   Rejected:            [bold red]{results['rejected']}[/bold red]")
    console.print(f"   Tracks added:        [bold cyan]{results['tracks_added']}[/bold cyan]")
    console.print(f"\n   Results saved to: [bold]{CRAWLED_LINKS_FILE}[/bold]")
    console.print(f"   Run [bold]'cli.py ingest'[/bold] then [bold]'cli.py pipeline'[/bold] to process.\n")

    # Show discovery stats
    stats = trackdb.get_discovery_stats(conn)
    if stats.get("total", 0) > 0:
        console.print(f"   All-time discovery stats:")
        for status, count in sorted(stats.items()):
            if status != "total":
                console.print(f"     {status}: {count}")

    conn.close()
    return results
