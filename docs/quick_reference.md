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

### Analysis & Indexing
```bash
.venv/bin/python3.12 cli.py analyze                          # Analyze MP3s in data/raw_snippets
.venv/bin/python3.12 cli.py reindex                          # Rebuild ChromaDB search index
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
