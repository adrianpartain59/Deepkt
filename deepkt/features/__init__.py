"""Pluggable feature extractors for Sonic DNA analysis.

The registry maps feature names (as used in features.yaml) to their
extractor classes. ALL_EXTRACTORS is the ordered list used during
analysis — every extractor runs regardless of config.
"""

from deepkt.features.tempo import TempoExtractor
from deepkt.features.mfcc import MFCCExtractor
from deepkt.features.spectral import SpectralCentroidExtractor, SpectralContrastExtractor, SpectralFlatnessExtractor, HissDensityExtractor, RolloffRatioExtractor, MidFrequencyFlatnessExtractor, SubBandEnergyExtractor, NarrowbandCrestExtractor, VocalBandFluxExtractor, SpectralContrastMeanExtractor
from deepkt.features.rhythm import ZeroCrossingRateExtractor, OnsetStrengthExtractor, RMSEnergyExtractor, HPSSRatioExtractor, TimeDomainCrestExtractor, TempogramRatioExtractor
from deepkt.features.chroma import ChromaExtractor
from deepkt.features.tonnetz import TonnetzExtractor

# Maps feature names (from features.yaml) to extractor classes
EXTRACTOR_REGISTRY = {
    "tempo": TempoExtractor,
    "mfcc": MFCCExtractor,
    "spectral_centroid": SpectralCentroidExtractor,
    "spectral_contrast": SpectralContrastExtractor,
    "zero_crossing_rate": ZeroCrossingRateExtractor,
    "onset_strength": OnsetStrengthExtractor,
    "rms_energy": RMSEnergyExtractor,
    "chroma": ChromaExtractor,
    "tonnetz": TonnetzExtractor,
    "hpss_ratio": HPSSRatioExtractor,
    "spectral_flatness": SpectralFlatnessExtractor,
    "hiss_density": HissDensityExtractor,
    "rolloff_ratio": RolloffRatioExtractor,
    "mid_frequency_flatness": MidFrequencyFlatnessExtractor,
    "sub_band_energy": SubBandEnergyExtractor,
    "narrowband_crest": NarrowbandCrestExtractor,
    "vocal_band_flux": VocalBandFluxExtractor,
    "time_domain_crest": TimeDomainCrestExtractor,
    "tempogram_ratio": TempogramRatioExtractor,
    "spectral_contrast_mean": SpectralContrastMeanExtractor,
}

# Ordered list of all extractors — used during analysis
ALL_EXTRACTOR_NAMES = sorted(EXTRACTOR_REGISTRY.keys())
