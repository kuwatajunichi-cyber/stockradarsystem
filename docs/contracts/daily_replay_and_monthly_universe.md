# Daily replay and monthly universe (contract)

Japanese summary: README and workflow comments describe operator-facing behavior.

## Definitions

- Normal run: schedule, or dispatch with empty run_date, or run_date equals Tokyo today.
- Replay run: dispatch with run_date not equal to Tokyo today.
- Replay window: run_date within last 3 calendar months from Tokyo today.

## Monthly selection

- Tags: monthly-YYYYMMDD-<github.run_id>. Max snapshot D with D <= run_date; tie-break max run_id.
- If none: first parsable monthly-* from gh release list order; universe_resolution=fallback_latest.

## Patched cache

- Reuse only when manifest chosen_monthly_tag (else base_release) equals selected tag exactly.

## Replay cache policy

- is_replay=true: skip actions/cache/save for shared keys; restore allowed.

## Publish

- Default publish; skip_publish=true on dispatch skips render/upload.

## Code

- src/stockradar/universe/monthly_release_pick.py
- src/stockradar/jobs/validate_daily_dispatch_run_date.py
- src/stockradar/jobs/resolve_monthly_release_for_run_date.py
