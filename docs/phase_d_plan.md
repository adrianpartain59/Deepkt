# Phase D: CLI Polish + Basic Auto Crawler + Quality Gates

## Design Decisions (User-Specified)

> [!IMPORTANT]
> **Keep it basic.** This is a minimal v1 crawler — not a focus area yet.
> User wants to move on to other things after this ships.

| Decision | Choice |
|----------|--------|
| **Crawl methods** | Tags (primary) + keyword search + related spidering (depth 1 only) |
| **Related depth** | Max 1 hop — direct related tracks only |
| **Review workflow** | **Manual review** — crawler discovers URLs → user reviews → user runs `pipeline` |
| **Keyword search** | Supported — uses SoundCloud's search API via yt-dlp |
| **Seed artists** | User provides seed artist URLs in `crawler.yaml` → crawler fetches their tracks + related |
| **Pipeline trigger** | Never automatic — `crawl` only discovers, user manually decides to `pipeline` |
| **Scope** | Basic, functional, not over-engineered |

---

## What Already Exists (from Phases B/C)

`download`, `analyze`, `reindex`, `pipeline`, `pipeline-status`, `search`, `similar`, `stats`, `features`, `inspect`

## What This Phase Adds

1. CLI commands: `retry-failed`, `export`, `crawl`, `discovered`, `rejected`, `unreject`
2. `deepkt/crawler.py` — basic SoundCloud crawler
3. `deepkt/quality.py` — pre-download quality gates
4. `config/crawler.yaml` — crawl sources, seed artists, quality gates

---

## Part 1: Remaining CLI Commands

### `retry-failed`

```bash
python cli.py retry-failed            # Reset FAILED → DISCOVERED for re-processing
python cli.py retry-failed --limit 50 # Only retry the 50 most recent
```

### `export`

```bash
python cli.py export --format csv     # Metadata to CSV
python cli.py export --format json    # Metadata + all 43 features to JSON
```

---

## Part 2: Crawler Configuration

### [NEW] `config/crawler.yaml`

```yaml
sources:
  soundcloud:
    # Tag-based discovery (primary method)
    tags:
      - phonk
      - dark trap
      - drift phonk
      - wave
      - darkwave

    # Keyword search (uses SoundCloud search API)
    search_queries:
      - "phonk"
      - "dark phonk"
      - "drift phonk"

    # Seed artists — crawl their tracks + related (depth 1)
    seed_artists: []         # User populates with SoundCloud artist page URLs

    # Related-track spidering
    max_depth: 1             # Only direct related tracks, no recursion

    # Rate limiting
    request_pause: 3.0
    max_per_session: 200     # Keep sessions small for manual review

quality_gates:
  min_duration_seconds: 30
  max_duration_seconds: 900
  title_blocklist:
    - podcast
    - lecture
    - asmr
    - interview
    - remix contest
    - live stream
    - radio show
    - mix vol
    - full album
  required_tags:
    - phonk
    - trap
    - darkwave
    - drift
    - dark trap
    - wave
  tag_match_mode: "any"
  artist_blocklist: []
```

---

## Part 3: Quality Gates

### [NEW] `deepkt/quality.py`

Simple pass/fail checks run before any downloading:

```python
def check_quality(track_info, config) -> (bool, str):
    """Returns (passed, reason). Reason explains rejection."""

# Individual checks:
_check_duration(duration, min_dur, max_dur)
_check_title_blocklist(title, blocklist)
_check_tags(tags, required_tags, mode)
_check_artist(artist, blocklist)
```

Rejected tracks → `status=REJECTED` in SQLite with reason string.

---

## Part 4: Basic Crawler

### [NEW] `deepkt/crawler.py`

Three discovery methods, all basic:

```python
def crawl_by_tags(tags, limit, config):
    """Scrape SoundCloud tag pages for track URLs via yt-dlp --flat-playlist."""

def crawl_by_search(queries, limit, config):
    """Use SoundCloud search API via yt-dlp to find tracks by keyword."""

def crawl_seed_artists(artist_urls, config):
    """Fetch all tracks from seed artist pages, plus depth-1 related tracks."""
```

### Discovery flow (manual review):
```
cli.py crawl                        → URLs registered as DISCOVERED
cli.py discovered                   → User reviews the list
cli.py pipeline --status discovered → User processes approved tracks
cli.py rejected                     → User reviews what was filtered
cli.py unreject <track-id>          → Manual override
```

---

## Part 5: CLI Commands

### New commands

```bash
# Crawl using crawler.yaml defaults
python cli.py crawl
python cli.py crawl --tags "phonk" --limit 50
python cli.py crawl --search "dark phonk" --limit 30
python cli.py crawl --artists                  # Crawl seed artists from config

# Review discovered tracks (not yet processed)
python cli.py discovered
python cli.py discovered --limit 20

# Review rejected tracks
python cli.py rejected --limit 20

# Override a rejection
python cli.py unreject <track-id>
```

---

## Anticipated Errors & Mitigations

### Error 1: SoundCloud tag pages don't work via yt-dlp
**Fix**: Fall back to keyword search (`/search/tracks?q=phonk`), which yt-dlp handles more reliably. Both methods are implemented so one can compensate.

### Error 2: Massive duplicate URLs across tags
**Fix**: `INSERT OR IGNORE` in SQLite. Normalize URLs (strip query params, trailing slashes) before registering.

### Error 3: Quality gates too aggressive
**Fix**: Rejected tracks stored with reason. `unreject` command lets user manually override. Default gates are lenient.

### Error 4: Crawler runs forever
**Fix**: `max_per_session: 200` default. Small batches for manual review.

### Error 5: Rate limiting during metadata-only requests
**Fix**: `request_pause: 3.0` default. Exponential backoff on 429 responses.

### Error 6: Seed artist page has hundreds of tracks
**Fix**: Cap at `max_per_session` total across all seed artists.

### Error 7: yt-dlp can't extract metadata without downloading
**Fix**: Use `ydl.extract_info(url, download=False)` for metadata-only extraction. This is a standard yt-dlp feature.

### Error 8: Unicode in export breaks CSV
**Fix**: UTF-8 with BOM for Excel. JSON handles Unicode natively.

---

## Execution Checklist

1. [ ] `retry-failed` CLI command
2. [ ] `export` CLI command (CSV + JSON)
3. [ ] Create `config/crawler.yaml`
4. [ ] Add `load_crawler_config()` to `config.py`
5. [ ] Create `deepkt/quality.py`
6. [ ] Create `deepkt/crawler.py` (tags + search + seed artists, depth 1)
7. [ ] Add `crawl`, `discovered`, `rejected`, `unreject` CLI commands
8. [ ] Update tests
9. [ ] Test: crawl by tag (10-20 tracks)
10. [ ] Test: quality gates reject bad tracks
11. [ ] Test: manual review flow (crawl → discovered → pipeline → reindex)
