"""
Config — Loads and validates YAML configuration files.

Reads features.yaml to determine which features are extracted,
which are enabled for search, and provides version hashing for
cache invalidation.
"""

import hashlib
import os
from pathlib import Path

import yaml

# Resolve project root from this file's location
_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG_PATH = str(_PROJECT_ROOT / "config" / "features.yaml")
DEFAULT_PIPELINE_CONFIG_PATH = str(_PROJECT_ROOT / "config" / "pipeline.yaml")


def load_pipeline_config(config_path=DEFAULT_PIPELINE_CONFIG_PATH):
    """Load and return the pipeline configuration dict.

    Args:
        config_path: Path to pipeline.yaml.

    Returns:
        Dict with download, analysis, indexing, cleanup, and progress settings.
    """
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Apply defaults for missing keys
    defaults = {
        "download": {"workers": 4, "rate_limit_pause": 2.0, "max_retries": 3},
        "analysis": {"workers": "auto", "timeout": 120},
        "indexing": {"batch_size": 100},
        "cleanup": {"delete_mp3_after": True, "temp_dir": "data/tmp"},
        "progress": {"show_bar": True, "log_file": "data/pipeline.log"},
    }
    for section, section_defaults in defaults.items():
        if section not in config:
            config[section] = section_defaults
        else:
            for key, value in section_defaults.items():
                config[section].setdefault(key, value)

    # Resolve "auto" workers
    if config["analysis"]["workers"] == "auto":
        config["analysis"]["workers"] = os.cpu_count() or 4

    return config


def load_feature_config(config_path=DEFAULT_CONFIG_PATH):
    """Load and return the full feature configuration dict.

    Args:
        config_path: Path to features.yaml.

    Returns:
        Dict with 'version' (int) and 'features' (dict of feature configs).
    """
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config


def get_enabled_features(config_path=DEFAULT_CONFIG_PATH):
    """Return list of feature names that are enabled for search.

    These are the features included in the ChromaDB search vector.
    Sorted alphabetically for deterministic vector ordering.

    Returns:
        Sorted list of feature name strings.
    """
    config = load_feature_config(config_path)
    enabled = []
    for name, cfg in config.get("features", {}).items():
        if cfg.get("enabled", False):
            enabled.append(name)
    return sorted(enabled)


def get_feature_weights(config_path=DEFAULT_CONFIG_PATH):
    """Return dict of feature_name → weight for enabled features.

    Weights are applied at query time to scale feature importance.
    Default weight is 1.0 if not specified in config.

    Returns:
        Dict mapping feature name to float weight, sorted alphabetically.
    """
    config = load_feature_config(config_path)
    weights = {}
    for name in get_enabled_features(config_path):
        cfg = config.get("features", {}).get(name, {})
        weights[name] = float(cfg.get("weight", 1.0))
    return dict(sorted(weights.items()))

def get_feature_config(feature_name, config_path=DEFAULT_CONFIG_PATH):
    """Get the config dict for a specific feature.

    Args:
        feature_name: Name of the feature (e.g., "mfcc").
        config_path: Path to features.yaml.

    Returns:
        Dict of feature-specific config (e.g., {"n_coefficients": 13, ...}),
        or empty dict if not found.
    """
    config = load_feature_config(config_path)
    return config.get("features", {}).get(feature_name, {})


def get_search_dimensions(config_path=DEFAULT_CONFIG_PATH):
    """Total dimensions of the search vector (sum of enabled feature dims).

    Returns:
        Integer total dimension count.
    """
    config = load_feature_config(config_path)
    total = 0
    for name in get_enabled_features(config_path):
        feature_cfg = config.get("features", {}).get(name, {})
        total += feature_cfg.get("dimensions", 1)
    return total


def get_feature_version(config_path=DEFAULT_CONFIG_PATH):
    """Return a hash representing the current search feature configuration.

    Changes when enabled features or their parameters change.
    Used to detect stale vectors in the database.

    Returns:
        String hash (first 12 chars of SHA256).
    """
    enabled = get_enabled_features(config_path)
    config = load_feature_config(config_path)

    # Build a stable string from enabled features + their configs
    parts = []
    for name in enabled:
        cfg = config.get("features", {}).get(name, {})
        parts.append(f"{name}:{cfg.get('dimensions', '?')}")
        # Include extractor-specific params like n_coefficients
        for key in sorted(cfg.keys()):
            if key not in ("enabled", "dimensions", "description"):
                parts.append(f"  {key}={cfg[key]}")

    version_string = "\n".join(parts)
    return hashlib.sha256(version_string.encode()).hexdigest()[:12]


def get_search_feature_names(config_path=DEFAULT_CONFIG_PATH):
    """Return human-readable feature names for enabled search features.

    Used by the UI for labels on the Sonic DNA Breakdown.

    Returns:
        List of strings, one per dimension of the search vector.
    """
    config = load_feature_config(config_path)
    names = []

    for feature_name in get_enabled_features(config_path):
        feature_cfg = config.get("features", {}).get(feature_name, {})
        dims = feature_cfg.get("dimensions", 1)

        if dims == 1:
            # Simple name
            desc = feature_cfg.get("description", feature_name)
            names.append(desc.split(" — ")[0] if " — " in desc else feature_name.replace("_", " ").title())
        else:
            # Multi-dim: generate numbered labels
            base = feature_name.replace("_", " ").title()
            for i in range(dims):
                names.append(f"{base} {i+1}")

    return names
