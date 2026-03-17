# Plan: Claude Haiku LLM Integration for Genre Analysis

## Context
Users need a way to create a seed centroid (tags + seed artists) for their project's target subgenre. This feature adds Claude Haiku to analyze artists and generate highly specific genre tags + fill out the artist list to 30.

**Important change:** The Spotify import no longer cross-references tracks to SoundCloud. Instead, the raw Spotify artist names and track titles are sent directly to Haiku for analysis.

**Two flows:**
1. **Direct query** — user describes the subgenre with artist examples in a text input
2. **Playlist analysis** — auto-triggered after Spotify import, sends raw Spotify artist/track data to Haiku

## API Key Setup
See `docs/haiku_setup_guide.md` for detailed instructions.

---

## Implementation Steps

### Step 1: Add `anthropic` dependency
**File: `requirements.txt`**
- Add `anthropic>=0.44`

### Step 2: Modify Spotify import to skip SoundCloud cross-referencing
**File: `api.py`** — the background import thread currently:
1. Fetches tracks from Spotify playlists
2. Cross-references each track on SoundCloud
3. Groups by artist with SoundCloud URLs
4. Saves to project

**Change to:**
1. Fetch tracks from Spotify playlists
2. Save raw artist/track data directly to project's `playlist_urls` as:
```json
[{"artist": "Surgeon", "tracks": [{"title": "Magneze"}, {"title": "Bad Boy"}]}, ...]
```
3. No SoundCloud lookup step

### Step 3: Database — add `llm_output` column to `projects`

**File: `deepkt/db.py`** (SQLite, line ~130 migration block)
- Add migration: `ALTER TABLE projects ADD COLUMN llm_output TEXT`

**File: `deepkt/user_db.py`** (PostgreSQL, line ~91)
- Add migration: `ALTER TABLE projects ADD COLUMN llm_output TEXT`
- Update `load_user_project()`: parse `llm_output` JSON
- Add `save_project_llm_output(user_id, slot, llm_output_dict)` function

### Step 4: Create LLM service module
**New file: `deepkt/llm.py`**

Single function: `analyze_artists(artists, tracks, user_query) -> dict`

**System prompt instructs Haiku to:**
1. Extract/validate artist names — need 3+ recognizable artists or return `status: "failed"`
2. **Filter outliers** — identify artists that don't fit the dominant subgenre, exclude them, return in `filtered_out`
3. Generate exactly 3 highly specific **genre** tags (NOT mood tags) — optimized for playlist searching
4. Expand artist list to 30 total (user's remaining + new). Skip if 30+ after filtering.
5. Return structured JSON only

**Output format:**
```json
{
  "status": "success | failed",
  "tags": ["specific-genre-tag-1", "specific-genre-tag-2", "specific-genre-tag-3"],
  "seed_artists": ["Artist1", "...", "Artist30"],
  "message": "null or error explanation",
  "filtered_out": [{"artist": "ArtistX", "reason": "doesn't fit the subgenre"}]
}
```

**Model:** `claude-haiku-4-5-20251001`

### Step 5: Add API endpoint
**File: `api.py`**

```
POST /api/projects/{slot}/analyze
Body: { "query"?: string }
Returns: LlmOutput object
Rate limit: 10/minute
```

- Flow 1 (query provided): pass user text to Haiku
- Flow 2 (no query): extract artists/tracks from project data, send to Haiku
- Save result to `llm_output` column (PostgreSQL on Railway)
- Return result to frontend

### Step 6: Update frontend ProjectPage
**File: `web/src/components/ProjectPage.tsx`**

- Add "Genre Analysis" section with text input + Analyze button
- Auto-trigger after Spotify import completes
- **Show raw JSON output** from LLM for debugging/verification
- Display errors clearly

---

## Key Files to Modify
| File | Change |
|------|--------|
| `requirements.txt` | Add `anthropic>=0.44` |
| `deepkt/db.py` ~line 131 | SQLite migration for `llm_output` column |
| `deepkt/user_db.py` ~line 91, 272 | PG migration, parse `llm_output`, new save function |
| `deepkt/llm.py` | **New file** — `analyze_artists()` + system prompt |
| `api.py` ~line 605 | New analyze endpoint + modified Spotify import (no SoundCloud) |
| `web/src/components/ProjectPage.tsx` | Genre Analysis UI with raw JSON output |

## Verification
1. Start server, call `POST /api/projects/1/analyze` with a query containing 3+ artists
2. Import Spotify playlist → verify raw artist/track data saved (no SoundCloud URLs)
3. Verify auto-analysis triggers after import
4. Check raw JSON output displays on frontend
5. Verify `llm_output` persists in PostgreSQL on Railway
6. Test failure case with <3 artists
