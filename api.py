import hashlib
import json
import os
import statistics
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import List, Optional

from deepkt import db as trackdb
from deepkt.downloader import download_single
from deepkt.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_user, optional_current_user, UserClaims,
    create_user, get_user_by_email, get_user_by_provider,
    get_user_by_id, store_refresh_token, revoke_refresh_token,
    link_oauth_provider, google_oauth_exchange,
)

load_dotenv()

app = FastAPI(title="HyperPhonk API")

_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_extra = os.environ.get("CORS_ORIGINS", "")
if _extra:
    _cors_origins.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    """Return a JSON 500 so CORSMiddleware can still attach CORS headers."""
    from starlette.responses import JSONResponse
    if isinstance(exc, HTTPException):
        raise exc  # let FastAPI handle HTTPExceptions normally
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

MIN_PASSWORD_LENGTH = 8


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


def _issue_tokens(user: dict) -> dict:
    """Create access + refresh tokens for a user and store refresh in DB."""
    access = create_access_token(user["id"], user["email"])
    refresh, hashed_jti = create_refresh_token(user["id"])
    store_refresh_token(user["id"], hashed_jti)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
            "auth_provider": user.get("auth_provider", "email"),
        },
    }


@app.post("/api/auth/register")
@limiter.limit("3/minute")
def register(req: RegisterRequest, request: Request):
    if len(req.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not req.email or "@" not in req.email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = create_user(
        email=req.email,
        display_name=req.display_name or req.email.split("@")[0],
        password=req.password,
        auth_provider="email",
    )
    return _issue_tokens(user)


@app.post("/api/auth/login")
@limiter.limit("5/minute")
def login(req: LoginRequest, request: Request):
    user = get_user_by_email(req.email)
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _issue_tokens(user)


@app.post("/api/auth/refresh")
def refresh_tokens(req: RefreshRequest):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Verify the jti matches what's stored
    jti = payload.get("jti", "")
    hashed_jti = hashlib.sha256(jti.encode()).hexdigest()
    if user.get("refresh_token") != hashed_jti:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    return _issue_tokens(user)


@app.post("/api/auth/logout")
def logout(user: UserClaims = Depends(get_current_user)):
    revoke_refresh_token(user.user_id)
    return {"status": "logged_out"}


@app.get("/api/auth/me")
def get_me(user: UserClaims = Depends(get_current_user)):
    full_user = get_user_by_id(user.user_id)
    if not full_user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": full_user["id"],
        "email": full_user["email"],
        "display_name": full_user.get("display_name"),
        "auth_provider": full_user.get("auth_provider"),
    }


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------

@app.get("/api/auth/google/login")
def google_login():
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")
    if not client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
    )
    return RedirectResponse(url=url)


@app.get("/api/auth/google/callback")
async def google_callback(code: str):
    from urllib.parse import urlencode
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    try:
        info = await google_oauth_exchange(code)
        # Find or create user
        user = get_user_by_provider("google", info["provider_id"])
        if not user:
            existing = get_user_by_email(info["email"])
            if existing:
                link_oauth_provider(existing["id"], "google", info["provider_id"])
                user = existing
            else:
                user = create_user(
                    email=info["email"],
                    display_name=info.get("name", ""),
                    auth_provider="google",
                    provider_id=info["provider_id"],
                )
        tokens = _issue_tokens(user)
        params = urlencode({
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "user": json.dumps(tokens["user"]),
        })
        return RedirectResponse(url=f"{frontend_url}/auth/callback?{params}")
    except Exception as e:
        params = urlencode({"error": str(e)})
        return RedirectResponse(url=f"{frontend_url}/auth/callback?{params}")



class UniverseNode(BaseModel):
    id: str
    artist: str
    title: str
    x: float
    y: float
    url: Optional[str] = None

class TrackMetadata(BaseModel):
    id: str
    artist: str
    title: str
    url: Optional[str] = None
    status: str

@app.get("/api/universe", response_model=List[UniverseNode])
def get_universe():
    """
    Returns the core data needed to render the 2D canvas map and the Focal Track HUD.
    Includes IDs, Artist, Title, and UMAP (X,Y) coordinates.
    """
    conn = trackdb.get_db()
    
    # We only want downloaded/indexed tracks that have valid UMAP coordinates
    rows = conn.execute('''
        SELECT id, artist, title, x, y, url FROM tracks 
        WHERE x IS NOT NULL AND status IN ('DOWNLOADED', 'INDEXED')
    ''').fetchall()
    conn.close()
    
    universe = [{"id": r[0], "artist": r[1], "title": r[2], "x": r[3], "y": r[4], "url": r[5]} for r in rows]
    return universe

class SearchResult(BaseModel):
    id: str
    artist: str
    title: str
    x: float
    y: float
    url: Optional[str] = None

@app.get("/api/search", response_model=List[SearchResult])
def search_tracks(q: str):
    """
    Searches for tracks by artist or title and returns their coordinates.
    """
    conn = trackdb.get_db()
    
    # Simple case-insensitive search with wildcards
    query = f"%{q}%"
    rows = conn.execute('''
        SELECT id, artist, title, x, y FROM tracks 
        WHERE (artist LIKE ? OR title LIKE ?) 
        AND x IS NOT NULL AND status IN ('DOWNLOADED', 'INDEXED')
        LIMIT 20
    ''', (query, query)).fetchall()
    conn.close()
    
    results = [{"id": r[0], "artist": r[1], "title": r[2], "x": r[3], "y": r[4]} for r in rows]
    return results

class SimilarTrack(BaseModel):
    id: str
    artist: str
    title: str
    x: float
    y: float
    url: Optional[str] = None
    match_pct: float

# In-memory cosine similarity index built from SQLite track_features.
# Avoids needing ChromaDB (and its heavy dependency chain) in production.
_sim_matrix: Optional[np.ndarray] = None
_sim_ids: Optional[list] = None
_sim_id_to_idx: Optional[dict] = None
_sim_artists: Optional[dict] = None

def _build_similarity_index():
    global _sim_matrix, _sim_ids, _sim_id_to_idx, _sim_artists
    if _sim_matrix is not None:
        return

    conn = trackdb.get_db()
    rows = conn.execute('''
        SELECT tf.track_id, t.artist, tf.feature_data
        FROM track_features tf
        JOIN tracks t ON tf.track_id = t.id
        WHERE t.x IS NOT NULL AND t.status IN ('DOWNLOADED', 'INDEXED')
    ''').fetchall()
    conn.close()

    ids = []
    artists = []
    vectors = []
    for row in rows:
        features = json.loads(row[2])
        embedding = features.get("clap_embedding")
        if embedding and len(embedding) == 512:
            ids.append(row[0])
            artists.append(row[1] or "")
            vectors.append(embedding)

    if not vectors:
        return

    mat = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1
    _sim_matrix = mat / norms
    _sim_ids = ids
    _sim_id_to_idx = {tid: i for i, tid in enumerate(ids)}
    _sim_artists = {tid: artists[i] for i, tid in enumerate(ids)}

@app.get("/api/neighbors/{track_id}", response_model=List[SimilarTrack])
def get_neighbors(track_id: str, artist_boost: float = 0.15):
    """
    Returns the 10 most sonically similar tracks using cosine similarity
    on the full 512-dimensional CLAP embeddings (pre-UMAP).

    artist_boost: 0-1. Adds this amount to same-artist tracks to surface
    more from the same artist (e.g. HXVRMXN - HIGH ABOVE → HI-END 2000).
    Default 0.15. Set to 0 to disable.
    """
    _build_similarity_index()

    if _sim_matrix is None or track_id not in _sim_id_to_idx:
        raise HTTPException(status_code=404, detail="Track embedding not found")

    idx = _sim_id_to_idx[track_id]
    query_artist = _sim_artists.get(track_id, "")

    similarities = _sim_matrix @ _sim_matrix[idx]
    # Fetch more candidates so we can re-rank with artist boost
    n_candidates = 50 if artist_boost > 0 else 11
    top_indices = np.argsort(similarities)[::-1][:n_candidates]

    # Apply artist boost: same-artist tracks get a boost
    if artist_boost > 0 and query_artist:
        boosted = []
        for i in top_indices:
            sid = _sim_ids[i]
            if sid == track_id:
                continue
            sim = float(similarities[i])
            if _sim_artists.get(sid, "") == query_artist:
                sim += artist_boost
            boosted.append((i, sim))
        boosted.sort(key=lambda x: x[1], reverse=True)
        top_indices = [x[0] for x in boosted][:11]

    conn = trackdb.get_db()
    results = []
    for i in top_indices:
        sid = _sim_ids[i]
        if sid == track_id:
            continue
        row = conn.execute(
            'SELECT artist, title, x, y, url FROM tracks WHERE id = ?', (sid,)
        ).fetchone()
        if not row or row[2] is None:
            continue
        results.append({
            "id": sid,
            "artist": row[0] or "",
            "title": row[1] or "",
            "x": row[2],
            "y": row[3],
            "url": row[4] or "",
            "match_pct": round(float(similarities[i]) * 100, 1),
        })

    conn.close()
    return results[:10]

@app.get("/api/track/{track_id}", response_model=TrackMetadata)
def get_track_metadata(track_id: str):
    """
    Lazy-loads full metadata for a single track. Called by the frontend 
    only when a star becomes the Focal Node.
    """
    conn = trackdb.get_db()
    track = trackdb.get_track(conn, track_id)
    conn.close()
    
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
        
    return TrackMetadata(
        id=track["id"],
        artist=track["artist"],
        title=track["title"],
        url=track.get("url"),
        status=track["status"]
    )

class TagZone(BaseModel):
    tag: str
    x: float
    y: float
    count: int

@app.get("/api/tag-zones", response_model=List[TagZone])
def get_tag_zones():
    """
    Divides the universe into a 3x3 grid using quantile-based splits so each
    cell has roughly equal track density, then returns the dominant tag per cell.
    """
    conn = trackdb.get_db()
    rows = conn.execute('''
        SELECT x, y, tags FROM tracks
        WHERE status = 'INDEXED' AND tags IS NOT NULL AND tags != '[]' AND x IS NOT NULL
    ''').fetchall()
    conn.close()

    if not rows:
        return []

    tracks_data = [(row[0], row[1], json.loads(row[2])) for row in rows]
    xs_all = sorted(t[0] for t in tracks_data)
    ys_all = sorted(t[1] for t in tracks_data)

    n = len(xs_all)
    x_cuts = [xs_all[0] - 1, xs_all[n // 3], xs_all[2 * n // 3], xs_all[-1] + 1]
    y_cuts = [ys_all[0] - 1, ys_all[n // 3], ys_all[2 * n // 3], ys_all[-1] + 1]

    cells = []
    for i in range(3):
        for j in range(3):
            x_lo, x_hi = x_cuts[i], x_cuts[i + 1]
            y_lo, y_hi = y_cuts[j], y_cuts[j + 1]

            tag_counts: dict[str, int] = defaultdict(int)
            cell_xs, cell_ys = [], []
            for x, y, tags in tracks_data:
                if x_lo <= x < x_hi and y_lo <= y < y_hi:
                    cell_xs.append(x)
                    cell_ys.append(y)
                    for tag in tags:
                        tag_counts[tag] += 1

            if tag_counts:
                ranked = sorted(tag_counts.items(), key=lambda t: -t[1])
                median_x = statistics.median(cell_xs)
                median_y = statistics.median(cell_ys)
                cells.append((ranked, median_x, median_y))

    cells.sort(key=lambda c: -c[0][0][1])

    used_tags: set[str] = set()
    zones = []
    for ranked, cx, cy in cells:
        for tag, count in ranked:
            if tag not in used_tags:
                used_tags.add(tag)
                zones.append(TagZone(tag=tag, x=cx, y=cy, count=count))
                break

    return zones

@app.get("/api/audio/{track_id}")
def get_track_audio(track_id: str):
    """
    Streams the raw .mp3 snippet to the frontend HTML5 Audio Player.
    Downloads it explicitly if it does not exist locally.
    """
    # Use a dedicated cache directory for the API
    cache_dir = "data/api_audio_cache"
    os.makedirs(cache_dir, exist_ok=True)
    file_path = os.path.join(cache_dir, f"{track_id}.mp3")
    
    if not os.path.exists(file_path):
        conn = trackdb.get_db()
        track = trackdb.get_track(conn, track_id)
        conn.close()
        
        if not track or not track.get("url"):
            raise HTTPException(status_code=404, detail="Track URL not found")
            
        try:
            result = download_single(track["url"], output_dir=cache_dir)
            # Rename to {track_id}.mp3 so the cache check works on next request
            if result["file_path"] != file_path:
                os.rename(result["file_path"], file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to download audio: {str(e)}")
            
    return FileResponse(file_path, media_type="audio/mpeg", headers={"Accept-Ranges": "bytes"})

# ---------------------------------------------------------------------------
# Projects (per-user, SQL-backed)
# ---------------------------------------------------------------------------

MAX_PROJECT_SLOTS = 5


class ProjectCreate(BaseModel):
    name: str
    slot: int  # 1-5


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    playlist_urls: Optional[List[str]] = None


def _load_user_project(user_id: str, slot: int) -> Optional[dict]:
    conn = trackdb.get_db()
    row = conn.execute(
        "SELECT * FROM projects WHERE user_id = ? AND slot = ?", (user_id, slot)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["playlist_urls"] = json.loads(d.get("playlist_urls", "[]"))
    return d


def _save_user_project(user_id: str, slot: int, name: str, playlist_urls: list):
    conn = trackdb.get_db()
    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT id FROM projects WHERE user_id = ? AND slot = ?", (user_id, slot)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE projects SET name = ?, playlist_urls = ?, updated_at = ? WHERE user_id = ? AND slot = ?",
            (name, json.dumps(playlist_urls), now, user_id, slot),
        )
    else:
        project_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO projects (id, user_id, slot, name, playlist_urls, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, user_id, slot, name, json.dumps(playlist_urls), now, now),
        )
    conn.commit()
    conn.close()


@app.get("/api/projects")
def list_projects(user: UserClaims = Depends(get_current_user)):
    """Returns all 5 project slots for the current user (null if empty)."""
    slots = []
    for i in range(1, MAX_PROJECT_SLOTS + 1):
        proj = _load_user_project(user.user_id, i)
        slots.append({"slot": i, "project": proj})
    return slots


@app.get("/api/projects/{slot}")
def get_project(slot: int, user: UserClaims = Depends(get_current_user)):
    if slot < 1 or slot > MAX_PROJECT_SLOTS:
        raise HTTPException(status_code=400, detail=f"Slot must be 1-{MAX_PROJECT_SLOTS}")
    proj = _load_user_project(user.user_id, slot)
    if not proj:
        raise HTTPException(status_code=404, detail="Empty slot")
    return proj


@app.post("/api/projects")
def create_project(req: ProjectCreate, user: UserClaims = Depends(get_current_user)):
    if req.slot < 1 or req.slot > MAX_PROJECT_SLOTS:
        raise HTTPException(status_code=400, detail=f"Slot must be 1-{MAX_PROJECT_SLOTS}")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Project name is required")
    existing = _load_user_project(user.user_id, req.slot)
    if existing:
        raise HTTPException(status_code=409, detail="Slot already occupied")
    _save_user_project(user.user_id, req.slot, req.name.strip(), [])
    return _load_user_project(user.user_id, req.slot)


@app.patch("/api/projects/{slot}")
def update_project(slot: int, req: ProjectUpdate, user: UserClaims = Depends(get_current_user)):
    if slot < 1 or slot > MAX_PROJECT_SLOTS:
        raise HTTPException(status_code=400, detail=f"Slot must be 1-{MAX_PROJECT_SLOTS}")
    proj = _load_user_project(user.user_id, slot)
    if not proj:
        raise HTTPException(status_code=404, detail="Empty slot")
    name = req.name.strip() if req.name is not None else proj["name"]
    urls = req.playlist_urls if req.playlist_urls is not None else proj["playlist_urls"]
    _save_user_project(user.user_id, slot, name, urls)
    return _load_user_project(user.user_id, slot)


@app.delete("/api/projects/{slot}")
def delete_project(slot: int, user: UserClaims = Depends(get_current_user)):
    if slot < 1 or slot > MAX_PROJECT_SLOTS:
        raise HTTPException(status_code=400, detail=f"Slot must be 1-{MAX_PROJECT_SLOTS}")
    conn = trackdb.get_db()
    conn.execute("DELETE FROM projects WHERE user_id = ? AND slot = ?", (user.user_id, slot))
    conn.commit()
    conn.close()
    return {"status": "deleted", "slot": slot}


# ---------------------------------------------------------------------------
# Spotify OAuth + Playlist Import
# ---------------------------------------------------------------------------

_import_progress: dict[str, object] = {}  # keyed by user_id
_import_lock = threading.Lock()


class SpotifyImportRequest(BaseModel):
    playlist_ids: List[str]
    project_slot: Optional[int] = None


@app.get("/api/spotify/login")
def spotify_login():
    from deepkt.spotify import get_auth_url
    return RedirectResponse(url=get_auth_url())


@app.get("/api/spotify/callback")
def spotify_callback(code: str):
    from fastapi.responses import HTMLResponse
    from deepkt.spotify import handle_callback
    success = handle_callback(code)
    status = "connected" if success else "error"
    return HTMLResponse(f"""<!DOCTYPE html><html><body><script>
        if (window.opener) {{
            window.opener.postMessage({{ type: "spotify-auth", status: "{status}" }}, "*");
            window.close();
        }} else {{
            window.location.href = "{os.environ.get("FRONTEND_URL", "http://localhost:3000")}?spotify={status}";
        }}
    </script><p>Authenticating... you can close this window.</p></body></html>""")


@app.post("/api/spotify/logout")
def spotify_logout(user: UserClaims = Depends(get_current_user)):
    """Clear the cached Spotify token."""
    from deepkt.spotify import logout
    logout()
    return {"status": "logged_out"}


@app.get("/api/spotify/auth-check")
def spotify_auth_check():
    """Lightweight check: is the backend holding a valid Spotify token?"""
    from deepkt.spotify import is_authenticated
    return {"authenticated": is_authenticated()}


@app.get("/api/spotify/playlists")
def spotify_playlists(user: UserClaims = Depends(get_current_user)):
    from deepkt.spotify import is_authenticated, get_user_playlists
    if not is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated with Spotify")
    try:
        return get_user_playlists()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Spotify API error: {e}")


@app.post("/api/spotify/import")
def spotify_import(req: SpotifyImportRequest, user: UserClaims = Depends(get_current_user)):
    from deepkt.spotify import is_authenticated, get_playlist_tracks
    from deepkt.cross_reference import CrossRefProgress

    if not is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated with Spotify")

    with _import_lock:
        existing = _import_progress.get(user.user_id)
        if existing and existing.state == "running":
            raise HTTPException(status_code=409, detail="Import already in progress")

    progress = CrossRefProgress()

    project_slot = req.project_slot
    uid = user.user_id
    playlist_ids = list(req.playlist_ids)

    def _run():
        try:
            from deepkt.cross_reference import cross_reference_tracks, save_seed_artists

            # Fetch tracks inside the background thread to avoid request timeout
            all_tracks: list[dict] = []
            for pid in playlist_ids:
                if progress.cancelled:
                    progress.state = "done"
                    return
                try:
                    tracks = get_playlist_tracks(pid)
                    print(f"[import] playlist {pid}: {len(tracks)} tracks")
                    all_tracks.extend(tracks)
                except Exception as e:
                    print(f"[import] playlist {pid} failed: {e}")

            if not all_tracks:
                progress.error = "No tracks found in the selected playlists"
                progress.state = "done"
                return

            cross_reference_tracks(all_tracks, rate_limit=1.0, progress=progress)
            if not progress.cancelled:
                save_seed_artists(progress)
                # Save matched artist URLs to project if a slot was specified
                if project_slot and 1 <= project_slot <= MAX_PROJECT_SLOTS:
                    proj = _load_user_project(uid, project_slot)
                    if proj:
                        existing_urls = set(proj.get("playlist_urls", []))
                        for m in progress.matched:
                            existing_urls.add(m["sc_url"])
                        _save_user_project(uid, project_slot, proj["name"], list(existing_urls))
        except Exception as e:
            import traceback
            traceback.print_exc()
            progress.error = f"{type(e).__name__}: {e}"
            progress.state = "done"

    with _import_lock:
        _import_progress[user.user_id] = progress

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"status": "started", "total_tracks": 0}


@app.get("/api/spotify/status")
def spotify_status(user: UserClaims = Depends(get_current_user)):
    progress = _import_progress.get(user.user_id)
    if progress is None:
        return {"state": "idle", "total": 0, "processed": 0, "matched_count": 0, "unmatched_count": 0, "matched": [], "unmatched": [], "error": ""}
    return progress.to_dict()


@app.post("/api/spotify/abort")
def spotify_abort(user: UserClaims = Depends(get_current_user)):
    progress = _import_progress.get(user.user_id)
    if progress and progress.state == "running":
        progress.cancelled = True
    return {"status": "aborted"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=True)
