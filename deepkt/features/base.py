"""Base interface for pluggable feature extractors.

All feature extractors should subclass BaseFeatureExtractor and implement
the extract() method. The analyzer will call extract() with the trimmed
audio array and sample rate, and concatenate the results.
"""

from abc import ABC, abstractmethod


class BaseFeatureExtractor(ABC):
    """Interface for a single audio feature extractor."""

    name: str = "unnamed"
    dimensions: int = 0

    @abstractmethod
    def extract(self, y, sr, config=None) -> list[float]:
        """Extract feature values from an audio signal.

        Args:
            y: Audio time series (numpy array), already silence-trimmed.
            sr: Sample rate (int), typically 22050.
            config: Optional dict of extractor-specific params from features.yaml.

        Returns:
            List of float values with length == self.dimensions.
        """
        raise NotImplementedError
