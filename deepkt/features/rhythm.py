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
    """Extracts the Groove Index — rhythm syncopation, kick density, and tempo-invariant bounce.
    
    1. First, we isolate the kicks by limiting the onset envelope to low frequencies (fmax=250Hz).
    2. We calculate the kick density (mean of the onset envelope) to distinguish high-energy 
       trap from smooth trap.
    3. We calculate the Global Tempogram (average periodicity over time). By calculating the 
       Crest Factor (peak-to-average ratio) of this global tempogram, we get a tempo-invariant 
       measure of "straightness". A 4/4 beat at ANY tempo has a massive singular peak, yielding 
       a high crest factor. A syncopated trap beat has kicks spread across many fractional beats, 
       yielding a flat/dense tempogram with a low crest factor.
    """
    
    name = "tempogram_ratio"
    dimensions = 2

    def extract(self, y, sr, config=None):
        # 1. Isolate the kicks (low frequency onsets only)
        # fmax=250 focuses purely on the sub/bass range (kicks and 808s)
        # ignoring hi-hats, snares, and synths completely.
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, fmax=250)
        
        # 2. Kick Density
        # How many kicks/how loud are they on average?
        kick_density = float(np.mean(onset_env))
        
        # 3. Tempo-Invariant Syncopation (Straight vs Bouncy)
        # Calculate the tempogram
        tg = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr, win_length=384)
        
        # Calculate the global tempogram (average periodicity across the entire track)
        global_tg = np.mean(tg, axis=1)
        
        # Exclude the zero-lag bin (which is always a massive spike)
        global_tg[:5] = 0
        
        # Calculate the Crest Factor of the global tempogram
        # 4/4 Beat = Huge peak at the fundamental beat lag, deep valleys elsewhere (High CF)
        # Trap Beat = Many peaks everywhere due to syncopation (Low CF)
        straightness = float(np.max(global_tg) / (np.mean(global_tg) + 1e-8))
        
        return [straightness, kick_density]


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


class HighFreqPercussionExtractor(BaseFeatureExtractor):
    """Measures high-end drum aggression (hi-hats/snares).
    
    1. Erases all bass, kicks, and synth pads below 4000Hz.
    2. Runs the Crest Factor purely on the remaining high-end audio.
    3. Sharp/aggressive trap hats stabbing through the mix return a high score.
    4. Smooth/padded hats buried in the mix return a low score.
    """
    name = "high_freq_percussion"
    dimensions = 1

    def extract(self, y, sr, config=None):
        # 1. High-Pass Filter (Isolate >4000Hz)
        # We transform to STFT, zero out everything below 4kHz, and transform back.
        S = librosa.stft(y)
        freqs = librosa.fft_frequencies(sr=sr)
        
        # Find the index where 4000Hz starts
        high_pass_idx = np.searchsorted(freqs, 4000)
        
        # Zero out the low end
        S[:high_pass_idx, :] = 0
        
        # Reconstruct high-passed audio
        y_high = librosa.istft(S)
        
        # 2. Measure High-End Aggression (Crest Factor)
        max_abs = np.max(np.abs(y_high))
        rms = np.sqrt(np.mean(y_high**2)) + 1e-10
        crest = max_abs / rms
        
        return [float(crest)]
