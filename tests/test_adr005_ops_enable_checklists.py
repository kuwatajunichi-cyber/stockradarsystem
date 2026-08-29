"""Ops checklist docs for ADR-005 Sept 1."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
_REPO = Path(__file__).resolve().parents[1]


def test_ops_and_enable_checklists_exist_utf8() -> None:
    for rel in (
        "docs/operations/adr005_ops_gates_sept1.md",
        "docs/operations/adr005_enable_sept1.md",
    ):
        raw = (_REPO / rel).read_bytes()
        assert bytes([0]) not in raw
        text = raw.decode("utf-8")
        assert "MNC_DISPATCH_ENABLED" in text
        assert "2026-09" in text or "9/1" in text
