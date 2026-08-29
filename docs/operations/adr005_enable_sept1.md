# ADR-005 enable window (9/1 00:00-10:59 JST)

Run **after** 8/31 Daily CAS canary success. Do **not** enable on 8/31 night.

## Prerequisites checklist

- [ ] Migrations 011-013 applied
- [ ] Worker production deployed with MNC_DISPATCH_ENABLED=false
- [ ] August committed Core confirmed
- [ ] 8/31 both Layer-1 pointers immutable + version bump

## Steps (order matters)

1. **00:00-10:59 JST:** enable + bootstrap in **one DB transaction**
   - Set adr005_runtime_config.feature_start_release_month = 2026-09
   - Bootstrap [2026-09, current] — if September canonical does not exist yet, grandfather **0** (do not invent current-only rows)
   - Set bootstrap_complete = true
   - YAML adr005.feature_start_release_month is mirror only; do not use YAML as input
2. Set Worker env MNC_DISPATCH_ENABLED=true and **redeploy** wrangler production.
3. Ensure Monthly can see metric set: ADR005_METRIC_SET_VERSION_ID (Actions secret / env) set to active Path B set id.
4. **11:00 JST:** Monthly runs commit_monthly_snapshot_with_backfill_request.
5. **11:15+:** poller claims outbox; worker runs series_seed. Watch poller runs (15m SLO not guaranteed under GitHub schedule delay).

## Abort / pause

- Pre-enable failure: leave dispatch false; keep Daily CAS.
- Post-enable failure: set dispatch false, pause incomplete requests, drain leases. Do not revert Daily CAS alone.
