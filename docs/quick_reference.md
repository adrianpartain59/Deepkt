# Deepkt Quick Reference

## Run the App
```bash
.venv/bin/python3.12 -m streamlit run app.py
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

### Analysis & Indexing
```bash
.venv/bin/python3.12 cli.py reindex                          # Rebuild ChromaDB search index
.venv/bin/python3.12 cli.py optimize                         # Find optimal feature weights for matching artists
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
