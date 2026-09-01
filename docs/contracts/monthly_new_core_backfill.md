# Monthly new-Core backfill runbook (ADR-005)

## Status

ADR-005 **Adopted**. Live gate closed 2026-09-01 (`docs/operations/adr005_gate_status.yaml`).

## Steady-state path (monthly inline)

Canonical runner is `monthly.yml` job `series_seed` (same pattern as Daily `write_derived_generation`):

1. `build` commits the monthly snapshot + MNC request/outbox via RPC.
2. When `mnc_outcome=runnable`, `series_seed` claims **that request's** outbox (`claim_mnc_outbox` with `p_request_id`) and runs `mnc_worker_cli.py drain-request` in-process (all remaining trade_dates).
3. If the poller (or another worker) already owns the outbox (`claimed` / `dispatched`, or request in `dispatched` / `series_running` / …), monthly **skips with exit 0** and leaves catch-up to the owner. Do **not** treat that as monthly failure, and never `fail_mnc_outbox` a foreign row.
4. Parallelism: `MNC_CODE_CONCURRENCY` (default 8) for Layer1 fetch/compute; `MNC_R2_CONCURRENCY` (default 32) for series GET/PUT. boto3 pool follows `MNC_R2_CONCURRENCY` or `DERIVED_R2_CONCURRENCY`. Drain visibility defaults to 7200s with ≤45s heartbeat. Layer1 ensure runs once per request. Same instrument code stays date-serial.
5. Parallel PUT blast radius: register stays serial; a mid-batch PUT failure can leave registered-but-not-uploaded objects — `derived_orphan_sweeper` / generation sweeper is the recovery path.
6. Cloudflare `mnc_poller` + `monthly_new_core_backfill.yml` remain for catch-up / retry when monthly seed skips (owned elsewhere) or fails.

## Split request (blocked added_codes or work_units)

1. Do not dispatch workers against the blocked request.
2. Partition `added_codes` into exclusive subsets. Union must equal the original set. Empty partitions are forbidden.
3. Commit all partition requests and mark the original blocked row `superseded` in **one** RPC transaction.
4. Identity includes `partition_index` (0-based), `partition_count` (>=1), and `partition_codes_digest` (ADR-005 section 7). Unsplit requests use (0, 1).
5. Date parallelism is allowed only after exclusive validation. The same instrument code stays serial. Completeness `candidate` uses that partition's codes only.
6. `history_quality` in-scope includes only link_role=canonical_winner partition requests on a winner snapshot. A loser snapshot is noncanonical_release and must not treat the linked winner request as in-scope (ADR-005 sections 1.2 and 4).

## Operator notes

- Owner: `docs/operations/adr005_gate_status.yaml` field `owner`
- Do not add `actions: write` to `monthly.yml`
- Live Layer 1 cache protocol is `immutable_pointer_cas` (`put-immutable` + pointer CAS)
- Repair approver team may stay `repo-maintainers`

## Related

- [ADR-005](../adr/adr-005-monthly-new-core-backfill.md)
- [Poller Cron skeleton](monthly_new_core_backfill_cloudflare_cron_dispatch.md)
