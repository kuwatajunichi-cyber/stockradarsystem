# ADR-005 enable window (9/1 00:00-10:59 JST)

Run **after** 8/31 Daily CAS canary success. Do **not** enable on 8/31 night.

## Prerequisites checklist

- [x] Migrations 011-013 applied (prod versions `20260829120000` / `20260829120100` / `20260829120200`; evidence `docs/operations/evidence/adr005_r2_supabase_pre_enable_20260829.json`)
- [x] Worker production deployed with MNC_DISPATCH_ENABLED=false (version `cc9a7e8c-10f6-44e5-82f0-21a286598aa3`)
- [x] August committed Core confirmed (`monthly-20260801-30679139304`; R2 object present under `R2_BASE_PREFIX`)
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
