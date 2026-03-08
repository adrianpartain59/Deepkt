# Deepkt Quick Reference

## Run the App
```bash
.venv/bin/python3.12 -m streamlit run app.py                 # Streamlit UI
.venv/bin/python3.12 api.py                                  # FastAPI backend (port 8000)
cd web && npm run dev                                        # Next.js frontend (port 3000)
```

## CLI Commands

### Pipeline (download + analyze in parallel)
```bash
.venv/bin/python3.12 cli.py pipeline --file links.txt       # Process all URLs
.venv/bin/python3.12 cli.py pipeline --resume                # Resume after crash
.venv/bin/python3.12 cli.py pipeline-status                  # Check progress
```

### Crawl & Ingest
```bash
.venv/bin/python3.12 cli.py crawl                            # Scrape new URLs to crawled_links.txt
.venv/bin/python3.12 cli.py ingest                           # Move URLs to links.txt for pipeline
```

### Prune (Database Cleanup)
```bash
.venv/bin/python3.12 cli.py prune --threshold 0.85 --dry-run --all # Show ALL tracks below 85% seed match (no delete)
.venv/bin/python3.12 cli.py prune --threshold 0.85                 # Permanently delete tracks below 85% match
```

### Audio-Gated Discovery
```bash
.venv/bin/python3.12 cli.py discover                         # Find new artists via seed likes + audio similarity
.venv/bin/python3.12 cli.py discover --target 100            # Stop after 100 tracks
.venv/bin/python3.12 cli.py discover --threshold 0.65        # Lower similarity gate (default 0.70)
.venv/bin/python3.12 cli.py discover --probe-count 2         # Fewer probe tracks per candidate
.venv/bin/python3.12 cli.py discover-log                     # View all candidate history
.venv/bin/python3.12 cli.py discover-log --status APPROVED   # Only approved artists
.venv/bin/python3.12 cli.py discover-log --status REJECTED   # Only rejected artists
```

### Analysis & Indexing
```bash
.venv/bin/python3.12 cli.py reindex                          # Rebuild ChromaDB search index (auto-fits whitening)
.venv/bin/python3.12 cli.py optimize                         # Find optimal feature weights for matching artists
```

### 2D Map (UMAP)
```bash
.venv/bin/python3.12 cli.py map                              # Generate 2D map (default params)
.venv/bin/python3.12 cli.py map --neighbors 200 --min-dist 0.15  # Global structure (subgenre separation)
.venv/bin/python3.12 cli.py map --neighbors 15 --min-dist 0.05   # Local fidelity (tight neighborhoods)
```

### Search & Discovery
```bash
.venv/bin/python3.12 cli.py search "HXVRMXN"                # Search by artist/title
.venv/bin/python3.12 cli.py similar "HXVRMXN - Eclipse.mp3"  # Find similar tracks
.venv/bin/python3.12 cli.py similar "HXVRMXN - Eclipse.mp3" --top 10
```

### Library Info
```bash
.venv/bin/python3.12 cli.py stats                            # Library overview
.venv/bin/python3.12 cli.py features                         # Show all 9 features
.venv/bin/python3.12 cli.py inspect "HXVRMXN - Eclipse.mp3"  # All 43 feature values
.venv/bin/python3.12 cli.py lab-status                       # Show Training Lab dataset stats
.venv/bin/python3.12 cli.py lab-undo                         # Wipe all triplets for recent Anchor
```
*(To see the fully indexed map of how all tracks are grouped by Artist, view `docs/indexed_artists.md!)*

### Download Only
```bash
.venv/bin/python3.12 cli.py download --file links.txt        # Download without analyzing
```

## SQLite Direct Access
```bash
sqlite3 data/tracks.db
```
```sql
SELECT id, artist, title, status FROM tracks;
.quit
```

## Tests
```bash
.venv/bin/python3.12 -m pytest tests/ -v
```
