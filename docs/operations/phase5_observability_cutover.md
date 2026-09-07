# Phase 5 observability cutover（Healthchecks.io）

**採用:** 方針 C — Healthchecks.io、通知メール。  
**ロードマップ:** [issue_93_roadmap.md](issue_93_roadmap.md)  
**ゲート正本:** [phase5_gate_status.yaml](phase5_gate_status.yaml)

ping は `daily.yml` / `daily_universe_patch.yml` に組み込み済み（PR #174）。`live_gate_55a` は 2026-09-07 に closed。Phase 5 overall は in_progress。カレンダー契約を満たさない実装は 5.5a としてマージしない。

---

## スコープ

| Check | Workflow | 営業日 ping | 閉場日 ping |
|-------|----------|-------------|-------------|
| **patch-daily** | `daily_universe_patch.yml` | `is_open=True` かつ `put-patched` 成功後 | `is_open=False` のとき `resolve_trading_day` job 内（後続 job は skip） |
| **daily-indicators** | `daily.yml` | 通常本番 run 成功後（下記「監視対象外」以外） | 同上（`resolve_trading_day` job 内） |

`monthly.yml` と MNC poller/worker は **5.5a の Out of scope**。Watchdog が別契約で見る。Period 1d は MNC に合わない。

---

## カレンダー契約（正本）

**採用トークン:** `closed_day_expected_ping`

Healthchecks は XTKS を知らない。Cloudflare Cron は毎日起動する（`45 6 * * *`）。`daily.yml` / `daily_universe_patch.yml` は `is_open=False` のとき後続 job を skip する。

**旧契約は live 政策にしてはならない。** Period **1 day** + Grace **26 hours** のまま閉場日に ping しないと、金曜 15:45 JST の最終 ping から Period+Grace ≈ 50h で日曜に Down する。つまり **毎週末**に誤報する。連休 Pause だけでは土日をカバーしない。HC の weekday-only Cron も XTKS 祝日を取りこぼす。

| 条件 | ping | 置き場 |
|------|------|--------|
| 営業日・通常本番成功 | する | patch: `put-patched` 直後。daily: `render_and_upload` 末尾 |
| `is_open=False`（土日・XTKS 祝日） | **する**（閉場の成功相当）。daily は下記の監視対象外なら **しない** | 両 workflow とも `resolve_trading_day` job。後続 job に置かない |
| `is_replay=true` | **しない**（閉場日経路も含む） | daily のみ。`validate_dispatch` の小文字 `true` / `false`（`!= 'True'` では止まらない） |
| `skip_publish=true` | **しない**（閉場日経路も含む） | daily のみ（`workflow_dispatch` **input**。job output ではない） |

閉場日 ping も daily の `is_replay` / `skip_publish` を除外する。監視対象外を「閉場日だから送ってよい」と混ぜない。営業日に `resolve_trading_day` と成功経路の両方から ping しない（`is_open` で排他）。

**Pause は主運用ではない。** 土日・祝日の誤報回避に Healthchecks Pause を使わない。Pause は HC メンテや想定外の長期停止の退避に限る。Pause 運用を 5.5a live gate の完了条件の代替にしない。`closed_day_expected_ping` の live 証拠が必須。

**Watchdog は代替ではない。** [cron_dispatch_watchdog.md](../contracts/cron_dispatch_watchdog.md) = Cloudflare 欠走の当日検知。Healthchecks = GHA 成功の長めネット。両方残す。Healthchecks で Watchdog を廃止しない。

---

## 監視対象外（契約）

以下の run では **heartbeat を送らない**（Healthchecks 側も ping 欠落を期待しない）。閉場日経路でも除外する。

| 条件 | 理由 |
|------|------|
| `is_replay=true` | replay 検証。warm cache 非更新契約と同型 |
| `skip_publish=true` | 手動検証。外部公開なし。`skip_publish=true` でも job は走るので、job success だけで ping しない |

実装: ping step に `if` を付与。replay 判定は `validate_dispatch` 出力（小文字）。skip_publish 判定は `workflow_dispatch` input。

---

## Healthchecks.io 設定

1. アカウント作成 → **Email** 通知を有効化（**U-55a-1**）
2. Check を 2 本作成:
   - `stockradar-patch-daily`
   - `stockradar-daily-indicators`
3. **Period / Grace（目安）**
   - Period: **1 day**
   - Grace: **26 hours**（Cloudflare/GHA 遅延吸収）
4. Check 側の weekday-only スケジュールは使わない（祝日欠落）。カレンダーは `closed_day_expected_ping` で満たす。

---

## GitHub Secrets

**U-55a-2。** コード PR を U-gate 証拠なしで `merged_and_verified` にしない。Secrets 未設定のままマージすると毎 run が ping step fail する。

| Secret | 用途 |
|--------|------|
| `HEALTHCHECKS_PATCH_PING_URL` | `https://hc-ping.com/<uuid>`（patch check） |
| `HEALTHCHECKS_DAILY_PING_URL` | `https://hc-ping.com/<uuid>`（daily check） |

URL 全体を Secret に格納（uuid 単体より rotate 容易）。Secret 欠落は黙って skip しない（step fail + `heartbeat_ok=false`）。

---

## Workflow 組み込み

`continue-on-error` は **ping step のみ**。`|| true` 禁止。`put-patched` / upload には付けない。ping は事後観測であり preflight ではない。ping を必須 step にすると HC 障害が `finalize_run` 経由で pipeline failed になる。

実装: `python -m stockradar.observability.healthchecks_heartbeat`（空 URL は fail-closed。URL はログに出さない）。

patch に `is_replay` / `skip_publish` は無い（outputs は `run_date` / `is_open` のみ）。
daily の `is_replay` は `validate_daily_dispatch_run_date` が `true` / `false`（小文字）を出す。`!= 'True'` では replay を止められない。

### daily_universe_patch.yml

`resolve_trading_day` job 末尾（閉場日。後続 job は skip される）:

```yaml
- name: Heartbeat (Healthchecks patch, closed day)
  if: success() && steps.resolve.outputs.is_open != 'True'
  continue-on-error: true
  env:
    PYTHONPATH: src
    HEALTHCHECKS_PING_URL: ${{ secrets.HEALTHCHECKS_PATCH_PING_URL }}
  run: |
    set -euo pipefail
    python -m stockradar.observability.healthchecks_heartbeat
```

`put-patched` 成功 step の直後（営業日）:

```yaml
- name: Heartbeat (Healthchecks patch)
  if: success() && needs.resolve_trading_day.outputs.is_open == 'True'
  continue-on-error: true
  env:
    PYTHONPATH: src:.
    HEALTHCHECKS_PING_URL: ${{ secrets.HEALTHCHECKS_PATCH_PING_URL }}
  run: |
    set -euo pipefail
    python -m stockradar.observability.healthchecks_heartbeat
```

### daily.yml

`resolve_trading_day` job 末尾（閉場日）:

```yaml
- name: Heartbeat (Healthchecks daily, closed day)
  if: |
    success()
    && steps.resolve.outputs.is_open != 'True'
    && steps.validate_dispatch.outputs.is_replay != 'true'
    && (github.event_name != 'workflow_dispatch' || github.event.inputs.skip_publish != 'true')
  continue-on-error: true
  env:
    PYTHONPATH: src
    HEALTHCHECKS_PING_URL: ${{ secrets.HEALTHCHECKS_DAILY_PING_URL }}
  run: |
    set -euo pipefail
    python -m stockradar.observability.healthchecks_heartbeat
```

`render_and_upload` job 末尾（Upload 成功後。営業日の通常本番）:

```yaml
- name: Heartbeat (Healthchecks daily)
  if: |
    success()
    && needs.resolve_trading_day.outputs.is_open == 'True'
    && needs.resolve_trading_day.outputs.is_replay != 'true'
    && (github.event_name != 'workflow_dispatch' || github.event.inputs.skip_publish != 'true')
  continue-on-error: true
  env:
    PYTHONPATH: src
    HEALTHCHECKS_PING_URL: ${{ secrets.HEALTHCHECKS_DAILY_PING_URL }}
  run: |
    set -euo pipefail
    python -m stockradar.observability.healthchecks_heartbeat
```

curl ではなく heartbeat モジュール失敗時は step fail で可視化する（`heartbeat_ok=false` を Step Summary に出す）。本処理成功は維持する。

---

## Live gate（Phase 5.5a）

U-gate 証拠なしで live close しない。replay / skip_publish の「ping なし」確認は **daily のみ**。閉場日に replay / skip_publish すると閉場日経路も送らない。live 確認の本線は **営業日の通常本番** と **Cron 閉場日**（replay ではない）に分ける。

- [x] **U-55a-1:** 2 check 作成、メール通知テスト（[Issue #93 comment](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93#issuecomment-5549891323)）
- [x] **U-55a-2:** Secrets 設定（[Issue #93 comment](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93#issuecomment-5549912192)）
- [x] 定時 Patch + Daily 各 1 回: HC ダッシュボードに ping 記録（運用者確認 2026-09-07）。GHA: [Patch](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/34078193224) / [Daily](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/34092303792)
- [x] 手動 `skip_publish=true` run: ping **なし**（[34096740733](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/34096740733)。`run_date=2026-09-07` 営業日、両 Heartbeat skipped）
- [x] 手動 `is_replay=true` run: ping **なし**（[34097933412](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/34097933412)。`run_date=2026-09-04` 営業日の過去日、両 Heartbeat skipped）
- [x] **閉場日** Cron 相当: `closed_day_expected_ping`（[Patch 34007930390](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/34007930390) / [Daily 34017354982](https://github.com/kuwatajunichi-cyber/stockradarsystem/actions/runs/34017354982)。2026-09-06、Pause なし）
- [x] Issue #93 コメント（uuid 伏せ + run URL）: https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93#issuecomment-5567447887

5.5a live close は Track A の一部完了に過ぎない。Phase 5 `overall_status` は閉じない。

---

## Out of scope（Phase 5.5a）

- Supabase KPI ダッシュボード（5.5b / Phase 4 `runs` 後。ops SQL。ユーザー向け画面ではない）
- `monthly.yml` / MNC poller/worker の heartbeat
- Worker 専用 heartbeat（Daily/Patch ping で足りる前提）
- Slack / Discord
- Watchdog の廃止

**2026-08-26 追記:** Cloudflare Cron の silent miss は Worker 内 ping では観測できない。当日検知は GitHub schedule watchdog（[cron_dispatch_watchdog.md](../contracts/cron_dispatch_watchdog.md)）。Healthchecks の Period 1d + Grace 26h は翌日以降の通知であり、当日 catch-up の代替ではない。

**2026-09-04 追記:** カレンダー契約を `closed_day_expected_ping` に改訂。Period 1d × 閉場日非 ping のまま実装しない。
