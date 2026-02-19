---
description: How to run the Deepkt app
---

## Prerequisites
- Python 3.12 virtual environment at `.venv/`
- ffmpeg installed (`brew install ffmpeg`)

## Steps

// turbo-all

1. Index the library (run once, or after adding new tracks):
```bash
.venv/bin/python3.12 cli.py index
```

2. Launch the Streamlit UI:
```bash
.venv/bin/python3.12 -m streamlit run app.py
```

3. Open http://localhost:8501 in your browser.

## CLI Commands

```bash
# Download snippets from links.txt
.venv/bin/python3.12 cli.py download

# Index snippets into ChromaDB
.venv/bin/python3.12 cli.py index

# Search tracks by artist/title
.venv/bin/python3.12 cli.py search "HXVRMXN"

# Find similar tracks
.venv/bin/python3.12 cli.py similar "HXVRMXN - Eclipse.mp3"

# Show library stats
.venv/bin/python3.12 cli.py stats
```

## Adding New Tracks

1. Add SoundCloud/YouTube URLs to `links.txt` (one per line)
2. Download and index:
```bash
.venv/bin/python3.12 cli.py download
.venv/bin/python3.12 cli.py index
```
