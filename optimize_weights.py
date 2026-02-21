import numpy as np
from deepkt import db as trackdb
from deepkt.config import get_enabled_features
from deepkt.features import EXTRACTOR_REGISTRY
import scipy.optimize

def evaluate_weights(weights, stored_norm, weight_indices, artist_labels, k=4):
    """
    Score a specific weight combination. 
    Higher score is better (returns negative score for scipy minimizer).
    """
    # Build weight vector
    w_vec = np.zeros(stored_norm.shape[1])
    for w_idx, (start, end) in enumerate(weight_indices):
        w_vec[start:end] = weights[w_idx]
        
    # Apply weights
    weighted = stored_norm * w_vec
    
    USE_COSINE = True
    
    if USE_COSINE:
        # Calculate pairwise Cosine distances
        norms = np.linalg.norm(weighted, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        normalized = weighted / norms
        sims = np.dot(normalized, normalized.T)
        dists = 1.0 - sims
    else:
        # Calculate pairwise Euclidean distances
        diffs = weighted[:, np.newaxis, :] - weighted[np.newaxis, :, :]
        dists = np.sqrt(np.sum(diffs ** 2, axis=2))
    
    # Ensure diagonal is infinity so a track doesn't match itself
    np.fill_diagonal(dists, np.inf)
    
    # Find top K indices for each track
    # argpartition is faster than argsort for just finding top K
    top_k_idx = np.argpartition(dists, k, axis=1)[:, :k]
    
    # Check if they match the artist
    score = 0
    for i in range(len(artist_labels)):
        # Array of artists for the top matches
        match_artists = artist_labels[top_k_idx[i]]
        # Count how many match the query artist
        score += np.sum(match_artists == artist_labels[i])
        
    return -score

def optimize():
    conn = trackdb.get_db("data/tracks.db")
    all_tracks = trackdb.get_all_features(conn)
    conn.close()

    if not all_tracks:
        print("No tracks found.")
        return

    enabled = get_enabled_features()
    
    print(f"Loaded {len(all_tracks)} tracks. Optimizing weights for {len(enabled)} features...")

    # Build raw vectors and labels
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
    baseline_score = -evaluate_weights(baseline_weights, stored_norm, weight_indices, artist_labels)
    print(f"Baseline Score (all 1.0): {baseline_score}")
        
    bounds = [(0.0, 3.0) for _ in enabled]
    
    print("Running Differential Evolution... this might take 1-3 minutes for a deep search...")
    result = scipy.optimize.differential_evolution(
        evaluate_weights,
        bounds,
        args=(stored_norm, weight_indices, artist_labels),
        maxiter=500,
        popsize=50,
        tol=0.001,
        disp=True
    )

    print("\noptimization finished!")
    print(f"Optimized Score: {-result.fun} (vs Baseline: {baseline_score})")
    print("\nOptimal Weights:")
    
    optimal_weights = {}
    for i, w in enumerate(result.x):
        optimal_weights[enabled[i]] = w
        print(f"  {enabled[i]}: {w:.2f}")

    # Save to features.yaml
    from deepkt.config import DEFAULT_CONFIG_PATH
    import re
    
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        lines = f.readlines()
        
    current_feature = None
    for i, line in enumerate(lines):
        # Match a feature block header, e.g. "  mfcc:"
        match = re.match(r"^ *([a-z_]+): *$", line)
        if match:
            current_feature = match.group(1)
            
        # Match the weight setting inside that feature block
        if current_feature in optimal_weights and re.match(r"^ *weight:.*$", line):
            # Preserve original indentation
            indent = line[:len(line) - len(line.lstrip())]
            lines[i] = f"{indent}weight: {optimal_weights[current_feature]:.2f}\n"

    with open(DEFAULT_CONFIG_PATH, "w") as f:
        f.writelines(lines)
        
    print("\n✅ Saved optimal weights to config/features.yaml!")

if __name__ == "__main__":
    optimize()
