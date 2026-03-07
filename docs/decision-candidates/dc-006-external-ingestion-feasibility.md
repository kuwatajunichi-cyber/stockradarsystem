# dc-006: 株探/TDNet 取得層の実現性調査（PoC）

## 背景

`z_turnover > 4` 銘柄の背景推定PoCを進めるうえで、
「候補イベントをどこから、どの条件で、継続取得できるか」がボトルネック。

本メモは**取得可否・制約・実装方針**を整理する。

## 事実確認（2026-03 時点）

### 1) TDnet（公開閲覧サイト）

- 公開閲覧サイト: `https://www.release.tdnet.info/inbs/I_main_00.html`
- 日別一覧ページ（例）: `I_list_001_YYYYMMDD.html` 形式で確認可能
- 一覧には以下が含まれる:
  - 開示時刻
  - コード（5桁、末尾0付き）
  - 会社名
  - 表題
  - PDFリンク
  - XBRL zipリンク（一部）
- JPX説明ページ上、公開閲覧は原則31日分（過去分は別サービス）

#### 重要な制約

- `https://www.release.tdnet.info/robots.txt` は `User-agent: * / Disallow: /`
- 公開一覧ページ免責に「無断で転用、複製又は販売等を禁じる」旨の記載あり

=> **クローリング前提の常時自動取得は避ける**のが安全。

### 2) TDnet（公式API）

- JPX総研の `TDnet API` は公式・有料（仕様/Swaggerあり）
- 過去5年の開示データ取得を想定した正規経路
- テストサーバ（ダミーデータ）あり

=> 継続運用を見据える場合、**TDnetは公式API経路を第一候補**にすべき。

### 3) 株探（kabutan）

- `robots.txt` は確認でき、`Disallow` は限定的（`/search*` 等）
- 銘柄ニュースURLは構造化されている:
  - `https://kabutan.jp/stock/news?code=7203`
  - `nmode`（開示/決算/材料）や `date=YYYYMM00` で絞り込み可能
  - 記事IDは `b=nYYYY...` 形式

#### 重要な制約

- 利用規約（`info.kabutan.jp/terms-site/`）で以下の禁止が明記:
  - コンテンツ蓄積
  - 複製/編集/加工
  - 第三者提供/再配信
  - 法人事業利用の禁止条項

=> robotsだけで可否判断せず、**規約面では自動収集を前提にしない**設計が必要。

## 取得層の結論（PoC段階）

### 結論A: 「自動スクレイピング収集」は実験対象から外す

- TDnet公開閲覧: robots と免責の観点で非推奨
- 株探: 利用規約上の制約が強い

### 結論B: 取得層PoCは「合法経路 + 手動投入」で検証する

- TDnet: 公式APIのテスト仕様を対象にAdapter設計・Fake試験
- 株探: 手動調査メモ/許諾済みデータをJSONL化して投入

## 具体実装案（既存フロー非干渉）

1. **Adapter境界**
   - `TdnetEventSource`（公式API想定）
   - `NewsEventSource`（株探代替含む、将来差し替え）
   - `ManualEventSource`（JSONL/CSV）

2. **現在のPoC接続**
   - `rank_turnover_event_causes` は `events_jsonl` 入力を維持
   - 取得層は別ジョブで `news_tdnet_events.jsonl` を生成

3. **検証優先順位**
   - P1: JSONLスキーマ確定（source/published_at/event_type 等）
   - P2: TDnet公式APIのダミーデータで end-to-end を試験
   - P3: 株探相当は法務確認後、許諾データ源へ差し替え

## 実務上の推奨

- 背景推定の安定性は「取得量」より「正規化品質」が効く
- 無理にサイト収集を自動化せず、
  - まずは入力品質（event_type, novelty, issuer_specificity）を上げる
  - 次に合法な供給経路（TDnet API、契約データ）を増やす
- 本リポジトリの方針どおり、取得手段は差し替え可能に保つ
