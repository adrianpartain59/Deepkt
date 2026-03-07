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

app = FastAPI(title="HyperPhonk API")

# Allow Next.js frontend to talk to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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

@app.get("/api/neighbors/{track_id}", response_model=List[SearchResult])
def get_neighbors(track_id: str):
    """
    Returns the 10 closest tracks by strict 2D Euclidean distance on the Universe map.
    This guarantees that the sidebar matches exactly what the user sees on the screen.
    """
    conn = trackdb.get_db()
    
    # 1. Get the target track's coordinates
    target = conn.execute('SELECT x, y FROM tracks WHERE id = ?', (track_id,)).fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="Track not found")
        
    tx, ty = target[0], target[1]
    
    # 2. Query for the 10 nearest tracks using squared Euclidean distance for performance
    # SQLite doesn't have a native SQRT function without extensions, but ordering by 
    # squared distance gives the exact same result.
    rows = conn.execute('''
        SELECT id, artist, title, x, y, url,
               ((x - ?) * (x - ?) + (y - ?) * (y - ?)) as dist_sq
        FROM tracks 
        WHERE id != ? AND x IS NOT NULL AND status IN ('DOWNLOADED', 'INDEXED')
        ORDER BY dist_sq ASC
        LIMIT 10
    ''', (tx, tx, ty, ty, track_id)).fetchall()
    conn.close()
    
    # Returning SearchResult (plus URL because the client needs the soundcloud link)
    # We'll extend SearchResult to optionally include URL
    results = [{"id": r[0], "artist": r[1], "title": r[2], "x": r[3], "y": r[4], "url": r[5]} for r in rows]
    return results

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
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
