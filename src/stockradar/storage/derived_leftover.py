"""Pure leftover derived object prefixes (failed manifests, forbidden shadow namespace)."""
from __future__ import annotations

FORBIDDEN_DERIVED_PREFIXES: tuple[str, ...] = ("derived-shadow/",)


def failed_generation_snapshot_prefix(
    *,
    metric_set_version_id: str,
    trade_date: str,
    generation_id: str,
) -> str:
    return (
        f"derived-snapshots/metric-set={metric_set_version_id.strip().lower()}/"
        f"trade-date={trade_date}/generation={generation_id.strip().lower()}/"
    )


def leftover_scan_prefixes(
    *,
    metric_set_version_id: str | None = None,
    trade_date: str | None = None,
    generation_id: str | None = None,
    include_forbidden: bool = True,
) -> list[str]:
    prefixes: list[str] = []
    if include_forbidden:
        prefixes.extend(FORBIDDEN_DERIVED_PREFIXES)
    if metric_set_version_id and trade_date and generation_id:
        prefixes.append(
            failed_generation_snapshot_prefix(
                metric_set_version_id=metric_set_version_id,
                trade_date=trade_date,
                generation_id=generation_id,
            )
        )
    return prefixes
