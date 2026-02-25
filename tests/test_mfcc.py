import numpy as np
from deepkt import db as trackdb
from deepkt.interpreter import SonicInterpreter

conn = trackdb.get_db("data/tracks.db")
tracks = trackdb.get_all_features(conn)
conn.close()

interpreter = SonicInterpreter("data/tracks.db")

print("Timbre Stats bounds:", interpreter.stats.get("Timbre"))

for i, t in enumerate(tracks[:5]):
    mfcc_vals = t["feature_data"]["mfcc"]
    mean_val = np.mean(mfcc_vals)
    analysis = interpreter.interpret(t["feature_data"])
    print(f"{t['title']}: mean={mean_val:.2f}, score={analysis.get('Timbre', 0)}")
