# Deepkt Quick Reference

## Run the App
```bash
.venv/bin/python3.12 -m streamlit run app.py                 # Streamlit UI
.venv/bin/python3.12 api.py                                  # FastAPI backend (port 8000)
cd web && npm run dev                                        # Next.js frontend (port 3000)
```

### Spotify Import (Local Dev)
Spotify allows `http://127.0.0.1` for local development (no HTTPS needed):

1. Add `http://127.0.0.1:8000/api/spotify/callback` as a Redirect URI in your [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Set credentials in `.env`:
   ```
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/spotify/callback
   FRONTEND_URL=http://localhost:3000
   ```
3. Start the API (`python api.py`) and Next.js (`cd web && npm run dev`)
4. Click "Sign In" in the app — you'll be redirected to Spotify to authorize

**Note:** Spotify requires `127.0.0.1` (not `localhost`) for loopback redirect URIs. For production, use HTTPS.

## CLI Commands

### Pipeline (download + analyze in parallel)
```bash
.venv/bin/python3.12 cli.py pipeline                        # Process all URLs
.venv/bin/python3.12 cli.py pipeline --resume                # Resume after crash
.venv/bin/python3.12 cli.py pipeline-status                  # Check progress
```

### Crawl & Ingest
```bash
.venv/bin/python3.12 cli.py crawl                            # Scrape new URLs to data/pipeline/crawled_links.txt
.venv/bin/python3.12 cli.py ingest                           # Move URLs to data/pipeline/links.txt
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
.venv/bin/python3.12 cli.py reindex                          # Rebuild ChromaDB search index from raw embeddings
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
.venv/bin/python3.12 cli.py features                         # Show enabled features
.venv/bin/python3.12 cli.py inspect "HXVRMXN - Eclipse.mp3"  # Feature values for a track
```
*(To see the fully indexed map of how all tracks are grouped by Artist, view `docs/indexed_artists.md!)*

### Download Only
```bash
.venv/bin/python3.12 cli.py download                         # Download without analyzing
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
