"""Free-tier preview ranking (testable pure)."""
from __future__ import annotations

from typing import Sequence


def free_preview_keep_mask(
    z_values: Sequence[float | None],
    *,
    top_n: int = 20,
) -> list[bool]:
    n = len(z_values)
    if n == 0:
        return []
    indexed: list[tuple[int, float]] = []
    for i, z in enumerate(z_values):
        if z is None:
            continue
        try:
            fz = float(z)
        except (TypeError, ValueError):
            continue
        if fz != fz:
            continue
        indexed.append((i, fz))
    indexed.sort(key=lambda t: (-t[1], t[0]))
    keep = [False] * n
    if not indexed:
        return keep
    if len(indexed) <= top_n:
        for i, _ in indexed:
            keep[i] = True
        return keep
    threshold = indexed[top_n - 1][1]
    for i, z in indexed:
        if z >= threshold:
            keep[i] = True
        else:
            break
    return keep
