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


class SpectralFlatnessExtractor(BaseFeatureExtractor):
    """Extracts spectral flatness (Wiener entropy).
    
    High values = Noise-like (vinyl crackle, harsh distortion, lo-fi hiss).
    Low values = Tone-like (clean synths, prominent 808s).
    """
    
    name = "spectral_flatness"
    dimensions = 1
    
    def extract(self, y, sr, config=None):
        flatness = librosa.feature.spectral_flatness(y=y)
        return [float(np.mean(flatness))]


class HissDensityExtractor(BaseFeatureExtractor):
    """Measures constant high-frequency background noise (Vinyl Crackle).
    
    Isolates energy above 8,000Hz (the "air" and tape hiss). Instead of calculating
    the average, it calculates the *minimum* energy. If the minimum never drops
    to zero across the track, there is constant analog lo-fi noise present.
    """
    
    name = "hiss_density"
    dimensions = 1
    
    def extract(self, y, sr, config=None):
        # We process the spectrogram and filter to only the top bins (high frequency)
        S, phase = librosa.magphase(librosa.stft(y))
        # Find which frequency bin corresponds to 8000Hz
        freqs = librosa.fft_frequencies(sr=sr)
        bin_idx = np.searchsorted(freqs, 8000)
        
        # Take the top frequencies only
        high_freq_S = S[bin_idx:, :]
        
        # Sum the energy per frame for those high frequencies
        frame_energy = np.sum(high_freq_S, axis=0)
        
        # Calculate the noise floor (e.g. 5th percentile, to avoid absolute zero drops)
        hiss_floor = np.percentile(frame_energy, 5)
        return [float(hiss_floor)]


class RolloffRatioExtractor(BaseFeatureExtractor):
    """Measures how 'muffled' or 'crisp' the entire production is.
    
    Uses spectral rolloff (the frequency below which 85% of energy is contained).
    A highly muffled, lo-fi drift phonk track has a low rolloff. Crisp EDM has 
    sparkling highs with a very high rolloff.
    """
    name = "rolloff_ratio"
    dimensions = 1
    
    def extract(self, y, sr, config=None):
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)
        # We divide by nyquist limit to get a normalized 0-1 ratio instead of raw Hz
        nyquist = sr / 2.0
        normalized_rolloff = float(np.mean(rolloff)) / nyquist
        return [float(normalized_rolloff)]


class MidFrequencyFlatnessExtractor(BaseFeatureExtractor):
    """Targeted Wiener Entropy to detect bit-crushed and distorted leads.
    
    Isolates the 500Hz-2000Hz window where synths and melodies live. 
    If this band is perfectly flat/noisy, the lead melody is aggressively distorted.
    If it is peaky, it's a clean sine/saw wave synth.
    """
    name = "mid_frequency_flatness"
    dimensions = 1

    def extract(self, y, sr, config=None):
        # Default n_fft is 2048 in STFT
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)
        
        # Find indices for 500Hz and 2000Hz
        idx_500 = np.searchsorted(freqs, 500)
        idx_2000 = np.searchsorted(freqs, 2000)
        
        # Extract just the mid-frequency band
        S_mid = S[idx_500:idx_2000, :]
        
        # Calculate Wiener Entropy manually on this sub-array
        # Formula: exp(mean(log(S))) / mean(S) (Add epsilon to avoid log(0))
        eps = 1e-10
        geom_mean = np.exp(np.mean(np.log(S_mid + eps), axis=0))
        arith_mean = np.mean(S_mid + eps, axis=0)
        
        flatness = geom_mean / arith_mean
        return [float(np.mean(flatness))]


class SpectralContrastMeanExtractor(BaseFeatureExtractor):
    """Measures the clarity of the mix using Spectral Contrast.
    
    A poorly mixed, muddy, or heavily distorted Phonk track will have low contrast
    because the noise floor bleeds into all the harmonic peaks. 
    A clean, punchy track with high separation will have a high spectral contrast.
    """
    name = "spectral_contrast_mean"
    dimensions = 1
    
    def extract(self, y, sr, config=None):
        S = np.abs(librosa.stft(y))
        
        # Calculate spectral contrast. It returns a 7-dimensional band array by default.
        # We can just take the overall mean across all bands and frames.
        contrast = librosa.feature.spectral_contrast(S=S, sr=sr)
        mean_contrast = np.mean(contrast)
        
        return [float(mean_contrast)]


class SubBandEnergyExtractor(BaseFeatureExtractor):
    """Isolates the 20Hz-60Hz range to detect side-chained sub-bass."""
    name = "sub_band_energy"
    dimensions = 1

    def extract(self, y, sr, config=None):
        # Calculate power spectrogram
        S = np.abs(librosa.stft(y))**2
        freqs = librosa.fft_frequencies(sr=sr)
        
        # Sub-bass frequencies
        idx_20 = np.searchsorted(freqs, 20)
        idx_60 = np.searchsorted(freqs, 60)
        
        # Total energy per frame
        total_energy = np.sum(S, axis=0) + 1e-10
        
        # Sub-bass energy per frame
        sub_energy = np.sum(S[idx_20:idx_60, :], axis=0)
        
        # Ratio of sub-bass to total
        ratio = sub_energy / total_energy
        return [float(np.mean(ratio))]


class NarrowbandCrestExtractor(BaseFeatureExtractor):
    """Isolates the 800Hz-1200Hz fundamental frequency band of classical 808 cowbells."""
    name = "narrowband_crest"
    dimensions = 1

    def extract(self, y, sr, config=None):
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)
        
        idx_800 = np.searchsorted(freqs, 800)
        idx_1200 = np.searchsorted(freqs, 1200)
        
        S_band = S[idx_800:idx_1200, :]
        
        # Crest Factor = max / rms
        max_val = np.max(S_band, axis=0)
        rms_val = np.sqrt(np.mean(S_band**2, axis=0)) + 1e-10
        crest = max_val / rms_val
        
        return [float(np.mean(crest))]


class VocalBandFluxExtractor(BaseFeatureExtractor):
    """Calculates Spectral Flux in the 300Hz-3000Hz vocal band (staccato Memphis chops)."""
    name = "vocal_band_flux"
    dimensions = 1

    def extract(self, y, sr, config=None):
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)
        
        idx_300 = np.searchsorted(freqs, 300)
        idx_3000 = np.searchsorted(freqs, 3000)
        
        S_band = S[idx_300:idx_3000, :]
        
        # Spectral flux: difference between consecutive frames
        # Only take positive diffs (increases in energy = transients/chops)
        diffs = np.diff(S_band, axis=1)
        positive_diffs = np.maximum(diffs, 0)
        
        # Mean flux across the band for each frame
        flux = np.mean(positive_diffs, axis=0)
        
        return [float(np.mean(flux))]
