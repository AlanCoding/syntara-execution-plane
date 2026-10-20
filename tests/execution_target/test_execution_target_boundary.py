"""Tests for removal of the execution_target service facade."""

from pathlib import Path


def test_execution_target_service_facade_is_removed() -> None:
    source_root = Path(__file__).parents[2] / "src" / "execution_plane"

    assert not (source_root / "execution_target" / "execution_target_service.py").exists()
