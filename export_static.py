"""Export pre-computed data from the Deepkt database to JSON for the static viewer.

Run: python export_static.py

Outputs to static_site/ directory:
  - data.json: All track metadata, artist centroids, pre-computed similarity matrix
"""

import json
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from deepkt import db as trackdb
from deepkt.indexer import build_search_vector


def export():
    print("📦 Exporting data for static site...\n")

    conn = trackdb.get_db()
    all_features = trackdb.get_all_features(conn)
    conn.close()

    print(f"   Loaded {len(all_features)} tracks with features")

    # Build artist data
    artist_tracks = {}  # artist -> list of track dicts
    all_tracks_list = []

    for t in all_features:
        vec = build_search_vector(t["feature_data"])
        if vec is None or len(vec) != 512:
            continue

        track_entry = {
            "id": t["track_id"],
            "artist": t["artist"],
            "title": t["title"],
            "url": t["url"],
        }
        all_tracks_list.append(track_entry)

        artist = t["artist"]
        if artist not in artist_tracks:
            artist_tracks[artist] = {"tracks": [], "vecs": []}
        artist_tracks[artist]["tracks"].append(track_entry)
        artist_tracks[artist]["vecs"].append(np.array(vec, dtype=np.float32))

    print(f"   Found {len(artist_tracks)} unique artists")

    # Compute centroids
    artist_centroids = {}
    centroid_list = []
    centroid_artists = []

    for artist, data in artist_tracks.items():
        vecs = np.array(data["vecs"])
        centroid = vecs.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm == 0:
            continue
        centroid_normed = centroid / norm
        artist_centroids[artist] = centroid_normed
        centroid_list.append(centroid_normed)
        centroid_artists.append(artist)

    print(f"   Computed {len(centroid_list)} artist centroids")

    # Compute full artist-to-artist similarity matrix
    centroid_matrix = np.array(centroid_list)  # (N_artists x 512)
    sim_matrix = centroid_matrix @ centroid_matrix.T  # (N_artists x N_artists)

    # For each artist, rank their tracks by centroid similarity
    artist_data_export = []
    for i, artist in enumerate(centroid_artists):
        data = artist_tracks[artist]
        vecs = np.array(data["vecs"])
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs_normed = vecs / norms

        centroid = artist_centroids[artist]
        track_sims = vecs_normed @ centroid

        # Sort tracks by centroid similarity
        sorted_idx = np.argsort(track_sims)[::-1]
        sorted_tracks = []
        for idx in sorted_idx:
            t = data["tracks"][int(idx)]
            t_copy = dict(t)
            t_copy["centroid_sim"] = round(float(track_sims[int(idx)]) * 100, 1)
            sorted_tracks.append(t_copy)

        # Get top 15 similar artists
        sims = sim_matrix[i]
        sorted_artists = np.argsort(sims)[::-1]
        similar = []
        for j in sorted_artists:
            if int(j) == i:
                continue
            if len(similar) >= 15:
                break
            other = centroid_artists[int(j)]
            similar.append({
                "artist": other,
                "similarity": round(float(sims[int(j)]) * 100, 1),
            })

        artist_data_export.append({
            "name": artist,
            "track_count": len(data["tracks"]),
            "tracks": sorted_tracks,
            "similar_artists": similar,
        })

    # Sort artists alphabetically
    artist_data_export.sort(key=lambda x: x["name"].lower())

    # For similar artists, we also need to compute the closest tracks
    # between each pair. We'll do this by looking up the centroid similarity
    # of each track to the query artist's centroid.
    # This is pre-computed per-artist in sorted_tracks already.
    # For the "closest tracks to X's vibe" view, we need the OTHER artist's
    # tracks ranked by similarity to the query centroid.
    # We'll add that data inline.
    
    # Build a lookup: artist_name -> index in centroid_artists
    artist_idx_lookup = {a: i for i, a in enumerate(centroid_artists)}

    for artist_entry in artist_data_export:
        query_artist = artist_entry["name"]
        query_centroid = artist_centroids.get(query_artist)
        if query_centroid is None:
            continue

        for sim_entry in artist_entry["similar_artists"]:
            other_name = sim_entry["artist"]
            other_data = artist_tracks.get(other_name)
            if not other_data:
                continue

            # Compute other's tracks similarity to query centroid
            other_vecs = np.array(other_data["vecs"])
            other_norms = np.linalg.norm(other_vecs, axis=1, keepdims=True)
            other_norms[other_norms == 0] = 1.0
            other_vecs_normed = other_vecs / other_norms
            other_sims = other_vecs_normed @ query_centroid

            sorted_other = np.argsort(other_sims)[::-1]
            top_tracks = []
            for idx in sorted_other[:5]:
                t = other_data["tracks"][int(idx)]
                top_tracks.append({
                    "title": t["title"],
                    "url": t["url"],
                    "similarity": round(float(other_sims[int(idx)]) * 100, 1),
                })
            sim_entry["top_tracks"] = top_tracks

    # Compute per-track similarities (top 10 per track)
    print("   Computing per-track similarities...")
    
    # Build flat vectors + metadata in order
    flat_vecs = []
    flat_meta = []  # index -> {artist, title, url}
    for artist, data in artist_tracks.items():
        for i, t in enumerate(data["tracks"]):
            vec = np.array(data["vecs"][i], dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                flat_vecs.append(vec / norm)
                flat_meta.append(t)

    flat_matrix = np.array(flat_vecs)  # (N_tracks x 512)
    n = len(flat_matrix)
    print(f"   Building {n}x{n} similarity matrix...")

    # Process in batches to avoid memory issues
    BATCH = 500
    TOP_K = 10
    track_similar = [None] * n

    for start in range(0, n, BATCH):
        end = min(start + BATCH, n)
        batch_sims = flat_matrix[start:end] @ flat_matrix.T  # (batch x N)
        
        for bi in range(end - start):
            gi = start + bi  # global index
            sims = batch_sims[bi]
            sims[gi] = -1  # exclude self
            top_idx = np.argpartition(sims, -TOP_K)[-TOP_K:]
            top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]
            
            track_similar[gi] = []
            for j in top_idx:
                t = flat_meta[int(j)]
                track_similar[gi].append({
                    "artist": t["artist"],
                    "title": t["title"],
                    "url": t["url"],
                    "similarity": round(float(sims[int(j)]) * 100, 1),
                })

    # Build flat track export list
    flat_tracks_export = []
    for i, t in enumerate(flat_meta):
        flat_tracks_export.append({
            "artist": t["artist"],
            "title": t["title"],
            "url": t["url"],
            "similar": track_similar[i],
        })

    print(f"   Computed top {TOP_K} similar tracks for {n} tracks")

    # Build output
    output = {
        "total_tracks": len(flat_tracks_export),
        "total_artists": len(artist_data_export),
        "artists": artist_data_export,
        "tracks": flat_tracks_export,
    }

    # Write output
    os.makedirs("static_site", exist_ok=True)
    out_path = os.path.join("static_site", "data.json")
    with open(out_path, "w") as f:
        json.dump(output, f)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"\n✅ Exported to {out_path} ({size_mb:.1f} MB)")
    print(f"   {output['total_tracks']} tracks, {output['total_artists']} artists")
    print(f"   Each track has top {TOP_K} similar tracks")
    print(f"   Each artist has top 15 similar artists with closest tracks")


if __name__ == "__main__":
    export()
