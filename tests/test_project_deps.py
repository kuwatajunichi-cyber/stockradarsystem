"""Project dependency contract: pyproject.toml is the single source of truth."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = REPO_ROOT / "requirements.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_requirements_txt_delegates_to_pyproject_only() -> None:
    """requirements.txt must not duplicate pins from pyproject.toml."""
    lines = [
        ln.strip()
        for ln in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert lines == ["-e ."], f"requirements.txt must contain only '-e .' (got {lines!r})"


def test_pyproject_declares_runtime_deps_for_phase3() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    for needle in ("httpx>=", "boto3>="):
        assert needle in text, f"missing {needle!r} in pyproject.toml dependencies"
