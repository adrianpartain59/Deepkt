import json
import numpy as np
from deepkt import db as trackdb
from deepkt.config import get_enabled_features
from deepkt.features import EXTRACTOR_REGISTRY
import scipy.optimize

def evaluate_anchors(weights, stored_norm, weight_indices, anchor_indices):
    """
    Score a specific weight combination based on Anchor Pairs.
    We want to MINIMIZE the distance between the anchor pairs.
    """
    # Build weight vector
    w_vec = np.zeros(stored_norm.shape[1])
    for w_idx, (start, end) in enumerate(weight_indices):
        w_vec[start:end] = weights[w_idx]
        
    # Apply weights
    weighted = stored_norm * w_vec
    
    # Calculate pairwise Cosine distances
    norms = np.linalg.norm(weighted, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    normalized = weighted / norms
    
    # We want to reward the algorithm for pulling the pairs as close together as possible.
    total_distance = 0.0
    for idx1, idx2 in anchor_indices:
        vec1 = normalized[idx1]
        vec2 = normalized[idx2]
        # Cosine distance = 1 - dot product
        sim = np.dot(vec1, vec2)
        dist = 1.0 - sim
        total_distance += dist
        
    # Sparsity Penalty (L2 Regularization)
    # Punish the algorithm for deviating wildly from the baseline 1.0 unless 
    # it significantly improves the core distance. This prevents it from just 
    # turning features off (0.0) to cheat the metric.
    regularization = np.sum((w_vec - 1.0)**2) * 0.1
        
    # We return the total distance because the minimizer wants to find the lowest possible number.
    return total_distance + regularization

def optimize():
    # 1. Load the Ground Truth Pairs
    try:
        with open("anchor_pairs.json", "r") as f:
            anchor_pairs = json.load(f)
    except FileNotFoundError:
        print("Error: anchor_pairs.json not found.")
        return

    # 2. Load the database
    conn = trackdb.get_db("data/tracks.db")
    all_tracks = trackdb.get_all_features(conn)
    conn.close()

    if not all_tracks:
        print("No tracks found.")
        return

    enabled = get_enabled_features()
    
    print(f"Loaded {len(all_tracks)} tracks. Optimizing {len(enabled)} features using {len(anchor_pairs)} Anchor Pairs...")

    # Build raw vectors and map track names to indices
    stored_vectors = []
    track_ids = []
    
    for track in all_tracks:
        raw = []
        for feat_name in enabled:
            raw.extend(track["feature_data"].get(feat_name, []))
        stored_vectors.append(raw)
        # Assuming the ID in the DB is the filename
        track_ids.append(track["track_id"])

    stored_matrix = np.array(stored_vectors, dtype=np.float64)

    # Convert anchor pair names to indices in the matrix
    anchor_indices = []
    for pair in anchor_pairs:
        try:
            idx1 = track_ids.index(pair[0])
            idx2 = track_ids.index(pair[1])
            anchor_indices.append((idx1, idx2))
        except ValueError as e:
            print(f"Warning: Could not find track in DB: {e}")
            continue

    if not anchor_indices:
        print("No valid anchor pairs found in the database. Aborting.")
        return

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
    baseline_distance = evaluate_anchors(baseline_weights, stored_norm, weight_indices, anchor_indices)
    print(f"Baseline Anchor Distance (all 1.0): {baseline_distance:.4f} (Lower is better)")
        
    # Bound parameters away from 0 to prevent feature collapse
    # We enforce a strict 0.3 minimum so it physically cannot turn features completely off.
    bounds = [(0.3, 5.0) for _ in enabled]
    
    print("Running Differential Evolution... this maps the mathematical gravity to the human pairs.")
    result = scipy.optimize.differential_evolution(
        evaluate_anchors,
        bounds,
        args=(stored_norm, weight_indices, anchor_indices),
        maxiter=150,
        popsize=20,
        tol=0.001,
        disp=True
    )

    print("\noptimization finished!")
    optimized_distance = result.fun
    print(f"Optimized Anchor Distance: {optimized_distance:.4f} (vs Baseline: {baseline_distance:.4f})")
    print("\nOptimal Weights:")
    
    for i, w in enumerate(result.x):
        print(f"  {enabled[i]}: {w:.4f}")

if __name__ == "__main__":
    optimize()
