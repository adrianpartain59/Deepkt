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


class HPSSRatioExtractor(BaseFeatureExtractor):
    """Extracts the ratio of Percussive to Harmonic energy.
    
    Phonk tracks heavily rely on either massive drum compression (Drift Phonk)
    or ambient pads/vocals (Wave Phonk). This physically splits the audio
    and returns how much of the energy belongs to the drum hits compared to the melody.
    """
    
    name = "hpss_ratio"
    dimensions = 1

    def extract(self, y, sr, config=None):
        # Increased margin for better separation of transient drums vs sustained pads
        y_harm, y_perc = librosa.effects.hpss(y, margin=(1.0, 5.0))
        
        perc_energy = np.sum(y_perc**2)
        harm_energy = np.sum(y_harm**2) + 1e-10 # avoid dev-by-zero
        
        ratio = perc_energy / harm_energy
        return [float(ratio)]


class TempogramRatioExtractor(BaseFeatureExtractor):
    """Extracts the Groove Index — rhythm syncopation and complexity.
    
    Calculates a local autocorrelation of the onset strength envelope to form a Tempogram.
    By finding the ratio between the primary beat peak and the secondary peaks (variance),
    we can distinguish between a straight 4/4 beat (low variance) and highly swung, 
    syncopated trap/phonk grooves (high variance).
    """
    
    name = "tempogram_ratio"
    dimensions = 1

    def extract(self, y, sr, config=None):
        # Calculate onset strength
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        
        # Calculate tempogram
        # Use a large win_length to capture full measure grooves
        tg = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr, win_length=384)
        
        # Calculate the variance of the tempogram across the time axis, 
        # then mean across all windows. High variance = complex syncopation.
        # Alternatively, the standard deviation of the tempogram gives us exactly how much 
        # the rhythm deviates from a simple straight pulse.
        pulse_complexity = np.std(tg, axis=0)
        
        return [float(np.mean(pulse_complexity))]


class TimeDomainCrestExtractor(BaseFeatureExtractor):
    """Measures the Crest Factor on the raw time-domain waveform (Aggression/Limiter).
    
    A low crest factor means the entire track is slammed against a limiter (pure loudness).
    A high crest factor means it retains dynamic bounce.
    """
    name = "time_domain_crest"
    dimensions = 1

    def extract(self, y, sr, config=None):
        max_abs = np.max(np.abs(y))
        rms = np.sqrt(np.mean(y**2)) + 1e-10
        crest = max_abs / rms
        return [float(crest)]
