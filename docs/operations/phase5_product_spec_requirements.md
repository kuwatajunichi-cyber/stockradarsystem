# Phase 5 製品・Web UI 仕様 — 要件整理

**状態:** 要件整理。**本ファイル全体は仕様正本ではない。** 画面正本は [web_ui_v1.md](../contracts/web_ui_v1.md)。採用判断は本ファイルの「採用済み」節。2026-09-10 の「作業中」は **打ち消し**。
画面ファーストバージョンの正本は [web_ui_v1.md](../contracts/web_ui_v1.md)（2026-09-22 採用）。`rs_sma75_*` は [metric_set_v1_1.md](../contracts/metric_set_v1_1.md)。**初回 Web live までに v1.1 を active にし、SMA75 空列を製品に出さない。** 本ファイルだけでは CAS しない。Track C / E の **実装** は未。T-3 / T-4 / T-9 等の製品判断は採用済み。
**ゲート:** [phase5_gate_status.yaml](phase5_gate_status.yaml) の `pr-5c-auth-entitlements` / `pr-5d-web-ui` / `pr-5e-distribution` は **pending**。`live_gate_5c` / `5d` / `5e` は **open**。
**本ファイルだけでは** Auth 実装、公開 mint（未認証の署名発行）、Web UI 実装、`published/` 切替、`live_gate_5d` close をしてはならない。
Phase 5 `overall_status` は **in_progress**。Issue #93 は **OPEN**。Web UI 完了とは書かない。

ロードマップ: [issue_93_roadmap.md](issue_93_roadmap.md)
Track B 配信契約（内部 capability。画面なし）: [signed_url_capability.md](../contracts/signed_url_capability.md)
Track A 5.5b（ops SQL。ユーザー画面ではない）: [ops_runs_views.md](../contracts/ops_runs_views.md)

---

## 目的

Track C（認可）・Track D（Web UI）・Track E（配布切替）の要件を一箇所に並べる。**採用の正は「採用済み」節と web_ui_v1.md。** 古い作業中節は打ち消し。

未決として残すのは CORS の Pages オリジン具体 URL と bundle 内部欄名など実装細部。結論済みは採用節へ移した。

## 置き場所

| 置かない場所 | 理由 |
|--------------|------|
| `docs/contracts/` | 入出力契約の adopted 正本。画面は web_ui_v1.md。本ファイルの作業中節は正本にしない |
| `docs/adr/` | 採択済み設計判断。本段階では未採択 |
| `docs/user-facing-spec/` | 現行 XLSX / 実装の**説明用**であり、設計正本ではない（[README](../user-facing-spec/README.md)） |
| `docs/decision-candidates/` | 仮 ADR。「影響しそう」の保存。本ファイルは Phase 5 着手ゲートの要件棚卸し |

`docs/operations/` に置く。`phase5_observability_options.md`（調査）と `phase5_observability_cutover.md`（採用 runbook）の関係と同じで、**本ファイルは options 相当**である。

## 既存ドキュメントとの関係

| 文書 | 関係 |
|------|------|
| [MVPdesignDoc_v1.2.md](../MVPdesignDoc_v1.2.md) §2.2 / §2.3 | 「UI をやらない」は **撤回**（2026-09-22）。助言禁止は残す。画面正本は web_ui_v1.md |
| [MVPuserstorymap_v1.1.md](../MVPuserstorymap_v1.1.md) US-8 / US-9 | 一覧閲覧は XLSX に加え Phase 5 Web（追加閲覧。T-3） |
| [ADR-004](../adr/adr-004-derived-indicators-warm-cache.md) | 書き手系列は `derived-series/`。画面読み口は `derived-web-asof/`（ベンチ別）。snapshot は監査 parquet であり XLSX 用ではない |
| [ADR-003](../adr/adr-003-r2-supabase-control-blob-split.md) | blob は R2、認可・entitlements・webhook は Supabase。利用者 download は committed 行だけ |
| プロジェクト共通ルール | **投資助言・売買シグナルは出さない。** 調査候補の抽出と定量指標の出力に限定する |

---

## すでに決まっている拘束（覆さない）

仕様作業で再議論してよいが、実装着手前に明示的に覆す文書がいる。黙って破らない。

1. **助言禁止。** 推奨・売買判断・スコア最適化を UI に出さない。
2. **配信は private R2 + committed のみ + 短命 GetObject。** 公開 bucket・`ListObjects` 通常経路・orphan mint は禁止（Track B）。
3. **P0 継承。** 制御面は RLS ON、`anon` / `authenticated` への広い GRANT を戻さない。ブラウザは PostgREST / preferences 表に直接触れない。T-6 は BFF が `service_role` で読む。利用者 policy は Track C の後続（T-9: 初回は足さない）。
4. **allow-stub 禁止。** entitlement 未証明の mint を通さない。
5. **公開 mint＝未認証の署名発行。禁止。** 内部 CLI を匿名 HTTP にしない。認証済み BFF（T-1 案 C）は Track C/D の製品口であり、Track B CLI の匿名公開ではない。
6. **5.5b ops views はユーザー画面の代替ではない。** Healthchecks と Watchdog は両方残す。
7. **live TARGETS を黙って変えない。** 現行 daily/monthly は `r2,dropbox`（Drive は解凍時のみ）。Track E 切替は別 live gate。
8. **無料段階の内部・少数利用。** 全履歴を Supabase に置かない。時系列本体は R2。有料移行条件は ADR-004 §10。
9. **CSV 当日値と series 同一日値は同一 pure 関数。** UI が dual source を見せるなら一致契約を壊さない。

---

## 作業中の捕捉（2026-09-10）— **打ち消し**

**正本ではない。** 衝突する記述は「採用済み」節と `web_ui_v1.md` / ADR-004（2026-09-22）が勝つ。撤回例: D-3 の `derived-series/` 直接読取、D-9 の `turnover_yen` 未決、D-8 の株探のみ、D-7 の「UI をやらない」、ニュース CSV のカレンダーずれ。

運用者ヒアリングのメモ。**採用ではない（打ち消し）。** 未決は質問のまま残す、という扱いもしない。

### 利用者（D-1 作業中）

4 種別。同じアプリのロール違い。インフラ画面は将来タブ追加（初回 Out。5.5b の代替にしない）。

| 種別 | 初回 live | 製品コンテンツ | 制約 |
|------|-----------|----------------|------|
| 運用者 | 出す | 内部β / 外部有料と原則同じ | ロールだけ違う。将来インフラタブ用に種別を残す |
| 内部β | 出す | フル（外部有料と同一） | ソート変更可。equity_domestic_core 全件を一覧 |
| 外部有料 | 種別だけ置く。初回 live には出さない | 内部βと同一（フル） | 課金開始は後続 |
| 外部無料 | 種別だけ置く。初回 live には出さない | 指標の種類は他と同じ。当日断面も時系列グラフも出す | `z_turnover_60` 降順でソート固定・変更不可。第 20 位の値と同点の銘柄まで含める（20 行固定ではない）。お気に入り等のアカウント紐付け機能は提供しない |

一覧の母集団は **equity_domestic_core のみ**（ipo / illiquid は出さない）。

### 画面の仕事（D-2 作業中）

大別 2 系統。運用者 / 内部β / 外部有料は core 全件をスクロール一覧する。

1. 当日断面 — 現行配布 XLSX（本番テンプレは indicators_template_v1.4）に近い横断表。デフォルト列は XLSX に合わせ、表示列の増減で他指標も出せる（D-9）。
2. 時系列グラフ — 日足 **60 本**。RS 31/63/126/252 と `z_turnover_60` を重畳。新規 `rs_sma75_*` も重畳（D-9）。（2026-09-10: 可視行のみ描画。**2026-09-22 で表の表示集合・並びと一致に更新**。）

**TOPIX 基準 / 日経平均基準（rs*_topix と rs*_nikkei）は表示モード切替**。同時表示しない。XLSX のシート分けに相当。


日次 XLSX 配布は **当面残す**（E-4）。Web は置換えではない。

### 読み口（D-3 作業中）

- 当日断面: core 向け日次指標（XLSX / CSV と同一 pure）。committed 行から key を解決。
- 時系列: ADR-004 `derived-series/` から日足 60 本を切る。通常読取で R2 ListObjects 禁止。

### 外部ページ（D-8 作業中）

Web で出すのは **株探の概要 / チャート / ニュース** のみ（`link_kabutan` / `link_kabutan_chart` / `link_kabutan_news`）。iframe を試し、拒否なら新規タブ。プロキシ埋め込みはしない。

**Web ではバフェット・コードを既定から省く**（先方仕様変更）。みんかぶ・Yahoo も既定オフ。XLSX 側の列は当面変えない。（**2026-09-22:** 表示設定で任意オン可。D-8 改。）

### 指標の割り当て（D-9 作業中）

**表（当日断面）**

- デフォルト列は現行配布 XLSX と同様。本番は `indicators_template_v1.4`（説明文書はまだ v1.2）。
- Web では D-8 どおり `link_buffett` をデフォルトから除く。
- 表示列の増減（列の出し隠し）で、日次 CSV にある他指標も出せる。例: `turnover_yen` / `turnover_ma_ratio_60` / `price_change_pct` / `perfect_order_days` / `beta_adjusted_rs_*` / `information_ratio_*`。
- 新規 `rs_sma75_*` はデフォルト表に足す（XLSX 本番には未登録）。

**グラフ（日足 60 本。2026-09-10 は可視行のみ。2026-09-22 は表と同じ集合・順）**

- 重畳: `rs31_*` / `rs63_*` / `rs126_*` / `rs252_*` / `z_turnover_60` / `rs_sma75_*`。
- ベンチは表と同じ表示モード（TOPIX または日経。同時非表示）。
- 表示のみ規格化（保存値は変えない）。`y_RS = RS`、`y_Z = z_turnover_60 / 5`。割る数 1 と 5 は XLSX カラースケール端点に合わせる。
- 縦軸の範囲は **全銘柄共通**（目安: [-1, 1]）。行ごと・可視 60 本ごとの自動スケールはしない。銘柄間で同じ高さが同じ意味に見えることが条件。
- 表とホバーは生値。端を超える点はクリップしない（軸外に描く）。

**新規指標 `rs_sma75_topix` / `rs_sma75_nikkei`（仮キー。localhost freeze 内では算出。metric_set 正本・本番 CSV は未採用）**

- 終値ではなく **SMA75 系列** に既存 RS（B方式: 期間リターン差）を適用する。ベンチも SMA75。
- RS 窓長は **31 営業日**。`rs75_*`（終値の 75 日 RS）ではない。
- SMA25/200 の値は依然として永続化しない。Perfect Order は日数のみ。
- 追加は新 metric set version（ADR-004）。既存日次 CSV と series は同一 pure。本ファイルだけでは metric_set を変えない。

### MVP との関係（D-7）

「UI をやらない」は撤回。バッチ MVP（ユニバース・指標・XLSX）は残す。画面は web_ui_v1。助言禁止は残す。

### ホストと認証（D-4 / C-1）

採用（T-1 案 C）: Pages + 認証必須 BFF。公開 mint＝未認証禁止。初回はブラウザ直読み。無料は後続中継。ブラウザは PostgREST 禁止。実装・live は未。

### 意図的に後回し

- 外部有料 / 外部無料の live 投入（T-4 / T-9 採用。初回は内部のみ）
- C-4 / C-5: 利用者 RLS は初回足さない。公開 mint（未認証）は解禁しない
- Pages オリジンの具体 URL（R2 CORS AllowedOrigins）
- view bundle の圧縮・内部欄名（prefix とベンチ分割は採用済み）


## プロト検証の捕捉（2026-09-22）— 画面要件の材料。**古い衝突は打ち消し**

localhost 叩き台 `prototypes/web-ui-asof/` から起こした画面要件。プロト実装自体は live 証拠にしない。
採用した画面は [web_ui_v1.md](../contracts/web_ui_v1.md)。本節のうち次は **撤回**: `turnover_yen` 未決（T-8）、タブ設定のクライアント保存（T-6）、ニュース CSV のカレンダーずれ（束は as-of に揃える）。
本節だけでは `pr-5d-web-ui` / `live_gate_5d` / Phase 5 overall / Issue #93 を閉じない。Web UI 完了とは書かない。

### レイアウト（D-2 改）

3 領域。運用者 / 内部β / 外部有料は core 全件をスクロール一覧する。

1. 左上: 当日断面の横断表
2. 左下: WEB ペイン（高さスプリッタ）
3. 右: 銘柄単位の時系列グラフ（凡例＋カード）

### 表（D-9 改 / D-10 / D-13）

- as-of はツールバーの日付プルダウンが正。`date` 列は表にも列の出し隠しにも出さない（D-10）
- ベンチは TOPIX / 日経の表示モード切替。同時表示しない。列パネルに `_*_nikkei` 双子は出さない
- デフォルト列: コード、銘柄名、お気入り、`price_text`、Zscore、加速Z、加速、RS31/63/126/252、SMA75 RS、ニュース候補束ね列、調査ブロック
- 株探リンク 3 列は表デフォルトから外し、WEB タブへ移す
- `event_news_1..3` の title/url は「売買代金急増 要因ニュース候補」1 列に束ねる。分解列は出し隠しに出さない
- 数値表示は `+0.0` / `±0`。条件付き書式は XLSX 端点（Z / 加速Z は ±5、RS / 加速は ±1、`price_text` はキーワード色）
- パネルから除外: `date`、`link_*`、ニュース分解列、内部キー、`turnover_yen`（T-8）
- タブ表示設定は T-6 のアカウント袋（クライアント保存はキャッシュ）
- 数値ヘッダは Excel 風のソートと比較フィルタ。お気に入り列で「お気に入りのみ」。特殊フィルタ「RS系（31/63/126/252/SMA75）が全てマイナスの銘柄を除外」（D-13）
- 無料プレビュー中はソート・お気入り・特殊フィルタ・列フィルタをロック（D-1 と整合。製品の絞りは C-2 どおりサーバ側）

### グラフ（D-9 改 / D-11 / D-12）

- 表示対象と並びは表の `displayRows()` と同一。仮想化は描画最適化であり、表に無い銘柄だけをグラフに出さない
- 共通 60 営業日軸。欠損日は穴。重畳: RS31/63/126/252、SMA75 RS、`z_turnover_60`（描画 `y_Z = z/5`）
- 縦軸は全銘柄共通。既定窓 **[-1, +1]**。行ごと・窓ごとの自動スケールはしない。値はクリップしない
- 表とホバーは生値（Z は raw と disp）
- 表↔グラフでホバー／選択を同期し、相手を表示領域内に保つ（D-11）
- ドラッグ中だけ縦パン。世界座標 **[-2, +5]** 内。離すと 0 基準（[-1, +1]）に戻す
- 上にはみ出しは緑、下は赤（RS31 の太さ・色）。**Z のみのはみ出しは Zscore 色**
- 左右端の Z 棒がプロット内に収まるよう x を調整する
- 実データの max は RS252 で極端（デモ as-of では約 +50）。p99 は約 +1.4。軸の恒久拡張は後回し（D-12 はパンで見る）

### WEB ペイン（D-8 改）

- 既定タブ: 株探の概要 / チャート / ニュース、およびニュース候補（タイトル冒頭 10 文字。一括スイッチ）
- **材料不明・需給起因疑いは候補タブにせずテキスト表示**
- タブ表示設定（列の出し隠しと同型。T-6 アカウント袋）: バフェットコード / みんかぶ / Yahoo!ファイナンスは **デフォルト OFF**
- iframe を試し、拒否・PDF 等は埋め込み不可オーバーレイ＋別タブ。プロキシ埋め込みはしない
- 未選択時は空状態。XLSX のリンク列構成はこのメモでは変えない

### 読み口の日付（D-3 改）

- 指標・価格情報・ローソク説明・ニュース候補・外部 URL・調査ブロックは **同じ as-of 営業日** で view bundle に入れる。カレンダー日がずれた CSV を as-of 表として出さない。
- CSV / series / bundle の同一 as-of 値は同一 pure（拘束 9）

### プロト専用で製品要件にしない

- bind `127.0.0.1`、freeze sqlite、mint CLI 禁止、開発バナーのユーザー ID、お気入りの localStorage 永続、デモ日付が数日分だけ

### まだ空けること

- CORS 許可オリジンと cookie ドメインの具体値
- view bundle のバイト上限・圧縮・内部スキーマ欄名（T-2 案 C の実装詳細）

---

## トラック別に先に決めること

Web UI 仕様が Track C / E の入力になる。**D の画面範囲が決まらないと C の「誰に何を許可するか」と E の「顧客正本はどれか」が閉じない。**

### トラック D — Web UI（これ自体が仕様）

画面ファーストバージョンは [web_ui_v1.md](../contracts/web_ui_v1.md)。本表は棚卸し。実装・live は未。

| ID | 決めること | 拘束・材料 |
|----|------------|------------|
| D-1 | 利用者は誰か | 採用（web_ui_v1 / T-4）: 4 ロール。同じアプリ。初回 live は運用者+内部β。core のみ。無料は z_turnover_60 降順の第 20 位同点まで+グラフあり。外部 live 後続 |
| D-2 | 画面の仕事は何か | 採用（web_ui_v1）: 表＋下 WEB（スプリッタ）＋右グラフ。断面は XLSX v1.4 相当。時系列 60 本。RS31/63/126/252 + z + rs_sma75 重畳。SMA75 空列禁止 |
| D-3 | 読み出す blob は何か | 採用（T-2 案 C）: `derived-web-asof/` の as-of×ベンチ bundle。書き手系列は derived-series。顧客正本は XLSX（T-3）。ニュースも as-of 揃え。ListObjects 禁止 |
| D-4 | ホストと認証境界（Pages / Worker / 別オリジン）。公開ページの有無 | 採用（T-1 案 C）: Pages UI + 認証必須 BFF。Supabase Auth。公開 mint＝未認証禁止。初回はブラウザ直読み。無料は後で中継 |
| D-5 | 画面が mint に渡すキー | 採用: mint キーは `as_of` + `benchmark`。object_key は BFF が committed bundle から解決。dates / preferences は別 API |
| D-6 | 出してはいけない表示（助言、ランキング確定、未 commit のプレビュー） | プロジェクト共通ルール、P0 |
| D-7 | MVP §2.2 との関係 | 採用: 「UI をやらない」は撤回。助言禁止は残す。画面正本は web_ui_v1 |
| D-8 | 外部サイトのページ内表示 | 採用（web_ui_v1）: 既定=株探3＋ニュース候補一括。材料不明はテキスト。バフェット/みんかぶ/Yahoo は既定オフで任意オン。iframe→拒否ならタブ。プロキシしない。ニュースは as-of 揃え |
| D-9 | 指標ごとの断面 / グラフ / 両方 | 採用（web_ui_v1）: CF は XLSX 端点。`turnover_yen` は列パネルに出さない（T-8） |
| D-10 | as-of 切替 | 採用（web_ui_v1）: 日付プルダウンが断面の正。date 列は出さない。データがある営業日。mint キーは as_of+benchmark |
| D-11 | 表とグラフの連動 | 採用（web_ui_v1）: 同一集合・同一順。ホバー／選択同期。相手を表示内に保つ |
| D-12 | グラフ操作とはみ出し | 採用: 既定 [-1,1]。パン [-2,+5]。恒久拡張しない（T-7） |
| D-13 | スクリーニング | 採用（web_ui_v1）: 数値ヘッダのソート＋比較フィルタ。特殊フィルタ（全 RS マイナス除外）。無料時は無効 |
| D-14 | お気入りと表示設定の永続 | 採用（T-6）: 星・列・タブ等を `auth.uid` に紐づける。設定袋は拡張可能。無料ロールはお気入りなし。API は T-1 案 C の BFF |

### トラック C — 認可製品（仕様が要る）

Track B の `EntitlementProofPort` は内部 fixture で live 確認しただけ。製品の「誰が proven か」は T-4 で初回分だけ採用（allowlist）。外部ロールは未定義。

| ID | 決めること | 拘束・材料 |
|----|------------|------------|
| C-1 | 認証（Supabase Auth 前提でよいか、IdP、セッション） | 採用（T-1 案 C）: Supabase Auth。T-6 PK は `auth.uid`。Pages は静的、セッション検証は BFF |
| C-2 | entitlement の単位 | 採用（T-4）: 初回 live は allowlist の operator / internal_beta のみ。未証明は拒否。無料 20 位同点は仕様に残し初回は実装しない |
| C-3 | 課金 webhook の入力と冪等（`webhook_events`） | 採用（T-9）: 外部有料 live まで実装しない。制御面は Supabase |
| C-4 | 利用者別 RLS | 採用（T-9）: 初回は足さない（P0 の policy ゼロを維持）。後で足すなら最小 SELECT |
| C-5 | 公開 mint | 採用（T-9）: 公開 mint＝未認証の署名発行。解禁しない。認証済み BFF は製品口。署名 URL 本文をログ・DB に残さない |
| C-6 | 未契約・期限切れ・identity_mismatch の UI 側失敗 | 採用（T-5）: 未ログインはログインへ。unproven / 期限切れ / identity_mismatch は「利用できません」。API 死はログインへ送らない。署名 URL 本文は出さない。allow-stub 禁止 |

### トラック E — 配布切替（仕様が要る）

| ID | 決めること | 拘束・材料 |
|----|------------|------------|
| E-1 | 顧客正本は `published/` か、Dropbox / Drive 残置か、Web series か | 採用（T-3）: 当面は現行 live TARGETS（r2, dropbox）の日次 XLSX。Web は追加閲覧。published/ 切替は内部 Web live の後 |
| E-2 | visibility（work / paid）を Auth とどう結ぶか | C-2 依存 |
| E-3 | 切替手順（shadow → cutover）と rollback。live `TARGETS` を壊さない条件 | 採用（T-3）: published/ 切替は内部 Web live の後。初回は TARGETS を変えない |
| E-4 | 日次 XLSX と Web の関係 | 採用（T-3 / E-4）: 当面両方残す。Web は XLSX の置換えではない。値は同一 pure |

---

## 本ファイルでやらないこと

- 画面ワイヤー、コンポーネント、ルーティングの確定
- DDL / mint / Auth / webhook の実装
- `pr-5c` / `pr-5d` / `pr-5e` を `merged_and_verified` にすること
- `live_gate_5c` / `5d` / `5e` を閉じること
- Phase 5 overall や Issue #93 を閉じること
- Track A の Healthchecks / ops views をユーザー向けダッシュボードに昇格すること

## 採用済み（docs。実装・live ではない）

2026-09-22 後半。画面 v1 と `rs_sma75` カタログに加え、次を採用する。本節だけでは `live_gate_5c` / `5d` / `5e` を閉じない。

| ID | 採用内容 |
|----|----------|
| T-3 / E-1 / E-3 / E-4 | 顧客正本は当面 live TARGETS（`r2,dropbox`）の日次 XLSX。Web は追加閲覧。`published/` 切替は内部 Web live の後。TARGETS は壊さない |
| T-4 / C-2 | 初回 live の proven は allowlist の `operator` / `internal_beta` のみ。未証明は拒否（allow-stub 禁止）。無料第20位同点は仕様に残し、そのロールを出さない初回は実装しない |
| T-6 / D-14 | お気入りに加え、列の出し隠し・タブ表示設定・ベンチ・特殊フィルタ等の表示設定を **アカウントに永続紐付け**。未知キーを落とさない設定袋（`schema_version` + 名前空間）で、後から項目を足せる。無料ロールはお気入りを持たない。書き込みは T-1 案 C の BFF（`auth.uid`） |
| T-7 / D-12 | 縦軸の恒久拡張はしない。既定 [-1,1]、パンで見る |
| T-8 / D-9 | `turnover_yen` は列パネルに出さない |
| T-9 / C-3 / C-4 / C-5 | 公開 mint＝未認証の署名発行。解禁しない。認証済み BFF は製品口。初回は利用者 RLS を足さない。課金 webhook は外部有料 live まで実装しない |
| T-10 | 運用者インフラタブは出さない。5.5b / Healthchecks をユーザー画面にしない |
| T-1 / D-4 / C-1 | **案 C**: Pages + 認証必須 BFF。公開 mint＝未認証禁止。初回（運用者/内部β/将来の有料）はブラウザが R2 直読み。無料ロールは後続で BFF 中継。ブラウザは PostgREST 禁止 |
| T-2 / D-5 / D-3 | **案 C**: mint キーは `as_of`+`benchmark`。`derived-web-asof/` をベンチ別に committed。両ベンチを 1 束にしない。ニュースは as-of 揃え。SMA75 空列禁止 |
| T-5 / C-6 | 未ログイン→ログイン。unproven 等→「利用できません」。API 死はログインへ送らない。署名 URL を DOM に出さない |

### T-6 設定袋（契約の骨）

サーバは利用者 1 人につき 1 つの preferences 行を持つ（DDL は Track C 実装 PR。本ファイルだけでは migration しない）。

- `schema_version`（整数。未知の新バージョンはクライアントが読めるキーだけ使い、未知キーは **round-trip で保持**）
- `bag`（JSON）。名前空間を足すだけで項目を増やせる。初回の名前空間例:
  - `favorites.codes` — 銘柄コード配列
  - `table.visible_keys` / `table.sort` / `table.col_filters` / `table.fav_only` / `table.exclude_all_rs_neg`
  - `tabs.settings` — WEB タブの出し隠し
  - `ui.bench` — TOPIX / 日経
- クライアントが知らない名前空間を delete してはならない。将来項目は **新名前空間を足す**（空予約は不要。未知キーの round-trip が拡張余地）。
- 更新は名前空間単位の merge。bag 全体の破壊的 replace は `schema_version` 更新時のみ。
- 1 アカウント 1 行。端末 localStorage はキャッシュ。衝突時はサーバが正。
- サイズ上限を契約する（目安 64KiB）。超過は拒否（413）。署名 URL・object_key・生セッションは bag に入れない。
- 無料ロールへの `favorites` 書き込みは拒否。他名前空間（列・タブ等）はロール方針に従う。
- **禁止:** ブラウザから Supabase PostgREST / preferences 表 / storage への直接アクセス。ログインは Auth セッション発行のみ可。JWT を BFF に渡し、BFF だけが `service_role` で bag を読む（T-9・P0）。

### T-1 案 C（契約の骨）

選定理由: UX（静的 UI を先に出せる）と継続開発の柔軟性（UI と API を別 PR・別ロールバック）。

- UI: Cloudflare Pages（静的）。データは出さない。
- API: 別ホストの Worker。責務は T-6 と view bundle mint。JWT 必須。
- セッション: Supabase Auth。T-6 PK は `auth.uid`。
- **公開 mint＝未認証の署名発行。** 未ログイン mint / preferences は 401。認証済み BFF は Track C/D の製品口。
- mint キーは `as_of` + `benchmark`。`object_key` をブラウザが組み立てない。
- **初回（運用者 / 内部β。将来の有料も）:** BFF が短命 GetObject URL を返し、ブラウザが R2（S3 API ドメイン）を読む。有料を中継で重くしない。
- **無料ロール（後続 live）:** BFF が束を取得して行キャップをかけて JSON を返す（中継）。初回は無料ロールを出さない（T-4）。
- R2 bucket CORS: Pages オリジンに対し GET / HEAD / OPTIONS のみ。PUT/DELETE 不可。bucket は private のまま。オリジン具体 URL は実装 PR。
- CORS 失敗は T-5 の「一時的に利用できません」（ログインへ送らない）。
- 本ファイルだけでは Pages / Worker / Auth / CORS 適用を実装しない。

### T-2 案 C（契約の骨）

選定理由: Class B / mint 回数と、表とグラフを同一束から出すこと。両ベンチ同時取得で有料を重くしない。

- **mint に渡すキーは `as_of` + `benchmark`。** dates 一覧と T-6 は別 API。
- prefix は `derived-web-asof/`。ベンチごとに別 committed オブジェクト。
- 1 束 = 横断表 + そのベンチの 60 営業日系列。銘柄切替は束の中。
- 顧客正本にしない（T-3）。書き手系列は `derived-series/`。
- ニュース・リンク・調査は **同じ as-of** で束に入れる。カレンダーずれを出さない。
- `rs_sma75_*` は束に必須。空列を製品に出さない。初回 live は metric_set_v1_1 active 後（本ファイルでは CAS しない）。
- 無料キャップのサーバ切替は無料 live 時の中継経路。初回直読みではフル core。
- ListObjects 禁止。allow-stub 禁止。`published/` を mint キーにしない。

### T-5（契約の骨）

T-1 案 C は「Pages は生きて API だけ死ぬ」が起きるので、失敗画面を同時採用する。秘密（署名 URL、object_key、JWT）を画面・ログに出さない。

| 状況 | 画面 |
|------|------|
| 未ログイン / 401 | ログインへ。データ面は出さない |
| `unproven` / 期限切れ / `identity_mismatch` / 403 | 「利用できません」。再ログイン可。stub データで埋めない |
| Pages 生存 + API 到達不能 / 5xx / CORS 失敗 | 「一時的に利用できません」。**ログイン画面へ送らない** |
| bundle 欠落 / orphan / identity_mismatch on object | 「利用できません」。object_key を出さない |

サポート用の内部コード（例: `unproven`）を出すかは実装 PR。本文に署名 URL を載せない。

## 不採用とした比較（記録）

採用は T-1 案 C、T-2 案 C、T-5。以下は覆す文書なしに戻さない。実装の出発点にしない。

### T-1 ホストと認証（D-4 / C-1）— 記録（採用は案 C）

T-6 をアカウント紐付けにしたので、**どの案でも identity は必要**。違うのは「セッションを誰が持つか」「ブラウザが blob をどう読むか」「T-6 の PK を何にするか」。公開 mint 禁止・private R2・allow-stub 禁止は全案共通。実装・DDL・live_gate は本節では開始しない。

比較の切り口は四つ。（1）セッション正本は Supabase Auth か、Access / OIDC / VPN か。（2）blob はブラウザ mint か、サーバ中継か、mint なし静的か。（3）UI と API は同一オリジンか。（4）外部有料へ伸ばすときの作り直し量。

#### 案 A — Pages 静的 + Supabase Auth。初回はブラウザ mint なし

画面は Cloudflare Pages。ログインは Supabase Auth（magic link）。時系列・断面は内部 CLI / バッチが作った **画面用の committed 配置**（または短命 URL をサーバ側で埋め込む）を読む。ブラウザは Track B の mint RPC を呼ばない。T-6 は Supabase の `auth.uid` 行。

- メリット:
  - mint の攻撃面を初回ゼロにできる。未認証の署名発行経路を画面が踏まない。
  - Pages は静的だけで、デプロイとキャッシュが小さい。
  - Auth は ADR-003 の制御面（Supabase）と一致する。T-6 を `auth.uid` に直接載せられる。
  - 公開 URL を置いても「ソースは見えても blob は見えない」にしやすい。
  - 外部有料へ伸ばすとき、セッション層を作り直さなくてよい。
- デメリット:
  - Track B で閉じた committed → GetObject 署名を画面が検証しない。live_gate_5d の「画面が本番読み口を踏む」証拠が弱くなる。
  - 後から Worker mint を足すと、静的配置と mint の **経路が二つ** になる。
  - as-of 履歴を静的バンドルすると容量・キャッシュ無効化が重い。埋め込み短命 URL は HTML / CDN / ログに秘密が乗る。
  - データ面が localhost sqlite 配置に近く、本番 isolation（P-ISO）の検証にならない。
  - T-6 の書き込みはできるが、系列取得と preferences が別チャネルになり、失敗分類が割れやすい。

#### 案 B — 同一オリジン Worker（UI + preferences API + mint）

一つの Worker が HTML / JSON API / GetObject mint を出す。Cookie は同一オリジン。未ログインは 401。公開 mint ではない（認証必須）。T-6 も同じセッション。

- メリット:
  - CORS が要らない。Cookie / CSRF の境界が一つ。
  - T-6 の読み書きと series 取得を同じセッションで扱える。失敗画面（T-5）も同じ 401/403 体系に載せやすい。
  - 画面が最初から Track B の契約（committed のみ、orphan 拒否、identity_mismatch）を踏む。
  - 後から「UI 用の別経路」を増やさない。live_gate_5d の読み口証拠が取りやすい。
- デメリット:
  - 初回の実装量が最大（静的配信 + Auth 検証 + T-6 + mint）。
  - 静的と API のデプロイ境界が曖昧。キャッシュヘッダを間違えると HTML に API レスポンスが乗る。
  - 認証必須の運用を誤ると、未ログイン mint が「公開 mint」相当になり拘束 5 を破る。
  - Pages プレビューと Worker プレビューがずれやすい。ロールバック単位が大きい。

#### 案 C — Pages UI + 認証必須の API Worker（BFF）【採用】

UI は Pages。別ホスト（またはカスタムドメイン配下）の Worker が preferences と mint だけ持つ。ブラウザは論理キーだけ API に渡し、署名 URL または中継を受ける。UI と API を別 PR で出せる。

- メリット:
  - 画面を先に内部公開し、mint を後から足せる。T-6 API だけ先行できる。
  - Worker の責務が API に閉じ、静的資産と分離できる。キャッシュ方針を分けられる。
  - Track B mint を画面キー契約（T-2）と独立に試験できる。
- デメリット:
  - オリジンが二つ。CORS かカスタムドメインの設計が要る。
  - Cookie の SameSite / ホストを間違えると T-6 が動かない（ログイン済みなのに 401）。
  - Pages に置いた JS から API の出し方が漏れやすい。キーは論理のみ、と契約で縛る必要。
  - 障害が「Pages は生きているが API だけ死ぬ」になり、失敗画面の設計（T-5）が要る。
  - 認証クッキーをどのホストに置くかで、案 B よりセッション設計が重い。

#### 案 D — Cloudflare Access で内部閉門。Supabase Auth は後

セッションは Cloudflare Access（Google Workspace 等の allowlist）。R2 は private のまま。entitlement のメールは Access identity。Supabase Auth は外部有料のときに足す。データ面は Worker 中継でも静的でもよい。

- メリット:
  - 内部βを最速で閉じられる。社内 IdP を新規に増やさない。
  - T-4 の allowlist を Access ポリシーにそのまま載せられる。未ログイン公開面を物理的に消せる。
  - 公開 mint 事故を起こしにくい（閉門の外側に画面が無い）。
- デメリット:
  - ADR-003「認可・entitlements は Supabase」から **セッション層が外れる**。
  - T-6 を Access の email に紐づけると、後で `auth.uid` へ移す移行が要る（設定袋の PK 変更）。
  - 外部有料・magic link・個人 Gmail に向かない。招待運用が Access 側に残る。
  - 制御面の RLS 設計と Access ポリシーが二重管理になる。
  - 監査ログが Cloudflare と Supabase に割れ、誰がどの as-of を見たか追いにくい。

比較の軸: A は安全で検証が弱い。B は契約どおりで重い。C は段階投入できるがオリジン設計が要る。D は内部最速だが制御面の正本から外れる。

以下は A–D と **方向が違う** 案（同じ「Pages vs Worker」軸の細分ではない）。

#### 案 E — Pages Functions（Pages に薄いサーバを載せる）

UI も T-6 も mint も **Pages プロジェクト内**。別 Worker サービスを立てない。同一オリジン。セッションは Supabase JWT を Functions が検証。

- メリット:
  - 案 B の同一オリジンを、Worker 別デプロイなしで取れる。
  - プレビュー URL が UI と API で揃いやすい。
  - 初回の Cloudflare 成果物が一つ。
- デメリット:
  - Functions の実行時間・CPU・ストリーミング制限が Worker より狭いことがある。GetObject 中継が厳しい。
  - 静的とサーバのロールバックが同じプロジェクトに結び付く。
  - Track B の mint 実装を Functions へ移植するとき、既存 CLI 試験との差が出やすい。
  - 後から「API だけスケール」がしにくい（結局 Worker 分離＝案 C へ回帰）。

#### 案 F — Cloudflare をアプリ面から外す（Supabase Auth + Edge Functions / PostgREST）

セッションも T-6 も Supabase。mint 相当は Edge Function が R2 API を呼ぶか、バッチが短命 URL を表に書く。画面ホストは何でもよい（Pages でも可）。**Cloudflare Worker を持たない**。

- メリット:
  - ADR-003 の制御面とデータ面のセッションが完全に一致する。T-6 は RLS だけで閉じられる。
  - Cloudflare 側の認証設定が要らない。Pages は本当に静的だけで済む。
  - 外部有料の magic link / 将来の IdP を Supabase の機能で足せる。
- デメリット:
  - Track B の mint 契約（Worker / R2 GetObject / 5 分 / 次数制限）を Supabase 側に **再実装** する。
  - R2 資格を Edge Function の secret に置くと、漏洩時の影響が大きい。
  - 実行基盤が二つ（バッチは R2、画面 API は Supabase）になり、観測が割れる。
  - 署名 URL を表に書く方式は期限切れと再発行の責務がバッチに残る（案 A と同じ弱点）。

#### 案 G — 公開ホストを置かない（VPN / WARP / Tailscale / 社内リバースプロキシ）

画面はインターネットに出さない。運用者と内部βだけがトンネル経由で `serve` 相当に届く。identity は VPN アカウント。T-6 は社内 DB でも Supabase でもよい。

- メリット:
  - 公開 mint・公開 Pages・CORS の議論が消える。攻撃面が最小。
  - localhost プロトを閉域のまま近づけるので、画面検証を早く回せる。
  - T-4 の内部のみと整合する。
- デメリット:
  - **製品のホスト契約にならない**。live_gate_5d の配布面証拠に使いにくい。
  - 外部有料へ伸ばすとき、ホストも Auth も作り直し。
  - T-6 を VPN ユーザー名に付けると PK 移行が案 D より重い。
  - 端末セットアップが利用者負担。iframe・別タブ検証が社内ネット依存になる。
  - 方針の「常時稼働サーバを想定しない」と、社内常時 `serve` が衝突しやすい。

#### 案 H — Worker が OIDC JWT を直接検証（Supabase Auth も Access も使わない）

Google / Microsoft の ID トークンを Worker が検証。T-6 の PK は IdP の `iss`+`sub`。entitlements は別表（メール allowlist）。Supabase は制御面の保管庫だけ、または使わない。

- メリット:
  - IdP を一つに固定でき、Auth ベンダーを増やさない。
  - Access の「Cloudflare アカウント必須」を避けつつ閉門に近い体験にできる。
  - セッション層を Worker に閉じ、Pages は静的のままにできる（案 C の Auth を IdP 直結にしたもの）。
- デメリット:
  - ADR-003 の「認可は Supabase」からセッションも外れる。Refresh・ログアウト・magic link を自前実装する。
  - T-6 PK が `sub` になり、後で Supabase `auth.uid` へ寄せる移行が要る。
  - ロール（T-4）と IdP グループの対応表が新しい単一障害点になる。
  - トークン検証の鍵ローテ・clock skew を Worker で間違えると、認証バイパスになる。

| 案 | セッション正本 | blob 読み | 同一オリジン | 内部最速 | 外部有料への伸び | T-6 PK |
|----|----------------|-----------|--------------|----------|------------------|--------|
| A | Supabase Auth | mint なし | しない（静的） | 中 | よい | `auth.uid` |
| B | Supabase Auth | Worker mint | する | 遅 | よい | `auth.uid` |
| C | Supabase Auth | BFF mint | しない | 中 | よい | `auth.uid` |
| D | Access | 任意 | 任意 | 最速 | 悪い | email（後で移行） |
| E | Supabase Auth | Pages Functions | する | 中 | よい | `auth.uid` |
| F | Supabase Auth | Edge / 表 | しない | 中 | よい | `auth.uid` |
| G | VPN | 閉域 serve | する（閉域） | 画面は速い | 最悪 | VPN 名（移行） |
| H | OIDC 直 | Worker | 任意 | 中 | 中 | `iss`+`sub`（移行） |

A/E/F は制御面に忠実で mint 検証が弱い（F は mint を再実装）。B/C/E は本番読み口に近い。D/G/H は内部閉門が速いが T-6 の PK 移行が残る。**採用は案 C。**

### T-2 画面が渡すキー（D-5）— 記録（採用は案 C）

T-3 採用により **初回の顧客正本は XLSX**。画面 mint キーは `as_of` + `benchmark`。読み口は `derived-web-asof/`。`published/` を初回の mint キーにしない。object_key をブラウザが組み立てない。ListObjects / allow-stub 禁止。

比較の切り口は記録用（採用は案 C・ベンチ別）。

#### 案 A — 画面が `as_of` + `metric_set_version` + `benchmark` + `code` を明示

object_key はクライアントが組み立てず、サーバが committed 行から解決する。時系列は `derived-series/`。断面は日次 committed snapshot。

- メリット:
  - どの version を見ているか画面・クエリ・監査が一致する。
  - Track B の identity_mismatch（指定と committed の不一致）をそのまま使える。
  - ベンチ切替がクエリで見える。T-6 の `ui.bench` と突き合わせできる。
  - 旧クライアントが新 active に黙って吸い寄せられない（明示拒否できる）。
- デメリット:
  - active pointer が動くと、古いクライアントが古い version を要求して拒否される。互換ウィンドウの運用が要る。
  - 画面が storage の単語（`metric_set_version`）を知る。レイアウト変更がフロント契約になる。
  - T-3 のあと `published/` に切るとキー集合が一度変わる。
  - 銘柄×指標の mint 回数が増えやすい（R2 Class B）。

#### 案 B — 画面は `as_of` + `code` + `benchmark` だけ。version はサーバが active に束縛

クライアントは論理日付と銘柄だけ送る。サーバが active metric set と object_key を選ぶ。

- メリット:
  - 画面が R2 レイアウトを知らない。キー契約が安定する。
  - active 切替（v1 → v1.1）でクライアントを増やさなくてよい。
  - T-3 の「Web は追加面」に合う（顧客は XLSX、Web はサーバが選んだ断面）。
- デメリット:
  - 「昨日の画面と今日で version が黙って変わった」を利用者が Replay できない。
  - 監査はサーバログ依存。画面 URL を保存しても再現不足。
  - 古い as-of を旧 version で再現する経路を別途用意しないと ADR-004 の監査と衝突する。
  - shadow 期間に「どれを見せるか」のサーバ分岐が新しい単一障害点になる。

#### 案 C — as-of ごとの view bundle（表＋60本を1オブジェクト）【採用】

freeze に近い束を committed する。**採用後の mint キーは `as_of` + `benchmark`（ベンチ別にオブジェクトを分ける。両ベンチを 1 束にしない）。** 当時の比較文にあった「画面は as_of だけ」は mint キーの意味であり、日付切替の話と混同しない。銘柄切替は bundle 内。

- メリット:
  - リクエスト数が少ない（R2 Class B 節約）。mint 回数も少ない。
  - プロトの sqlite に近い。表とグラフの集合・順序をサーバで固定できる（D-11）。
  - ネットワーク失敗が「日付単位」で閉じる。
- デメリット:
  - 新成果物タイプが増える。derived-series 正本と二重。
  - core 全件×60本でオブジェクトが大きい。部分更新ができず、銘柄1件の再計算でも束を作り直す。
  - T-3 のもとでは Web は XLSX の置換えではないので、「顧客正本の束」を増やさない方が安全。
  - 無料ロールの行キャップを bundle 内で切ると、サーバフィルタと二重になる。

T-3 のもとでは **Web は XLSX の置換えではない**。案 C の bundle は顧客正本ではなく Web 投影である（採用時の拘束）。A と B の差は「version を画面が知るか、サーバが縛るか」。

以下は A–C と **方向が違う** 案。

#### 案 D — 画面は opaque handle だけ渡す（`view_id` / 短命 capability）

ログイン後、サーバが「このセッションが見てよい断面」の handle を発行する。以降の表・系列はその handle だけ。`as_of` も version もクエリに出さない。

- メリット:
  - ブラウザとアクセスログにストレージ語彙が残らない。object_key 漏洩面が小さい。
  - T-4 のロール変更（失効）を handle 無効化で即時にできる。
  - T-2 と T-1 を切り離せる（ホストが何でも handle 発行口だけあればよい）。
- デメリット:
  - Replay・共有 URL・「この日付を開く」ができない。as-of プルダウン（D-10）と衝突する。
  - handle の保管・期限・再利用が新しい契約になる（mint の上にセッションが乗る）。
  - 障害時に「どの as-of を見ていたか」をサポートできない（T-5 がさらに曖昧）。
  - ブックマーク不能は調査ツールとして痛い。

#### 案 E — 断面と系列でキーを分ける（複合）

表は `as_of` だけの snapshot。グラフは銘柄ごとに `as_of`+`code`+`benchmark`（version は A または B）。ニュース束は断面 CSV 側。

- メリット:
  - 表は 1 リクエスト、グラフは必要な銘柄だけ。案 C の巨大 bundle を避けつつ Class B を抑えられる。
  - プロトの「sqlite 断面 + 銘柄 series」に近い。D-11 の同一集合は表側で固定できる。
  - 指標追加（rs_sma75）が系列キーに閉じ、表スキーマと分離できる。
- デメリット:
  - 画面契約が二つ（snapshot と series）。失敗が片方だけ起きる。
  - 表とグラフで metric set がずれる事故を、サーバで同一 committed に縛る必要。
  - 実装とテストが A/B より長い。T-1 の mint 回数見積もりが経路別に要る。

#### 案 F — クライアントが `object_key` を直接送る（比較用・採用しない想定）

ブラウザが R2 パスを知っており、mint にフルキーを渡す。

- メリット:
  - サーバの解決ロジックが最小。デバッグでキーをそのまま叩ける。
- デメリット:
  - ListObjects 相当の探索や、隣パスの推測が容易。拘束（committed のみ）をクライアント信頼に落とす。
  - パス変更が破壊的フロント変更。公開 JS にバケット構造が残る。
  - Track B が画面キーを Out of scope にした理由と矛盾する。**比較のための反例**。

#### 案 G — サーバ合成 API（1 クエリで表＋選択銘柄の 60 本を返す）

mint せず、Worker / Edge が複数 GetObject して JSON を合成。画面のキーは `as_of` + 選択 `code`（と任意の version）。

- メリット:
  - ブラウザに署名 URL が乗らない。T-5 で URL を隠す必要が減る。
  - 画面はストレージを全く知らない。T-2 のキー面がアプリケーション API になる。
  - ロールごとの行キャップ・列マスクを合成段で強制できる（無料・T-4）。
- デメリット:
  - Worker CPU / メモリ / 待ち時間が大きい。60 本×複数銘柄はタイムアウトしやすい。
  - R2 の短命 GetObject 契約（5 分・次数）を、合成 API のレート制限として **別契約** し直す。
  - キャッシュが難しい（利用者・ロール・選択銘柄でキーが爆発）。
  - Track B の「ブラウザが GetObject」モデルから外れ、中継プロキシになる。

案 F は反例。D は Replay を捨てる。E はプロトに近く分割が上手いが契約が二つ。G は秘密が漏れにくいが中継が重い。**採用は案 C**（Web 投影の束であり、XLSX の置換えではない）。

### T-5 失敗画面（C-6）— 記録（採用済み。契約の骨は上節）

暫定案として書いていた文言を採用した。メリットは小さい・秘密を漏らさないこと。デメリットはサポート導線がないこと（T-9 で外部 live が後なので初回は許容）。

## 次

1. 採用済みは docs。**実装・active CAS・live_gate は未。** SMA75 空列の Web live は禁止（v1.1 active 後）。
2. 残る未決は Pages オリジン具体 URL と bundle 内部欄名。DDL は Auth 実装 PR。
3. `metric_set_v1` は in-place 変更しない。v1.1 shadow→active は別 PR。
4. 本ファイルだけでは live_gate_5d を閉じない。

P2 残債（bus CLI Fake、storage mypy、migration `001` baseline）は本仕様の blocker にしない。
