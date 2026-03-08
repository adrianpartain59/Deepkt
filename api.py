import json
import os
import statistics
from collections import defaultdict

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from deepkt import db as trackdb
from deepkt.downloader import download_single

app = FastAPI(title="HyperPhonk API")

_cors_origins = [
    "http://localhost:3000",
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

def _build_similarity_index():
    global _sim_matrix, _sim_ids, _sim_id_to_idx
    if _sim_matrix is not None:
        return

    conn = trackdb.get_db()
    rows = conn.execute('''
        SELECT tf.track_id, tf.feature_data
        FROM track_features tf
        JOIN tracks t ON tf.track_id = t.id
        WHERE t.x IS NOT NULL AND t.status IN ('DOWNLOADED', 'INDEXED')
    ''').fetchall()
    conn.close()

    ids = []
    vectors = []
    for row in rows:
        features = json.loads(row[1])
        embedding = features.get("clap_embedding")
        if embedding and len(embedding) == 512:
            ids.append(row[0])
            vectors.append(embedding)

    if not vectors:
        return

    mat = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1
    _sim_matrix = mat / norms
    _sim_ids = ids
    _sim_id_to_idx = {tid: i for i, tid in enumerate(ids)}

@app.get("/api/neighbors/{track_id}", response_model=List[SimilarTrack])
def get_neighbors(track_id: str):
    """
    Returns the 10 most sonically similar tracks using cosine similarity
    on the full 512-dimensional CLAP embeddings (pre-UMAP).
    """
    _build_similarity_index()

    if _sim_matrix is None or track_id not in _sim_id_to_idx:
        raise HTTPException(status_code=404, detail="Track embedding not found")

    idx = _sim_id_to_idx[track_id]
    similarities = _sim_matrix @ _sim_matrix[idx]
    top_indices = np.argsort(similarities)[::-1][:11]

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=True)
