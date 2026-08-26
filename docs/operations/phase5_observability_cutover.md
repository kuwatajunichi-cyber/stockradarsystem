# Phase 5 observability cutover（Healthchecks.io）

**採用:** 方針 C — Healthchecks.io、通知メール。  
**ロードマップ:** [issue_93_roadmap.md](issue_93_roadmap.md)

---

## スコープ

| Check | Workflow | ping 条件 |
|-------|----------|-----------|
| **patch-daily** | `daily_universe_patch.yml` | `is_open=True` かつ `put-patched` 成功後 |
| **daily-indicators** | `daily.yml` | 通常本番 run 成功後（下記「監視対象外」以外） |

---

## 監視対象外（契約）

以下の run では **heartbeat を送らない**（Healthchecks 側も ping 欠落を期待しない）。

| 条件 | 理由 |
|------|------|
| `is_replay=true` | replay 検証。warm cache 非更新契約と同型 |
| `skip_publish=true` | 手動検証。外部公開なし |

実装: ping step に `if` を付与。replay / skip_publish 判定は既存 dispatch 入力・`resolve_trading_day` 出力を利用。

---

## Healthchecks.io 設定

1. アカウント作成 → **Email** 通知を有効化
2. Check を 2 本作成:
   - `stockradar-patch-daily`
   - `stockradar-daily-indicators`
3. **Period / Grace（目安）**
   - Period: **1 day**
   - Grace: **26 hours**（Cloudflare/GHA 遅延吸収）
4. **休場日:** パイプラインは `is_open=False` で skip → ping なし  
   - 連休（GW 等）で false alert しうる → **Healthchecks 上で Pause** する運用を runbook に明記  
   - 中長期: Supabase 週次集計（別 PR）で補完可

---

## GitHub Secrets

| Secret | 用途 |
|--------|------|
| `HEALTHCHECKS_PATCH_PING_URL` | `https://hc-ping.com/<uuid>`（patch check） |
| `HEALTHCHECKS_DAILY_PING_URL` | `https://hc-ping.com/<uuid>`（daily check） |

URL 全体を Secret に格納（uuid 単体より rotate 容易）。

---

## Workflow 組み込み（実装 PR 時）

### daily_universe_patch.yml

`put-patched` 成功 step の直後（または job 末尾）:

```yaml
- name: Heartbeat (Healthchecks patch)
  if: success() && needs.resolve_trading_day.outputs.is_open == 'True'
  run: curl -fsS -m 10 --retry 3 "$HEALTHCHECKS_PATCH_PING_URL"
  env:
    HEALTHCHECKS_PATCH_PING_URL: ${{ secrets.HEALTHCHECKS_PATCH_PING_URL }}
```

### daily.yml

`render_and_upload` job 末尾（Upload 成功後）:

```yaml
- name: Heartbeat (Healthchecks daily)
  if: |
    success()
    && needs.resolve_trading_day.outputs.is_open == 'True'
    && needs.resolve_trading_day.outputs.is_replay != 'True'
    && (github.event_name != 'workflow_dispatch' || github.event.inputs.skip_publish != 'true')
  run: curl -fsS -m 10 --retry 3 "$HEALTHCHECKS_DAILY_PING_URL"
  env:
    HEALTHCHECKS_DAILY_PING_URL: ${{ secrets.HEALTHCHECKS_DAILY_PING_URL }}
```

**契約:** ping 失敗で job を落とさない（`|| true` 禁止 — サイレント失敗）。curl 失敗時は step fail で可視化しつつ、本処理成功は維持するかは Phase 5 PR で決定（推奨: `continue-on-error: true` + Step Summary に `heartbeat_ok` 出力）。

---

## Live gate（Phase 5.5a）

- [ ] 2 check 作成、メール通知テスト
- [ ] Secrets 設定
- [ ] 定時 Patch + Daily 各 1 回: HC ダッシュボードに ping 記録
- [ ] 手動 `skip_publish=true` run: ping **なし** を確認
- [ ] 手動 `is_replay=true` run: ping **なし** を確認
- [ ] Issue #93 コメントに HC check URL（uuid は伏せ）と検証 run URL

---

## Out of scope（Phase 5.5a）

- Supabase KPI ダッシュボード（5.5b / Phase 4 後）
- Worker 専用 heartbeat（Daily/Patch ping で足りる前提）
- Slack / Discord

**2026-08-26 追記:** Cloudflare Cron の silent miss は Worker 内 ping では観測できない。当日検知は GitHub schedule watchdog（[cron_dispatch_watchdog.md](../contracts/cron_dispatch_watchdog.md)）。Healthchecks の Period 1d + Grace 26h は翌日以降の通知であり、当日 catch-up の代替ではない。
