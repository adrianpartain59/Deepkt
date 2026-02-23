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
    python cli.py optimize              Find optimal feature weights for matching artists
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
        print()


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


def cmd_optimize(args):
    """Run weight optimization to improve artist grouping."""
    try:
        from optimize_weights import optimize
        optimize()
    except ImportError:
        print("❌ Could not import optimize_weights script or its dependencies (like scipy).")


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
    opt = subparsers.add_parser("optimize", help="Find optimal feature weights for grouping artists")
    opt.set_defaults(func=cmd_optimize)

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

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
