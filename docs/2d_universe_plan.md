# HyperPhonk Minimalist 2D Universe: Detailed Implementation Plan

The objective is to replace the Streamlit prototype with an ultra-minimalist, immersive 2D web application (`Next.js` + `FastAPI` + `react-konva`). Navigation happens exclusively by dragging the star map, with audio cross-fading based on proximity to the dead-center of the screen.

Given the architectural shift and the complexity of the math (UMAP) and rendering (HTML5 Canvas), this plan is explicitly broken into highly isolated phases. Each phase must be completed, tested, and firmly verified before moving to the next to strictly minimize risk.

---

## Phase 1: UMAP Data Generation (Python / CLI)
**Goal:** Prove we can effectively squash 512D ChromaDB embeddings into a stable 2D `(x, y)` coordinate plane without touching any web code yet.

**Steps:**
1. Create `deepkt/umap_projector.py`.
2. Fetch all 11,000+ vectors from ChromaDB.
3. Apply `umap-learn` to reduce dimensionality to 2, ensuring we save the random state for reproducibility.
4. Update the `tracks` SQLite database table to include `x` and `y` columns.
5. Add a CLI command: `cli.py map` to execute this projection.

**Anticipated Errors & Mitigation:**
* *Error:* `umap-learn` crashes or takes >10 minutes on an M-series Mac due to unoptimized C++ dependencies.
* *Mitigation:* Ensure we install the library via pip correctly, and use a small subset of tracks (e.g., 500) for the initial test run to verify the math works before projecting the full 11,000 set.
* *Error:* 2D points clump together into an unreadable monolithic dot.
* *Mitigation:* We will expose UMAP parameters (`n_neighbors`, `min_dist`) and iteratively tweak them in the CLI until the spread of coordinates looks healthy (verified by printing min/max ranges to the console).

**Verification Checkpoint:** Are X and Y coordinates successfully saved in SQLite for all tracks?

---

## Phase 2: The FastAPI Backend
**Goal:** Build a robust, lightweight Python web server capable of serving database records and streaming audio `.mp3` files securely to a frontend.

**Steps:**
1. Create `api.py` using FastAPI.
2. Build endpoint `GET /api/universe`: Returns the entire catalog as a JSON array `[{id, x, y}]`. This payload needs to be extremely minimal (no artist/title strings yet) to ensure the frontend loads instantly.
3. Build endpoint `GET /api/track/{id}`: Returns full metadata (Artist, Title, URL) for a specific ID.
4. Build endpoint `GET /api/audio/{id}`: Securely streams the requested `.mp3` file from the `data/` directory.

**Anticipated Errors & Mitigation:**
* *Error:* CORS completely blocks the Next.js frontend from talking to the FastAPI backend during local development.
* *Mitigation:* Pre-configure the FastAPI CORS middleware to explicitly allow `localhost:3000` from the exact start.
* *Error:* `GET /api/universe` payload is too large (>10MB) causing browser stutter on load.
* *Mitigation:* Return only raw floats for X/Y and the Track UUID string. We parse full metadata lazily via `/api/track/{id}` only when a track gets close to the center.

**Verification Checkpoint:** Do all 3 API endpoints return 200 OK when tested in the browser swagger UI (`http://127.0.0.1:8000/docs`)? Can we hear audio playing from `/api/audio/{id}`?

---

## Phase 3: Next.js Frontend Scaffold & Render
**Goal:** Create a React frontend that can ingest the massive X/Y coordinate array and successfully render 11,000 dots on a draggable 2D canvas without lagging.

**Steps:**
1. Run `npx create-next-app@latest web` with Tailwind styling layout set to 100vw/100vh absolute.
2. Install `react-konva` (a React wrapper for the HTML5 Canvas API, highly optimized for thousands of shapes).
3. Fetch `GET /api/universe` on load.
4. Render 11,000 simple `Circle` components.
5. Implement drag-to-pan logic across the map.

**Anticipated Errors & Mitigation:**
* *Error:* Rendering 11,000 SVGs or DOM nodes crashes the browser.
* *Mitigation:* We are strictly using HTML5 Canvas via Konva, *not* SVGs or standard DOM elements. If lag persists, we will implement Konva's `FastLayer` which disables complex shading for raw speed.
* *Error:* Coordinates are out of bounds (stars render off-screen).
* *Mitigation:* Implement a math normalizer to scale the raw UMAP floats `[-10.5, 12.3]` to fit perfectly within the Canvas viewport pixels `[0, 2000]`.

**Verification Checkpoint:** Can the user freely drag a canvas filled with 11,000 stars at a smooth 60 Frames Per Second?

---

## Phase 4: Center-Proximity Engine (Math & Visuals)
**Goal:** Detect which star is closest to the screen's dead-center while dragging, while strictly enforcing a high zoom level so tracks don't overlap and the focal point doesn't switch too chaotically.

**Steps:**
1. **Viewport Tuning (Critical UI Constraint):**
   - Multiply the UMAP coordinate scalar until the map spans something massive like `200,000px × 200,000px`.
   - Set the default and minimum zoom clamp exceptionally high so that **only 10 to 20 dots** fit inside the user's monitor at any one time.
   - Set the `radius` of each star extremely small to guarantee zero overlapping.
2. **The `requestAnimationFrame` Loop:**
   - Instead of checking all 11,000 tracks every frame (which would crash the browser), calculate the `[x_min, x_max]` bounding box of the current viewport. 
   - Filter the 11,000 array down to *only the ~15 dots* currently inside those bounds.
3. **The Distance Math:**
   - Loop through those ~15 dots. Calculate the Pythagorean distance `Math.sqrt(dx*dx + dy*dy)` between each dot and the center.
   - The dot with the smallest distance becomes the `activeFocalTrack`.
4. **The UI Reaction:**
   - Once a track becomes the `activeFocalTrack`, apply a CSS Glow effect to its specific `<Circle>` and render its Artist/Title on screen using the `/api/track/{id}` endpoint.

**Anticipated Errors & Mitigation:**
* *Error:* Re-calculating Pythagorean distances 60 times a second on 11,000 elements will tank the framerate.
* *Mitigation:* The Bounding Box filter is mandatory. Bounding box checks (simple `<` and `>` math) are 100x faster than square roots. Only run square roots on the ~15 visible stars.  
* *Error:* The user is trapped at high zoom and scrolling is too slow to cross the 11,000-track map.
* *Mitigation:* We will implement a Search Bar. When the user searches an artist, the camera instantly "warps" to those coordinates, bypassing the need to slowly drag across the map.

**Verification Checkpoint:** As you aggressively pan the map, does the glowing "Focal Star" seamlessly hand off from dot to dot without any framedrops or lag, staying strictly limited to 10-20 on screen?

---

## Phase 5: Predictive Regional Audio Caching (The "Buffer Zone")
**Goal:** Achieve 0ms audio crossfading latency without requiring a massive 5GB pre-download of every MP3 in the database. Instead, stream and locally cache audio for the tracks immediately surrounding the user's current coordinates.

**Steps:**
1. **The Spatial Fetcher (Frontend):** 
   - Write an intelligent background daemon that runs in Next.js.
   - When the user's camera stops panning (or when they first double-click a region), use a Spatial QuadTree query to find the nearest `N` stars (e.g., the 10 closest stars to the center).
   - Dispatch silent background `fetch()` requests to the backend for those 10 tracks to explicitly load them into browser memory/disk cache.
2. **The Loader Feedback (UI):**
   - If the user moves to a completely new region, immediately show a sleek, minimalist loading indicator around the center-reticle (e.g., a spinning neon ring).
   - As the 10 surrounding `.mp3` files finish downloading from the backend, the ring fills up. Once loaded, the user can freely scrub locally with 0ms delay.
3. **The Directional Pre-Loader (Frontend):**
   - As the user pans the camera left, the Spatial Fetcher detects which new stars are entering the "buffer radius" on the left edge and initiates early background downloads for them, while gracefully purging old tracks on the right edge to keep browser memory lean.

**Anticipated Errors & Mitigation:**
* *Error:* Rapidly dragging across the map queues up hundreds of stale background `fetch()` requests, crashing the browser or hitting SoundCloud rate limits.
* *Mitigation:* Implement an aggressive `AbortController` system. The microsecond a star leaves the "buffer radius", cancel its pending flight request natively in the browser so we only ever use bandwidth on what the user is currently looking at.

**Verification Checkpoint:** The user can drop into a cluster, wait ~5 seconds for the buffer ring to fill, and then seamlessly and instantly crossfade through the local area exactly as imagined.
