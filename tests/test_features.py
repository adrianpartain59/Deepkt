"""Tests for deepkt.features — Pluggable extractors."""

import pytest
import os
import numpy as np
import librosa

from deepkt.features.base import BaseFeatureExtractor
from deepkt.features import EXTRACTOR_REGISTRY, ALL_EXTRACTOR_NAMES

DATA_DIR = "data/raw_snippets"
SAMPLE_FILE = None
for f in os.listdir(DATA_DIR):
    if f.endswith(".mp3"):
        SAMPLE_FILE = os.path.join(DATA_DIR, f)
        break


class TestBaseFeatureExtractor:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseFeatureExtractor()

    def test_valid_subclass(self):
        class Dummy(BaseFeatureExtractor):
            name = "dummy"
            dimensions = 1
            def extract(self, y, sr, config=None):
                return [1.0]
        ext = Dummy()
        assert ext.extract(None, 22050) == [1.0]


class TestExtractorRegistry:
    def test_has_9_extractors(self):
        assert len(EXTRACTOR_REGISTRY) == 9

    def test_names_match(self):
        expected = {"tempo", "mfcc", "spectral_centroid", "spectral_contrast",
                    "zero_crossing_rate", "onset_strength", "rms_energy",
                    "chroma", "tonnetz"}
        assert set(EXTRACTOR_REGISTRY.keys()) == expected

    def test_all_extractor_names_sorted(self):
        assert ALL_EXTRACTOR_NAMES == sorted(ALL_EXTRACTOR_NAMES)

    def test_total_dimensions_is_43(self):
        total = sum(cls().dimensions for cls in EXTRACTOR_REGISTRY.values())
        assert total == 43


class TestIndividualExtractors:
    @pytest.mark.skipif(SAMPLE_FILE is None, reason="No audio files")
    def test_all_extractors_produce_correct_dimensions(self):
        y, sr = librosa.load(SAMPLE_FILE)
        y_trimmed, _ = librosa.effects.trim(y, top_db=20)

        for name, cls in EXTRACTOR_REGISTRY.items():
            ext = cls()
            result = ext.extract(y_trimmed, sr)
            assert len(result) == ext.dimensions, \
                f"{name}: expected {ext.dimensions} dims, got {len(result)}"
            assert all(isinstance(v, float) for v in result), \
                f"{name}: non-float values"
