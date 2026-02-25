import traceback
from deepkt.indexer import query_similar_weighted
from deepkt.interpreter import SonicInterpreter
from deepkt import db as trackdb
from deepkt.config import get_feature_weights

def mock_flow():
    conn = trackdb.get_db("data/tracks.db")
    all_features = trackdb.get_all_features(conn)
    conn.close()
    
    kanjo_track = next((t for t in all_features if "KANJO" in t["title"].upper() or "KANJO" in t["artist"].upper()), None)
    if not kanjo_track:
        print("Kanjo not found")
        return
        
    print("Found:", kanjo_track["track_id"])
    
    try:
        # 1. render_feature_breakdown
        interpreter = SonicInterpreter("data/tracks.db")
        interpreter.interpret(kanjo_track["feature_data"])
        print("Interpreter ok")
        
        # 2. query_similar_weighted
        weights = get_feature_weights()
        results = query_similar_weighted(
            kanjo_track["feature_data"], 
            weights, 
            n_results=5, 
            exclude_id=kanjo_track["track_id"]
        )
        print("Query ok. Found", len(results))
        
        # 3. render_results
        conn = trackdb.get_db("data/tracks.db")
        for r in results:
            features = trackdb.get_features(conn, r['id'])
            if features:
                interpreter.interpret(features)
        conn.close()
        print("Render ok.")
    except Exception as e:
        traceback.print_exc()

mock_flow()
