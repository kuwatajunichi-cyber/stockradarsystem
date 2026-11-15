"""Import direction: core does not depend on scripts, and rollout stays one-way."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from stockradar.storage import mapping_catalog, phase4_rollout
from stockradar.storage.r2_staging import R2StagingAdapter as SrcAdapter

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "stockradar"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_src_does_not_import_scripts() -> None:
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for module in _imported_modules(path):
            if module == "scripts" or module.startswith("scripts."):
                offenders.append(f"{path.relative_to(_REPO)} -> {module}")
    assert offenders == []


def test_phase4_rollout_does_not_import_mapping_catalog() -> None:
    modules = _imported_modules(_SRC / "storage" / "phase4_rollout.py")
    assert "stockradar.storage.mapping_catalog" not in modules
    assert hasattr(mapping_catalog, "resolve_phase4_rollout_stage")
    assert not hasattr(phase4_rollout, "resolve_phase4_rollout_stage")


def test_daily_sma75_comes_from_indicators() -> None:
    modules = _imported_modules(_SRC / "jobs" / "compute_indicators_for_core.py")
    assert "stockradar.indicators.sma75_rs" in modules
    assert "stockradar.prototype_web_ui_asof.sma75_rs" not in modules
    from stockradar.indicators.sma75_rs import compute_rs_sma75_from_closes
    from stockradar.prototype_web_ui_asof.sma75_rs import (
        compute_rs_sma75_from_closes as facade,
    )

    assert facade is compute_rs_sma75_from_closes


def test_staging_adapter_reexport_is_the_src_class() -> None:
    from scripts.storage.r2_staging_client import R2StagingAdapter

    assert R2StagingAdapter is SrcAdapter
