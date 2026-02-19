"""
Analyzer — Config-driven feature extraction engine.

Runs ALL registered feature extractors on audio and returns a dict
of {feature_name: [values]}. The full feature dict is stored in SQLite.
A subset is selected for the ChromaDB search vector based on features.yaml.
"""

import librosa
import numpy as np

from deepkt.features import EXTRACTOR_REGISTRY, ALL_EXTRACTOR_NAMES
from deepkt.config import get_enabled_features, get_feature_config


def analyze_snippet(file_path, config_path=None):
    """Extract ALL features from an audio file.

    Runs every registered extractor regardless of what's enabled in config.
    Returns a dict keyed by feature name so values can be stored and
    selectively used later.

    Args:
        file_path: Path to an audio file (MP3, WAV, etc.)
        config_path: Optional path to features.yaml (for extractor-specific params).

    Returns:
        Dict of {feature_name: [float, ...]} with all 43 dimensions.
        Example: {"tempo": [143.5], "mfcc": [-20.4, 65.2, ...], ...}
    """
    # 1. Load audio
    y, sr = librosa.load(file_path)

    # 2. Remove silence
    y_trimmed, _ = librosa.effects.trim(y, top_db=20)

    # 3. Run ALL extractors
    feature_dict = {}
    for name in ALL_EXTRACTOR_NAMES:
        extractor_cls = EXTRACTOR_REGISTRY[name]
        ext = extractor_cls()

        # Get extractor-specific config (e.g., n_coefficients for MFCC)
        cfg = {}
        if config_path:
            cfg = get_feature_config(name, config_path)

        try:
            values = ext.extract(y_trimmed, sr, cfg)
            feature_dict[name] = values
        except Exception as e:
            # If one extractor fails, store zeros and continue
            feature_dict[name] = [0.0] * ext.dimensions
            print(f"  [WARN] Extractor '{name}' failed: {e}")

    return feature_dict


def build_search_vector(feature_dict, config_path=None, weights_override=None):
    """Select enabled features from a stored feature dict → weighted flat list for ChromaDB.

    Weights scale each feature group's influence in similarity search.
    Higher weight = more influence. Weight of 0.0 effectively disables.

    Args:
        feature_dict: Dict from analyze_snippet() or loaded from SQLite.
        config_path: Path to features.yaml.
        weights_override: Optional dict of {feature_name: weight} to override
                          config weights. Used by the UI sliders.

    Returns:
        List of floats — the weighted search vector.
    """
    from deepkt.config import DEFAULT_CONFIG_PATH, get_feature_weights
    config_path = config_path or DEFAULT_CONFIG_PATH

    enabled = get_enabled_features(config_path)
    default_weights = get_feature_weights(config_path)

    # Merge overrides
    weights = {**default_weights}
    if weights_override:
        weights.update(weights_override)

    vector = []
    for name in enabled:
        values = feature_dict.get(name, [])
        w = weights.get(name, 1.0)
        vector.extend([v * w for v in values])
    return vector


def get_full_feature_names():
    """Return human-readable names for ALL stored features (all 43 dims).

    Returns:
        List of (feature_group, dimension_label) tuples.
    """
    names = []
    for name in ALL_EXTRACTOR_NAMES:
        ext = EXTRACTOR_REGISTRY[name]()
        if ext.dimensions == 1:
            names.append(name.replace("_", " ").title())
        else:
            base = name.replace("_", " ").title()
            for i in range(ext.dimensions):
                names.append(f"{base} {i+1}")
    return names
