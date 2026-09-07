# Track A 5.5b ops `runs` views

Phase 5 Track A operator SQL aggregation. Not a user dashboard. Not a Web UI (Track D) substitute.

**Adopt token:** `ops_runs_views`
**Gates:** [phase5_gate_status.yaml](../operations/phase5_gate_status.yaml) `pr-55b-runs-views`
**DDL:** `supabase/migrations/018_ops_runs_views.sql`

live_gate_55b cannot close from this file and DDL alone. Production apply plus service_role SELECT evidence is required. Phase 5 overall_status stays in_progress. Issue #93 stays OPEN.

---

## Purpose

Aggregate `public.runs` by workflow / day / terminal status for operators. Auth / screens / billing are out of scope.

## Views

| View | Grain | Notes |
|------|-------|-------|
| `ops_runs_by_day` | `workflow`, `run_date`, `status` | `run_count`, first/last timestamps |
| `ops_runs_success_rate_30d` | `workflow` | last 30 days; `success_rate` is success / terminal (success+failed+cancelled) |

`security_invoker = true`. Underlying `runs` RLS remains. `service_role` bypasses RLS.

## P0 inherit

- `REVOKE ALL ... FROM PUBLIC, anon, authenticated`
- `GRANT SELECT` to `service_role` only
- Zero policies for `anon` / `authenticated`
- No INSERT / UPDATE / DELETE on the views

## Out of scope

- User-facing dashboard / Web UI
- Track C entitlements
- Replacing Healthchecks (5.5a) or Watchdog

## live gate 55b

Minimum to close:

- `pr-55b-runs-views` is `merged_and_verified`
- migration 018 applied in production
- operator SELECT evidence (no user UI screenshot as substitute)

Closing `live_gate_55b` leaves Phase 5 `overall_status` `in_progress`.

