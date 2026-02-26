# GitHub Push Guide

> **Purpose**: This document is a reference for AI agents and collaborators to understand the dual-repository push workflow for the Deepkt project. Read this BEFORE committing or pushing any code.

---

## Repositories

| Property        | Public Repo (`origin`)                          | Dev Repo (`dev`)                                  |
|-----------------|-------------------------------------------------|---------------------------------------------------|
| **URL**         | `https://github.com/adrianpartain59/Deepkt.git` | `https://github.com/adrianpartain59/DeepktDev.git`|
| **Remote Name** | `origin`                                        | `dev`                                             |
| **Branch**      | `main`                                          | `personal-dev`                                    |
| **Visibility**  | Public                                          | Private                                           |

---

## What Goes Where

### Public Repo (`origin` → `main`)
**Source code only. No data, no secrets, no large files.**

✅ Push:
- All Python source code (`deepkt/`, `app.py`, `cli.py`)
- Configuration templates (`config/`)
- Documentation (`docs/`)
- Tests (`tests/`)
- `requirements.txt`, `.gitignore`, `README.md`
- Workflow/agent config files (`.agents/`)

❌ Never push:
- `data/` directory (SQLite DB, ChromaDB, audio files, logs)
- `.venv/` or any virtual environment files
- `.env` or secrets/API keys
- `links.txt`, `links2.txt`, `crawled_links.txt` (contain scraped URLs)
- `seed_artists.txt` (personal curation list)
- Any `.mp3`, `.wav`, or audio files
- Pipeline logs (`*.log`)

### Dev Repo (`dev` → `personal-dev`)
**Everything from public + personal data and curation files.**

✅ Push (in addition to everything in Public):
- `links.txt`, `links2.txt`, `crawled_links.txt`
- `seed_artists.txt`
- `data/tracks.db` (SQLite database with track metadata and features)
- Any personal scripts, notes, or experimental files

❌ Never push:
- `data/chroma_db/` (can be rebuilt via `cli.py reindex`)
- `data/tmp/` or `data/raw_snippets/` (temporary audio files)
- `.venv/`
- `.env` or secrets/API keys
- Any `.mp3`, `.wav`, or audio files

---

## Push Commands

### Push to Public (source code update)
```bash
git add -A
git commit -m "descriptive message"
git push origin main
```

### Push to Dev (includes personal data)
```bash
git checkout personal-dev
git merge main
git add -A
git commit -m "descriptive message"
git push dev personal-dev
git checkout main
```

> [!IMPORTANT]
> Always push to `origin main` FIRST, then merge `main` into `personal-dev` and push to `dev`. This keeps the dev branch as a strict superset of the public branch.

---

## .gitignore Behavior

The `.gitignore` is configured for the **public** repo and blocks `data/` entirely. When pushing to the `dev` repo on the `personal-dev` branch, you may need to force-add data files:

```bash
git add -f data/tracks.db
git add -f links.txt seed_artists.txt
```

---

## Pre-Push Checklist

1. **No secrets** — Verify no API keys, tokens, or `.env` files are staged
2. **No audio** — Verify no `.mp3` or `.wav` files are staged
3. **No venv** — Verify `.venv/` is not staged
4. **Correct remote** — Double-check you are pushing to the intended remote
5. **Correct branch** — `main` for public, `personal-dev` for dev
