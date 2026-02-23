"""
Indexer — Two-layer indexing: full feature store + configurable search index.

Layer 1 (expensive, once): Analyze audio → store ALL features in SQLite
Layer 2 (cheap, minutes): Build ChromaDB search index from stored features
"""

import os
import chromadb
import numpy as np

from deepkt.analyzer import analyze_snippet, build_search_vector
from deepkt.config import get_enabled_features, get_search_dimensions, get_feature_version
from deepkt import db as trackdb

# --- Default paths ---
DEFAULT_DATA_DIR = "data/raw_snippets"
DEFAULT_DB_DIR = "data/chroma_db"
DEFAULT_DB_PATH = "data/tracks.db"


def get_collection(db_dir=DEFAULT_DB_DIR):
    """Get or create the sonic_dna ChromaDB collection.

    Returns:
        ChromaDB Collection configured for cosine similarity.
    """
    client = chromadb.PersistentClient(path=db_dir)
    return client.get_or_create_collection(
        name="sonic_dna",
        metadata={"hnsw:space": "cosine"}
    )


# ============================================================
# Layer 1: Analyze & Store (expensive — runs all extractors)
# ============================================================

def analyze_and_store(data_dir=DEFAULT_DATA_DIR, db_path=DEFAULT_DB_PATH):
    """Analyze all MP3 snippets and store ALL features in SQLite.

    This is the expensive operation — runs every extractor on every
    new track. Only needs to happen once per track.

    Args:
        data_dir: Directory containing MP3 snippets.
        db_path: Path to SQLite database.

    Returns:
        Number of newly analyzed tracks.
    """
    conn = trackdb.get_db(db_path)

    files = [f for f in os.listdir(data_dir) if f.endswith(".mp3")]
    existing = {t["id"] for t in trackdb.get_tracks(conn, status="INDEXED")}
    print(f"Found {len(files)} audio files. {len(existing)} already analyzed.\n")

    new_count = 0
    for filename in files:
        if filename in existing:
            print(f"  [SKIP] {filename}")
            continue

        # Parse artist/title from "ARTIST - TITLE.mp3"
        if " - " in filename:
            artist, title = filename.split(" - ", 1)
            title = title.rsplit(".", 1)[0]
        else:
            artist, title = "Unknown", filename.rsplit(".", 1)[0]

        # Register track
        trackdb.register_track(conn, filename, artist, title)
        trackdb.update_status(conn, filename, "ANALYZING")

        file_path = os.path.join(data_dir, filename)
        print(f"  [ANALYZING] {filename}...")

        try:
            feature_dict = analyze_snippet(file_path)
        except Exception as e:
            print(f"  [ERROR] {filename}: {e}")
            trackdb.update_status(conn, filename, "FAILED", error=str(e))
            continue

        # Store ALL features
        trackdb.store_features(conn, filename, feature_dict)
        trackdb.update_status(conn, filename, "INDEXED")
        new_count += 1

        total_dims = sum(len(v) for v in feature_dict.values())
        print(f"  [STORED] {filename} ({total_dims} feature dimensions)")

    stats = trackdb.get_stats(conn)
    print(f"\nDone! Analyzed {new_count} new tracks. Total indexed: {stats.get('INDEXED', 0)}")
    conn.close()
    return new_count


# ============================================================
# Layer 2: Build Search Index (cheap — reads from SQLite)
# ============================================================

def rebuild_search_index(db_path=DEFAULT_DB_PATH, db_dir=DEFAULT_DB_DIR):
    """Rebuild ChromaDB search index from stored features in SQLite.

    This is the cheap operation — just reads feature dicts from SQLite,
    selects the enabled subset, and inserts into ChromaDB. Takes minutes
    even for 1M tracks.

    Args:
        db_path: Path to SQLite database.
        db_dir: Path to ChromaDB persistent storage.

    Returns:
        ChromaDB Collection with the new search index.
    """
    conn = trackdb.get_db(db_path)

    # Wipe and recreate the collection
    client = chromadb.PersistentClient(path=db_dir)
    try:
        client.delete_collection("sonic_dna")
    except Exception:
        pass

    collection = client.create_collection(
        name="sonic_dna",
        metadata={"hnsw:space": "cosine"}
    )

    all_features = trackdb.get_all_features(conn)
    enabled = get_enabled_features()
    search_dims = get_search_dimensions()
    version = get_feature_version()

    print(f"Rebuilding search index: {len(all_features)} tracks")
    print(f"Enabled features: {', '.join(enabled)} ({search_dims} dims)")
    print(f"Feature version: {version}\n")

    # Batch insert for performance
    batch_ids = []
    batch_embeddings = []
    batch_metadatas = []
    batch_size = 100
    skipped = 0

    for track in all_features:
        search_vector = build_search_vector(track["feature_data"])

        if len(search_vector) != search_dims:
            print(f"  [SKIP] {track['track_id']} — dimension mismatch ({len(search_vector)} vs {search_dims})")
            skipped += 1
            continue

        batch_ids.append(track["track_id"])
        batch_embeddings.append(search_vector)
        batch_metadatas.append({
            "artist": track["artist"],
            "title": track["title"],
            "filename": track["track_id"],
        })

        if len(batch_ids) >= batch_size:
            collection.add(ids=batch_ids, embeddings=batch_embeddings, metadatas=batch_metadatas)
            batch_ids, batch_embeddings, batch_metadatas = [], [], []

    # Insert remaining
    if batch_ids:
        collection.add(ids=batch_ids, embeddings=batch_embeddings, metadatas=batch_metadatas)

    total = collection.count()
    print(f"Done! Search index built with {total} tracks ({search_dims} dims)")
    if skipped:
        print(f"  ({skipped} tracks skipped due to dimension mismatch)")

    conn.close()
    return collection


# ============================================================
# Query (unchanged interface)
# ============================================================

def query_similar(query_vector, n_results=5, exclude_id=None, db_dir=DEFAULT_DB_DIR):
    """Find the most similar tracks to a given DNA vector.

    Args:
        query_vector: List of floats (search vector with enabled features only).
        n_results: Number of results to return.
        exclude_id: Optional track ID to exclude.
        db_dir: Path to ChromaDB persistent storage.

    Returns:
        List of dicts: [{id, artist, title, similarity, match_pct}, ...]
    """
    collection = get_collection(db_dir)

    if collection.count() == 0:
        return []

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=min(n_results + (1 if exclude_id else 0), collection.count()),
    )

    scored = []
    for track_id, distance, meta in zip(
        results["ids"][0], results["distances"][0], results["metadatas"][0]
    ):
        if track_id == exclude_id:
            continue
        similarity = 1 - distance
        scored.append({
            "id": track_id,
            "artist": meta["artist"],
            "title": meta["title"],
            "similarity": similarity,
            "match_pct": round(similarity * 100, 1),
        })

    return scored[:n_results]


def query_similar_weighted(query_feature_dict, weights, n_results=5,
                           exclude_id=None, db_path=DEFAULT_DB_PATH):
    """Find similar tracks using weighted, normalized Euclidean distance.

    Steps:
      1. Load all features from SQLite
      2. Build raw vectors for all tracks + query
      3. Z-score normalize each dimension (mean=0, std=1) across the library
      4. Apply per-feature-group weights
      5. Compute Euclidean distance, convert to 0-100% similarity

    This correctly handles:
      - Single-dimension features like tempo (where cosine always = 1.0)
      - Features at very different scales (tempo ~150 vs ZCR ~0.05)
      - Arbitrary weight combinations including all-zeros-except-one

    Args:
        query_feature_dict: Full feature dict (from analyze_snippet or SQLite).
        weights: Dict of {feature_name: float} weights.
        n_results: Number of results to return.
        exclude_id: Optional track ID to exclude.
        db_path: Path to SQLite database.

    Returns:
        List of dicts: [{id, artist, title, similarity, match_pct}, ...]
    """
    conn = trackdb.get_db(db_path)
    all_tracks = trackdb.get_all_features(conn)
    conn.close()

    if not all_tracks:
        return []

    enabled = get_enabled_features()

    # Build weight vector: one weight per dimension, expanded from feature groups
    from deepkt.features import EXTRACTOR_REGISTRY
    weight_vector = []
    for feat_name in enabled:
        ext = EXTRACTOR_REGISTRY[feat_name]()
        w = weights.get(feat_name, 1.0)
        weight_vector.extend([w] * ext.dimensions)
    weight_vector = np.array(weight_vector, dtype=np.float64)

    # Skip if all weights are zero
    if np.sum(weight_vector) == 0:
        return []

    # Build raw vectors for all stored tracks
    stored_vectors = []
    track_info = []
    for track in all_tracks:
        raw = []
        for feat_name in enabled:
            raw.extend(track["feature_data"].get(feat_name, []))
        stored_vectors.append(raw)
        track_info.append({
            "id": track["track_id"],
            "artist": track["artist"],
            "title": track["title"],
            "url": track.get("url"),
        })

    stored_matrix = np.array(stored_vectors, dtype=np.float64)

    # Build query vector
    query_raw = []
    for feat_name in enabled:
        query_raw.extend(query_feature_dict.get(feat_name, []))
    query = np.array(query_raw, dtype=np.float64)

    # Z-score normalize: use library stats (mean/std per dimension)
    mean = stored_matrix.mean(axis=0)
    std = stored_matrix.std(axis=0)
    std[std == 0] = 1.0  # Avoid division by zero for constant features

    query_norm = (query - mean) / std
    stored_norm = (stored_matrix - mean) / std

    # Apply weights
    query_weighted = query_norm * weight_vector
    stored_weighted = stored_norm * weight_vector

    # Compute Euclidean distances
    diffs = stored_weighted - query_weighted
    
    # --- Octave-Invariant Tempo Handling (Cosine-Compatible) ---
    # Find the index of the 'tempo' feature
    try:
        tempo_idx = enabled.index("tempo")
        
        current_idx = 0
        from deepkt.features import EXTRACTOR_REGISTRY
        tempo_col = -1
        
        for feat_name in enabled:
            dims = EXTRACTOR_REGISTRY[feat_name]().dimensions
            if feat_name == "tempo":
                tempo_col = current_idx
                break
            current_idx += dims
            
        if tempo_col != -1 and weights.get("tempo", 0) > 0:
            # Get raw tempos (before normalization)
            t_query = query[tempo_col]
            t_stored = stored_matrix[:, tempo_col]
            
            # Calculate absolute difference for 1x, 0.5x, and 2x matches
            diff_1x = np.abs(t_stored - t_query)
            diff_05x = np.abs((t_stored * 0.5) - t_query)
            diff_2x = np.abs((t_stored * 2.0) - t_query)
            
            # Map the stored tempo to the closest octave for this specific query
            best_t_stored = np.where(diff_05x < diff_1x, t_stored * 0.5, t_stored)
            best_t_stored = np.where(diff_2x < np.minimum(diff_1x, diff_05x), t_stored * 2.0, best_t_stored)
            
            # Re-normalize and re-weight just for this column
            tempo_mean = mean[tempo_col]
            tempo_std = std[tempo_col]
            tempo_weight = weight_vector[tempo_col]
            
            stored_weighted[:, tempo_col] = ((best_t_stored - tempo_mean) / tempo_std) * tempo_weight
            
    except ValueError:
        pass # Tempo feature not enabled
    
    # ---------------------------------------
    # Calculate Cosine Similarity
    
    q_norm_val = np.linalg.norm(query_weighted)
    if q_norm_val == 0: q_norm_val = 1e-10
    q_normalized = query_weighted / q_norm_val
    
    s_norm_vals = np.linalg.norm(stored_weighted, axis=1, keepdims=True)
    s_norm_vals[s_norm_vals == 0] = 1e-10
    s_normalized = stored_weighted / s_norm_vals
    
    # Vectorized dot product (Cosine Similarity)
    similarities = np.dot(s_normalized, q_normalized).flatten()
    
    # Map from [-1, 1] to [0, 1] range for UI percentage display
    similarities = np.clip((similarities + 1.0) / 2.0, 0.0, 1.0)

    # Build results
    scored = []
    for i, info in enumerate(track_info):
        if info["id"] == exclude_id:
            continue
        scored.append({
            "id": info["id"],
            "artist": info["artist"],
            "title": info["title"],
            "url": info.get("url"),
            "similarity": float(similarities[i]),
            "match_pct": round(float(similarities[i]) * 100, 1),
        })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:n_results]
