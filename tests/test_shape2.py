from deepkt import db as trackdb
from deepkt.config import get_enabled_features

conn = trackdb.get_db("data/tracks.db")
tracks = trackdb.get_all_features(conn)
enabled = get_enabled_features()

print("Enabled features:", enabled)
for t in tracks:
    raw_dim = sum(len(t["feature_data"].get(f, [])) for f in enabled)
    if raw_dim != 43:
        print(f"Track {t['track_id']} has dim {raw_dim}")

import math
for t in tracks:
    for f in enabled:
        v = t["feature_data"].get(f, [])
        if len(v) == 0:
            print(f"Track {t['track_id']} has empty feature {f}")
        elif any(math.isnan(x) for x in v):
            print(f"Track {t['track_id']} has NaN in feature {f}")
