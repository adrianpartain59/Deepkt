from deepkt.indexer import query_similar_weighted
from deepkt import db as trackdb

conn = trackdb.get_db("data/tracks.db")
all_features = trackdb.get_all_features(conn)
conn.close()

# The weights outputted by scipy DE
optimal_weights = {
    'chroma': 0.01,
    'mfcc': 0.56,
    'onset_strength': 0.77,
    'rms_energy': 1.44,
    'spectral_centroid': 0.94,
    'spectral_contrast': 1.41,
    'tempo': 2.57,
    'tonnetz': 0.16,
    'zero_crossing_rate': 1.70,
}

kanjo_track = next((t for t in all_features if "KANJO KILLA" in t["title"].upper()), None)
if kanjo_track:
    print(f"--- QUERY: {kanjo_track['artist']} - {kanjo_track['title']} ---")
    results = query_similar_weighted(kanjo_track["feature_data"], optimal_weights, n_results=5, exclude_id=kanjo_track["track_id"])
    for r in results:
        print(f" {r['match_pct']}% - {r['artist']} : {r['title']}")
        
print()

skeler_track = next((t for t in all_features if "skeler" in t["artist"].lower()), None)
if skeler_track:
    print(f"--- QUERY: {skeler_track['artist']} - {skeler_track['title']} ---")
    results = query_similar_weighted(skeler_track["feature_data"], optimal_weights, n_results=5, exclude_id=skeler_track["track_id"])
    for r in results:
        print(f" {r['match_pct']}% - {r['artist']} : {r['title']}")
        
