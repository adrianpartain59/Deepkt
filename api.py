import json
import os
import statistics
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from deepkt import db as trackdb
from deepkt.downloader import download_single
from deepkt.indexer import get_collection

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

@app.get("/api/neighbors/{track_id}", response_model=List[SimilarTrack])
def get_neighbors(track_id: str):
    """
    Returns the 10 most sonically similar tracks using cosine similarity
    on the full 512-dimensional CLAP embeddings (pre-UMAP).
    """
    collection = get_collection()
    if collection.count() == 0:
        return []

    # Retrieve the query track's embedding from ChromaDB
    result = collection.get(ids=[track_id], include=["embeddings"])
    if len(result["ids"]) == 0 or result["embeddings"] is None or len(result["embeddings"]) == 0:
        raise HTTPException(status_code=404, detail="Track embedding not found")

    query_embedding = result["embeddings"][0]

    # Query ChromaDB for the most similar tracks (cosine distance)
    similar = collection.query(
        query_embeddings=[query_embedding],
        n_results=11,  # +1 to account for self-match
    )

    # Look up (x, y) coordinates from SQLite for map navigation
    conn = trackdb.get_db()
    results = []
    for sid, distance, meta in zip(
        similar["ids"][0], similar["distances"][0], similar["metadatas"][0]
    ):
        if sid == track_id:
            continue
        row = conn.execute(
            'SELECT x, y FROM tracks WHERE id = ?', (sid,)
        ).fetchone()
        if not row or row[0] is None:
            continue
        similarity = 1 - distance
        results.append({
            "id": sid,
            "artist": meta.get("artist", ""),
            "title": meta.get("title", ""),
            "x": row[0],
            "y": row[1],
            "url": meta.get("url", ""),
            "match_pct": round(similarity * 100, 1),
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
