from deepkt import db as trackdb
from optimize_weights import optimize
from deepkt.config import get_enabled_features
import scipy.optimize
import numpy as np
from optimize_weights import evaluate_weights, EXTRACTOR_REGISTRY

conn = trackdb.get_db("data/tracks.db")
all_tracks = trackdb.get_all_features(conn)
conn.close()

enabled = get_enabled_features()

stored_vectors = []
artist_labels = []

for track in all_tracks:
    raw = []
    for feat_name in enabled:
        raw.extend(track["feature_data"].get(feat_name, []))
    stored_vectors.append(raw)
    artist_labels.append(track["artist"])

stored_matrix = np.array(stored_vectors, dtype=np.float64)
artist_labels = np.array(artist_labels)

mean = stored_matrix.mean(axis=0)
std = stored_matrix.std(axis=0)
std[std == 0] = 1.0 
stored_norm = (stored_matrix - mean) / std

weight_indices = []
current_idx = 0
for feat_name in enabled:
    dims = EXTRACTOR_REGISTRY[feat_name]().dimensions
    weight_indices.append((current_idx, current_idx + dims))
    current_idx += dims

print('Running constrained optimization where chroma and tonnetz are perfectly zeroed...')
bounds = []
for f in enabled:
    if f in ['chroma', 'tonnetz']:
        bounds.append((0.0, 0.0))
    else:
        bounds.append((0.0, 3.0))
        
result = scipy.optimize.differential_evolution(
    evaluate_weights,
    bounds,
    args=(stored_norm, weight_indices, artist_labels),
    maxiter=100,
    popsize=20,
    tol=0.01
)

print(f"Max score achieved when chroma/tonnetz are locked to 0: {-result.fun}")
