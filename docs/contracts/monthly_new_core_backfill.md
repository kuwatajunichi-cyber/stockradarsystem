# Monthly new-Core backfill runbook (ADR-005)

## Status

Skeleton only. Implementation is unstarted. This is not a live operator runbook.

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
- Live Layer 1 cache keys stay fixed-key until `pr-005-daily-cas`
- Repair approver team may stay `repo-maintainers` until `pr-005-series-seed`

## Related

- [ADR-005](../adr/adr-005-monthly-new-core-backfill.md)
- [Poller Cron skeleton](monthly_new_core_backfill_cloudflare_cron_dispatch.md)
