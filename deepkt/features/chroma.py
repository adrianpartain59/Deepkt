"""Chroma feature extractor — pitch class profile."""

import numpy as np
import librosa
from deepkt.features.base import BaseFeatureExtractor


class ChromaExtractor(BaseFeatureExtractor):
    """Extracts chroma features — which musical notes dominate.

    Produces 12 values representing energy in each pitch class
    (C, C#, D, D#, E, F, F#, G, G#, A, A#, B). Useful for
    matching tracks with similar harmonic content or key.
    """

    name = "chroma"
    dimensions = 12

    def extract(self, y, sr, config=None):
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        return np.mean(chroma.T, axis=0).tolist()
