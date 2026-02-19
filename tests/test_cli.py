"""Tests for cli.py — Command-line interface."""

import subprocess
import pytest

PYTHON = ".venv/bin/python3.12"
CLI = "cli.py"
CWD = "/Users/adrianpartain/Documents/SoloProjects/apps/HyperPhonkCurator"


def run_cli(*args):
    return subprocess.run(
        [PYTHON, CLI] + list(args),
        capture_output=True, text=True, cwd=CWD,
    )


class TestCLIStats:
    def test_stats_runs(self):
        result = run_cli("stats")
        assert result.returncode == 0
        assert "SQLite tracks:" in result.stdout

    def test_stats_shows_dimensions(self):
        result = run_cli("stats")
        assert "Search dimensions:" in result.stdout


class TestCLISearch:
    def test_search_finds_artist(self):
        result = run_cli("search", "HXVRMXN")
        assert result.returncode == 0
        assert "HXVRMXN" in result.stdout

    def test_search_no_results(self):
        result = run_cli("search", "NONEXISTENT_12345")
        assert result.returncode == 0
        assert "No tracks found" in result.stdout


class TestCLISimilar:
    def test_similar_with_valid_id(self):
        result = run_cli("similar", "HXVRMXN - Eclipse.mp3")
        assert result.returncode == 0
        assert "%" in result.stdout

    def test_similar_with_invalid_id(self):
        result = run_cli("similar", "FAKE.mp3")
        assert result.returncode == 0
        assert "not found" in result.stdout


class TestCLIFeatures:
    def test_features_shows_all(self):
        result = run_cli("features")
        assert result.returncode == 0
        assert "tempo" in result.stdout
        assert "tonnetz" in result.stdout
        assert "43 stored" in result.stdout or "43" in result.stdout


class TestCLIInspect:
    def test_inspect_shows_features(self):
        result = run_cli("inspect", "HXVRMXN - Eclipse.mp3")
        assert result.returncode == 0
        assert "tempo" in result.stdout
        assert "mfcc" in result.stdout
        assert "tonnetz" in result.stdout

    def test_inspect_invalid_id(self):
        result = run_cli("inspect", "FAKE.mp3")
        assert result.returncode == 0
        assert "not found" in result.stdout


class TestCLIHelp:
    def test_no_args(self):
        result = run_cli()
        assert result.returncode == 1

    def test_help_flag(self):
        result = run_cli("--help")
        assert result.returncode == 0
