# ADR-005: Monthly new-Core backfill（OHLCV と active Web 系列の差分補完）

## 状態

**Adopted（2026-08-29）。** 人間レビュー承認と同一 docs PR（`pr-005-docs-adoption`）で採択条件 1–8 を満たす。Phase 4.5 `live_gate_45c` はユーザー承認の waiver で closed（連続 3 営業日 soak 達成とは書かない）。実装ゲートは [adr005_gate_status.yaml](../operations/adr005_gate_status.yaml)（`overall_status: in_progress`）。

本 ADR は Issue #93 の運用ギャップ（月次で Core に昇格した銘柄の履歴が Daily / Phase 4.5 series に自動で載らない）を解消する設計契約である。2026-08-24 採択版、2026-08-25 改定、2026-08-27 第 1 次・第 2 次再レビュー、同日第 3 次再レビュー（canonical 全順序、partition identity、§6 `planned_*`、outbox 原子性、catalog fingerprint、Daily skip と `expected_object_count`、`feature_start` SSOT）を反映する。

コード・workflow の更新は実装 PR（`pr-005-daily-cas` 以降を含む本バッチ）で行う。docs 採択単体を Phase 4.5 / Issue #93 の完了とみなさない（Phase 4.5 gate の close は別途の live-gate waiver）。Issue #93 は Phase 5 が残るため OPEN。

### 採択条件（同一 docs PR。ここが唯一の一覧）

1. 本改定の再レビュー通過。
2. ADR-004（状態行の実態修正、§1 再構築、§6 に `series_seed` / `series_repair`）。
3. ADR-003 の R2 holds に `derived-inputs/` を追加。
4. `docs/contracts/exit_codes.md`（下記 entrypoint）。
5. `docs/contracts/daily_replay_and_monthly_universe.md`（選択 `MONTHLY_TAG` の `history_quality`、Phase 4.5「未実装」記述の是正、`canonical_release_for_month` と `pick_monthly_release` の混同禁止）。
6. mapping YAML の `schema_version` bump、トップレベル `adr005`、cache エントリの `planned_*`、および mapping 契約。**live Layer 1 は `immutable_pointer_cas`（`target_r2_key_pattern` = sha256 objects）** — `pr-005-daily-cas` は PR #159 で main にマージ済み。`adr005.status: proposed` は feature_start unset（未 enable）であり fixed-key を意味しない。YAML の `feature_start_release_month` は mirror。正本は DB（§4）。
7. `docs/operations/adr005_gate_status.yaml` の schema 固定（owner team slug を空にしない。採択後は `status: in_progress` と `owner: repo-maintainers`）。
8. 新規 cron 契約 `docs/contracts/monthly_new_core_backfill_cloudflare_cron_dispatch.md` の骨格（実装 PR で Worker 差分を埋める）。

### 採択条件の進捗（Adopted）

| # | 進捗 |
|---|------|
| 1 | **Adopted**（2026-08-29。Grok 単体承認 + 人間レビュー / docs PR） |
| 2 | 同期済み（ADR-004） |
| 3 | 同期済み（ADR-003 `derived-inputs/`） |
| 4 | 同期済み（`exit_codes.md`） |
| 5 | 同期済み（`daily_replay_and_monthly_universe.md`） |
| 6 | 同期済み（mapping YAML `schema_version: 6`、`adr005` ブロック、`planned_*`、mapping 契約）。**live の Layer 1 は `immutable_pointer_cas`（sha256 objects）** — `pr-005-daily-cas` は PR #159（`9c58ddc`）で merge 済み。`adr005.status: proposed` は feature_start unset（未 enable）であり fixed-key を意味しない |
| 7 | 同期済み（`docs/operations/adr005_gate_status.yaml`。`overall_status: in_progress`、`owner: repo-maintainers`） |
| 8 | 同期済み（cron 骨格 + 分割 runbook 骨格）。Worker / `wrangler.toml` は実装 PR |

`pr-005-docs-adoption` は `local_only` から merge 後に `merged_and_verified` へ更新する。

## 改定履歴

| 日付 | 内容 |
|------|------|
| 2026-08-24 | 初版採択（async_quality、series-only、過去 snapshot 不変） |
| 2026-08-25 | 原子性・CAS・状態機械を追記した改定案 |
| 2026-08-27 | 第 1 次再レビュー必須項目を規範化。状態を保留に戻す |
| 2026-08-27 | 第 2 次再レビューを反映（delta key、pre-listing、完全性代数、loser、lease 待ち、poller secret） |
| 2026-08-28 | 採択条件 2–8 の docs 同期（未採択・未マージ） |
| 2026-08-28 | 第 4 次 Grok MUST（loser 行形の一意化、cron 契約の欠走検知と UTF-8） |
| 2026-08-28 | 第 5 次: フロー / §2 / runbook / 降格 / §11 を §1.2 に揃える。続けて §1.1 分岐・winner 限定 fail-fast・§11 降格テスト。Grok 単体承認。未採択 |
| 2026-08-29 | Adopted。live_gate_45c user-authorized waiver close と同梱。実装は in_progress |

## 用語

| 語 | 意味 |
|----|------|
| `release_month` | Monthly 起動時の Tokyo 日付を `YYYY-MM` に正規化した値 |
| `monthly_tag` | 個別 Monthly run の tag（実行日と `github_run_id` 由来） |
| 暦月の所属 | `monthly_snapshots.snapshot_date` の `YYYY-MM`。`monthly_tag` 埋め込みの実行日は使わない |
| canonical release | `canonical_release_for_month(release_month, committed_rows)` が返す committed winner。該当なしは `None`（`fallback_latest` しない）。全順序は `snapshot_date` 降順、同日は `github_run_id` 降順（last-wins）。既存 `pick_monthly_release(run_date, tags)` は Daily replay 用で、入力（`run_date` 上限）も適用対象も別。本関数の別名ではない |
| `snapshot_date` | `monthly_snapshots.snapshot_date`（現行は当該月の 1 日） |
| `current_core_logical_digest` | Core CSV の `code` 列を strip した集合を安定ソートした `canonical_json_sha256_v1`。CSV バイト SHA（`monthly_snapshots.sha256`）とは別 |
| request | `monthly_new_core_backfill_requests` の 1 行 |
| outbox | dispatch 行。状態は request と別語彙（§4.1） |
| chunk | 1 worker invocation が処理する連続 trade_date（最大 10） |
| series coordinate | `(metric_set_version_id, instrument_code, series_year)` |
| candidate coordinate | `added_codes × expected_trade_dates` |
| expected coordinate | `candidate \ structural_exclusion` |
| resolved-noop | その trade_date で `commit_trade_date_progress` の `write_count=0`。generation は出さず checkpoint だけ進める |
| `feature_start_release_month` | DB `adr005_runtime_config` の観測境界（YAML は mirror）。これより前は `not_applicable` |
| not_runnable | request を作っても outbox を作らない作成時状態（`noop` / `blocked` / `grandfather`）。`noncanonical_loser` は request 状態ではなく **link_role** |
| link_role | `request_release_links` の役割。`canonical_winner` または `noncanonical_loser` |
| poller | Cloudflare Cron 起点の `monthly_new_core_backfill_dispatch.yml` |
| reconciler | 同一 poller workflow の先頭ステップ（lease / claim TTL の昇格） |

DB / RPC の規範識別子は **小文字**（`series_seed`、`series_only`、`series_repair`、`series_seed_delta`、`series_repair_delta`）。

## 文脈

### 現行（実装実態）

- Core ユニバース（`equity_domestic_core`）は **月次** `monthly.yml` → `scripts/run_monthly.py` の二次分割でのみ再生成される。
- 日次 `daily_universe_patch.yml` は上場廃止の**除外のみ**であり、銘柄を追加しない。
- 月次 `fetch_yf_daily_for_universe` はランナー上の `data/cache/yf_daily/` に最大約 252 営業日を取るが、**Daily の OHLC warm cache**（R2 `cache-ohlc-store-zip-v2`）へは書き戻さない。
- 新規 Core 銘柄は次の Daily `ensure_core_cache` で初めてフル取得され、派生系列は **載った初日から日次 1 点ずつ伸びるだけ**である。
- Phase 4.5 の `derived_backfill.yml` は **shadow set 専用**（[ADR-004](adr-004-derived-indicators-warm-cache.md) §6、`phase4_5_rollout.write_allowed`）。
- historical `reconcile` の profile は `snapshot_series` / `snapshot_series_latest` で snapshot を書く。
- 定時 Daily / Monthly / patch の正本は Cloudflare Worker Cron。運用系（orphan sweep 等）は GitHub `schedule` も現役。
- 現行 Worker は静的 secret `GH_DISPATCH_TOKEN`（PAT または App token）。GitHub App installation token は約 1 時間で失効するため、App を使うなら tick ごとに App ID / private key から mint する。
- `GITHUB_TOKEN` は他 workflow の `workflow_dispatch` を連鎖起動できない（watchdog 契約と同じ）。本 ADR は最小権限のため poller / worker / Monthly のいずれも `GITHUB_TOKEN` で他 workflow を起動しない。
- 現行 `commit_monthly_snapshot` は PostgREST の `monthly_snapshots` 単表 PATCH。
- Monthly の R2 は **最終 key**（`monthly/{tag}/...`）へ直接 put し、canonical 選択は `status=committed` でフィルタする。staging prefix は無い。
- 現行 `commit_derived_generation` の CAS は committed **snapshot** の `logical_digest` 1 件。series は同一 `(set, code, year)` の旧行を `orphan` にする。
- 現行 `merge_trade_date_into_series` は既存日を比較せず上書きし、新規日を末尾 append する（再ソートしない）。
- `jpx_primary.py` の即時必須列は `コード` / `銘柄名`。`市場・商品区分` 欠落は alert + `unknown`。**上場日列は正本に存在しない**。二次分割の IPO 判定は bar 本数である。
- Cloudflare Cron Trigger は Worker あたり無料 5 本。現行 3 本、本 poller 追加後 4 本。

### 新しい要求

1. 月次で Core に**新規追加**された銘柄について、OHLCV（Layer 1）と active Web series の履歴を補完する。
2. 履歴範囲は **request 作成時に固定した active metric set の既存 coverage** に合わせる。
3. Monthly snapshot の公開は補完完了を待たない。未完了は別軸の品質表示で観測する。
4. 過去の immutable daily Core snapshot と latest projection は変更しない。
5. Daily と非同期補完が同一 cache / series に競合しても last-write-wins にしない。
6. `feature_start_release_month` 以降の **各 canonical** Monthly に request / quality が無い状態を作らず、欠落時は fail-closed。導入前は `not_applicable`。

### ユーザー固定の設計選択（採択時も維持）

| 項目 | 選択 |
|------|------|
| derived 履歴範囲 | active set の既存 committed coverage |
| Monthly 公開ゲート | 先に commit し、補完は非同期。未完了を quality 表示 |
| 過去 snapshot | 不変。active Web series のみ補完（`series_only`） |

## 決定

### 1. 責務分離と全体フロー

```text
Monthly build
  → monthly CSV を最終 R2 key へ immutable put（status はまだ pending）
  → release_month advisory lock
  → canonical_release_for_month を評価
  → previous / active set / coverage / core logical digest を固定
  → Core Diff
  → RPC commit_monthly_snapshot_with_backfill_request
       snapshot を committed
       winner なら request upsert + links + 必要なら outbox(pending)
       loser なら request 行は INSERT しない（stub も含む）。link 1 行のみ（§1.2）
  → Daily が committed を選択可能（Monthly はここで exit 0 可）
  → poller（Cloudflare Cron、Monthly 非依存）
       reconcile ステップ → outbox claim
       named secret で monthly_new_core_backfill.yml を dispatch
```

| 責務 | 正本 | 更新者 |
|------|------|--------|
| 今月の Core 集合 | R2 `monthly/{tag}/equity_domestic_core_with_name.csv` | `monthly.yml` |
| canonical release | `canonical_release_for_month` | Monthly RPC（lock 内） |
| 追加候補集合 | request の `added_codes` | winner の Monthly RPC |
| Layer 1 cache | immutable object + pointer | Daily または worker。cache-key lease + pointer CAS |
| immutable daily snapshot | `derived-snapshots/...` | Daily / historical reconcile のみ。**本 ADR は触らない** |
| active Web series | `derived-series/...` | Daily / `series_seed` / `series_repair`。coordinate CAS |
| seed / repair delta | content-addressed `derived-inputs/...`（§5.1） | `series_seed` / `series_repair` のみ |
| latest projection | `latest_derived_observations` | Daily / current-latest reconcile のみ。**本 ADR は触らない** |
| request / 品質 | request + event | Monthly RPC / poller / worker |
| 監査 manifest | versioned immutable | worker（row が key を指す） |

#### 1.1 原子 commit RPC

新規 `SECURITY DEFINER` RPC `commit_monthly_snapshot_with_backfill_request` が snapshot commit と `request_release_links` を 1 transaction で行う。**winner** のみ request upsert と runnable 時の outbox。**loser** は request 行を INSERT しない（stub も含む。§1.2）。既存 REST PATCH は当該用途で使わない。

RPC は先に `pg_advisory_xact_lock(hashtextextended('mnc:' || release_month, 0))` を取る（既存 006/009 と同じ **単一 bigint** overload。`(bigint, bigint)` の 2 引数は使わない）。

transaction 失敗時: R2 の最終 key に object が残っていても row を `committed` にしない（必要なら `orphan`）。`list_committed_monthly_tags` の対象にしない。staging prefix は新設しない。

not_runnable（`noop` / `blocked` / `grandfather`）には outbox を作らない。loser snapshot は request 行を **INSERT しない**（§1.2）。

#### 1.2 同月並行と loser

lock 内で `canonical_release_for_month` を再評価する。

- **winner**（この snapshot が canonical）: identity が既存なら再利用。Core 論理 digest が変わり identity が変わる場合のみ新 request を作り、旧を `superseded` にする。successor は **この RPC が同一 transaction で作る**。winner snapshot は自 request（partition ごと 1 行）へ `link_role=canonical_winner` を付ける。
- **loser**: snapshot は committed にしてよい。**`monthly_new_core_backfill_requests` に行を新設しない**（runnable も stub も作らない。digest が winner と一致しても不一致でも同じ）。
- loser の `request_release_links` は **ちょうど 1 行**: `request_id` は **現 winner の primary request**（未分割はその request。分割なら `partition_index=0`）。`link_role=noncanonical_loser`。digest 一致/不一致で分岐しない。
- 旧 winner が loser になった場合: その snapshot の `canonical_winner` link を **すべて DELETE** し、§1.2 の loser 1 行（現 winner primary、`noncanonical_loser`）を INSERT する。in-place UPDATE で旧 `request_id` を残してはならない。旧 request は winner 側の supersede 規則に従う。loser は winner request を `superseded` にしてはならない。
- Daily が `pick_monthly_release` で loser tag を選んでも、その snapshot の `history_quality.tier` は **`noncanonical_release`** である。winner request の `completed` / `full` を継承しない。補完の書き込み対象は winner の Core CSV / winner request のみ。loser CSV は当時断面として残す。

in-flight worker は各 generation commit の直前に request を version CAS で再読込する。`superseded` / `paused` なら書込せず終了コード 0（checkpoint は進めない）。次 outbox も作らない。

#### 1.3 dispatcher / reconciler

非同期消費は Monthly に依存しない。翌月 Monthly は別 `release_month` である。

| 役割 | 実体 | 起動 | 権限 |
|------|------|------|------|
| poller | `monthly_new_core_backfill_dispatch.yml` | Cloudflare Worker Cron `*/15 * * * *`、env `MNC_DISPATCH_ENABLED`。`workers/github-cron-dispatcher/` に登録。未登録 cron は throw するため `constants.js` と同一 PR | GHA `permissions: contents: read` のみ。**`actions: write` 禁止**。dispatch は Actions secret `GH_DISPATCH_TOKEN`（Worker と同一値）。**`GITHUB_TOKEN` 禁止**。owner は `adr005_gate_status.yaml` の `owner` |
| worker | `monthly_new_core_backfill.yml` | poller の `workflow_dispatch` のみ | `contents: read`。**`actions: write` 禁止**（self-dispatch しない） |
| Monthly | `monthly.yml` | 既存月次 Cron | outbox を RPC 内で作るだけ。**`actions: write` を足さない** |

poller は空転でも 96 run/日。public リポジトリのため Actions 分課金は無い。観測項目として capacity 記録に残す。

GitHub `schedule` の poller は不採用（§不採用）。Worker が outbox を直接 claim する案も不採用（Supabase secret を Worker に足す）。

poller 1 tick:

1. reconciler: lease heartbeat が 2 TTL 超の `*_running` を `failed_retryable` へ。outbox `claimed` で heartbeat が 2 回欠けるもの、または visibility timeout（初期 20 分）超過を `pending` へ戻す。両条件が同時なら復帰は 1 回だけ。
2. claim は RPC `claim_mnc_outbox` のみ。`FOR UPDATE SKIP LOCKED` で outbox 状態が `pending`、または `failed` かつ `next_retry_at` 到達かつ attempt < budget の 1 行を取る。`fencing_token` を +1 し `claimed` にする。request 状態名で claim しない。
3. `UNIQUE(request_id, chunk_seq)`。`chunk_seq` は 0 始まりで決定的: `floor(index_of(next_trade_date) / 10)`。`next_trade_date` は `last_committed_trade_date` の次（無ければ coverage 先頭）。**request（partition）あたり非終端 outbox（`pending`/`claimed`/`dispatched`/`failed`）は最大 1 行**。
4. GitHub dispatch は at-least-once。worker の heartbeat / progress / done は claim 時の `fencing_token` を提示する。不一致は書込せず終了コード 0（他 worker が所有）。
5. API 受理後・outbox `dispatched` 前クラッシュは claim TTL 後に再送。`dispatched` には GitHub run id を記録する。queued/in_progress の run がある間は再 claim しない。
6. 1 tick の claim 上限は 2。poller workflow に concurrency group は付けない（重なりは SKIP LOCKED）。
7. `superseded` なのに successor が無い場合は **自動生成しない**。理由 `stranded_successor` を event と step summary に残し警報する。
8. 独立欠走検知: GitHub `schedule` 60 分（Cloudflare Cron ではない。既存 3 本の Worker-miss watchdog 表にも 15 分行を足さない）。`MNC_DISPATCH_ENABLED=true` のとき、直近 45 分に poller の `workflow_dispatch` が無ければ miss（exit 2）。catch-up は poller workflow のみ（worker は起動しない）。secret は `GH_DISPATCH_TOKEN`。

次 outbox の作成者は worker の progress RPC（chunk 最終日）が正。poller は `ohlcv_ready` 以降に非終端 outbox が 0 件なら、決定的 `chunk_seq` の `pending` を `ON CONFLICT DO NOTHING` で補うだけ（request は作らない）。

`ohlcv_ready` は lease 非保持。

### 2. 新規 Core の定義（差分契約）

```text
added_codes   = codes(current_core_csv) \ codes(previous_core_csv)
removed_codes = codes(previous_core_csv) \ codes(current_core_csv)
codes(csv)    = strip した `code` 列の集合（logical digest と同じ正規化）
```

- **previous**: `release_month` より前の暦月（`snapshot_date` の `YYYY-MM`）に属する committed のうち最新。同月先行 run は除外。自分自身を previous にしない。
- **current**: 今月 `split_equity_domestic_secondary` 後の Core CSV（commit 対象と同一）。
- 同一 identity の再実行は request を再利用する。
- `added_codes` が空でも winner は `noop` を transaction 内で作る。
- `removed_codes` の series / OHLC は削除しない。
- 導入前 Core の one-shot catch-up は対象外（別 ADR）。

**Fail-fast（差分段階）**

| 条件 | 挙動 |
|------|------|
| 前暦月の committed Core が無い | snapshot + `blocked(missing_previous_core)`。worker なし |
| `added_codes` が 50 超過 | snapshot + `blocked(added_codes_over_limit)`。人手分割 |
| `added_codes × expected_trade_dates` が 4000 超過 | snapshot + `blocked(work_units_over_limit)`。日付数の絶対上限は設けない |
| 差分計算不能 | Monthly fail-fast。snapshot 非 committed |
| winner 経路で RPC が request / 必要な outbox を作れない | 同上。loser の request 非 INSERT は成功経路であり fail-fast ではない |
| `seed_capability=not_series_seedable` | snapshot + `blocked(metric_not_series_seedable)` |

`expected_trade_dates` 件数は観測する。中央値が 80 を超えたら容量（GHA / R2 Class A / yfinance）を再レビューする。**80 日での自動 `blocked` はしない**（Path B は既に約 60 日で、数週間で 80 を超える）。

分割 request: 人手分割は `docs/contracts/monthly_new_core_backfill.md`。RPC は同一 snapshot 配下の partition について次を検証し、失敗なら snapshot 非 committed。

- code 集合は互いに排他。交差は拒否。
- union は分割前の `added_codes` と一致。欠落・余剰は拒否。
- `partition_count` は全行で同一。`partition_index` は `0 .. count-1` を重複なく被覆。
- 元の `blocked(added_codes_over_limit)` / `work_units_over_limit` request がある場合、分割 successor 一式と元行 `superseded` を **同一 transaction** で行う。

未分割は `partition_index=0`、`partition_count=1`。排他なら日付並列を許可する（concurrency group は `mnc-{request_id}` のまま）。`candidate` と complete 判定の `added_codes` は **当該 partition の code 集合**である。winner snapshot の `history_quality` in-scope は `link_role=canonical_winner` の partition request のみ（§4）。loser snapshot は `noncanonical_release` であり、link 先の winner request を in-scope に入れない。

### 3. 対象期間（coverage）と Layer 1 必要長

request **初回作成時**に coverage を固定する。同一 identity の再実行は伸ばさない。取り直しは successor（Core digest 変更または active set 変更）に限る。

```text
metric_set_version_id = 当時の active set
expected_trade_dates   = active set に committed snapshot がある trade_date の昇順
expected_trade_dates_digest = canonical_json_sha256_v1(expected_trade_dates)
coverage_start / coverage_end = min / max
required_input_schedule =
  compute_metric_input_schedule(metric_set_version_id, expected_trade_dates, calendar_version)
required_input_start = min(required_input_schedule)
```

- coverage は日付集合そのもの。内部欠落日を埋めない。identity に coverage digest は入れない。
- `compute_metric_input_schedule` は日付集合を返す。`compute_layer1_required_trading_days` はその内部 primitive。Daily の 5 年 floor と request schedule は別引数。Daily の取得長を変えない。
- stock と required benchmark の双方を `required_input_start` から `coverage_end` まで確保する。

#### 3.1 metric catalog 前提

現行 YAML は `required_inputs: ohlcv` のみ。`series_seed` 有効化前に次を追加する。未定義は `blocked(metric_input_contract_missing)`。

| フィールド | fingerprint | 用途 |
|------------|-------------|------|
| `seed_capability` | **入れない** | `instrument_local` / `benchmark_relative` / `not_series_seedable` |
| `required_benchmarks` | 既存 `definition_canonical` 経由（ADR-004） | 安定 ID 配列。変更は新 `metric_version` |
| `calendar_version` | **入れない** | 営業日暦 ID（seed 実行時メタ） |
| `adjustment_policy` | 既存 `definition_canonical` 経由（ADR-004） | 変更は新 `metric_version` |
| `lookback_trading_days` / `warmup_trading_days` | **入れない** | 入力長。式の窓長そのものは既存 canonical 側 |
| `state_checkpoint` | **入れない** | 無ければ coverage_start からその日まで Layer 1 再計算 |
| `listing_source_policy` | **入れない** | 初期値 `first_valid_bar`（§3.2） |

`definition_payload_for_fingerprint` の allow-list（`definition_canonical` + `required_inputs` + `missing_policy`）は維持する。seed 専用フィールドの追加だけでは新 `metric_set_version` を発行しない。したがって既存 Path B の committed coverage は空にならない。

ベンチマークまたは調整価格を変えるときは ADR-004 どおり新 version / 新 set を発行する。その set を active にしたあとの `expected_trade_dates` は **新 set の committed snapshot 日**である。旧 set の coverage を自動継承しない。active 切替は CAS であり、本 ADR の seed 有効化より前に行う。

cross-sectional 指標は `not_series_seedable`。

#### 3.2 pre-listing（沈黙スキップ禁止）

**現行 JPX 正本に上場日列は無い。** 外部上場日ソースの調達は本 ADR の範囲外（別 ADR）。本機能の既定は `listing_source_policy=first_valid_bar` である。

構造的除外（`pre_listing_dates` ⊂ candidate）にしてよい条件（すべて必須）:

1. bounded window fetch が正常終了した。
2. fetch window 開始が `required_input_start` より前（下限は `required_input_start` の 5 営業日前。`coverage_start` だけでは warm-up 不足と上場前を区別できない）。
3. その銘柄の最初の有効 OHLC bar が存在する。
4. 対象 `trade_date` がその bar より前である。
5. 1–4 が `layer1_input_fingerprint` と manifest の `listing_source_policy=first_valid_bar` に入る。

取得不足・fetch 失敗・window が短い場合は **除外にしない**。`failed_retryable(fetch_short)`、上限後は `blocked(listing_date_unknown)`。`completed` にしない。

上場後の lookback 不足は行を作り `null` + quality flag。

#### 3.3 完全性集合（complete RPC）

```text
partition_codes = 当該 request の added_codes（未分割なら Core diff の全 added）
candidate  = partition_codes × expected_trade_dates
exclusion  ⊂ candidate          # §3.2 を満たす pre_listing のみ
expected   = candidate \ exclusion
resolved   ⊆ expected           # 既存 canonical 一致または本 request が commit
complete iff
  resolved = expected
  AND resolved ∩ exclusion = ∅
  AND conflict_count = 0
  AND uncommitted_count = 0
```

構造的除外は **resolved に入れない**。`null` + 契約フラグの行は expected に入り resolved になる。

各 digest の payload は `canonical_json_sha256_v1` に渡す配列:

```json
[{"instrument_code":"<csv code>","trade_date":"YYYY-MM-DD"}, ...]
```

ソートは `instrument_code` Unicode 昇順、同 code は `trade_date` 昇順。重複禁止。golden vector は `tests/fixtures/adr005_canonical_vectors.json` に identity / coverage / candidate / expected / exclusion / resolved を含める。

`history_quality.tier=full` は当該 snapshot の in-scope request がすべて `completed` / `noop` / `grandfather` であることだけを意味する。Core 全体の穴・Web 最大窓・5 年保持ではない。

### 4. 非同期実行モデル（async_quality）

1. Monthly RPC が snapshot +（winner なら）request / outbox を commit する。
2. poller が outbox を claim し worker を dispatch する。concurrency = `mnc-{request_id}`、`cancel-in-progress: false`。
3. worker は `ohlcv_ready` でなければ Layer 1 ensure を **request につき 1 回**、その後 series chunk（最大 10 `trade_date` / invocation）。
4. ceiling: 10 dates / invocation、銘柄並列 4（fetch/compute のみ）、timeout 120 分、CAS retry 5、lease TTL 15 分、heartbeat 60 秒以下、retry budget 5。変更は容量証拠と再レビュー。
5. 各 `trade_date` は RPC `commit_trade_date_progress` を **1 回だけ**呼ぶ（旧称の `commit_series_only_generation_with_checkpoint` / `checkpoint_resolved_noop` はこの RPC の分岐であり、同じ日に並べて呼ぶことは禁止）。partition 内の各 code を同一 transaction で分類する:
   - §3.2 を満たす → `exclusion` に加算。generation に入れない
   - 既存 committed series がその日の canonical 値と一致 → `resolved` に加算。書かない
   - 欠落 → generation に入れ、成功後 `resolved` に加算
   `write_count >= 1` のときだけ generation + delta を出す。`write_count = 0` なら generation なし。いずれの場合も `last_committed_trade_date` をその日へ進める。
6. chunk の中間日: outbox は `claimed` のまま checkpoint のみ。chunk の最終日、または次日が無いとき: 現 outbox を `done` にし、未完了なら次 `chunk_seq` の `pending` を同一 transaction で作る。
7. 再開位置は `last_committed_trade_date` の次（exclusion / 一致 / 書き込み日を含めて単調増加）。
8. worker は次 workflow を dispatch しない。
9. Daily / Web は raw 行を読み `aggregate_history_quality` で tier を決める。Postgres view は raw 専用（二重実装禁止）。読取は service_role バックエンドのみ。anon / authenticated に GRANT しない。control plane 不能は 503 または last-known + `stale=true`。

#### 4.1 Outbox 状態機械

```text
pending → claimed → dispatched → done
claimed → pending            # heartbeat 2 回欠落 / visibility timeout
claimed|dispatched → failed  # transport 失敗等
failed → pending             # next_retry_at かつ attempt < budget
```

| 状態 | 意味 |
|------|------|
| `pending` | 未 claim。poller が取ってよい |
| `claimed` | fencing token + heartbeat 中 |
| `dispatched` | GitHub dispatch 受理を記録済み |
| `done` | 対応 chunk の全 trade_date の `commit_trade_date_progress` が確定 |
| `failed` | 再送待ち。request は `dispatch_failed` または `failed_retryable` |

#### Request 状態機械

作成時: `dispatch_pending` / `noop` / `blocked` / `grandfather`。`planned` は commit 後に残さない。**loser snapshot は request を INSERT しない**（`noncanonical_loser` は link_role のみ）。

```text
dispatch_pending → dispatched → ohlcv_running → ohlcv_ready
  → series_running → dispatch_pending | completed

dispatch_pending → dispatch_failed → dispatch_pending
*_running → failed_retryable → dispatch_pending
non-terminal → blocked | paused
non-terminal → superseded   # successor は同一 actor の同一 transaction
```

| 状態 | actor |
|------|--------|
| `dispatch_pending` | Monthly RPC / worker（次 outbox） |
| `dispatched` / `dispatch_failed` | poller |
| `ohlcv_running` / `ohlcv_ready` / `series_running` / `completed` | worker |
| `noop` / `blocked` / `grandfather` | Monthly または bootstrap RPC |
| `failed_retryable` | worker / reconciler ステップ |
| `paused` | poller（flag off） |
| `superseded` | その supersede を起こした Monthly RPC または worker（active set 変更）。successor も同じ transaction |

`completed` に未解決 partial を含めない。worker exit 0 は invocation の checkpoint / next outbox 成功であり、request `completed` ではない。

#### `history_quality`

集約キー: `(monthly_snapshot_id, metric_set_version_id)`。Daily は選択済み `MONTHLY_TAG`。Web は canonical current を明示解決。

必須フィールド: 既存に加え `grandfather_count`、`current_core_logical_digest`、`expected_trade_dates_digest`。

優先順位（blocked を paused で隠さない）:

```text
snapshot に link_role=noncanonical_loser がある     → noncanonical_release
release_month < feature_start_release_month           → not_applicable
feature 以降で canonical_winner request 不在           → unknown_backfill
dispatch_failed が存在                                 → dispatch_failed
blocked かつ既 commit coordinate が存在                → partial_backfill
blocked が存在                                         → blocked_backfill
paused が存在                                          → paused_backfill
未完了が存在                                           → pending_backfill
全 in-scope request が completed / noop / grandfather → full
```

in-scope は当該 snapshot の `link_role=canonical_winner` の request だけ。`noncanonical_loser` link が指す winner request は loser snapshot の集約に入れない。

`feature_start_release_month` の **正本は Supabase** `adr005_runtime_config` の 1 行（NULL または `YYYY-MM`）。mapping YAML `adr005.feature_start_release_month` は mirror であり、enable transaction の入力にしない。

初回 enable RPC が **同一 transaction** で (1) DB の `feature_start_release_month` を NOT NULL に固定する (2) `[feature_start, current]` の **全 canonical** に grandfather または正規 request を作る (3) bootstrap 完了フラグを立てる。current だけ bootstrap してはならない。read path 有効化はこの transaction の後に限る。

YAML が null の docs 段階では DB も null。live 後の drift は ops smoke。CI 単体は YAML の null を検証する。

### 5. 新モード `series_seed` / `series_repair` と profile `series_only`

| モード | pointer | snapshot | series | latest | 用途 |
|--------|---------|----------|--------|--------|------|
| `normal` | 更新 | 新規日 | 当日 merge | 更新 | Daily |
| `replay` | 不変 | 不変 | 不変 | 不変 | 再現 |
| `backfill` | 不変 | shadow | shadow | 不変 | 新 set |
| `reconcile` | 不変 | CAS | merge | 条件付き | フル断面訂正 |
| `series_seed` | 不変 | 不変 | 欠落日のみ | 不変 | 新規 Core |
| `series_repair` | 不変 | 不変 | 承認訂正のみ | 不変 | `value_conflict` |

`write_allowed`: seed / repair は active series のみ。snapshot / latest / pointer は不可。

#### 5.1 delta 物理契約（create-only）

year gzip と key を共有してはならない。orphan 行の `delete_object` が committed 実体を消すためである。

```text
derived-inputs/monthly-new-core/{request_id}/delta/
  kind={series_seed_delta|series_repair_delta}/
  trade-date={YYYY-MM-DD}/
  generation={generation_id}/
  delta-sha256={object_sha256}.json.gz
```

- `object_kind` は `series_seed_delta` / `series_repair_delta`。
- shape: `trade_date NOT NULL`、`instrument_code IS NULL`（1 日×複数 code の payload）、`series_year IS NULL`。
- committed UNIQUE: `(request_id, trade_date, object_kind) WHERE status = 'committed'`。
- 同一 key 上書き禁止。失敗 generation は別 `generation_id` / 別 sha の key。
- status は committed のまま。year 置換で `orphan` にしない。
- `derived_object_shape` / `derived_object_committed_ts` / `object_kind` CHECK を改訂する。
- `derived_orphan_sweeper.py` は committed delta を削除しない。`status=orphan` かつ kind が delta でも、同一 sha の committed 行が指す object は削除しない。generation prefix 削除は `derived-snapshots/` と `derived-series/` に限定し、`derived-inputs/` を対象にしない。series prefix の既存不一致（`symbol=` 配下）是正もこの改修範囲に含める。
- `derived_generation_runs` の CHECK に `series_seed` / `series_repair`、`artifact_profile` に `series_only` を足す。

delta JSON payload（gzip 前。文字列は `canonical_json_sha256_v1` と同じ NFC + compact JSON）:

```json
{
  "schema_version": 1,
  "object_kind": "series_seed_delta",
  "request_id": "mnc-v1-<hex>",
  "trade_date": "YYYY-MM-DD",
  "metric_set_version_id": "<lowercase-uuid>",
  "generation_id": "<lowercase-uuid>",
  "rows": [
    {"instrument_code": "<csv code>", "metric_key": "<key>", "value": null, "flags": []}
  ]
}
```

`rows` は `instrument_code` 昇順、同 code は `metric_key` 昇順。重複禁止。R2 object の sha256 は **gzip バイト**。`value` は JSON number または null。

`expected_object_count = 2 × touched_series_coordinate_count + 1`（year gzip + manifest + delta）。`touched_series_coordinate_count` はこの generation で year gzip を書いた `(set, code, year)` の数（= その日に seed 書き込みした code 数。1 日 1 generation のため）。0 なら generation なし、delta も出さない。begin は skip / 分類後の membership で呼ぶ。

#### `series_only` CAS

- begin で coordinate 集合、`expected_prior_logical_digest`、`prior_absent` を登録。
- `prior_absent=true`: digest NULL、committed 行が無いことを検証。NULL を CAS スキップに使わない。
- `prior_absent=false`: 64 hex。1 件不一致なら pointer を 1 件も更新しない。
- `p_expected_old_digest` は `series_only` でエラー。
- begin/stage/commit は **1 worker run × 1 trade_date あたり 1 generation**（`derived_generation_runs_source_identity`）。日付直列の根拠はこの UNIQUE ではなく、code 単位の昇順 checkpoint である。

#### merge API

Daily は既存 `merge_trade_date_into_series`（当日 LWW）。seed は `merge_missing_dates_only`。

- 欠落日のみ挿入。既存日は canonical 比較。不一致は conflict 集合、上書きしない。
- 挿入後の `dates` は [phase45_canonical_digest.md](phase45_canonical_digest.md) の Series canonical bytes どおり **昇順**。末尾 append だけにしない。
- 過去日挿入後の logical digest は、全日を昇順一括生成した結果と一致しなければならない。

`series_repair`: expected prior、理由、`approver_github_login` 必須。RPC `commit_series_repair` は approver が worker の GitHub actor と一致したら拒否する（自己承認禁止）。承認ロールは `adr005_gate_status.yaml` の `repair_approver_team`。docs 採択時は `repo-maintainers` をプレースホルダとしてよい。**`pr-005-series-seed` で実在 GitHub team slug に置き、membership 検証を有効化する**。プレースホルダの間は login 不一致のみを強制する。snapshot / latest / pointer は不変。rebuild 順: snapshot 投影 → seed delta → repair delta。

#### lease と日付順

| ロック | 粒度 | 目的 |
|--------|------|------|
| series write lease | `(set, instrument_code, series_year)` | year gzip |
| Layer 1 lease | cache-key | 全体 zip |
| 日付シリアル | `(set, instrument_code)` の trade_date 昇順 | Perfect Order。set 全体 lease は持たない |

- lease は 1 generation の read-merge-commit の間。Daily の保持上限は 30 分。heartbeat 必須。worker は 60 秒以下で outbox heartbeat を打ち visibility timeout を延長する（`timeout-minutes: 120` と両立）。
- 優先: Daily > reconcile > repair > seed。**preempt しない**。待ち行列テーブルは作らない。
- seed が Daily の **active** lease を見たら新規取得せず `failed_retryable`（指数バックオフ）。
- Daily が seed の active lease に当たった場合: 当該 cache-key または当該 code だけ **最大 120 秒**待つ。超過した code は **`begin_derived_generation` より前**に当日 membership から外す。`expected_object_count` はその後の集合で確定する（skip 後に begin するため live の count mismatch で Daily を落とさない）。
- skip した `(code, trade_date)` は Daily 成果物 flags に `daily_seed_lease_skip` を残す（沈黙禁止）。indicators CSV と Daily 終了コード 0 は維持する。set 全体や job を赤にしない。
- 翌日 Daily は当日のみ merge し、skip した過去日を埋めない。その穴は seed の `merge_missing_dates_only` が埋める。seed が当該日を書けずに request が terminal なら `series_repair`。
- 排他 partition 間の日付並列は許可。同一 code の日付並列は禁止。論理結果は code 単位直列と等価。§11 で partition 並列 vs 直列の digest 等価をテストする。

stateful 再開: その code の前日 committed series。無ければ `coverage_start` から Layer 1 再計算。

#### provenance と再構築

1. 運用上の最新値は最新 committed year gzip。
2. 補完 coordinate の再構築正本は committed delta + fingerprints。
3. status: `orphan` = 未 commit / 失敗（sweeper）。`superseded` = 置換済み year gzip / cache（§6.1 の保持後削除）。`committed` = 現行 pointer または delta。
4. 論理 rebuild: snapshot に載る code×date は snapshot。載らないものは delta を日付昇順に適用。欠落 delta は fingerprint から再計算し不一致なら fail-fast。
5. series manifest `schema_version: 2`。`provenance` は **必須**（`daily_normal` / `series_seed` / `series_repair`）。default 省略は禁止（旧 writer がフィールド無しで通るのを防ぐ）。Daily writer 移行と同時に必須化する。

`superseded` は Daily normal の year 置換にも適用する（§6.1）。

### 6. Layer 1 補完契約

固定 key 上書き後の pointer CAS は禁止。Daily と MNC worker は同一 `immutable_pointer_cas` protocol を共有する（片側だけ旧 fixed-key に戻さない）。Daily CAS 切替は PR gate `pr-005-daily-cas`（本バッチ local_only / 未マージ）。本機能の Monthly RPC より先にマージする前提。

1. pointer から key / sha / logical digest / version を読む。`cache_pointers` に version 列が無ければ migration で足す。
2. cache-key lease。失敗は `failed_retryable`。
3. `added_codes` と benchmarks を `required_input_schedule` まで確保。
4. span が 400 暦日超または 252 営業日超なら long-history 必須。PoC モジュールを本番へ上げ、bounded `[start, end]` を足す。`period_for_required_days` の `2y` と `min(400,…)` をこの worker で使わない。不足は `benchmark_or_warmup_insufficient`。
5. `cache/{kind}/objects/sha256={object_sha256}.zip` へ create-only（live mapping 正本。`pr-005-daily-cas`）。
6. pointer CAS。失敗時 pointer 不変。未参照 object は orphan として 7 日保持。
7. `_manifest.jsonl` のみ更新。universe manifest と混ぜない。

mapping **live**（`pr-005-daily-cas` local_only 同梱。YAML 正本）: `writer_workflow: daily.yml`、`target_r2_key_pattern: cache/{kind}/objects/sha256={object_sha256}.zip`、`retention_policy: warm_cache_immutable_pointer_cas`。

mapping **planned**（worker 昇格用。live と同型）: `planned_writer_workflows: [daily.yml, monthly_new_core_backfill.yml]`、`planned_target_r2_key_pattern` / `planned_retention_policy` は live と同値。`scan_workflows` へ未作成 workflow を足さない。テストは YAML から生成し、タプルの二重定義をやめる。

#### 6.1 retention（単一指標）

| 対象 | 保持 | 削除 |
|------|------|------|
| pointer が指す Layer 1 object | 必須 | 不可 |
| superseded Layer 1 object | **直近 3 世代** | 超過分 |
| 未参照 Layer 1 create-only | 7 日 | orphan sweeper |
| in-flight fingerprint の Layer 1 | request terminal まで | その後は上に従う |
| 現行 committed series / manifest | 必須 | 不可 |
| superseded series year gzip / manifest（Daily 含む） | 直近 1 世代 **または** 3 暦日以内 | `(世代距離 > 1) AND (age > 3 暦日)` |
| committed seed / repair delta | 監査期間（初期 400 日） | 期限後に別途 ADR |
| orphan（未 commit） | 7 日 | sweeper |

着手条件の capacity 再測定に `layer1_immutable_generations_retained: 3` と `derived_series_superseded_days: 3` を `projection_inputs` へ入れる。

データポリシー: Provider Adapter のみ。レート制限。生 OHLCV 非再配布。cache 非公開。

### 7. Request identity・永続化・監査

#### `canonical_json_sha256_v1`

UTF-8、BOM 無し、**NFC は本関数の入力文字列にのみ適用**。その後 compact JSON（`,` / `:`）、`sort_keys=True`、`ensure_ascii=False`、`allow_nan=False`。UUID lowercase。日付 `YYYY-MM-DD`。

既存 `compute_definition_fingerprint` / `compute_set_fingerprint` のバイト列は **変更しない**（NFC を足さない）。切り出しは共通 dumps 部分だけ。snapshot `logical_digest` と `compute_object_set_digest` は使わない。

```text
identity_payload_v1 = {
  schema_version,
  release_month,
  previous_monthly_tag,
  current_core_logical_digest,
  metric_set_version_id,
  added_codes_digest,
  partition_index,
  partition_count,
  partition_codes_digest
}
request_id = "mnc-v1-" + canonical_json_sha256_v1(identity_payload_v1)
```

`added_codes_digest` と `partition_codes_digest` は当該 partition の code 集合（未分割では Core diff の全 added と一致）。`partition_index` は 0 始まり、`partition_count` は 1 始まり。未分割は `(0, 1)`。

`current_core_logical_digest = canonical_json_sha256_v1(sorted_unique_codes)`。`monthly_snapshots.sha256`（CSV バイト）と混同しない。

R2 manifest は `derived-inputs/monthly-new-core/{request_id}/manifest-version={version}.json`。ListObjects で最新を探さない。

SSOT: requests + events + outbox。row `version` CAS。

### 8. Fail-fast・停止条件

| 理由コード | 挙動 |
|------------|------|
| `missing_previous_core` | `blocked` |
| `added_codes_over_limit` / `work_units_over_limit` | `blocked` |
| `coverage_empty` / `metric_input_contract_missing` / `metric_not_series_seedable` | `blocked` |
| `listing_date_unknown` | `blocked`。fetch 不足を pre-listing にしない |
| `set_fingerprint_mismatch` | `blocked` |
| `active_set_changed` | worker が同一 transaction で `superseded` + successor |
| `benchmark_or_warmup_insufficient` | retry 後 `blocked` |
| `ohlcv_cas_conflict` / `series_cas_conflict` | 上限内 retry、超過 `blocked` |
| `lease_lost` | `failed_retryable` |
| `value_conflict` | `blocked` → 人手 `series_repair` |
| `dispatch_failed` | outbox `failed`、poller 再送 |
| `retry_exhausted` | `blocked` |
| `stranded_successor` | 警報。自動生成しない |
| `stale_pending_alert` | `dispatch_pending` が 6 時間超 |

### 9. 終了コード

対象 entrypoint（`exit_codes.md` に登録）:

- `python scripts/storage/monthly_bus_cli.py commit-snapshot`（Monthly の RPC 呼び出し）
- poller CLI（実装 PR でモジュール名固定）
- worker CLI（同上）

`scripts/run_monthly.py` の 1/2 は維持する。本 ADR はそこに 3 を足さない。RPC 成功後は `run_monthly.py` も 0 でよく、補完成否を載せない。

worker / poller は別 workflow なので、その非ゼロは `monthly.yml` を失敗させない（monthly に publish 専用 job は無い。成果物 put は build 内ステップ）。

| コード | `commit-snapshot` | poller | worker |
|--------|-------------------|--------|--------|
| 0 | RPC 成功（not_runnable commit を含む） | tick 成功（claim 0 も 0） | 当該 invocation の全 progress と、chunk 終端なら outbox done / 次 pending |
| 1 | commit 前の不正。snapshot 非 committed | 契約違反 | 契約違反。副作用なし |
| 2 | RPC / R2 / ネットワーク / 予期しない例外。snapshot を committed にしない。**dispatch 失敗では使わない**（Monthly は dispatch しない） | 永続化済み outbox `failed` | `failed_retryable` 永続化済み |
| 3 | 使わない | 使わない | `blocked` 永続化済み |

### 10. 段階導入・ロールバック・SLO

#### 着手条件

1. `live_gate_45c.status=closed`、または active を書かない明示承認。
2. `adr005_gate_status.yaml` が採択 PR で存在する。
3. capacity 再測定（Layer 1 3 世代 + series superseded 3 日）。
4. catalog §3.1。listing 外部正本は不要（既定 `first_valid_bar`）。

順序:

1. DDL（request/event/outbox/links/lease/`series_only`/`superseded`/delta kind/`adr005_runtime_config`/CHECK）、Fake、dual-read。seed flag off。
2. **独立 PR** `pr-005-daily-cas`: Daily cache + series writer を lease + CAS へ。旧/新同時起動を preflight 拒否。3 営業日再 soak。**`live_gate_45c` が open の間は Daily writer を置き換えない**（着手条件 1 の明示承認が無い限り）。
3. enable + bootstrap **同一 transaction**: DB に `feature_start_release_month` を固定し、`[feature_start, current]` の全 canonical に grandfather/request。その後 quality read path。
4. Monthly atomic RPC（series write はまだ off）。
5. shadow dry-run 後に `series_seed` active write。
6. Worker env `MNC_DISPATCH_ENABLED=true` は **step 4 の後**（outbox を書く RPC が live になってから）。それ以前に poller Cron を足してもよいが dispatch はしない。独立欠走検知（§1.3.8）は env が true のときだけ miss を出す。

ロールバック: flag off、未完了を `paused`、lease drain。Daily CAS は残してよい。fixed-key 復帰は全 writer 停止 + pointer materialize + 単一 flag。quality は `paused_backfill`。committed delta は 400 日保持。

#### SLO

| 項目 | 初期値 |
|------|--------|
| owner | `adr005_gate_status.yaml` の `owner`（採択時 `repo-maintainers` 可。空禁止） |
| 到達 | 直近 30 日に `dispatch_pending` へ入った runnable。件数が 5 未満なら百分率ではなく件数のみ。除外: `paused`。目標 7 日以内に 95% が `completed`/`blocked` |
| stranded `dispatch_pending` | 6 時間で poller を failure にし通知。目標ゼロ。**poller 非発火**は §1.3.8 の 60 分 GitHub schedule watchdog（45 分無 dispatch で miss） |
| Daily 本体が seed 待ちで非ゼロ | 0（120 秒後 skip） |
| `stranded_successor` / `retry_exhausted` | 次営業日に owner が判断 |
| 通知 | poller workflow failure が当面のチャネル。Phase 5 heartbeat 転用は任意 |

### 11. 実装境界（本 ADR では未実装）

| 区分 | 必須変更 |
|------|----------|
| Pure | `core_delta`、`canonical_release_for_month`、`canonical_json_sha256_v1`、schedule、`merge_missing_dates_only`（昇順）、`aggregate_history_quality`、complete 集合 |
| Jobs | 差分、Layer 1 ensure、subset 計算、seed / repair、chunk |
| Storage | `commit_monthly_snapshot_with_backfill_request`、`commit_trade_date_progress`、`claim_mnc_outbox`、`commit_series_repair`、outbox/lease RPC、delta kind、immutable cache pointer、CHECK 改訂、sweeper、`adr005_runtime_config` |
| Daily | 取得長は不変、CAS は独立 gate、coordinate lease、`history_quality.json`、manifest v2 必須 provenance |
| Workflows | poller / worker、`GH_DISPATCH_TOKEN`、`MNC_DISPATCH_ENABLED`、`constants.js` / `wrangler.toml`。Monthly に `actions: write` を足さない |
| Config | mapping 一式、catalog、ceilings、flag |
| Security | 新規 table は `ENABLE ROW LEVEL SECURITY` + REVOKE ALL + service_role 最小 GRANT。RPC は `SECURITY DEFINER SET search_path=public`（または空 search_path + 完全修飾）。public CREATE を revoke。入力上限。secret 非ログ |
| Tests | 下記 |
| Gate | honesty。完了主張の前に yaml を更新 |

必須テスト（Secrets-free）:

- pending row のみで canonical に出ないこと。RPC 失敗後の request 不在 fail-closed
- `[feature_start, current]` bootstrap と、その外の `not_applicable`
- loser が request 行を INSERT しないこと（stub 含む）。in-scope に `noncanonical_loser` link 先を入れないこと。winner のみ supersede
- 旧 winner 降格: その snapshot の `canonical_winner` link をすべて DELETE し loser 1 行を INSERT すること。旧 `request_id` を残す in-place UPDATE は禁止
- outbox heartbeat 延長と TTL 復帰。`GITHUB_TOKEN` を poller が使わないこと（workflow YAML 契約）
- coverage freeze、work_units 超過、partition 排他検証と並列/直列 digest 等価
- `merge_missing_dates_only` 非上書き + 昇順 digest 等価
- fetch_short を pre-listing にしない。first_valid_bar 除外の fingerprint
- Daily 120 秒待ち後 skip でも Daily 0
- sweeper が committed delta を消さない。同一 sha の orphan 行があっても object を残す
- complete 代数（exclusion ∩ resolved = ∅）。混合日の 1 RPC
- partition identity 衝突が起きないこと、union 被覆
- Daily skip 後 begin の `expected_object_count` 一致と `daily_seed_lease_skip` flag
- catalog seed フィールド追加後も既存 definition/set fingerprint が不変
- worker 中間 0 と `commit-snapshot` 0 の分離
- NFC 追加後も既存 definition/set fingerprint が不変
- `claim_mnc_outbox` fencing token 不一致で書かないこと

### 12. 採択時同期

§冒頭「採択条件」が正本。再掲しない。ADR-004 §1 に「snapshot に無い code×date は committed seed/repair delta が supplementary」を書く。

## 不採用

| 案 | 却下理由 |
|----|----------|
| historical `reconcile` で過去 snapshot に銘柄を遡及 | 当時 Core 断面を壊す |
| Monthly 内同期完了待ち | GHA 時間、60 日直列実測。公開遅延 |
| 次 Daily が過去 series を同期埋込 | 当日スクリーニングを壊す |
| active への `backfill` 流用 | shadow 専用 |
| shadow-only 系列 | Web に届かない |
| 固定 60 営業日 | coverage より短いと穴が残る |
| 無条件 5 年 | coverage 外コスト |
| `expected_trade_dates` 80 で自動 blocked | Path B が数週間で超過し機能が止まる。work_units で制限する |
| 部分 snapshot put | 断面契約を壊す |
| LWW | CAS に反する |
| fixed key 上書き後 pointer CAS | 共有 object が先に変わる |
| request / delta の固定 key 上書き | sweeper が正本を消す |
| year gzip commit 順 replay | UNIQUE + orphan と非両立 |
| set 単位の長期 lease | Daily を止める |
| `GITHUB_TOKEN` で他 workflow を起動 | 連鎖 dispatch できない。最小権限・監査のため使わない |
| `(hashtextextended, hashtextextended)` の 2 引数 advisory lock | 現行 006/009 は単一 bigint。migration が通らない |
| GitHub `schedule` の poller 本体 | 遅延と 60 日無活動停止。Daily/Monthly 正本である Worker Cron と経路を分けない。欠走検知の 60 分 schedule は poller 本体ではない |
| Worker が outbox を直接 claim | Supabase secret を Worker に足す |
| per-symbol Layer 1 同時移行 | 範囲外 |
| Monthly 終了コード 3 | 月次を誤って失敗にする |
| poller が successor を自動生成 | 入力再計算が曖昧。stranded 警報にする |
| 外部上場日ソースを本 ADR で調達 | JPX 正本に列が無い。別 ADR |

## 影響範囲

- **文書（本変更）**: 本 ADR、`docs/INDEX.md`、`docs/operations/issue_93_roadmap.md`、`docs/contracts/monthly_new_core_backfill.md`
- **採択時**: §冒頭の一覧
- **将来実装**: jobs / storage / universe / metrics / scripts/storage / workflows / Worker / wrangler / migrations / mapping / catalog / pytest
- **非変更**: Daily 当日更新、replay 非更新、shadow backfill、historical reconcile フル断面、patch の廃止除外のみ

## 参照

- [Issue #93](https://github.com/kuwatajunichi-cyber/stockradarsystem/issues/93)
- [ADR-003](adr-003-r2-supabase-control-blob-split.md)
- [ADR-004](adr-004-derived-indicators-warm-cache.md)
- [Phase 4.5 canonical digest](phase45_canonical_digest.md)
- [daily replay / monthly universe 契約](../contracts/daily_replay_and_monthly_universe.md)
- [exit codes](../contracts/exit_codes.md)
- [Monthly Cloudflare Cron](../contracts/monthly_cloudflare_cron_dispatch.md)
- [Monthly new-Core backfill Cron 骨格](../contracts/monthly_new_core_backfill_cloudflare_cron_dispatch.md)
- [分割 runbook 骨格](../contracts/monthly_new_core_backfill.md)
- [mapping 契約](../contracts/github_state_to_r2_supabase_mapping.md)
- [adr005_gate_status.yaml](../operations/adr005_gate_status.yaml)
- [Phase 4.5 cutover](../operations/phase4_5_cutover.md)
- [Issue #93 roadmap](../operations/issue_93_roadmap.md)
- [品質ガバナンス](../../.cursor/rules/quality-governance.mdc)
- [R2 / Supabase mapping](../../config/github_state_to_r2_supabase_mapping.yaml)
