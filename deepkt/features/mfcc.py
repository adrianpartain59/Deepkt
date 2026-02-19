"""MFCC (Mel-Frequency Cepstral Coefficients) feature extractor."""

import numpy as np
import librosa
from deepkt.features.base import BaseFeatureExtractor


class MFCCExtractor(BaseFeatureExtractor):
    """Extracts MFCC coefficients — the core timbre/texture fingerprint.

    MFCCs capture the spectral envelope shape, which is what makes
    a distorted 808 sound different from a clean synth pad. This is
    the single most important feature group for sonic similarity.
    """

    name = "mfcc"
    dimensions = 13  # default, overridable via config

    def extract(self, y, sr, config=None):
        n_coefficients = (config or {}).get("n_coefficients", 13)
        self.dimensions = n_coefficients
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_coefficients)
        return np.mean(mfccs.T, axis=0).tolist()
