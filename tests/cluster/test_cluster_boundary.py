"""Tests for removal of the cluster service facade."""

from pathlib import Path


def test_cluster_service_facade_is_removed() -> None:
    source_root = Path(__file__).parents[2] / "src" / "execution_plane"

    assert not (source_root / "cluster" / "cluster_service.py").exists()
