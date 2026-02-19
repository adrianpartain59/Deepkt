# Phase A: Project Restructure — Detailed Plan

## Objective
Move from flat scripts (`phase1.py`, `phase2.py`, `phase3.py`) into a proper `deepkt/` Python package, so all future phases (B-F) build on a clean, importable foundation.

---

## What Changes

### Before (current)
```
HyperPhonkCurator/
├── phase1.py          # Download logic + yt-dlp config
├── phase2.py          # Feature extraction + test loop at module level
├── phase3.py          # ChromaDB indexing + query
├── app.py             # Streamlit UI (imports from phase1/2/3)
├── links.txt
└── data/
```

**Problems with this structure:**
- `phase2.py` runs analysis code **at import time** (lines 39-45 execute when any file does `from phase2 import ...`)
- All paths are relative and assume CWD is the project root
- No package boundary — everything is a loose script
- Adding new modules (db, config, pipeline) would clutter the root further

### After (target)
```
HyperPhonkCurator/
├── deepkt/                   # Core package
│   ├── __init__.py             # Package marker, version string
│   ├── downloader.py           # From phase1.py
│   ├── analyzer.py             # From phase2.py (function only, no auto-run)
│   ├── indexer.py              # From phase3.py
│   └── features/               # Placeholder for Phase B
│       ├── __init__.py
│       └── base.py             # BaseFeatureExtractor stub
├── config/                     # Placeholder for Phase B
│   └── features.yaml           # Default config (matches current behavior)
├── app.py                      # Updated imports: from deepkt.X import Y
├── cli.py                      # Thin wrapper (placeholder for Phase D)
├── links.txt
├── docs/
│   └── architecture_plan.md
└── data/
```

---

## Step-by-Step Execution

### Step 1: Create `deepkt/` package skeleton

Create the directories and `__init__.py` files:

```
deepkt/__init__.py
deepkt/features/__init__.py
deepkt/features/base.py
config/features.yaml
```

`__init__.py` should contain:
```python
"""Deepkt — Sonic similarity engine."""
__version__ = "0.2.0"
```

---

### Step 2: Move `phase1.py` → `deepkt/downloader.py`

**What to change:**
- Move the two functions (`smart_download_range`, `run_crawler`) into `deepkt/downloader.py`
- Remove the `if __name__ == "__main__"` block (that goes in `cli.py` later)
- Make paths configurable via function parameters (already are ✓)

**What to keep:**
- The existing `phase1.py` remains temporarily as a thin redirect (prevents breakage if anything still imports it):

```python
# phase1.py — DEPRECATED, use deepkt.downloader
from deepkt.downloader import smart_download_range, run_crawler
if __name__ == "__main__":
    run_crawler()
```

---

### Step 3: Move `phase2.py` → `deepkt/analyzer.py`

**What to change:**
- Move `analyze_music_snippet()` into `deepkt/analyzer.py`
- **Critical fix**: Remove the module-level test loop (lines 38-45 of current `phase2.py`). This code runs on import and will break things. It moves to a `if __name__ == "__main__"` block or `cli.py`.

**What to keep:**
- Thin redirect at `phase2.py`:

```python
# phase2.py — DEPRECATED, use deepkt.analyzer
from deepkt.analyzer import analyze_music_snippet
```

---

### Step 4: Move `phase3.py` → `deepkt/indexer.py`

**What to change:**
- Move `get_collection`, `build_index`, `query_similar` into `deepkt/indexer.py`
- Update the internal import: `from phase2 import ...` → `from deepkt.analyzer import ...`
- Make `DATA_DIR` and `DB_DIR` constants configurable (pull from a central config later in Phase B)

**What to keep:**
- Thin redirect at `phase3.py`:

```python
# phase3.py — DEPRECATED, use deepkt.indexer
from deepkt.indexer import get_collection, build_index, query_similar
if __name__ == "__main__":
    from deepkt.indexer import _self_test
    _self_test()
```

---

### Step 5: Update `app.py` imports

Change all imports from:
```python
from phase1 import smart_download_range
from phase2 import analyze_music_snippet
from phase3 import get_collection, build_index, query_similar
```

To:
```python
from deepkt.downloader import smart_download_range
from deepkt.analyzer import analyze_music_snippet
from deepkt.indexer import get_collection, build_index, query_similar
```

---

### Step 6: Create `deepkt/features/base.py` stub

A minimal interface that Phase B will build on:

```python
class BaseFeatureExtractor:
    """Interface for pluggable feature extractors."""
    name: str = "unnamed"
    dimensions: int = 0

    def extract(self, y, sr, config=None) -> list[float]:
        raise NotImplementedError
```

This doesn't change any behavior now — it's scaffolding.

---

### Step 7: Create default `config/features.yaml`

A config that **exactly matches** current hardcoded behavior, so nothing changes functionally:

```yaml
version: 1
features:
  tempo:
    enabled: true
    dimensions: 1
  mfcc:
    enabled: true
    n_coefficients: 13
    dimensions: 13
  spectral_centroid:
    enabled: true
    dimensions: 1
  zero_crossing_rate:
    enabled: true
    dimensions: 1
```

Phase B will wire this config into the analyzer. For now it just documents what exists.

---

### Step 8: Verify

- `python3.12 phase1.py` — still works (via redirect)
- `python3.12 phase3.py` — still works (via redirect)
- `python3.12 -m streamlit run app.py` — still works (new imports)
- `python3.12 -c "from deepkt.analyzer import analyze_music_snippet; print('OK')"` — package importable

---

## Anticipated Errors & Mitigations

### Error 1: `ModuleNotFoundError: No module named 'deepkt'`
**When**: Running any script that does `from deepkt import ...`
**Why**: Python doesn't know `deepkt/` is a package unless it's on `sys.path` or installed.
**Fix**: Two options (we'll use option A):
- **(A)** Always run from the project root — Python adds CWD to `sys.path` by default. Since we already run `python3.12 app.py` from the project root, this works with no changes.
- **(B)** Create a `pyproject.toml` and do `pip install -e .` to make it a proper installable package. Better long-term, but not needed yet.

**If Talapas later**: Option B becomes necessary. We'd add `pyproject.toml` at that point.

---

### Error 2: `phase2.py` runs analysis on import
**When**: Any file does `from phase2 import analyze_music_snippet` or `from deepkt.analyzer import ...` if we accidentally leave the test loop
**Why**: Lines 38-45 of current `phase2.py` are module-level code (not guarded by `if __name__`), so they execute during import
**Fix**: The move to `deepkt/analyzer.py` must **only** include the function definition. The test loop is either deleted or moved behind `if __name__ == "__main__"`.

---

### Error 3: Circular imports between `deepkt` modules
**When**: If `indexer.py` imports from `analyzer.py` and `analyzer.py` imports from `indexer.py`
**Why**: Python can't resolve circular import chains
**Fix**: Not a concern in Phase A — the dependency graph is one-directional:
```
downloader.py  ← (no internal deps)
analyzer.py    ← (no internal deps)
indexer.py     ← imports analyzer.py
```
However, in later phases when `pipeline.py` orchestrates all three, we must ensure it imports them — not the other way around. **Rule: modules deeper in the tree never import from orchestrators.**

---

### Error 4: Relative path breakage
**When**: Running a script from a different working directory (e.g., `python3.12 /full/path/to/app.py` from `~`)
**Why**: Current code uses relative paths like `"data/raw_snippets"` and `"data/chroma_db"` which resolve against CWD
**Fix**: In Phase A we keep relative paths (matching current behavior). In Phase B, we introduce `config.py` that resolves paths relative to the **project root** using `pathlib.Path(__file__).parent.parent`, making it CWD-independent.

---

### Error 5: Existing ChromaDB data incompatibility
**When**: After restructure, running indexer
**Why**: ChromaDB `data/chroma_db/` already has 10 indexed tracks — will they still be accessible?
**Fix**: Yes — nothing about the restructure changes the ChromaDB path or collection name. The data persists exactly as-is. **No re-indexing needed.**

---

### Error 6: `__pycache__` confusion
**When**: Old `__pycache__` from phase1/2/3 lingers and Python loads stale bytecode
**Why**: Python caches compiled `.pyc` files. If the source moves but cache remains, imports can behave unpredictably.
**Fix**: Delete `__pycache__/` in the project root after the restructure. The new package will generate its own cache under `deepkt/__pycache__/`.

---

### Error 7: Streamlit caching breaks after import path change
**When**: After updating `app.py` imports, Streamlit shows errors or stale state
**Why**: Streamlit caches by import path — changing `from phase3 import ...` to `from deepkt.indexer import ...` invalidates its cache
**Fix**: Not actually an error — Streamlit handles this gracefully with a page reload. Worst case, clear `.streamlit/` cache manually with `rm -rf ~/.streamlit/cache`.

---

## Questions

1. **Old phase files**: I'll keep `phase1.py`, `phase2.py`, `phase3.py` as thin redirect wrappers so your muscle memory (`python3.12 phase3.py`) still works. Eventually you can delete them. **Sound good, or do you want a clean break?**

2. **`pyproject.toml`**: Should I set up a proper `pip install -e .` now (makes the package installable anywhere, needed for Talapas), or wait until you're closer to switching environments?

3. **`cli.py` stub**: Should I create a basic Click/argparse CLI skeleton in Phase A so it's ready for Phase D, or keep Phase A strictly about the file restructure?
