import numpy as np
from deepkt import db as trackdb
from deepkt.config import get_enabled_features
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

weights_dict = {
    'chroma': 0.0,
    'mfcc': 0.82,
    'onset_strength': 1.93,
    'rms_energy': 2.87,
    'spectral_centroid': 0.67,
    'spectral_contrast': 0.51,
    'tempo': 2.21,
    'tonnetz': 0.0,
    'zero_crossing_rate': 0.48
}

w_array = np.array([weights_dict[f] for f in enabled])

score = -evaluate_weights(w_array, stored_norm, weight_indices, artist_labels)
print(f"Original optimized score: 57.0")
print(f"Score with Tonnetz and Chroma explicitly zeroed out: {score}")
