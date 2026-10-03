"""Localhost Web UI as-of prototype (not Track D)."""

ABS_TOL = 1e-9
AXIS_LEN = 60

P_ISO_README_MARKERS: tuple[str, ...] = (
    'Track D ではない',
    '仕様正本ではない',
    'live_gate_5d を閉じない',
    '本番隔離',
    'P-ISO-1',
    'P-ISO-6',
    'P-ISO-10',
)

FORBIDDEN_FREEZE_IMPORT_SUBSTRINGS: tuple[str, ...] = (
    "yfinance",
    "signed_url_mint",
    "put_immutable",
    "put-immutable",
    "upload_to_all_targets",
    "upload_to_all",
)

__all__ = [
    "ABS_TOL",
    "AXIS_LEN",
    "P_ISO_README_MARKERS",
    "FORBIDDEN_FREEZE_IMPORT_SUBSTRINGS",
]
