"""Architectural boundary tests for WorkItem consumers."""

from __future__ import annotations

import ast
from pathlib import Path

_WORK_ITEM_STORE_IDENTIFIERS = {"WorkStore", "work_item_store", "_work_item_store"}
_WORK_ITEM_STORE_MODULE = "execution_plane.work_item.work_item_store"


def _imported_store_aliases(tree: ast.Module) -> set[str]:
    aliases = {"WorkStore"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != _WORK_ITEM_STORE_MODULE:
            continue
        aliases.update(alias.asname or alias.name for alias in node.names if alias.name == "WorkStore")
    return aliases


def test_production_code_limits_work_store_to_composition_roots() -> None:
    source_root = Path(__file__).parents[2] / "src" / "execution_plane"
    internal_work_item_files = {
        source_root / "work_item" / "work_item_store.py",
        source_root / "work_item" / "work_scheduler.py",
        source_root / "work_item" / "ports.py",
    }
    composition_roots = {
        source_root / "commands" / "control.py",
        source_root / "commands" / "queries.py",
        source_root / "commands" / "work.py",
        source_root / "worker.py",
    }
    production_files = [path for path in source_root.rglob("*.py") if path not in internal_work_item_files]

    assert production_files
    for path in production_files:
        if path in composition_roots:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        aliases = _imported_store_aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in _WORK_ITEM_STORE_IDENTIFIERS, path
                assert node.id not in aliases, path
            if isinstance(node, ast.Attribute):
                assert node.attr not in _WORK_ITEM_STORE_IDENTIFIERS, path
