import traceback
from deepkt.indexer import query_similar_weighted
from deepkt.interpreter import SonicInterpreter
from deepkt import db as trackdb
from deepkt.config import get_feature_weights

def test_all():
    conn = trackdb.get_db("data/tracks.db")
    all_features = trackdb.get_all_features(conn)
    conn.close()
    
    interpreter = SonicInterpreter("data/tracks.db")
    weights = get_feature_weights()
    print(f"Testing {len(all_features)} tracks")
    
    for t in all_features:
        try:
            # Test interpreter logic
            interpreter.interpret(t["feature_data"])
            # Test find similar
            res = query_similar_weighted(t["feature_data"], weights, n_results=5, exclude_id=t["track_id"])
        except Exception as e:
            print(f"Error on track {t['track_id']}:")
            traceback.print_exc()

test_all()
