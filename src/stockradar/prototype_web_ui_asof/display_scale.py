"""Display-only axis scaling (do not persist)."""
from __future__ import annotations


def y_z_from_z(z: float | None) -> float | None:
    """Map z_turnover_60 to shared display axis via /5. Never clamp."""
    if z is None:
        return None
    return float(z) / 5.0
