"""Contract: generation sweep must not delete derived-inputs/."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
_REPO = Path(__file__).resolve().parents[1]


def test_orphan_sweeper_does_not_target_derived_inputs_prefix() -> None:
    text = (_REPO / "scripts" / "storage" / "orphan_sweeper.py").read_text(encoding="utf-8")
    assert "derived-inputs/" not in text or "derived-inputs" not in text.split("DELETE")[0]
    # Prefer explicit allow-list of generation prefixes when present.
    derived = _REPO / "scripts" / "storage" / "derived_generation_sweeper.py"
    if derived.is_file():
        body = derived.read_text(encoding="utf-8")
        assert "derived-snapshots/" in body
        assert "derived-series/" in body
        assert "derived-inputs/" not in body or "not delete derived-inputs" in body.lower()
