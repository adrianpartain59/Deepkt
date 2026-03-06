# GitHub Push Guide

> **Purpose**: This document is a reference for AI agents and collaborators to understand the dual-repository push workflow for the Deepkt project. Read this BEFORE committing or pushing any code.

> [!CAUTION]
> **NEVER use `git checkout` to switch branches.** Switching between `main` and `personal-dev` will DELETE `data/tracks.db` because it is gitignored on `main` but tracked on `personal-dev`. Use `git push dev main:personal-dev` instead — this pushes directly without switching branches.

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
**Same source code as public. Data files are NOT pushed to avoid branch-switching data loss.**

The dev repo receives the exact same source code as the public repo via a direct push (no branch switching). Data files (`tracks.db`, ChromaDB) live only on the local machine and can be fully rebuilt via `cli.py pipeline` + `cli.py reindex`.

---

## Push Commands

### Push to Both Repos (safe, no branch switching)
```bash
git add -A
git commit -m "descriptive message"
git push origin main
git push dev main:personal-dev
```

> [!IMPORTANT]
> The command `git push dev main:personal-dev` pushes the local `main` branch directly to the `dev` remote's `personal-dev` branch **without ever switching branches locally**. This protects `data/tracks.db` from being deleted.

### Push `links.txt` to Dev (ALWAYS do this after every push)

`links.txt` contains all crawled and discovered track URLs. It is **excluded from origin** (public) but must **always be pushed to dev** (private) so it is backed up.

```bash
# After the main push, always do:
git add links.txt
git commit -m "chore: update links.txt"
git push dev main:personal-dev
```

> [!CAUTION]
> Do **NOT** push `links.txt` to `origin`. Do **NOT** skip this step — `links.txt` is the single source of all discovered track URLs and cannot be rebuilt.

### Push Personal Data (Dev Repo Only)
If you have generated valuable personal data (e.g., Training Lab triplets in `data/tracks.db`) or have large files that would take a long time to retrieve/rebuild, you should back them up **exclusively** to the private dev repository.

Because `data/` is blocked by `.gitignore`, you must force-add the specific files, commit them, and push *only* to `dev`:

```bash
# 1. Force-add the specific ignored file
git add -f data/tracks.db

# 2. Commit the data backup
git commit -m "chore(data): backup SQLite database"

# 3. Push ONLY to the dev remote
git push dev main:personal-dev
```

> [!WARNING]
> Do **not** run `git push origin main` after force-adding data files, or you will accidentally publish your personal database to the public repository!

---

## .gitignore Behavior

The `.gitignore` blocks `data/` entirely. This is intentional — database files should never be committed. If the database is lost, it can be fully rebuilt:

```bash
python cli.py pipeline --file links.txt   # Re-download and analyze all tracks
python cli.py reindex                       # Rebuild ChromaDB search index
```

---

## Pre-Push Checklist

1. **No secrets** — Verify no API keys, tokens, or `.env` files are staged
2. **No audio** — Verify no `.mp3` or `.wav` files are staged
3. **No venv** — Verify `.venv/` is not staged
4. **No branch switching** — NEVER run `git checkout personal-dev`
5. **Correct remote** — Double-check you are pushing to the intended remote
