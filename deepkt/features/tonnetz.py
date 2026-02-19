"""Tonnetz feature extractor — harmonic relationships."""

import numpy as np
import librosa
from deepkt.features.base import BaseFeatureExtractor


class TonnetzExtractor(BaseFeatureExtractor):
    """Extracts Tonnetz features — harmonic/tonal relationships.

    Produces 6 values representing relationships on the Tonnetz grid:
      [0] Fifths           — C→G movement
      [1] Minor thirds     — C→Eb (key for Phonk's signature minor key sound)
      [2] Major thirds     — C→E
      [3] Diminished       — dissonance/tension
      [4] Minor movement   — minor chord progressions
      [5] Major movement   — major chord progressions

    Phonk tracks lean heavily on minor thirds (dim[1]), making this
    a valuable feature for separating dark/minor-key tracks from
    major-key EDM.
    """

    name = "tonnetz"
    dimensions = 6

    def extract(self, y, sr, config=None):
        # Tonnetz requires harmonic content — use chroma as basis
        harmonic = librosa.effects.harmonic(y)
        tonnetz = librosa.feature.tonnetz(y=harmonic, sr=sr)
        return np.mean(tonnetz.T, axis=0).tolist()
