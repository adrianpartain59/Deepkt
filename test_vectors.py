import numpy as np
from deepkt import db as trackdb
from deepkt.analyzer import build_search_vector

conn = trackdb.get_db("data/tracks.db")
tracks = trackdb.get_all_features(conn)
conn.close()

if len(tracks) >= 2:
    v1 = build_search_vector(tracks[0]["feature_data"])
    v2 = build_search_vector(tracks[1]["feature_data"])
    
    print(f"Track 1: {tracks[0]['title']}")
    print(f"Track 2: {tracks[1]['title']}")
    
    is_same = np.allclose(v1, v2)
    print("Are vectors identical?", is_same)
    
    if not is_same:
        cos_sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        print("Cosine similarity:", cos_sim)
