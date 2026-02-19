"""Tests for deepkt.indexer — Two-layer indexing system."""

import os
import tempfile
import pytest

from deepkt.indexer import get_collection, analyze_and_store, rebuild_search_index, query_similar
from deepkt.analyzer import analyze_snippet, build_search_vector
from deepkt import db as trackdb

DATA_DIR = "data/raw_snippets"
HAS_DATA = any(f.endswith(".mp3") for f in os.listdir(DATA_DIR))


class TestGetCollection:
    def test_creates_collection_in_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            collection = get_collection(db_dir=tmpdir)
            assert collection.name == "sonic_dna"
            assert collection.count() == 0

    def test_collection_is_cosine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            collection = get_collection(db_dir=tmpdir)
            assert collection.metadata.get("hnsw:space") == "cosine"


class TestAnalyzeAndStore:
    @pytest.mark.skipif(not HAS_DATA, reason="No audio files")
    def test_stores_all_tracks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            analyze_and_store(data_dir=DATA_DIR, db_path=db_path)
            conn = trackdb.get_db(db_path)
            stats = trackdb.get_stats(conn)
            mp3_count = len([f for f in os.listdir(DATA_DIR) if f.endswith(".mp3")])
            assert stats.get("INDEXED", 0) == mp3_count
            conn.close()

    @pytest.mark.skipif(not HAS_DATA, reason="No audio files")
    def test_stores_43_features_per_track(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            analyze_and_store(data_dir=DATA_DIR, db_path=db_path)
            conn = trackdb.get_db(db_path)
            tracks = trackdb.get_tracks(conn)
            for track in tracks:
                features = trackdb.get_features(conn, track["id"])
                assert features is not None
                total = sum(len(v) for v in features.values())
                assert total == 43, f"{track['id']} has {total} dims, expected 43"
            conn.close()

    @pytest.mark.skipif(not HAS_DATA, reason="No audio files")
    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            analyze_and_store(data_dir=DATA_DIR, db_path=db_path)
            analyze_and_store(data_dir=DATA_DIR, db_path=db_path)
            conn = trackdb.get_db(db_path)
            mp3_count = len([f for f in os.listdir(DATA_DIR) if f.endswith(".mp3")])
            assert trackdb.get_stats(conn).get("INDEXED", 0) == mp3_count
            conn.close()


class TestRebuildSearchIndex:
    @pytest.mark.skipif(not HAS_DATA, reason="No audio files")
    def test_builds_index_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            chroma_dir = os.path.join(tmpdir, "chroma")
            analyze_and_store(data_dir=DATA_DIR, db_path=db_path)
            collection = rebuild_search_index(db_path=db_path, db_dir=chroma_dir)
            mp3_count = len([f for f in os.listdir(DATA_DIR) if f.endswith(".mp3")])
            assert collection.count() == mp3_count


class TestQuerySimilar:
    @pytest.mark.skipif(not HAS_DATA, reason="No audio files")
    def test_returns_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            chroma_dir = os.path.join(tmpdir, "chroma")
            analyze_and_store(data_dir=DATA_DIR, db_path=db_path)
            rebuild_search_index(db_path=db_path, db_dir=chroma_dir)

            sample = [f for f in os.listdir(DATA_DIR) if f.endswith(".mp3")][0]
            feature_dict = analyze_snippet(os.path.join(DATA_DIR, sample))
            vector = build_search_vector(feature_dict)

            results = query_similar(vector, n_results=3, db_dir=chroma_dir)
            assert len(results) > 0

    @pytest.mark.skipif(not HAS_DATA, reason="No audio files")
    def test_result_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            chroma_dir = os.path.join(tmpdir, "chroma")
            analyze_and_store(data_dir=DATA_DIR, db_path=db_path)
            rebuild_search_index(db_path=db_path, db_dir=chroma_dir)

            sample = [f for f in os.listdir(DATA_DIR) if f.endswith(".mp3")][0]
            feature_dict = analyze_snippet(os.path.join(DATA_DIR, sample))
            vector = build_search_vector(feature_dict)

            results = query_similar(vector, n_results=1, db_dir=chroma_dir)
            r = results[0]
            assert "id" in r
            assert "artist" in r
            assert "title" in r
            assert "match_pct" in r
