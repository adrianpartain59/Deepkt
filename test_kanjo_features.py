from deepkt import db as trackdb
conn = trackdb.get_db("data/tracks.db")
all_features = trackdb.get_all_features(conn)
kanjo_track = next((t for t in all_features if "KANJO" in t["title"].upper() or "KANJO" in t["artist"].upper()), None)
if kanjo_track:
    for k, v in kanjo_track["feature_data"].items():
        if len(v) == 0:
            print(f"Feature {k} is empty!")
        # check for NaN or Inf
        import math
        if any(math.isnan(x) for x in v):
            print(f"Feature {k} contains NaN!")
else:
    print("Not found")
