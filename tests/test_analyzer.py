"""Tests for deepkt.analyzer — Config-driven feature extraction."""

import os
import pytest

from deepkt.analyzer import analyze_snippet, build_search_vector, get_full_feature_names
from deepkt.config import get_enabled_features

DATA_DIR = "data/raw_snippets"
SAMPLE_FILE = None
for f in os.listdir(DATA_DIR):
    if f.endswith(".mp3"):
        SAMPLE_FILE = os.path.join(DATA_DIR, f)
        break


class TestAnalyzeSnippet:
    """Tests for the full feature extraction."""

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_returns_dict(self):
        result = analyze_snippet(SAMPLE_FILE)
        assert isinstance(result, dict)

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_has_all_9_extractors(self):
        result = analyze_snippet(SAMPLE_FILE)
        assert len(result) == 9

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_total_43_dimensions(self):
        result = analyze_snippet(SAMPLE_FILE)
        total = sum(len(v) for v in result.values())
        assert total == 43

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_all_values_are_floats(self):
        result = analyze_snippet(SAMPLE_FILE)
        for name, values in result.items():
            assert isinstance(values, list), f"{name} is not a list"
            for v in values:
                assert isinstance(v, float), f"{name} has non-float: {v}"

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_tempo_in_range(self):
        result = analyze_snippet(SAMPLE_FILE)
        bpm = result["tempo"][0]
        assert 30 <= bpm <= 300, f"BPM {bpm} is outside expected range"

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_deterministic(self):
        r1 = analyze_snippet(SAMPLE_FILE)
        r2 = analyze_snippet(SAMPLE_FILE)
        assert r1 == r2

    def test_nonexistent_file_raises(self):
        with pytest.raises(Exception):
            analyze_snippet("/nonexistent/path/fake.mp3")


class TestBuildSearchVector:
    """Tests for selecting enabled features from a full dict."""

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_search_vector_is_flat_list(self):
        feature_dict = analyze_snippet(SAMPLE_FILE)
        vector = build_search_vector(feature_dict)
        assert isinstance(vector, list)
        assert all(isinstance(v, float) for v in vector)

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_search_vector_length_matches_enabled(self):
        feature_dict = analyze_snippet(SAMPLE_FILE)
        vector = build_search_vector(feature_dict)
        # All 9 features enabled: 43 total dims
        assert len(vector) == 43

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_search_vector_subset_of_full(self):
        """Every value in the search vector should exist in the full dict."""
        feature_dict = analyze_snippet(SAMPLE_FILE)
        vector = build_search_vector(feature_dict)
        all_values = []
        for name in sorted(feature_dict.keys()):
            all_values.extend(feature_dict[name])
        for v in vector:
            assert v in all_values

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_weights_scale_vector(self):
        feature_dict = analyze_snippet(SAMPLE_FILE)
        v_normal = build_search_vector(feature_dict)
        v_weighted = build_search_vector(feature_dict, weights_override={"tempo": 2.0})
        assert v_normal != v_weighted
        assert len(v_weighted) == 43

    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_zero_weight_zeroes_feature(self):
        feature_dict = analyze_snippet(SAMPLE_FILE)
        v = build_search_vector(feature_dict, weights_override={"tempo": 0.0})
        # Tempo is alphabetically after: chroma(12) mfcc(13) onset(1) rms(1) centroid(1) contrast(7) = 35
        assert v[35] == 0.0


class TestFullFeatureNames:
    def test_returns_43_names(self):
        names = get_full_feature_names()
        assert len(names) == 43

    def test_all_strings(self):
        names = get_full_feature_names()
        assert all(isinstance(n, str) for n in names)

