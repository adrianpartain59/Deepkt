"""Spectral feature extractors — brightness and production quality."""

import numpy as np
import librosa
from deepkt.features.base import BaseFeatureExtractor


class SpectralCentroidExtractor(BaseFeatureExtractor):
    """Extracts spectral centroid — the "brightness" of the sound.

    High values = bright, shimmery (EDM leads, hi-hats).
    Low values = dark, bassy (Phonk 808s, dark ambient).
    """

    name = "spectral_centroid"
    dimensions = 1

    def extract(self, y, sr, config=None):
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        return [float(np.mean(centroid))]


class SpectralContrastExtractor(BaseFeatureExtractor):
    """Extracts spectral contrast — peak-to-valley ratios per frequency band.

    Measures how "punchy" vs "muddy" a mix sounds across 7 frequency bands.
    Clean, well-produced tracks have high contrast; lo-fi/compressed tracks
    have low contrast.
    """

    name = "spectral_contrast"
    dimensions = 7

    def extract(self, y, sr, config=None):
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        return np.mean(contrast.T, axis=0).tolist()
