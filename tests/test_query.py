import traceback
from deepkt.indexer import query_similar_weighted
from deepkt import db as trackdb
from deepkt.config import get_feature_weights

conn = trackdb.get_db("data/tracks.db")
all_features = trackdb.get_all_features(conn)
if all_features:
    track = all_features[0]
    weights = get_feature_weights()
    try:
        results = query_similar_weighted(track["feature_data"], weights)
        print("Success, results:", len(results))
    except Exception as e:
        traceback.print_exc()
else:
    print("No tracks indexed.")
