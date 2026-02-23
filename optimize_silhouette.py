import numpy as np
from deepkt import db as trackdb
from deepkt.config import get_enabled_features
from deepkt.features import EXTRACTOR_REGISTRY
import scipy.optimize
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

def evaluate_silhouette(weights, stored_norm, weight_indices, n_clusters=8):
    # Build weight vector
    w_vec = np.zeros(stored_norm.shape[1])
    for w_idx, (start, end) in enumerate(weight_indices):
        w_vec[start:end] = weights[w_idx]
        
    # Apply weights
    weighted = stored_norm * w_vec
    
    # We want to use Cosine distance, but KMeans typically uses Euclidean.
    # To mimic Cosine distance in KMeans, we can L2-normalize the data points first.
    norms = np.linalg.norm(weighted, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    normalized = weighted / norms

    # Run KMeans
    # n_init=5 to be robust but fast
    kmeans = KMeans(n_clusters=n_clusters, n_init=5, random_state=42)
    labels = kmeans.fit_predict(normalized)
    
    # Calculate Silhouette Score using Cosine metric
    # The silhouette score ranges from -1 to 1. Higher is better.
    try:
        score = silhouette_score(normalized, labels, metric='cosine')
    except Exception:
        score = -1.0
        
    # We want to maximize score, so return -score for the minimizer
    return -score

def optimize():
    conn = trackdb.get_db("data/tracks.db")
    all_tracks = trackdb.get_all_features(conn)
    conn.close()

    if not all_tracks:
        print("No tracks found.")
        return

    enabled = get_enabled_features()
    
    print(f"Loaded {len(all_tracks)} tracks. Optimizing weights for {len(enabled)} features with Silhouette Score...")

    # Build raw vectors
    stored_vectors = []
    
    for track in all_tracks:
        raw = []
        for feat_name in enabled:
            raw.extend(track["feature_data"].get(feat_name, []))
        stored_vectors.append(raw)

    stored_matrix = np.array(stored_vectors, dtype=np.float64)

    # Pre-calculate z-score nomalization
    mean = stored_matrix.mean(axis=0)
    std = stored_matrix.std(axis=0)
    std[std == 0] = 1.0 
    stored_norm = (stored_matrix - mean) / std

    # Map features to column indices
    weight_indices = []
    current_idx = 0
    for feat_name in enabled:
        dims = EXTRACTOR_REGISTRY[feat_name]().dimensions
        weight_indices.append((current_idx, current_idx + dims))
        current_idx += dims

    # Baseline Score (all weights = 1.0)
    baseline_weights = np.ones(len(enabled))
    baseline_score = -evaluate_silhouette(baseline_weights, stored_norm, weight_indices, n_clusters=8)
    print(f"Baseline Silhouette Score (all 1.0): {baseline_score:.4f}")
        
    # Bound parameters away from 0 to prevent feature collapse
    bounds = [(0.1, 3.0) for _ in enabled]
    
    print("Running Differential Evolution... this will evaluate hundreds of weight matrices...")
    result = scipy.optimize.differential_evolution(
        evaluate_silhouette,
        bounds,
        args=(stored_norm, weight_indices, 8), # 8 clusters for 56 tracks (~7 tracks/cluster)
        maxiter=100,  # lower maxiter for faster testing
        popsize=15,
        tol=0.01,
        disp=True
    )

    print("\noptimization finished!")
    optimized_score = -result.fun
    print(f"Optimized Silhouette Score: {optimized_score:.4f} (vs Baseline: {baseline_score:.4f})")
    print("\nOptimal Weights:")
    
    for i, w in enumerate(result.x):
        print(f"  {enabled[i]}: {w:.2f}")

if __name__ == "__main__":
    optimize()
