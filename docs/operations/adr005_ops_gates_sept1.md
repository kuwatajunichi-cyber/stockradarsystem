# ADR-005 ops gates (8/31 canary -> 9/1 enable)

Repository code for P0-P5/P4 is local. The following are **operator steps** (not claimed complete in-repo).

## Before 8/31 Daily (15:45 JST)

1. Merge ADR-005 PR(s) to main (P0-P5 then P4).
2. Apply Supabase migrations 011, 012, 013 to production.
3. Confirm Actions secret GH_DISPATCH_TOKEN matches Worker secret (same PAT/App token).
4. Deploy Cloudflare Worker to production with MNC_DISPATCH_ENABLED=false (4th cron registers but does not dispatch).
5. Confirm August committed Core in DB: monthly_snapshots with snapshot_date in 2026-08, status=committed, object_keys.core present.
   - Hint tag: monthly-20260801-30679139304 (verify in DB; do not trust GitHub alone).

## 8/31 Daily CAS canary

1. After green daily.yml, verify **both** cache_pointers for cache-index-store-zip-v1 and cache-ohlc-store-zip-v2:
   - object_key contains sha256=
   - version increased vs pre-run
2. If either side fails: keep MNC_DISPATCH_ENABLED=false; do **not** enable feature_start. Leave Daily CAS in place.

## 8/31 night

Do **not** run enable/bootstrap. current is still 2026-08.

## After merge (repo)

- ADR-005 code is on main via PR #159 (`9c58ddc`).
- Set GitHub Actions repository variable `MNC_DISPATCH_ENABLED` only when Worker env is true (9/1 morning). Until then leave unset/false so hourly poller liveness stays green (`mnc_dispatch_disabled`).

## Record

| Gate | Evidence |
|------|----------|
| Worker prod deploy | wrangler version / dashboard deploy time |
| GH_DISPATCH_TOKEN | secret exists (no value in git) |
| August Core | Supabase query result (operator) |
| 8/31 dual pointer CAS | pointer rows / run URL |
