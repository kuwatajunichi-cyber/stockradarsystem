# ユニバース・指標仕様 v1.2

**用途**: ランディングページ・解説記事での説明用の情報ソース  
**仕様の根拠**: 実装実態（コードを正とする。一次ユニバースは `src/stockradar/universe/jpx_primary.py`、二次分割は `equity_secondary.py`、指標は `compute_indicators_for_core.py` 等）  
**バージョン**: 1.2  
**更新方針**: ユニバースや指標の追加・変更がある都度、本ドキュメントを更新する。  
**ユーザー向けレイアウトの詳細**: [indicators_template_v1.2_design.md](indicators_template_v1.2_design.md)（`config/templates/indicators_template_v1.2.xlsx`）。本ディレクトリの役割は [README.md](README.md) を参照。

---

## 1. 概要

本システムは、日本株市場を対象に、定量指標にもとづいて調査候補となる銘柄群を日次で抽出・可視化する。投資助言や売買シグナルは提供せず、**調査対象候補の抽出**に特化している。

ユニバース（対象銘柄の集合）と指標の算出ロジックを、コードを用いず平易に説明する。  
**日次でエンドユーザーに配布する主成果物**は、`render_sheet` が日次指標 CSV を `indicators_template_v1.2.xlsx` に流し込んだスプレッドシート（TOPIX 基準シート・日経平均基準シート・README）である。第4章で CSV と XLSX の対応を整理する。

---

## 2. ユニバース

### 2.1 一次ユニバース（JPX銘柄一覧ベース）

**データソース**: JPX（日本取引所グループ）が公表する銘柄一覧の Excel。  
取得元ページ: <https://www.jpx.co.jp/markets/statistics-equities/misc/01.html（コード上の既定> URL は `stockradar.config.DEFAULT_JPX_PAGE_URL` と一致）

**分類の仕方**: 銘柄一覧の「市場・商品区分」列の文字列を、次のルールで `universe_primary` にマッピングする。  
（**部分一致**と**完全一致**が混在する。以下は実装どおりの優先順である。）

|universe_primary|判定（実装）|
|---------------------|------------|
|equity_domestic|区分文字列に **「内国株式」** を含む|
|equity_foreign|区分文字列に **「外国株式」** を含む|
|etf_etn|区分文字列が **`ETF・ETN`** と**完全一致**|
|reit_funds|区分文字列が **`REIT・ベンチャーファンド・カントリーファンド・インフラファンド`** と**完全一致**|
|pro_market|区分に **「PRO Market」** または **「TOKYO PRO Market」** を含む|
|investment_securities|区分文字列が **`出資証券`** と**完全一致**|
|unknown|空欄、または上記のいずれにも該当しない|

#### 除外ルール

- 銘柄コードに**数字が5桁以上**含まれる銘柄（種類株など）は一次ユニバースから除外する（アルファベット混在の4桁コードは対象外）。

---

### 2.2 二次ユニバース（内国株式の分割）

一次ユニバースのうち **equity_domestic（内国株式）** を、次の3つに**排他的**に分割する。

|区分|内容|
|----|----|
|**ipo**|キャッシュ取得が失敗している、または取得済みバー数が IPO 判定に必要な営業日数**未満**の銘柄（`insufficient` を含む）|
|**illiquid**|ipo 以外で、直近の営業日における売買代金（終値×出来高）の**中央値**が、所定の閾値**未満**の銘柄|
|**core**|ipo・illiquid 以外|

#### manifest（二次分割が参照するもの）

- 二次分割は **`data/cache/yf_daily/_manifest_universe.jsonl` のみ**を読む
  （`fetch_yf_daily_for_universe` が更新）。日次ジョブの
  `_manifest.jsonl`（`ensure_*` が `run_date` 鮮度を記録）とは
  **別ファイル**であり、日次の `stale` や run_date 整合は
  二次分割の IPO 判定に混ぜない。
- JSONL 1行は **`code` を主キー**とする。`symbol` のみの行も `code` 扱いで読める（実装: `equity_secondary._load_manifest_entries`）。
- manifest の `status` が **`stale`**（日次側の語義で乗ってきた場合）かつ **`fetched_bars` が IPO 必要本数以上**のとき、二次分割では **IPO に回さず**流動性（中央値）判定へ回す。サマリに `n_stale_run_date` を出す。

#### 判定パラメータ（参照値）

- IPO 判定に必要な営業日数: **252**（環境変数 `IPO_LOOKBACK_DAYS`）
- 流動性判定の直近営業日数: **60**（`LIQ_LOOKBACK_DAYS`）
- 流動性閾値: 中央値がこれ未満なら illiquid（環境変数 `LIQ_MIN_MEDIAN_TURNOVER_YEN`。**未設定時はコード上 20,000,000 円が既定**。運用手順では明示設定を求める場合がある）

---

### 2.3 指標算出の対象

指標は **equity_domestic_core**（二次ユニバースの core）に対して算出される。

日次運用では、月次で生成した core に**上場廃止銘柄の除外パッチ**を適用した CSVを入力に用いることがある。適用済み CSV は **`daily_universe_patch.yml`** が Actions cache に書き込み、**`daily.yml`** 側の **`resolve_core_csv`** が同一ルールで月次タグを解決したうえで cache から復元するか、候補が無ければ月次リリースの core にフォールバックする（**`daily.yml` 内では `patch_universe_daily` を実行しない**）。

---

## 3. 指標

以下はすべて **equity_domestic_core** の銘柄を対象とする。  
各小節の末尾に、**日次指標 CSV**（`compute_indicators_for_core` の出力）と**配布用 XLSX**（テンプレ v1.2 に `render_sheet` で流し込んだ列）の有無を記す。

**`date` 列とファイル名**: 出力ファイル名 `indicators_YYYYMMDD.csv` の `YYYYMMDD` は **run_date**。行の `date` も `run_date` 基準で算出し、run_date 未達（stale）銘柄は日次除外ポリシーに従って行を出力しない。

**stale 除外ポリシー（日次）**: `ensure_core_cache` で再試行後 stale が残っても、件数が閾値（既定 9 件）以下なら継続し、`_stale_exclusions.json` に当日除外コードを記録する。`compute_indicators_for_core` は **同一 run_date の除外集合のみ**を適用し、それ以外の stale 検出は失敗扱いにする。
**実行性能**: 日次指標算出は銘柄単位並列（ProcessPool）で実行する。並列化は性能目的のみで、算出式・欠損時契約・出力順（code昇順）は不変とする。

### 3.1 売買代金（turnover_yen）

**定義**: 終値 × 出来高（円建て近似の売買代金）。

**日次 CSV / 配布 XLSX**: CSV に出力あり / **v1.2 テンプレ列なし**（ユーザー向け表には出ない）

---

### 3.2 売買代金 z スコア（z_turnover_*）

**定義**: 売買代金の `log1p(売買代金)` を、直近の一定期間（窓）で標準化した値。  
**列名**: `z_turnover_{Z_LOOKBACK_DAYS}`（参照値では `z_turnover_60`）

**読み方**: 0 付近が通常水準。正が大きいほど出来高が多い方向、負が大きいほど少ない方向。

**日次 CSV / 配布 XLSX**: 両方あり。`render_sheet` の既定ソートは本列の**降順**（`config/render_sheet.yaml` の `sort_column`）。XLSX では 2 行目ラベル「Zscore」、**3 段カラースケール**（設計上 ±5 を目安とした式端点）が適用される。

---

### 3.3 売買代金の移動平均比（turnover_ma_ratio_*）

**定義**: 当日の売買代金（`turnover_yen` と同様に終値×出来高）を、**直近 `Z_LOOKBACK_DAYS` 営業日**の売買代金の**算術平均**で除した倍率。営業日アンカーおよび窓の切り方は **売買代金 z（3.2）と同一**で、当日を窓に含む。

**列名**: `turnover_ma_ratio_{Z_LOOKBACK_DAYS}`（参照値では `turnover_ma_ratio_60`）

**読み方**: 1.0 付近は直近平均に近い水準。1 を大きく上回ると当日の売買代金が直近平均より大きい。

**日次 CSV / 配布 XLSX**: CSV に出力あり / **v1.2 テンプレ列なし**（履歴不足などで z と同様に欠損しうる）

---

### 3.4 前営業日比騰落率（price_change_pct）

**定義**: 前営業日終値に対する当日終値の変化率（百分率）。\((当日終値 / 前営業日終値 - 1) \times 100\)。

**列名**: `price_change_pct`

**読み方**: 正は値上がり、負は値下がり。前日終値が 0、または終値が 2 本未満で取れない場合は欠損。

**日次 CSV / 配布 XLSX**: CSV に出力あり / **v1.2 テンプレ列なし**

---

### 3.5 相対力（RS・B方式）

**定義**: 銘柄の期間リターンからベンチマークの期間リターンを差し引いた値。  
**算出式**（概念）: RS = 銘柄の期間リターン − ベンチマークの期間リターン（`run_date` と `run_date` から T 営業日前の**日付アンカー**で評価）

**期間（窓）**: 参照値は 31・63・126・252 営業日（`RS_WINDOWS`）。  
**ベンチマーク**: TOPIX・日経平均のいずれか、または**両方**（`RS_BENCHMARK`、**既定は `BOTH`**）。  
**列名**: `rs{窓}_topix` / `rs{窓}_nikkei`（小文字の `topix` / `nikkei`）。

**読み方**: 正はベンチマークより相対的に強い、負は弱い。

**日次 CSV / 配布 XLSX**: 両方あり。**TOPIX 版シート**では TOPIX 基準の RS 列のみ、**日経平均版シート**では日経基準の RS 列のみが同じレイアウトで並ぶ（1 行目のグループ見出しのみ文言が異なる）。数値列に **3 段カラースケール**（式端点 −1 / 0 / 1）。

---

### 3.6 RS 加速（Short-term RS Acceleration）

**定義**: 短期 RS − 長期 RS（短期 31 営業日、長期 252 営業日、いずれも日付アンカー方式）。  
**列名**: `rs_acceleration_topix` / `rs_acceleration_nikkei`

**読み方**: 正は直近の相対強度が上向き、負は下向き。

**日次 CSV / 配布 XLSX**: 両方あり。2 行目ラベル「加速」。カラースケール対象（z 系列と同ブロックの設計）。

---

### 3.7 RS 加速 z スコア

**定義**: 短期 RS 加速を、**出来高 z と同じ窓**（`Z_LOOKBACK_DAYS`、参照 60 営業日）で日付アンカー窓の平均・標準偏差により標準化した値。  
**列名**: `rs_acceleration_zscore_topix` / `rs_acceleration_zscore_nikkei`

**読み方**: 0 付近が通常。正が大きいほど加速が顕著、負が大きいほど減速が顕著。

**日次 CSV / 配布 XLSX**: 両方あり。2 行目ラベル「加速Z」。カラースケール対象。

---

### 3.8 β調整 RS（Market-adjusted Excess Return）

**定義**: 期間累積リターンから、β×ベンチマーク累積リターンを差し引いた値。β 推定窓（126）・累積窓（252）はともに日付アンカー方式で評価。  
**列名**: `beta_adjusted_rs_topix` / `beta_adjusted_rs_nikkei`

**読み方**: 市場に連動する分を除いた銘柄固有寄与の強さの目安。

**日次 CSV / 配布 XLSX**: CSV に算出結果あり / **v1.2 テンプレ列なし**

---

### 3.9 情報比率（Information Ratio）

**定義**: 日次の（銘柄リターン − ベンチマークリターン）の平均を、その標準偏差で割った値。窓は参照値 63 営業日で、日付アンカー方式で切り出す。  
**列名**: `information_ratio_topix` / `information_ratio_nikkei`

**読み方**: 正が大きいほどベンチを安定的に上回る方向。振れ幅が大きいと絶対値は小さくなりやすい。

**日次 CSV / 配布 XLSX**: CSV に算出結果あり / **v1.2 テンプレ列なし**

---

### 3.10 価格挙動（candle_labels / price_text）

**概要**: 当日の OHLC から形状・サイズ・制限値幅への到達などを判定し、ラベル列と自然文列を生成する。

**列**: `candle_labels`（構造化ラベル）、`price_text`（表示用テキスト）

詳細は [OHLC 記述子仕様 v1.2（設計正本）](../OHLC_desripter_v1.2.md) を参照。

**日次 CSV / 配布 XLSX**: CSV では両列。XLSX では **`price_text` のみ**（列 H「日足形状」相当）。**部分文字列条件**によるセル塗り分け（陽線・陰線・S高・S安・構造要因疑い・レンジ0 等）がテンプレ側に定義されている。`candle_labels` は表には出さない。

---

### 3.11 外部リンク

`build_external_links` により、株探（概要・チャート・ニュース）、みんかぶ、バフェットコード、Yahoo! ファイナンスの URL を生成する。キーは [externalLink_v1.0.md](externalLink_v1.0.md) と整合。日次 CSV では `link_kabutan` 等の列名で出力される。

**日次 CSV / 配布 XLSX**: v1.2 テンプレに載るのは
**`link_kabutan`・`link_kabutan_chart`・`link_kabutan_news`・`link_buffett`**
の 4 列。セル表示は `config/render_sheet.yaml` の `link_label_map` に従い
（例: 概要 / チャート / ニュース / Bcode）、URL はハイパーリンク。
**みんかぶ・Yahoo は CSV には列があるが v1.2 シートには列がない**。

---

### 3.12 イベント要因・ニュース列（日次拡張）

日次パイプラインで列を拡張した CSV をレンダー入力に使う場合がある。

- `event_cause_type`（`A` / `B` / `C` 等）
- `event_news_{1,2,3}_title` / `event_news_{1,2,3}_url`

ルール（v1.0 以来の整理）:

- 対象外銘柄は欠損
- タイプ C ではタイトルに「材料不明・需給起因疑い」等を入れ URL が空の場合がある

**日次 CSV / 配布 XLSX**: テンプレには **`event_news_1_title`〜`event_news_3_title`** のみ。URL 列は画面上に専用列として出さず、`hyperlink_source_map` により**タイトル文字列にハイパーリンクを埋め込む**。`event_cause_type` は**テンプレ列なし**。

---

### 3.13 監査用（n_bars_used）

**定義**: 指標算出に用いた銘柄側のバー数。

**日次 CSV / 配布 XLSX**: CSV のみ / **テンプレ列なし**

---

## 4. ユーザー向け表示の整理（日次 XLSX v1.2）

本章は [indicators_template_v1.2_design.md](indicators_template_v1.2_design.md) の機械可読ヘッダー（3 行目）および 1〜2 行目の人向けラベルに基づく。配布ブックは **TOPIX 版**・**日経平均版**のデータシートが**同型**で、RS 系の**列名（機械キー）だけ**がベンチマークごとに異なる。

### 4.1 エンドユーザー向けスプレッドシートに**表示される**項目

| 機械列名（CSV ヘッダーと一致） | ユーザーへの見え方（要約） |
| ------------------------------ | -------------------------- |
| `date` | **A 列**。列幅が極めて狭く、実質ほぼ非表示に近いが、分析日が入る。 |
| `code` | 銘柄コード（2 行目「コード」）。条件付き書式でサンプル行のみ強調のルールがテンプレに残っている場合がある（全行展開は設計書参照）。 |
| `name` | 銘柄名。 |
| `link_kabutan` | 表示ラベル「概要」＋株探 URL のハイパーリンク。 |
| `link_kabutan_chart` | 「チャート」＋ハイパーリンク。 |
| `link_kabutan_news` | 「ニュース」＋ハイパーリンク。 |
| `link_buffett` | 「Bcode」等（`link_label_map` 準拠）＋ハイパーリンク。 |
| `price_text` | 当日の価格挙動の自然文（2 行目は当日の説明用）。**キーワード条件**による背景色・文字色。 |
| `z_turnover_*` | 売買代金 z（2 行目「Zscore」）。**カラースケール**。 |
| `rs_acceleration_zscore_topix` または `rs_acceleration_zscore_nikkei` | 「加速Z」。カラースケール。 |
| `rs_acceleration_topix` または `rs_acceleration_nikkei` | 「加速」。カラースケール。 |
| `rs31_*`〜`rs252_*`（シートに応じて topix または nikkei） | 「31日」「63日」「126日」「252日」。カラースケール。 |
| `event_news_1_title`〜`event_news_3_title` | 1 行目グループ「売買代金急増　要因ニュース候補（β）」下の「第一候補」「第二候補」「第三候補」。URL はタイトルに埋め込み。 |

**README シート**: 利用上の注意・著作権などの**固定文**（データ流し込み対象外）。

**ウィンドウ枠**: `H4` 固定により、横スクロール時も **A〜G**（日付・コード・銘柄・リンク列）が固定表示される。

---

### 4.2 算出されるが、v1.2 ユーザー向け表には**出ない**項目

| 種別 | 例 |
| ---- | -- |
| パイプライン・ユニバースの内部区分 | `universe_primary`、`ipo` / `illiquid` / `core`、JPX 生データの列 |
| CSV のみの数値列 | `turnover_yen`、`turnover_ma_ratio_*`、`price_change_pct`、`beta_adjusted_rs_*`、`information_ratio_*`、`n_bars_used` |
| CSV のみのテキスト列 | `candle_labels` |
| CSV にあるがテンプレに列がないリンク | `link_minkabu`、`link_yahoo` |
| レンダーでタイトルに埋め込むため**専用列として表示しない** URL | `event_news_*_url` |
| 分類メタデータ | `event_cause_type` |

これらは**調査・再現性・将来の列追加**のために CSV に残る場合があるが、現行の配布 XLSX では列が割り当てられていない。

---

### 4.3 設計書との対応

条件付き書式の sqref・優先度、ヘッダー結合範囲、`headerAnchor` のブック単位定義など、**ユーザー向け表の見た目の説明**は [indicators_template_v1.2_design.md](indicators_template_v1.2_design.md) とテンプレート実体（`config/templates/indicators_template_v1.2.xlsx`）に合わせる。

---

## 5. パラメータ一覧（参照値）

| パラメータ | 参照値 | 備考 |
| ---------- | ------ | ---- |
| IPO 判定に必要な営業日数 | 252 | `IPO_LOOKBACK_DAYS` |
| 流動性判定の直近営業日数 | 60 | `LIQ_LOOKBACK_DAYS` |
| 流動性閾値（円） | 20,000,000 | `LIQ_MIN_MEDIAN_TURNOVER_YEN`（未設定時のコード既定。運用で上書き可） |
| 出来高 z の窓 | 60 営業日 | `Z_LOOKBACK_DAYS`。RS 加速 z の標準化窓にも同じ値を使用 |
| RS の期間 | 31, 63, 126, 252 営業日 | `RS_WINDOWS` |
| RS のベンチマーク | TOPIX・日経 **両方**（既定） | `RS_BENCHMARK` = `TOPIX` / `NIKKEI` / `BOTH` |
| β 推定窓 | 126 営業日 | コード内固定 |
| β 調整 RS の累積期間 | 252 営業日 | コード内固定 |
| 情報比率の窓 | 63 営業日 | コード内固定 |
| 短期 RS（加速用） | 31 営業日 | コード内固定 |
| 長期 RS（加速用） | 252 営業日 | コード内固定 |

---

## 6. データフロー概要

1. JPX 銘柄一覧 Excel を取得 → 一次ユニバース（7 分類）を生成  
2. equity_domestic に株価キャッシュ取得・流動性判定を適用 → `ipo` / `illiquid` / `core` に分割  
3. equity_domestic_core に対して日次で指標を算出（CSV 出力）  
4. 必要に応じ上場廃止除外済み core を入力に用いる  
5. 任意の列拡張（イベント・ニュース）を経て、`render_sheet` で v1.2 テンプレに流し込み配布  

---

## 7. 更新履歴

| バージョン | 日付 | 内容 |
| ---------- | ---- | ---- |
| 1.0 | 2025-03-01 | 初版（アーカイブ: [../archive/universe_and_indicators_v1.0.md](../archive/universe_and_indicators_v1.0.md)） |
| 1.1 | 2026-03-28 | 一次ユニバースの実装どおりの判定（完全一致／部分一致）を反映。`LIQ_MIN` の既定値、`RS_BENCHMARK` 既定、日次 CSV と v1.2 XLSX の表示分離を追加。誤記「日次レポートのは」を修正相当として整理 |
| 1.2 | 2026-04-20 | 売買代金の移動平均比（`turnover_ma_ratio_*`）と前営業日比騰落率（`price_change_pct`）を追加。アーカイブ: [../archive/universe_and_indicators_v1.1.md](../archive/universe_and_indicators_v1.1.md) |

---

## 8. 今後の更新ガイドライン

- ユニバース区分の追加・変更 → 第2章と実装を同期  
- 指標の追加・削除・定義変更 → 第3章・第5章を更新。テンプレ列が変わる場合は第4章と [indicators_template_v1.2_design.md](indicators_template_v1.2_design.md) を同期  
- パラメータ参照値の変更 → 第5章を更新  
- 実装変更と同時の更新を推奨する  
