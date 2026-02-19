"""Tests for deepkt.downloader — yt-dlp audio download wrapper."""

import os
import pytest

from deepkt.downloader import smart_download_range


class TestSmartDownloadRange:
    """Tests for the dynamic download range function."""

    def test_long_track_uses_30_to_60(self):
        """Tracks longer than 60s should download 00:30 to 01:00."""
        info = {'duration': 180}  # 3 min track
        result = smart_download_range(info, None)
        assert result == [{'start_time': 30, 'end_time': 60}]

    def test_short_track_uses_full_duration(self):
        """Tracks shorter than 60s should download from 0 to duration."""
        info = {'duration': 45}
        result = smart_download_range(info, None)
        assert result == [{'start_time': 0, 'end_time': 45}]

    def test_exactly_60s_uses_30_to_60(self):
        """A 60s track should still use the 30-60 range."""
        info = {'duration': 60}
        result = smart_download_range(info, None)
        assert result == [{'start_time': 30, 'end_time': 60}]

    def test_very_short_track(self):
        """A very short track (e.g., 10s) should download fully."""
        info = {'duration': 10}
        result = smart_download_range(info, None)
        assert result == [{'start_time': 0, 'end_time': 10}]

    def test_no_duration_info(self):
        """If duration is unknown (None), use default 30-60 range."""
        info = {'duration': None}
        result = smart_download_range(info, None)
        assert result == [{'start_time': 30, 'end_time': 60}]

    def test_missing_duration_key(self):
        """If 'duration' key is absent, use default range."""
        info = {}
        result = smart_download_range(info, None)
        assert result == [{'start_time': 30, 'end_time': 60}]
