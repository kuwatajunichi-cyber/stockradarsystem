# Phase 5 observability — 方針比較と採用決定

Issue #93 Phase 5.5。実装 runbook: [phase5_observability_cutover.md](phase5_observability_cutover.md)

## 採用決定（2026-07-08）

| 項目 | 決定 |
|------|------|
| 方針 | **C — 外部 Heartbeat（Healthchecks.io）** |
| ベンダー | [Healthchecks.io](https://healthchecks.io) |
| 通知 | **メール**（HC アカウント設定） |
| 監視対象外 | **`is_replay=true`** および **`skip_publish=true`** の run（heartbeat 送信しない） |

段階導入: **5.5a = 方針 C 本番**。Supabase 集計（旧 5.5b）は Phase 4 `runs` lifecycle 後に別 PR。

---

## 監視シグナル（参考）

| 層 | 例 | Heartbeat でカバー |
|----|-----|-------------------|
| Worker → GHA dispatch | dispatch 失敗 | △（Daily/Patch 未到達で間接検知） |
| GHA 成功終了 | 全 job success | ◎（ping 位置） |
| Supabase KPI | publish 率 | ✗（将来 SQL 集計） |

---

## 方針比較（調査メモ）

### A — Supabase 集計のみ

メリット: ADR-003 一致、KPI/監査。デメリット: 死活は間接、アラート自前。

### B — Cloudflare ネイティブ

メリット: dispatch ログ。デメリット: GHA/Supabase 別系統、標準アラートなし。

### C — 外部 Heartbeat（**採用**）

メリット: 「来なかった」検知、実装軽量、AC-2 直結。デメリット: degraded 中身は弱い。

### D — 統合 SaaS

メリット: フル observability。デメリット: コスト・工数大。Web 本格化時に再検討。

### E — GitHub のみ

不足（欠落不可視）。

---

## 参照

- [Healthchecks.io docs](https://healthchecks.io/docs/)
- [Phase 1 インシデント](incidents/phase1_cron_dispatch_cutover_2026-06.md)
- Issue #93 AC-2
