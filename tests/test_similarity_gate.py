"""Tests for the similarity gate logic using synthetic vectors."""

import os
import tempfile
import unittest
import numpy as np

from deepkt import db as trackdb


class TestSimilarityGate(unittest.TestCase):
    """Test the similarity gate with controlled synthetic data."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = trackdb.get_db(self.tmp.name)

        # Create a small corpus of 5 known tracks with specific embeddings
        np.random.seed(42)
        self.corpus_base = np.random.randn(512).astype(np.float32)
        self.corpus_base /= np.linalg.norm(self.corpus_base)

        # Store 5 tracks that are slight variations of the base vector
        for i in range(5):
            track_id = f"corpus_track_{i}.mp3"
            noise = np.random.randn(512).astype(np.float32) * 0.05
            vec = self.corpus_base + noise
            vec = vec / np.linalg.norm(vec)

            trackdb.register_track(self.conn, track_id, f"Artist{i}", f"Track{i}")
            trackdb.store_features(self.conn, track_id, {"clap_embedding": vec.tolist()})
            trackdb.update_status(self.conn, track_id, "INDEXED")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_gate_passes_similar_vectors(self):
        """Vectors that are close to the corpus should pass the gate."""
        from deepkt.discovery import similarity_gate

        # Create probe vectors that are similar to the corpus
        # In 512-d space, noise must be very small relative to signal
        rng = np.random.RandomState(123)
        probe_vectors = []
        for _ in range(3):
            noise = rng.randn(512).astype(np.float32) * 0.005
            vec = self.corpus_base + noise
            vec = vec / np.linalg.norm(vec)
            probe_vectors.append(vec.tolist())

        avg_sim, passed = similarity_gate(
            probe_vectors, ["url1", "url2", "url3"],
            "https://soundcloud.com/test", self.conn, threshold=0.60
        )

        self.assertTrue(passed, f"Expected to pass but got avg_sim={avg_sim:.3f}")
        self.assertGreater(avg_sim, 0.60)

    def test_gate_rejects_dissimilar_vectors(self):
        """Completely random vectors should fail the gate."""
        from deepkt.discovery import similarity_gate

        np.random.seed(999)
        probe_vectors = [np.random.randn(512).tolist() for _ in range(3)]

        avg_sim, passed = similarity_gate(
            probe_vectors, ["url1", "url2", "url3"],
            "https://soundcloud.com/random", self.conn, threshold=0.70
        )

        self.assertFalse(passed, f"Expected to reject but got avg_sim={avg_sim:.3f}")

    def test_gate_threshold_tuning(self):
        """Changing the threshold should affect pass/fail decision."""
        from deepkt.discovery import similarity_gate

        # Moderately similar vector (small noise = high similarity)
        noise = np.random.randn(512).astype(np.float32) * 0.05
        vec = self.corpus_base + noise
        vec = vec / np.linalg.norm(vec)
        probe_vectors = [vec.tolist()]

        # With low threshold, should pass
        avg_sim, passed_low = similarity_gate(
            probe_vectors, ["url1"],
            "https://soundcloud.com/medium", self.conn, threshold=0.10
        )
        self.assertTrue(passed_low)

        # With very high threshold, should fail
        _, passed_high = similarity_gate(
            probe_vectors, ["url1"],
            "https://soundcloud.com/medium2", self.conn, threshold=0.999
        )
        self.assertFalse(passed_high)

    def test_empty_probes_returns_zero(self):
        """Empty probe list should return 0.0 and not pass."""
        from deepkt.discovery import similarity_gate

        avg_sim, passed = similarity_gate(
            [], [], "https://soundcloud.com/empty", self.conn, threshold=0.70
        )
        self.assertEqual(avg_sim, 0.0)
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
