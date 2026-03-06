"""
Deepkt CLI — Command-line interface for pipeline operations.

Usage:
    python cli.py download              Download snippets from links.txt
    python cli.py analyze               Analyze MP3s → store ALL features in SQLite
    python cli.py reindex               Rebuild ChromaDB search index from stored features
    python cli.py pipeline              Download + analyze in parallel
    python cli.py pipeline-status       Show pipeline progress and errors
    python cli.py search <query>        Search indexed tracks by artist/title
    python cli.py similar <track-id>    Find similar tracks to a given ID
    python cli.py stats                 Show library statistics
    python cli.py features              Show all features and which are enabled
    python cli.py inspect <track-id>    Show all stored features for a track
    python cli.py crawl                 Crawl SoundCloud for new similar tracks
    python cli.py ingest                Move crawled links into the main pipeline
"""

import argparse
import sys


# NOTE: All deepkt imports are lazy (inside functions) to avoid loading
# chromadb on every CLI invocation. Only commands that need chromadb
# (reindex, similar, stats) will import it.


def cmd_download(args):
    """Download audio snippets from a links file."""
    from deepkt.downloader import download_from_file
    print(f"📥 Downloading snippets from {args.file}...")
    download_from_file(links_file=args.file, output_dir=args.output)
    print("✅ Done!")


def cmd_analyze(args):
    """Analyze all MP3 snippets and store ALL features in SQLite."""
    from deepkt.indexer import analyze_and_store
    print("🧬 Analyzing audio snippets (extracting ALL features)...")
    new_count = analyze_and_store(data_dir=args.data_dir)
    if new_count > 0:
        print(f"\n💡 Run 'cli.py reindex' to rebuild the search index.")


def cmd_reindex(args):
    """Rebuild the ChromaDB search index from stored features."""
    from deepkt.indexer import rebuild_search_index
    print("🔄 Rebuilding search index from stored features...\n")
    rebuild_search_index()
    print("\n✅ Search index is up to date!")


def cmd_search(args):
    """Search for tracks by artist or title."""
    from deepkt import db as trackdb
    conn = trackdb.get_db()
    matches = trackdb.search_tracks(conn, args.query)
    conn.close()

    if not matches:
        print(f"No tracks found matching '{args.query}'")
        return

    print(f"Found {len(matches)} track(s) matching '{args.query}':\n")
    for track in matches:
        status_icon = "✅" if track["status"] == "INDEXED" else "⏳"
        print(f"  {status_icon} {track['artist']} - {track['title']}")
        print(f"     ID: {track['id']}  Status: {track['status']}")
        print("\n")


def cmd_lab_undo(args):
    """Wipe all training pairs generated for the most recently evaluated Anchor."""
    from rich.console import Console
    from deepkt import db as trackdb
    
    console = Console()
    conn = trackdb.get_db()
    
    recent_anchor = conn.execute('''
        SELECT anchor_id FROM training_pairs ORDER BY id DESC LIMIT 1
    ''').fetchone()
    
    if not recent_anchor:
        console.print("[yellow]The Training Lab database is already empty.[/yellow]")
        conn.close()
        return
        
    anchor_id = recent_anchor[0]
    track_info = conn.execute("SELECT artist, title FROM tracks WHERE track_id = ?", (anchor_id,)).fetchone()
    anchor_name = f"{track_info[0]} - {track_info[1]}" if track_info else anchor_id
    
    count = conn.execute("SELECT COUNT(*) FROM training_pairs WHERE anchor_id = ?", (anchor_id,)).fetchone()[0]
    conn.execute("DELETE FROM training_pairs WHERE anchor_id = ?", (anchor_id,))
    conn.commit()
    conn.close()
    
    console.print(f"[bold red]Deleted {count} triplets[/bold red] associated with Anchor: [cyan]{anchor_name}[/cyan]")


def cmd_similar(args):
    """Find tracks similar to a given track ID."""
    from deepkt import db as trackdb
    from deepkt.indexer import query_similar
    from deepkt.analyzer import build_search_vector
    from deepkt.config import get_enabled_features
    conn = trackdb.get_db()
    features = trackdb.get_features(conn, args.track_id)
    track = trackdb.get_track(conn, args.track_id)
    conn.close()

    if not features or not track:
        print(f"❌ Track '{args.track_id}' not found in database.")
        return

    # Build search vector from stored features
    search_vector = build_search_vector(features)

    print(f"🔍 Finding tracks similar to: {track['artist']} - {track['title']}")
    print(f"   Search vector: {len(search_vector)} dims ({', '.join(get_enabled_features())})\n")

    results = query_similar(search_vector, n_results=args.top, exclude_id=args.track_id)

    if not results:
        print("No similar tracks found.")
        return

    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['artist']} - {r['title']}  ({r['match_pct']}% match)")


def cmd_stats(args):
    """Show library statistics."""
    from deepkt import db as trackdb
    from deepkt.indexer import get_collection
    from deepkt.config import get_search_dimensions, get_feature_version, get_enabled_features
    conn = trackdb.get_db()
    stats = trackdb.get_stats(conn)
    conn.close()

    collection = get_collection()
    search_dims = get_search_dimensions()
    version = get_feature_version()
    enabled = get_enabled_features()

    print(f"📊 Deepkt Library Stats")
    print(f"   SQLite tracks: {stats.get('total', 0)}")
    for status, count in sorted(stats.items()):
        if status != "total":
            print(f"     {status}: {count}")
    print(f"   ChromaDB indexed: {collection.count()}")
    print(f"   Search dimensions: {search_dims} ({len(enabled)} features enabled)")
    print(f"   Feature version: {version}")
    print(f"   Total stored dims: 43")


def cmd_features(args):
    """Show all features and their status."""
    from deepkt.config import load_feature_config, get_enabled_features
    config = load_feature_config()
    enabled = get_enabled_features()

    print(f"🧬 Feature Configuration (version: {config.get('version', '?')})\n")
    print(f"   {'Feature':<22} {'Dims':>4}  {'Search':>7}  Description")
    print(f"   {'─'*22} {'─'*4}  {'─'*7}  {'─'*40}")

    total_stored = 0
    total_search = 0
    for name, cfg in config.get("features", {}).items():
        dims = cfg.get("dimensions", "?")
        is_enabled = "✅" if name in enabled else "  "
        desc = cfg.get("description", "")
        print(f"   {name:<22} {dims:>4}  {is_enabled:>7}  {desc}")
        total_stored += int(dims) if isinstance(dims, int) else 0
        if name in enabled:
            total_search += int(dims) if isinstance(dims, int) else 0

    print(f"\n   Total: {total_stored} stored, {total_search} in search index")


def cmd_lab_status(args):
    """Show statistics for the AI Training Lab triplets."""
    from rich.console import Console
    from rich.table import Table
    from deepkt import db as trackdb
    
    console = Console()
    conn = trackdb.get_db()
    
    stats_req = conn.execute('''
        SELECT 
            COUNT(*) as total_pairs,
            SUM(CASE WHEN label = 1.0 THEN 1 ELSE 0 END) as p_match,
            SUM(CASE WHEN label = 0.5 THEN 1 ELSE 0 END) as m_match,
            SUM(CASE WHEN label = -0.5 THEN 1 ELSE 0 END) as m_neg,
            SUM(CASE WHEN label = -1.0 THEN 1 ELSE 0 END) as c_neg,
            COUNT(DISTINCT anchor_id) as anchors
        FROM training_pairs
    ''').fetchone()
    
    total = stats_req[0]
    p_match = stats_req[1] or 0
    m_match = stats_req[2] or 0
    m_neg = stats_req[3] or 0
    c_neg = stats_req[4] or 0
    anchors = stats_req[5] or 0
    
    # Combined for ratio
    pos_total = p_match + m_match
    neg_total = m_neg + c_neg
    ratio = f"1:{neg_total/pos_total:.1f}" if pos_total > 0 else "N/A"
    
    console.print(f"\n[bold magenta]🏋️ AI Training Lab Status[/bold magenta]")
    console.print(f"Total Triplets: [bold white]{total}[/bold white]")
    console.print(f"Unique Anchors: [bold white]{anchors}[/bold white]")
    console.print(f"Ratio (+/-):    [bold cyan]{ratio}[/bold cyan]\n")
    console.print(f"🟢 Perfect Matches (1.0):   [bold green]{p_match}[/bold green]")
    console.print(f"🟡 Medium Matches (0.5):    [green]{m_match}[/green]")
    console.print(f"🟠 Medium Negatives (-0.5): [yellow]{m_neg}[/yellow]")
    console.print(f"🔴 Complete Negatives (-1.0): [bold red]{c_neg}[/bold red]\n")

    if total > 0:
        table = Table(title="Recent 20 Training Pairs", show_header=True, header_style="bold magenta")
        table.add_column("Anchor Artist", overflow="fold")
        table.add_column("Anchor Title", overflow="fold")
        table.add_column("Candidate Artist", overflow="fold")
        table.add_column("Candidate Title", overflow="fold")
        table.add_column("Label", justify="center")

        recent = conn.execute('''
            SELECT 
                t1.artist as a_artist, t1.title as a_title,
                t2.artist as c_artist, t2.title as c_title,
                tp.label
            FROM training_pairs tp
            JOIN tracks t1 ON tp.anchor_id = t1.id
            JOIN tracks t2 ON tp.candidate_id = t2.id
            ORDER BY tp.id DESC
            LIMIT 20
        ''').fetchall()

        for row in reversed(recent):
            val = float(row[4])
            if val == 1.0:
                lbl = "[bold green]1.0[/bold green]"
            elif val == 0.5:
                lbl = "[green]0.5[/green]"
            elif val == -0.5:
                lbl = "[yellow]-0.5[/yellow]"
            else:
                lbl = "[bold red]-1.0[/bold red]"
                
            table.add_row(
                row[0], row[1],
                row[2], row[3],
                lbl
            )
            
        console.print(table)
    
    conn.close()

def cmd_inspect(args):
    """Show all stored features for a specific track."""
    from deepkt import db as trackdb
    from deepkt.config import get_enabled_features
    conn = trackdb.get_db()
    track = trackdb.get_track(conn, args.track_id)
    features = trackdb.get_features(conn, args.track_id)
    conn.close()

    if not track:
        print(f"❌ Track '{args.track_id}' not found.")
        return

    print(f"🔍 Track: {track['artist']} - {track['title']}")
    print(f"   ID: {track['id']}")
    print(f"   Status: {track['status']}")
    print(f"   Source: {track.get('source', 'unknown')}")
    print()

    if not features:
        print("   No features stored yet.")
        return

    enabled = get_enabled_features()
    print(f"   {'Feature':<22} {'Dims':>4}  {'In Search':>9}  Values")
    print(f"   {'─'*22} {'─'*4}  {'─'*9}  {'─'*40}")

    for name in sorted(features.keys()):
        values = features[name]
        search_flag = "✅" if name in enabled else "  "
        # Show first few values, truncate if many
        if len(values) <= 3:
            val_str = ", ".join(f"{v:.4f}" for v in values)
        else:
            val_str = ", ".join(f"{v:.4f}" for v in values[:3]) + f", ... ({len(values)} total)"
        print(f"   {name:<22} {len(values):>4}  {search_flag:>9}  [{val_str}]")

def cmd_lab_undo(args):
    """Wipe all training pairs generated for the most recently evaluated Anchor."""
    from rich.console import Console
    from deepkt import db as trackdb
    
    console = Console()
    conn = trackdb.get_db()
    
    recent_anchor = conn.execute('''
        SELECT anchor_id FROM training_pairs ORDER BY id DESC LIMIT 1
    ''').fetchone()
    
    if not recent_anchor:
        console.print("[yellow]The Training Lab database is already empty.[/yellow]")
        conn.close()
        return
        
    anchor_id = recent_anchor[0]
    track_info = conn.execute("SELECT artist, title FROM tracks WHERE id = ?", (anchor_id,)).fetchone()
    anchor_name = f"{track_info[0]} - {track_info[1]}" if track_info else anchor_id
    
    count = conn.execute("SELECT COUNT(*) FROM training_pairs WHERE anchor_id = ?", (anchor_id,)).fetchone()[0]
    conn.execute("DELETE FROM training_pairs WHERE anchor_id = ?", (anchor_id,))
    conn.commit()
    conn.close()
    
    console.print(f"[bold red]Deleted {count} triplets[/bold red] associated with Anchor: [cyan]{anchor_name}[/cyan]")


def cmd_migrate_labels(args):
    """One-time migration script: Converts binary (1/0) labels to float (1.0/-1.0)."""
    from rich.console import Console
    from deepkt import db as trackdb
    console = Console()
    conn = trackdb.get_db()
    
    # Update Positives
    res_pos = conn.execute("UPDATE training_pairs SET label = 1.0 WHERE label = 1")
    # Update Negatives
    res_neg = conn.execute("UPDATE training_pairs SET label = -1.0 WHERE label = 0")
    conn.commit()
    
    console.print(f"[bold green]Successfully migrated training pairs to 4-tier floats![/bold green]")
    console.print(f"Positives Converted (1 -> 1.0): {res_pos.rowcount}")
    console.print(f"Negatives Converted (0 -> -1.0): {res_neg.rowcount}")
    conn.close()


# obsolete optimize command removed


def cmd_pipeline(args):
    """Run the full download → analyze → store pipeline in parallel."""
    from rich.console import Console
    from deepkt.pipeline import run_pipeline

    console = Console()
    console.print("\n[bold magenta]🚀 Deepkt Pipeline[/bold magenta]")
    console.print(f"   Source: {args.file}")
    console.print(f"   Resume: {args.resume}\n")

    results = run_pipeline(
        links_file=args.file,
        resume=args.resume,
    )

    console.print("\n[bold green]Pipeline complete![/bold green]")
    console.print(f"  ✅ Downloaded: {results['downloaded']}")
    console.print(f"  🧬 Analyzed:   {results['analyzed']}")
    console.print(f"  💾 Stored:     {results['stored']}")
    console.print(f"  ⏭️  Skipped:    {results['skipped']}")
    console.print(f"  ❌ Failed:     {results['failed']}")

    if results.get('errors'):
        console.print("\n[bold red]Errors:[/bold red]")
        for err in results['errors'][:10]:
            console.print(f"  • {err}")

    console.print("\n💡 Run [bold]cli.py reindex[/bold] to rebuild the search index.\n")


def cmd_pipeline_status(args):
    """Show pipeline status and recent errors."""
    from deepkt.pipeline import get_pipeline_status

    status = get_pipeline_status()
    stats = status['stats']

    print(f"📊 Pipeline Status")
    print(f"   Total tracks: {stats.get('total', 0)}")
    for s, count in sorted(stats.items()):
        if s != 'total':
            print(f"     {s}: {count}")

    if status['in_progress']:
        print(f"\n   ⏳ In progress: {len(status['in_progress'])}")
        for tid in status['in_progress'][:5]:
            print(f"     - {tid}")

    if status['failed_recent']:
        print(f"\n   ❌ Recent failures:")
        for f in status['failed_recent']:
            print(f"     - {f['id']}: {f['error']}")


def cmd_crawl(args):
    """Crawl SoundCloud for new artists based on similarity to indexed artists."""
    from deepkt.crawler import SoundCloudSpider
    spider = SoundCloudSpider()
    spider.crawl()


def cmd_ingest(args):
    """Move URLs from crawled_links.txt to links.txt for processing."""
    import os
    if not os.path.exists("crawled_links.txt"):
        print("❌ No crawled_links.txt found. Run 'cli.py crawl' first.")
        return
        
    with open("crawled_links.txt", "r") as f:
        new_links = [line.strip() for line in f if line.strip()]
        
    if not new_links:
        print("❌ crawled_links.txt is empty.")
        return
        
    # Read existing links to prevent duplicates in links.txt
    existing = set()
    if os.path.exists("links.txt"):
        with open("links.txt", "r") as f:
            for line in f:
                if line.strip():
                    existing.add(line.strip())
                    
    added = 0
    with open("links.txt", "a") as f:
        for link in new_links:
            if link not in existing:
                f.write(f"{link}\n")
                existing.add(link)
                added += 1
                
    # Clear crawled_links.txt
    open("crawled_links.txt", "w").close()
    
    print(f"✅ Ingested {added} new links into links.txt.")
    print("💡 Run 'cli.py pipeline' to begin downloading and analyzing.")


def cmd_discover(args):
    """Run playlist-based audio-gated artist discovery."""
    from deepkt.discovery import run_discovery
    from deepkt.config import load_pipeline_config

    config = load_pipeline_config()
    disc_config = config.get("discovery", {})

    target = args.target or disc_config.get("target_tracks", 5000)
    threshold = args.threshold or disc_config.get("similarity_threshold", 0.95)
    probe_count = args.probe_count or disc_config.get("probe_count", 3)
    playlists_per_keyword = disc_config.get("playlists_per_keyword", 20)

    run_discovery(
        target_tracks=target,
        threshold=threshold,
        probe_count=probe_count,
        playlists_per_keyword=playlists_per_keyword,
    )


def cmd_discover_log(args):
    """Show discovery candidate history for threshold tuning."""
    from rich.console import Console
    from rich.table import Table
    from deepkt import db as trackdb

    console = Console()
    conn = trackdb.get_db()

    # Get candidates, optionally filtered
    candidates = trackdb.get_candidates(conn, status=args.status)

    if not candidates:
        status_msg = f" with status '{args.status}'" if args.status else ""
        console.print(f"[yellow]No discovery candidates found{status_msg}.[/yellow]")
        conn.close()
        return

    # Summary stats
    stats = trackdb.get_discovery_stats(conn)
    console.print(f"\n[bold magenta]🧬 Discovery Log[/bold magenta]")
    for status, count in sorted(stats.items()):
        if status != "total":
            color = "green" if status in ("APPROVED", "PROMOTED") else "red" if status == "REJECTED" else "cyan"
            console.print(f"   [{color}]{status}: {count}[/{color}]")
    console.print(f"   Total: {stats.get('total', 0)}\n")

    # Table of candidates
    table = Table(title="Discovery Candidates", show_header=True, header_style="bold magenta")
    table.add_column("Artist", overflow="fold")
    table.add_column("Seen", justify="center")
    table.add_column("Similarity", justify="center")
    table.add_column("Followers", justify="right")
    table.add_column("Status", justify="center")

    for c in candidates[:50]:  # Limit display to 50
        sim_str = f"{c['avg_similarity']:.1%}" if c.get("avg_similarity") else "—"
        status = c["status"]

        if status in ("APPROVED", "PROMOTED"):
            status_str = f"[bold green]{status}[/bold green]"
        elif status == "REJECTED":
            status_str = f"[bold red]{status}[/bold red]"
        else:
            status_str = f"[cyan]{status}[/cyan]"

        followers = f"{c.get('followers', 0):,}" if c.get("followers") else "?"

        table.add_row(
            c.get("permalink", c["artist_url"]),
            str(c.get("times_seen", 1)),
            sim_str,
            followers,
            status_str,
        )

    console.print(table)

    if len(candidates) > 50:
        console.print(f"\n[dim](Showing first 50 of {len(candidates)} candidates)[/dim]")

    conn.close()


def cmd_prune(args):
    import numpy as np
    from rich.console import Console
    from deepkt import db as trackdb
    from deepkt.indexer import build_search_vector
    from deepkt.crawler import SoundCloudSpider
    from deepkt.discovery import compute_seed_centroid

    console = Console()
    threshold = args.threshold
    dry_run = args.dry_run

    console.print(f"[bold cyan]🧹 Pruning database (Threshold: {threshold*100:.1f}%)[/bold cyan]")
    if dry_run:
        console.print("[yellow]DRY RUN ACTIVE: No tracks will be deleted.[/yellow]")

    conn = trackdb.get_db()

    # 1. Build seed centroid
    s = SoundCloudSpider()
    seeds = set(s.get_seed_artists())
    seed_centroid, seed_count = compute_seed_centroid(conn, seeds)

    if seed_centroid is None:
        console.print("[bold red]Cannot prune: Failed to build a seed centroid.[/bold red]")
        sys.exit(1)

    console.print(f"   [dim]Reference centroid built from {seed_count} seed tracks.[/dim]")

    # 2. Score all tracks
    all_features = trackdb.get_all_features(conn)
    all_metadata = trackdb.get_all_metadata(conn)
    meta_by_id = {m['track_id']: m for m in all_metadata}

    to_prune = []
    
    for t in all_features:
        track_id = t['track_id']
        meta = meta_by_id.get(track_id)
        if not meta:
            continue
            
        v = build_search_vector(t['feature_data'])
        if v is None or len(v) != 512:
            continue
            
        vec = np.array(v, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
            sim = float(vec @ seed_centroid)
            
            if sim < threshold:
                to_prune.append((sim, meta))

    # Sort lowest similarity first
    to_prune.sort(key=lambda x: x[0])

    if not to_prune:
        console.print("[green]No tracks fall below the threshold. Your library is clean![/green]")
        conn.close()
        return

    console.print(f"\n[bold yellow]Found {len(to_prune)} tracks below {threshold*100:.1f}% similarity:[/bold yellow]")
    
    show_count = len(to_prune) if args.show_all else 10
    
    for sim, meta in to_prune[:show_count]:
        console.print(f"  [red]{sim*100:.1f}%[/red] {meta['artist']} - {meta['title']}")
    
    if len(to_prune) > show_count:
        console.print(f"  ... and {len(to_prune) - show_count} more (use --all to see them all).")

    # 3. Execute Deletion
    if not dry_run:
        confirm = console.input(f"\n[bold red]Are you sure you want to DELETE {len(to_prune)} tracks? (y/N): [/bold red]")
        if confirm.lower() == 'y':
            deleted = 0
            
            # Open a log file to keep track of pruned tracks
            import os
            from datetime import datetime
            log_path = "pruned_tracks.txt"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- Prune Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Threshold: {threshold*100:.1f}%) ---\n")
                
                for sim, meta in to_prune:
                    track_id = meta['track_id']
                    
                    # Log it
                    f.write(f"{sim*100:.1f}% | {meta['artist']} - {meta['title']} | {meta.get('url', '')}\n")
                    
                    # Delete the heavy feature data and training pairs
                    conn.execute("DELETE FROM track_features WHERE track_id = ?", (track_id,))
                    conn.execute("DELETE FROM training_pairs WHERE anchor_id = ? OR candidate_id = ?", (track_id, track_id))
                    
                    # Instead of deleting from the tracks table, mark as REJECTED
                    # so the crawler doesn't just download it again tomorrow
                    conn.execute("UPDATE tracks SET status = 'REJECTED' WHERE id = ?", (track_id,))
                    
                    deleted += 1
            
            conn.commit()
            console.print(f"[bold green]Successfully pruned {deleted} tracks.[/bold green]")
            console.print(f"[dim]A log of all pruned tracks has been saved to '{log_path}'.[/dim]")
            console.print("[yellow]Note: You should run `python cli.py reindex` to update your ChromaDB search index.[/yellow]")
        else:
            console.print("[dim]Prune cancelled.[/dim]")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        prog="deepkt",
        description="Deepkt — Sonic similarity engine CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- download ---
    dl = subparsers.add_parser("download", help="Download snippets from links file")
    dl.add_argument("--file", default="links.txt", help="Path to links file")
    dl.add_argument("--output", default="data/raw_snippets", help="Output directory")
    dl.set_defaults(func=cmd_download)

    # --- analyze ---
    ana = subparsers.add_parser("analyze", help="Analyze MP3s → store ALL features in SQLite")
    ana.add_argument("--data-dir", default="data/raw_snippets", help="Snippets directory")
    ana.set_defaults(func=cmd_analyze)

    # --- reindex ---
    ri = subparsers.add_parser("reindex", help="Rebuild ChromaDB search index from stored features")
    ri.set_defaults(func=cmd_reindex)

    # --- search ---
    srch = subparsers.add_parser("search", help="Search tracks by artist/title")
    srch.add_argument("query", help="Search query (artist or title)")
    srch.set_defaults(func=cmd_search)

    # --- similar ---
    sim = subparsers.add_parser("similar", help="Find similar tracks")
    sim.add_argument("track_id", help="Track ID (filename) to find matches for")
    sim.add_argument("--top", type=int, default=5, help="Number of results")
    sim.set_defaults(func=cmd_similar)

    # --- stats ---
    st = subparsers.add_parser("stats", help="Show library statistics")
    st.set_defaults(func=cmd_stats)

    # --- features ---
    feat = subparsers.add_parser("features", help="Show all features and their status")
    feat.set_defaults(func=cmd_features)

    # --- inspect ---
    insp = subparsers.add_parser("inspect", help="Show all stored features for a track")
    insp.add_argument("track_id", help="Track ID (filename) to inspect")
    insp.set_defaults(func=cmd_inspect)

    # --- optimize ---
    # Obsolete with Neural Networks

    # --- pipeline ---
    pipe = subparsers.add_parser("pipeline", help="Download + analyze in parallel")
    pipe.add_argument("--file", default="links.txt", help="Path to links file")
    pipe.add_argument("--resume", action="store_true", help="Resume interrupted pipeline")
    pipe.set_defaults(func=cmd_pipeline)

    # --- pipeline-status ---
    ps = subparsers.add_parser("pipeline-status", help="Show pipeline progress and errors")
    ps.set_defaults(func=cmd_pipeline_status)

    # --- crawl ---
    crl = subparsers.add_parser("crawl", help="Crawl SoundCloud for similar artists and tracks")
    crl.set_defaults(func=cmd_crawl)

    # --- ingest ---
    ing = subparsers.add_parser("ingest", help="Move approved URLs from crawled_links.txt into links.txt")
    ing.set_defaults(func=cmd_ingest)

    # --- prune ---
    prune = subparsers.add_parser("prune", help="Delete indexed tracks that fall below a similarity threshold to the seed centroid")
    prune.add_argument("--threshold", type=float, default=0.85, help="Similarity threshold. Tracks below this are deleted. (default: 0.85)")
    prune.add_argument("--dry-run", action="store_true", help="Show which tracks would be deleted without actually deleting them")
    prune.add_argument("-a", "--all", dest="show_all", action="store_true", help="Print the full list of tracks instead of just 10")
    prune.set_defaults(func=cmd_prune)

    # --- discover ---
    disc = subparsers.add_parser("discover", help="Audio-gated artist discovery from seed likes")
    disc.add_argument("--target", type=int, default=None, help="Target number of tracks to discover (default: from config)")
    disc.add_argument("--threshold", type=float, default=None, help="Similarity threshold 0-1 (default: from config)")
    disc.add_argument("--probe-count", type=int, default=None, help="Tracks to probe per candidate (default: from config)")
    disc.set_defaults(func=cmd_discover)

    # --- discover-log ---
    dlog = subparsers.add_parser("discover-log", help="View discovery candidate history")
    dlog.add_argument("--status", default=None, help="Filter by status (PENDING, APPROVED, REJECTED, PROMOTED)")
    dlog.set_defaults(func=cmd_discover_log)

    # --- lab-status ---
    labs = subparsers.add_parser("lab-status", help="Show AI Training Lab dataset statistics")
    labs.set_defaults(func=cmd_lab_status)

    # --- lab-undo ---
    labu = subparsers.add_parser("lab-undo", help="Wipe all triplets for the most recent Anchor")
    labu.set_defaults(func=cmd_lab_undo)
    
    # --- migrate-labels ---
    mig = subparsers.add_parser("migrate-labels", help="Convert binary labels to 4-tier float labels")
    mig.set_defaults(func=cmd_migrate_labels)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
