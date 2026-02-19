"""Rhythm and energy feature extractors."""

import numpy as np
import librosa
from deepkt.features.base import BaseFeatureExtractor


class ZeroCrossingRateExtractor(BaseFeatureExtractor):
    """Extracts zero-crossing rate — noisiness/distortion.

    High ZCR = noisy, distorted (Phonk's signature heavy distortion).
    Low ZCR = clean, pure tones.
    """

    name = "zero_crossing_rate"
    dimensions = 1

    def extract(self, y, sr, config=None):
        zcr = librosa.feature.zero_crossing_rate(y)
        return [float(np.mean(zcr))]


class OnsetStrengthExtractor(BaseFeatureExtractor):
    """Extracts onset strength — how "hard" the beats hit.

    High values = aggressive, punchy drums (trap snares, Phonk kicks).
    Low values = smooth, ambient textures.
    """

    name = "onset_strength"
    dimensions = 1

    def extract(self, y, sr, config=None):
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        return [float(np.mean(onset_env))]


class RMSEnergyExtractor(BaseFeatureExtractor):
    """Extracts RMS energy — perceived loudness.

    Most Phonk and trap is heavily compressed (loud), so this
    helps distinguish heavily mastered tracks from dynamic ones.
    """

    name = "rms_energy"
    dimensions = 1

    def extract(self, y, sr, config=None):
        rms = librosa.feature.rms(y=y)
        return [float(np.mean(rms))]
