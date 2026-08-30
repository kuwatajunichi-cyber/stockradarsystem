# ADR-005 ops gates (8/31 canary -> 9/1 enable)

Operator steps. Pre-enable evidence (2026-08-29): `docs/operations/evidence/adr005_r2_supabase_pre_enable_20260829.json`.

## Before 8/31 Daily (15:45 JST) — status

1. [x] Merge ADR-005 impl to main — PR #159 (`9c58ddc`)
2. [x] Apply Supabase migrations 011 / 012 / 013
3. Confirm Actions secret `GH_DISPATCH_TOKEN` matches Worker secret (same PAT/App token) — operator re-check
4. [x] Deploy Worker with `MNC_DISPATCH_ENABLED=false` (version `cc9a7e8c-10f6-44e5-82f0-21a286598aa3`)
5. [x] August committed Core — `monthly-20260801-30679139304`

## 8/31 Daily CAS canary

Cron: Cloudflare `45 6 * * *` UTC → **15:45 JST** → `daily.yml` via Worker.

**DB `cache_key`（正本）** は mapping `source_name_pattern`。entry id ではない。

| entry id (workflow) | `cache_pointers.cache_key` |
|---------------------|----------------------------|
| `cache-index-store-zip-v1` | `index-store-zip-v1` |
| `cache-ohlc-store-zip-v2` | `ohlc-store-zip-v2` |

### Pre-run baseline（2026-08-29 観測）

| cache_key | object_key | version |
|-----------|------------|---------|
| `index-store-zip-v1` | `cache/index-store-zip-v1/index_store.zip` | 1 |
| `ohlc-store-zip-v2` | `cache/ohlc-store-zip-v2/ohlc_store.zip` | 1 |

### Pre-run SQL（Daily 前に再取得して記録）

```sql
SELECT cache_key, object_key, version, sha256, writer_workflow, committed_at_utc
FROM cache_pointers
WHERE cache_key IN ('index-store-zip-v1', 'ohlc-store-zip-v2')
ORDER BY cache_key;
```

### Post-run SQL（Daily green 後）

```sql
SELECT cache_key, object_key, version, sha256, writer_workflow, committed_at_utc,
       (object_key LIKE '%sha256=%') AS has_sha256_path,
       (object_key LIKE '%/objects/sha256=%') AS has_objects_prefix
FROM cache_pointers
WHERE cache_key IN ('index-store-zip-v1', 'ohlc-store-zip-v2')
ORDER BY cache_key;
```

### Pass 条件（両方必須）

1. `has_sha256_path = true`（推奨: `has_objects_prefix = true`）
2. `version` が **pre-run より大きい**（baseline が 1 なら ≥ 2）
3. `writer_workflow = 'daily.yml'`
4. Daily run が success（下記 URL）

どちらか一方でも失敗 → `MNC_DISPATCH_ENABLED` を false のまま。**feature_start を立てない**。Daily CAS コードはそのまま残す。

### Run URL の取り方

```bash
# 直近の daily.yml（完了後）
gh run list --workflow daily.yml --limit 5
gh run view <RUN_ID> --json url,conclusion,displayTitle,createdAt,headSha
```

想定 URL 形: `https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/<RUN_ID>`

### Evidence 記録テンプレ

ファイル: `docs/operations/evidence/adr005_daily_cas_canary_20260831.json`

```json
{
  "recorded_at_utc": "REPLACE_ISO8601",
  "gate": "8/31_dual_pointer_cas",
  "daily_run_url": "https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/REPLACE",
  "daily_run_conclusion": "success|failure",
  "daily_head_sha": "REPLACE",
  "pre_run": {
    "index-store-zip-v1": {"object_key": "REPLACE", "version": 0},
    "ohlc-store-zip-v2": {"object_key": "REPLACE", "version": 0}
  },
  "post_run": {
    "index-store-zip-v1": {
      "object_key": "REPLACE",
      "version": 0,
      "has_sha256_path": false
    },
    "ohlc-store-zip-v2": {
      "object_key": "REPLACE",
      "version": 0,
      "has_sha256_path": false
    }
  },
  "pass": false,
  "notes": []
}
```

## 8/31 night

Do **not** run enable/bootstrap. `current` release month is still **2026-08**.

## Repo notes

- ADR-005 code on main via PR #159 (`9c58ddc`). Pre-enable evidence PR #161.
- Set GitHub Actions repository variable `MNC_DISPATCH_ENABLED=true` **only** when Worker env is true (9/1 morning). Until then leave unset/false so hourly `mnc_poller` stays `mnc_dispatch_disabled`.

## Record

| Gate | Evidence |
|------|----------|
| Worker prod deploy | wrangler version / dashboard deploy time |
| GH_DISPATCH_TOKEN | secret exists (no value in git) |
| August Core | pre-enable JSON / Supabase query |
| 8/31 dual pointer CAS | `adr005_daily_cas_canary_20260831.json` + run URL |
