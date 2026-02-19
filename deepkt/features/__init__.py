"""Pluggable feature extractors for Sonic DNA analysis.

The registry maps feature names (as used in features.yaml) to their
extractor classes. ALL_EXTRACTORS is the ordered list used during
analysis — every extractor runs regardless of config.
"""

from deepkt.features.tempo import TempoExtractor
from deepkt.features.mfcc import MFCCExtractor
from deepkt.features.spectral import SpectralCentroidExtractor, SpectralContrastExtractor
from deepkt.features.rhythm import ZeroCrossingRateExtractor, OnsetStrengthExtractor, RMSEnergyExtractor
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
}

# Ordered list of all extractors — used during analysis
ALL_EXTRACTOR_NAMES = sorted(EXTRACTOR_REGISTRY.keys())
