import numpy as np
import scipy.spatial.distance as dist
import umap
from deepkt import db as trackdb
from deepkt.features import EXTRACTOR_REGISTRY
from deepkt.config import get_enabled_features, get_feature_weights

def evaluate_umap_score(db_path="data/tracks.db"):
    conn = trackdb.get_db(db_path)
    all_features = trackdb.get_all_features(conn)
    conn.close()

    enabled = get_enabled_features()
    weights = get_feature_weights()
    w_vec = np.array([weights.get(f, 1.0) for f in enabled])
    
    # Build data matrix
    tracks = []
    matrix = []
    for t in all_features:
        vec = []
        for feat in enabled:
            val = t["feature_data"].get(feat)
            if isinstance(val, list):
                vec.extend(val)
            else:
                vec.append(val)
        matrix.append(vec)
        tracks.append((t["track_id"], t["artist"], t["title"]))
        
    matrix = np.array(matrix)
    
    # Normalize features (z-score)
    mean = np.mean(matrix, axis=0)
    std = np.std(matrix, axis=0)
    std[std == 0] = 1
    stored_norm = (matrix - mean) / std

    # Build dimension-matched weights
    weight_indices = []
    current_idx = 0
    for feat_name in enabled:
        dims = EXTRACTOR_REGISTRY[feat_name]().dimensions
        weight_indices.append((current_idx, current_idx + dims))
        current_idx += dims

    w_vec_full = np.zeros(stored_norm.shape[1])
    for w_idx, (start, end) in enumerate(weight_indices):
        w_vec_full[start:end] = w_vec[w_idx]

    # Apply optimal genetic weights
    weighted = stored_norm * w_vec_full

    # Fit UMAP
    # UMAP is stochastic; setting random_state for reproducibility
    reducer = umap.UMAP(n_neighbors=5, n_components=3, metric='cosine', random_state=42)
    embedding = reducer.fit_transform(weighted)

    # Calculate Cosine Distances on the UMAP 3D embedding
    norms = np.linalg.norm(embedding, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    normalized = embedding / norms
    sims = np.dot(normalized, normalized.T)
    dists = 1.0 - sims

    np.fill_diagonal(dists, np.inf)

    # Calculate score
    score = 0
    for i, (tid, t_artist, t_title) in enumerate(tracks):
        top_k_idx = np.argsort(dists[i])[:4]
        for idx in top_k_idx:
            match_artist = tracks[idx][1]
            if match_artist == t_artist:
                score += 1

    print(f"UMAP Target Dimensionality: 3")
    print(f"Total Matches in Top 4: {score} / 220")
    if score > 86:
        print("🚀 UMAP beat the 86.0 Euclidean/Cosine ceiling!")
    else:
        print("📉 UMAP scored lower than or equal to 86.0.")

if __name__ == "__main__":
    evaluate_umap_score()
