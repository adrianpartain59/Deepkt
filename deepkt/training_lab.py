import random
import numpy as np
import queue

from deepkt import db as trackdb
from deepkt.analyzer import build_search_vector
from deepkt.indexer import get_collection

# Global variables for thread-safe UI communication
LAB_BATCH_QUEUE = queue.Queue()
LAB_IS_LOADING = False

def get_random_anchor(conn):
    """Pick a random track that has INDEXED status and hasn't already been used as an anchor."""
    row = conn.execute('''
        SELECT id, artist, title, url 
        FROM tracks 
        WHERE status = 'INDEXED' 
          AND url IS NOT NULL 
          AND id NOT IN (SELECT DISTINCT anchor_id FROM training_pairs)
        ORDER BY RANDOM() LIMIT 1
    ''').fetchone()
    
    if not row:
        return None
        
    return {
        "track_id": row["id"],
        "artist": row["artist"],
        "title": row["title"],
        "url": row["url"]
    }

def get_hard_candidates(anchor_track, n=10):
    """
    Find the tracks most similar to the anchor using ChromaDB.
    These are the 'hard' candidates because the model currently thinks they belong together.
    """
    conn = trackdb.get_db()
    
    # Load anchor embedding to perform the search
    row = conn.execute(
        "SELECT feature_data FROM track_features WHERE track_id = ?",
        (anchor_track["track_id"],)
    ).fetchone()
    # Find all track IDs that have already been labeled against this anchor
    labeled_rows = conn.execute(
        "SELECT candidate_id FROM training_pairs WHERE anchor_id = ?",
        (anchor_track["track_id"],)
    ).fetchall()
    labeled_ids = {r[0] for r in labeled_rows}
    conn.close()
    
    if not row:
        return []

    import json
    feature_dict = json.loads(row["feature_data"])
    search_vector = build_search_vector(feature_dict)

    collection = get_collection()
    
    # We fetch more than we need in case many are already labeled
    results = collection.query(
        query_embeddings=[search_vector],
        n_results=n + 50, # generous buffer
    )

    candidates = []
    
    if results and results["ids"] and len(results["ids"][0]) > 0:
        ids = results["ids"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for i in range(len(ids)):
            t_id = ids[i]
            
            # Skip the anchor itself, and skip any tracks we've already labeled
            if t_id == anchor_track["track_id"] or t_id in labeled_ids:
                continue
                
            meta = metadatas[i]
            dist = distances[i]
            
            candidates.append({
                "track_id": t_id,
                "artist": meta.get("artist", "Unknown"),
                "title": meta.get("title", "Unknown"),
                "url": meta.get("url", ""),
                "distance": float(dist)
            })
            
            if len(candidates) == n:
                break
                
    return candidates

def generate_training_batch(tmp_dir):
    """
    Worker function to fetch an anchor, find its 10 closest candidates,
    download all 11 audio clips, and base64 encode them for instant UI rendering.
    Returns a dictionary representing a complete, ready-to-render batch.
    """
    from deepkt.downloader import download_single
    from app import encode_clip_b64 # Reuse the base64 encoder from app.py
    import os

    conn = trackdb.get_db()
    anchor = get_random_anchor(conn)
    if not anchor:
        return None
        
    candidates = get_hard_candidates(anchor, n=10)
    
    # helper
    def fetch_and_encode(url):
        try:
            res = download_single(url, output_dir=tmp_dir)
            if res and res.get("file_path") and os.path.exists(res["file_path"]):
                return encode_clip_b64(res["file_path"])
        except Exception:
            pass
        return None

    # Fetch anchor audio
    anchor_b64 = None
    if anchor.get("url"):
        anchor_b64 = fetch_and_encode(anchor["url"])
        
    # Fetch candidate audios
    batch_candidates = []
    for cand in candidates:
        cand_b64 = None
        if cand.get("url"):
            cand_b64 = fetch_and_encode(cand["url"])
            
        if cand_b64: # Only include candidates we successfully got audio for
            batch_candidates.append({
                "track": cand,
                "b64": cand_b64
            })

    return {
        "anchor": anchor,
        "anchor_b64": anchor_b64,
        "candidates": batch_candidates
    }

def auto_balance_batch(anchor_id):
    """
    Called when a batch finishes. Checks if the user provided enough positive and negative labels.
    - If positive count < 5, injects tracks by the same artist as Positives.
    - If negative count < 5, injects the farthest tracks in the vector space as Negatives.
    """
    conn = trackdb.get_db()
    
    # --- 1. POSITIVE BALANCING ---
    pos_count = conn.execute(
        "SELECT COUNT(*) FROM training_pairs WHERE anchor_id = ? AND label = 1",
        (anchor_id,)
    ).fetchone()[0]
    
    pos_needed = 5 - pos_count
    if pos_needed > 0:
        artist_row = conn.execute("SELECT artist FROM tracks WHERE id = ?", (anchor_id,)).fetchone()
        if artist_row:
            anchor_artist = artist_row[0]
            auto_candidates = conn.execute('''
                SELECT id FROM tracks 
                WHERE artist = ? 
                  AND status = 'INDEXED' 
                  AND id != ?
                  AND id NOT IN (SELECT candidate_id FROM training_pairs WHERE anchor_id = ?)
                ORDER BY RANDOM() LIMIT ?
            ''', (anchor_artist, anchor_id, anchor_id, pos_needed)).fetchall()
            
            for cand in auto_candidates:
                try:
                    conn.execute(
                        "INSERT INTO training_pairs (anchor_id, candidate_id, label) VALUES (?, ?, ?)",
                        (anchor_id, cand[0], 1)
                    )
                except trackdb.sqlite3.Error:
                    pass
    
    # --- 2. NEGATIVE BALANCING ---
    neg_count = conn.execute(
        "SELECT COUNT(*) FROM training_pairs WHERE anchor_id = ? AND label = 0",
        (anchor_id,)
    ).fetchone()[0]
    
    neg_needed = 5 - neg_count
    if neg_needed > 0:
        # We need to find tracks that are mathematically as far away as possible
        # We'll pull 150 documents from Chroma and grab the ones at the very end
        row = conn.execute(
            "SELECT feature_data FROM track_features WHERE track_id = ?",
            (anchor_id,)
        ).fetchone()
        
        if row:
            import json
            from deepkt.analyzer import build_search_vector
            from deepkt.indexer import get_collection
            
            feature_dict = json.loads(row["feature_data"])
            search_vector = build_search_vector(feature_dict)
            
            collection = get_collection()
            results = collection.query(
                query_embeddings=[search_vector],
                n_results=150
            )
            
            if results and results["ids"] and len(results["ids"][0]) > 0:
                # We want the highest distances (last elements)
                ids = results["ids"][0]
                
                # Fetch what's already labeled to avoid injecting known tracks
                labeled_rows = conn.execute(
                    "SELECT candidate_id FROM training_pairs WHERE anchor_id = ?",
                    (anchor_id,)
                ).fetchall()
                labeled_ids = {r[0] for r in labeled_rows}
                
                injected = 0
                # Iterate backwards from the worst possible matches
                for i in range(len(ids) - 1, -1, -1):
                    t_id = ids[i]
                    if t_id != anchor_id and t_id not in labeled_ids:
                        try:
                            conn.execute(
                                "INSERT INTO training_pairs (anchor_id, candidate_id, label) VALUES (?, ?, ?)",
                                (anchor_id, t_id, 0)
                            )
                            injected += 1
                        except trackdb.sqlite3.Error:
                            pass
                        
                        if injected >= neg_needed:
                            break

    conn.commit()
    conn.close()
