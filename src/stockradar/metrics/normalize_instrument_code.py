"""Single implementation for instrument_code normalization (Phase 4.5 SSOT)."""
from __future__ import annotations

import re
import unicodedata


def normalize_instrument_code(raw: str) -> str:
    """
    Normalize raw CSV ``code`` / logical ``instrument_code``.

    Rules (fixed contract):
    - Strip leading/trailing whitespace
    - Unicode NFC
    - Pure numeric codes with length < 4 are zero-padded to 4 digits
    - Length >= 4 numeric codes are unchanged
    - Alphanumeric codes are trimmed only (no zero-padding)
    """
    text = unicodedata.normalize("NFC", str(raw).strip())
    if not text:
        return text
    if re.fullmatch(r"\d+", text):
        if len(text) < 4:
            return text.zfill(4)
        return text
    return text
