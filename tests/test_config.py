"""Tests for deepkt.config — YAML feature configuration."""

import pytest
from deepkt.config import (
    load_feature_config,
    get_enabled_features,
    get_search_dimensions,
    get_feature_version,
    get_search_feature_names,
    get_all_feature_names,
)


class TestLoadConfig:
    def test_loads_successfully(self):
        config = load_feature_config()
        assert "version" in config
        assert "features" in config

    def test_has_9_features(self):
        config = load_feature_config()
        assert len(config["features"]) == 9


class TestEnabledFeatures:
    def test_returns_sorted_list(self):
        enabled = get_enabled_features()
        assert enabled == sorted(enabled)

    def test_default_has_9_enabled(self):
        enabled = get_enabled_features()
        assert len(enabled) == 9


class TestSearchDimensions:
    def test_default_is_43(self):
        dims = get_search_dimensions()
        assert dims == 43


class TestFeatureVersion:
    def test_returns_string(self):
        ver = get_feature_version()
        assert isinstance(ver, str)
        assert len(ver) == 12


class TestAllFeatureNames:
    def test_returns_9_features(self):
        names = get_all_feature_names()
        assert len(names) == 9


class TestSearchFeatureNames:
    def test_returns_43_labels(self):
        names = get_search_feature_names()
        assert len(names) == 43

    def test_all_strings(self):
        names = get_search_feature_names()
        assert all(isinstance(n, str) for n in names)
