import traceback
from deepkt.indexer import query_similar_weighted
from deepkt import db as trackdb
from deepkt.config import get_feature_weights
from deepkt.interpreter import SonicInterpreter

conn = trackdb.get_db("data/tracks.db")
all_features = trackdb.get_all_features(conn)
conn.close()

kanjo_track = next((t for t in all_features if "KANJO KILLA" in t["title"].upper() or "KANJO KILLA" in t["artist"].upper()), None)

if kanjo_track:
    print(f"Testing interpreter on KANJO KILLA")
    try:
        interpreter = SonicInterpreter("data/tracks.db")
        analysis = interpreter.interpret(kanjo_track["feature_data"])
        print("Analysis ok:", analysis.keys())
        
        weights = get_feature_weights()
        results = query_similar_weighted(kanjo_track["feature_data"], weights)
        print("Similar tracks ok:", len(results))
    except Exception as e:
        traceback.print_exc()
else:
    print("Not found")
