from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_timezone_normalization_is_centralized_to_date_anchor() -> None:
    base = Path("src/stockradar/indicators")
    date_anchor = (base / "date_anchor.py").read_text(encoding="utf-8")
    assert "normalize_utc_naive_index" in date_anchor

    forbidden = ("tz_convert(", "tz_localize(")
    for path in sorted(base.glob("*.py")):
        if path.name == "date_anchor.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} に禁止トークンが残存: {token}"
