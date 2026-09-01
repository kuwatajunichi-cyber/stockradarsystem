# ADR-005 enable window (9/1 00:00-10:59 JST)

**Status (2026-09-01 ~00:52 JST): ENABLE APPLIED** — evidence `docs/operations/evidence/adr005_enable_20260901.json`.  
`feature_start=2026-09`, `bootstrap_complete=true`, grandfather 0, Worker `MNC_DISPATCH_ENABLED=true` (version `8e37a9e8-725a-4d2b-8292-d7d33efc241d`), GHA var true, `ADR005_METRIC_SET_VERSION_ID` set.  
Next: wait for **11:00 JST Monthly**, then poller/series_seed evidence. `live_gate_005` stays **open**.

Run **after** 8/31 Daily CAS canary success. Do **not** enable on 8/31 night.

## Prerequisites checklist

- [x] Migrations 011-013 applied (prod versions `20260829120000` / `20260829120100` / `20260829120200`; evidence `docs/operations/evidence/adr005_r2_supabase_pre_enable_20260829.json`)
- [x] Worker production deployed with MNC_DISPATCH_ENABLED=false (version `cc9a7e8c-10f6-44e5-82f0-21a286598aa3`)
- [x] August committed Core confirmed (`monthly-20260801-30679139304`; R2 object present under `R2_BASE_PREFIX`)
- [x] 8/31 both Layer-1 pointers immutable + version bump (pass; evidence `docs/operations/evidence/adr005_daily_cas_canary_20260831.json`; Daily run `33365512413`)

## Final confirmation (implementation reality)

| ADR 文言 | 本番の事実 |
|----------|------------|
| 「初回 enable RPC」同一 transaction | **enable RPC は未実装**。正本は手動 SQL transaction（下記） |
| `[feature_start, current]` に grandfather/request | 9/1 午前（Monthly 前）は `current=2026-08` で範囲が空 → **grandfather 0 行**が正しい。September request は 11:00 Monthly RPC が作る |
| YAML `feature_start_release_month` | mirror のみ。**入力にしない** |
| `bootstrap_complete` | コード参照はほぼ無し（フラグ記録）。それでも enable 契約どおり `true` にする |

Active Path B set（2026-08-30 確認）: `13209d23-ded6-482d-be08-7da6062013c0`（`daily_core_v1__4dca11eaed32`）。Actions secret `ADR005_METRIC_SET_VERSION_ID` にこれを入れる（Monthly / backfill worker）。

## Steps (order matters)

### 0. Gate check（00:00 前）

- 8/31 evidence `pass: true`
- `adr005_runtime_config.feature_start_release_month IS NULL`
- Worker / GHA `MNC_DISPATCH_ENABLED` はまだ false

### 1. Enable + bootstrap（00:00–10:59 JST）— **one DB transaction**

Preflight（別セッション可）:

```sql
-- current release month = max committed monthly YYYY-MM (Core あり)
SELECT max(to_char(snapshot_date::date, 'YYYY-MM')) AS current_release_month
FROM monthly_snapshots
WHERE status = 'committed'
  AND object_keys ? 'core';

SELECT config_key, feature_start_release_month, bootstrap_complete, updated_at_utc
FROM adr005_runtime_config
WHERE config_key = 'monthly_new_core';

-- 9/1 午前の期待: current_release_month = '2026-08'
-- → bootstrap 対象 [2026-09, 2026-08] は空集合
```

Enable transaction（**この順・1 トランザクション**）:

```sql
BEGIN;

SELECT feature_start_release_month, bootstrap_complete
FROM adr005_runtime_config
WHERE config_key = 'monthly_new_core'
FOR UPDATE;

-- 手動確認: feature_start IS NULL AND bootstrap_complete = false
-- そうでなければ ROLLBACK;

-- 空範囲のとき INSERT は行わない（grandfather 0）
-- （将来、enable を Monthly 後にやる場合のみ [2026-09, current] の canonical ごとに
--  grandfather / request を同 transaction で埋める。本窓では禁止）

UPDATE adr005_runtime_config
SET
  feature_start_release_month = '2026-09',
  bootstrap_complete = true,
  updated_at_utc = now()
WHERE config_key = 'monthly_new_core'
  AND feature_start_release_month IS NULL
  AND bootstrap_complete = false;

-- 期待: UPDATE 1 row。0 row なら ROLLBACK;

SELECT feature_start_release_month, bootstrap_complete
FROM adr005_runtime_config
WHERE config_key = 'monthly_new_core';

SELECT count(*) AS mnc_request_count
FROM monthly_new_core_backfill_requests;

-- 9/1 午前の期待: mnc_request_count = 0

COMMIT;
```

Post-check:

```sql
SELECT public.get_adr005_feature_start_release_month() AS feature_start;
-- 期待: 2026-09
```

### 2. Worker + GHA flag（DB commit の直後、Monthly 前）

1. `workers/github-cron-dispatcher/wrangler.toml`: `MNC_DISPATCH_ENABLED = "true"`
2. `npx wrangler deploy`（本番）
3. GitHub repo variable `MNC_DISPATCH_ENABLED=true`（`mnc_poller` 欠走検知を有効化）
4. Actions secret `ADR005_METRIC_SET_VERSION_ID=13209d23-ded6-482d-be08-7da6062013c0`（未設定なら追加）

### 3. Metric set

Monthly / `monthly_new_core_backfill.yml` が上記 secret を読む。`feature_start` セット後は secret 無しだと Monthly commit が fail-closed。

### 4. 11:00 JST — Monthly

Worker cron `0 2 1 * *` UTC = **11:00 JST** day-1 → `monthly.yml` → `commit_monthly_snapshot_with_backfill_request`。

観測:

```sql
SELECT monthly_tag, snapshot_date, status
FROM monthly_snapshots
WHERE snapshot_date >= '2026-09-01'
ORDER BY github_run_id DESC
LIMIT 5;

SELECT request_id, release_month, status, reason_code, previous_monthly_tag
FROM monthly_new_core_backfill_requests
WHERE release_month = '2026-09'
ORDER BY created_at_utc DESC
LIMIT 5;
```

### 5. 11:15+ — poller / series_seed

`*/15` Cron → `monthly_new_core_backfill_dispatch.yml`。GHA 遅延あり（15m SLO 非保証）。

```bash
gh run list --workflow monthly_new_core_backfill_dispatch.yml --limit 5
gh run list --workflow monthly_new_core_backfill.yml --limit 5
```

## Abort / pause

- Pre-enable failure: leave dispatch false; keep Daily CAS; do not set feature_start.
- Post-enable failure: set Worker + GHA `MNC_DISPATCH_ENABLED=false`, pause incomplete requests, drain leases. Do **not** revert Daily CAS alone.
- Do **not** reopen enable by clearing `feature_start` without repair plan（ADR §10 rollback: flag off / pause / drain）。

## Evidence after enable（追記用）

`docs/operations/evidence/adr005_enable_20260901.json`（作成は実行時）:

```json
{
  "recorded_at_utc": "REPLACE",
  "feature_start_release_month": "2026-09",
  "bootstrap_complete": true,
  "grandfather_count": 0,
  "mnc_request_count_at_enable": 0,
  "worker_version_id": "REPLACE",
  "mnc_dispatch_enabled": true,
  "adr005_metric_set_version_id": "13209d23-ded6-482d-be08-7da6062013c0",
  "monthly_run_url": "REPLACE",
  "poller_run_urls": [],
  "notes": []
}
```
