## Phase 1 正系復旧インシデント記録（2026-06-18〜19）

後続フェーズ（patch / monthly / cleanup 等の Cron 移管）でも参照するため、事象・反省・対策を残す。

---

### 事象サマリー

Phase 1 で `daily.yml` の GitHub `schedule` を削除し Cloudflare Cron → Worker → `workflow_dispatch` を正系としたが、**Worker の本番デプロイが未実施**のまま `main` にマージされた。その結果、定時起動経路が存在せず **1 営業日分の日次ジョブが起動しなかった**。

| 日時 (JST) | 出来事 |
|------------|--------|
| 6/18 19:58 | 最後の GitHub `schedule` 起動（成功） |
| 6/18 23:16 | PR #95 マージ（`daily.yml` から `schedule` 削除、Phase 1 コード反映） |
| 6/19 15:37 | 旧仕様の定時起動時刻 → **起動なし** |
| 6/19 16:45 頃 | 未起動を確認 |
| 6/19 夕方 | 正系復旧（Worker デプロイ・Cron 登録・手動 dispatch で当日分補完） |
| 6/19 以降 | 定時起動を確認。のち Cron を `45 6 * * *`（毎日 JST 15:45）に変更 |

---

### 直接原因

1. **コードマージと運用デプロイの分離が契約化されていなかった** — 手動デプロイ完了をマージ/リリースのゲートにしていなかった。
2. **`main` マージ時点で起動経路がゼロ** — GitHub `schedule` 削除後、Cloudflare Worker が無いと dispatch 主体がいない。
3. **デプロイ時の前提不足（初回のみ）** — `workers.dev` サブドメイン未登録で Cron 登録 403、`workers_dev = false` が必要。

---

### 復旧で実施したこと

1. `wrangler deploy`（`workers/github-cron-dispatcher`）
2. `GH_DISPATCH_TOKEN` secret 設定
3. `workers.dev` サブドメイン登録（`stockradarsystem`）
4. Cron Trigger 登録（後に `45 6 * * *` へ変更）
5. 未起動日を `workflow_dispatch` で手動補完

---

### 反省

- **契約と運用のギャップ**: schedule 削除と Worker 稼働が原子的に切り替わるべきだった。
- **受け入れ条件の不足**: テスト/マージ成功 ≠ 翌日定時に run が作られる。
- **観測の遅れ**: Cloudflare API で Worker 未デプロイは即判明可能だった。

---

### 後続フェーズ向け対策（チェックリスト）

**schedule 削除 PR をマージする前に:**

- [ ] Worker デプロイ済み
- [ ] `wrangler.toml` crons と routing table 定数が一致
- [ ] secret/vars 設定済み（`GH_DISPATCH_TOKEN` 等）
- [ ] `workers.dev` サブドメイン登録済み（初回のみ）
- [ ] `npm test` + pytest 契約テスト通過

**マージ後 24h 以内:**

- [ ] Cloudflare で Cron Trigger 登録を確認（schedules が空でない）
- [ ] smoke / 必要なら 1 回 live dispatch で GitHub run 確認
- [ ] 初回定時発火後、Worker ログと GitHub run の時刻差を記録

**設計原則:**

1. 旧 schedule 削除と新 Cron 有効化は **同一リリース単位**（中間状態を残さない）
2. Worker は dispatch 失敗時 `throw`（Phase 1 反映済み）
3. CI（secrets-free）と本番デプロイ/ live 検証を分離し、後者をマージ後ゲートにする
4. cron 定数は wrangler / constants.js / pytest / docs で一致検証
5. ロールバック手順をフェーズごとに docs 化

**Phase 2 以降:** routing table 集約時は Cron Trigger 上限（5/account）と各 workflow の dispatch inputs を契約化。

---

### 参照

- `docs/operations/cloudflare_github_cron.md`
- `docs/contracts/daily_cloudflare_cron_dispatch.md`
- `docs/operations/incidents/phase1_cron_dispatch_cutover_2026-06.md`（リポジトリ内の同一内容）
- `workers/github-cron-dispatcher/`
- 現在の Cron: `DAILY_CRON = "45 6 * * *"`（毎日 JST 15:45）

---

- [x] 正系復旧完了（定時起動確認済み）
- [x] Cron を毎日 15:45 JST に更新済み
