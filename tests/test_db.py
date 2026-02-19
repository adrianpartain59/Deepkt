"""Tests for deepkt.db — SQLite track registry and feature store."""

import os
import json
import tempfile
import pytest

from deepkt import db as trackdb


class TestGetDB:
    def test_creates_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            assert conn is not None
            conn.close()
            assert os.path.exists(db_path)

    def test_creates_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t["name"] for t in tables}
            assert "tracks" in table_names
            assert "track_features" in table_names
            conn.close()


class TestTrackManagement:
    def test_register_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            trackdb.register_track(conn, "test.mp3", "Artist", "Title")
            track = trackdb.get_track(conn, "test.mp3")
            assert track["artist"] == "Artist"
            assert track["title"] == "Title"
            assert track["status"] == "DISCOVERED"
            conn.close()

    def test_register_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            trackdb.register_track(conn, "test.mp3", "Artist", "Title")
            trackdb.register_track(conn, "test.mp3", "Artist", "Title")
            stats = trackdb.get_stats(conn)
            assert stats["total"] == 1
            conn.close()

    def test_update_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            trackdb.register_track(conn, "test.mp3", "Artist", "Title")
            trackdb.update_status(conn, "test.mp3", "INDEXED")
            track = trackdb.get_track(conn, "test.mp3")
            assert track["status"] == "INDEXED"
            assert track["indexed_at"] is not None
            conn.close()

    def test_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            trackdb.register_track(conn, "a.mp3", "HXVRMXN", "Eclipse")
            trackdb.register_track(conn, "b.mp3", "SAGE", "Lethal Presence")
            results = trackdb.search_tracks(conn, "hxvrmxn")
            assert len(results) == 1
            assert results[0]["artist"] == "HXVRMXN"
            conn.close()

    def test_get_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            trackdb.register_track(conn, "a.mp3", "A", "A")
            trackdb.register_track(conn, "b.mp3", "B", "B")
            trackdb.update_status(conn, "b.mp3", "INDEXED")
            stats = trackdb.get_stats(conn)
            assert stats["total"] == 2
            assert stats["DISCOVERED"] == 1
            assert stats["INDEXED"] == 1
            conn.close()


class TestFeatureStorage:
    def test_store_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            trackdb.register_track(conn, "test.mp3", "A", "B")
            features = {"tempo": [143.5], "mfcc": [1.0, 2.0, 3.0]}
            trackdb.store_features(conn, "test.mp3", features)
            loaded = trackdb.get_features(conn, "test.mp3")
            assert loaded == features
            conn.close()

    def test_get_all_features(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            trackdb.register_track(conn, "a.mp3", "A", "Title A")
            trackdb.register_track(conn, "b.mp3", "B", "Title B")
            trackdb.store_features(conn, "a.mp3", {"tempo": [140.0]})
            trackdb.store_features(conn, "b.mp3", {"tempo": [160.0]})
            trackdb.update_status(conn, "a.mp3", "INDEXED")
            trackdb.update_status(conn, "b.mp3", "INDEXED")
            all_feats = trackdb.get_all_features(conn)
            assert len(all_feats) == 2
            assert all("feature_data" in f for f in all_feats)
            conn.close()

    def test_missing_features_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = trackdb.get_db(db_path)
            result = trackdb.get_features(conn, "nonexistent.mp3")
            assert result is None
            conn.close()
