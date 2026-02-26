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
            "url": track.get("url", ""),
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
            "url": meta.get("url", ""),
            "similarity": similarity,
            "match_pct": round(similarity * 100, 1),
        })

    return scored[:n_results]


# Weights are obsolete with Neural Networks.
# Please use query_similar() directly to leverage ChromaDB's native Cosine distance.
