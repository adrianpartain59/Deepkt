"""Tempo (BPM) feature extractor."""

import numpy as np
import librosa
from deepkt.features.base import BaseFeatureExtractor


class TempoExtractor(BaseFeatureExtractor):
    """Extracts beats-per-minute from audio.

    Uses librosa.feature.tempo() with onset envelope analysis.
    Configured with start_bpm=145 for Phonk (typically 130-170 BPM),
    which prevents sub-harmonic lock-on (e.g. 150 BPM detected as 100).
    """

    name = "tempo"
    dimensions = 1
    
    # Phonk is fast (130-170ish). Default 120 pulls estimates down to 100.
    # 145 is a safer center for this genre.
    START_BPM = 145

    def extract(self, y, sr, config=None):
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = librosa.feature.tempo(
            onset_envelope=onset_env,
            sr=sr,
            start_bpm=self.START_BPM,
            aggregate=np.mean
        )
        if isinstance(tempo, np.ndarray):
            tempo = tempo.item()
            
        # Post-processing clamp for Phonk range (typically 90-180)
        # Handle octave errors (double/half speed detection)
        while tempo > 185:
            tempo /= 2
        while tempo < 70:
            tempo *= 2
            
        return [float(tempo)]
