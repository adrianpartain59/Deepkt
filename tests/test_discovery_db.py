"""Tests for the discovery database functions in db.py."""

import os
import tempfile
import unittest

from deepkt import db as trackdb


class TestDiscoveryCandidates(unittest.TestCase):
    """Test the discovery_candidates table functions."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = trackdb.get_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_register_candidate(self):
        trackdb.register_candidate(self.conn, "https://soundcloud.com/testartist", "testartist", 500)
        candidates = trackdb.get_candidates(self.conn)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["artist_url"], "https://soundcloud.com/testartist")
        self.assertEqual(candidates[0]["permalink"], "testartist")
        self.assertEqual(candidates[0]["followers"], 500)
        self.assertEqual(candidates[0]["times_seen"], 1)
        self.assertEqual(candidates[0]["status"], "PENDING")

    def test_register_candidate_increments_times_seen(self):
        trackdb.register_candidate(self.conn, "https://soundcloud.com/artist1", "artist1", 100)
        trackdb.register_candidate(self.conn, "https://soundcloud.com/artist1", "artist1", 100)
        trackdb.register_candidate(self.conn, "https://soundcloud.com/artist1", "artist1", 100)

        candidates = trackdb.get_candidates(self.conn)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["times_seen"], 3)

    def test_update_candidate_status(self):
        trackdb.register_candidate(self.conn, "https://soundcloud.com/artist2", "artist2", 200)
        trackdb.update_candidate_status(self.conn, "https://soundcloud.com/artist2", "APPROVED", avg_similarity=0.85)

        candidates = trackdb.get_candidates(self.conn, status="APPROVED")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["status"], "APPROVED")
        self.assertAlmostEqual(candidates[0]["avg_similarity"], 0.85, places=2)

    def test_get_candidates_filtered(self):
        trackdb.register_candidate(self.conn, "https://soundcloud.com/a", "a", 10)
        trackdb.register_candidate(self.conn, "https://soundcloud.com/b", "b", 20)
        trackdb.update_candidate_status(self.conn, "https://soundcloud.com/b", "REJECTED", avg_similarity=0.3)

        pending = trackdb.get_candidates(self.conn, status="PENDING")
        rejected = trackdb.get_candidates(self.conn, status="REJECTED")
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(pending[0]["permalink"], "a")
        self.assertEqual(rejected[0]["permalink"], "b")


class TestDiscoveryLog(unittest.TestCase):
    """Test the discovery_log table functions."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = trackdb.get_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_log_probe(self):
        trackdb.log_probe(
            self.conn,
            "https://soundcloud.com/artist1",
            "https://soundcloud.com/artist1/track1",
            0.82,
            "sometrack.mp3",
        )
        logs = trackdb.get_discovery_log(self.conn)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["candidate_url"], "https://soundcloud.com/artist1")
        self.assertAlmostEqual(logs[0]["similarity_score"], 0.82, places=2)
        self.assertEqual(logs[0]["nearest_track_id"], "sometrack.mp3")

    def test_log_probe_filtered(self):
        trackdb.log_probe(self.conn, "https://soundcloud.com/a", "track1", 0.9, "id1")
        trackdb.log_probe(self.conn, "https://soundcloud.com/b", "track2", 0.5, "id2")
        trackdb.log_probe(self.conn, "https://soundcloud.com/a", "track3", 0.8, "id3")

        logs_a = trackdb.get_discovery_log(self.conn, candidate_url="https://soundcloud.com/a")
        logs_b = trackdb.get_discovery_log(self.conn, candidate_url="https://soundcloud.com/b")
        self.assertEqual(len(logs_a), 2)
        self.assertEqual(len(logs_b), 1)

    def test_get_discovery_stats(self):
        trackdb.register_candidate(self.conn, "https://soundcloud.com/a", "a")
        trackdb.register_candidate(self.conn, "https://soundcloud.com/b", "b")
        trackdb.register_candidate(self.conn, "https://soundcloud.com/c", "c")
        trackdb.update_candidate_status(self.conn, "https://soundcloud.com/b", "APPROVED")
        trackdb.update_candidate_status(self.conn, "https://soundcloud.com/c", "REJECTED")

        stats = trackdb.get_discovery_stats(self.conn)
        self.assertEqual(stats["PENDING"], 1)
        self.assertEqual(stats["APPROVED"], 1)
        self.assertEqual(stats["REJECTED"], 1)
        self.assertEqual(stats["total"], 3)


if __name__ == "__main__":
    unittest.main()
