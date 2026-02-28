# MVP Design Document v1.1

（v1.0 から更新。実装の命名規則に合わせた）

---

## 1. 本書の目的と位置づけ

本ドキュメントは、stockradarsystem MVP における**設計の単一の正本（Single Source of Truth）**として機能することを目的とする。

* 過去の rev02〜rev05（supplement 含む）で分散していた設計意図・仕様・判断を**完全統合**する
* 要約や抽象化は行わず、**実装判断に必要な情報をすべて含む**
* 本書以外の設計ドキュメントは、以後すべて参考資料または履歴扱いとする

---

## 2. MVPの定義

### 2.1 MVPで達成すること

* 日次で再現可能な株式ユニバース生成
* ユニバースを分母として用いた指標算出
* 成果物（CSV / XLSX / manifest）の自動生成
* GitHub Actions による完全自動実行

### 2.2 MVPでやらないこと

* 推奨・売買判断の提示
* スコアの最適化やランキング思想の確定
* UI / ダッシュボード提供
* 個別銘柄解釈やストーリー付与

---

## 3. 全体アーキテクチャ概要

### 3.1 レイヤ構造

1. Raw ingest layer
2. Universe layer
3. Indicator layer
4. Export layer
5. Publish / Archive layer

各レイヤは**再実行可能・副作用最小**を原則とする。

---

## 4. データ取得（Raw ingest）

### 4.1 対象市場・データ

* 市場：JPX（東証）
* 粒度：日足
* 主データ：

  * 終値
  * 始値
  * 高値
  * 安値
  * 出来高
  * 売買代金

### 4.2 rawデータの役割

* 下流工程の**唯一の事実ソース**
* universe・indicator は raw に対する純関数として設計

### 4.3 raw出力仕様（実装準拠）

* **JPX銘柄一覧**
  * raw: `data/raw/jpx/jpx_list_YYYYMMDD.xls` または `.xlsx`
  * processed: `data/processed/jpx/jpx_list_YYYYMMDD.csv`
* **日次指標**
  * `data/indicators/daily/indicators_YYYYMMDD.csv`
* 欠損行は保持（削除しない）

---

## 5. Universe設計

### 5.1 Universeの定義

Universe とは、
「**ある日付において評価対象とする銘柄集合**」を指す。

### 5.2 universe_memberships

* 銘柄 × 日付 の membership テーブルを生成
* True / False により包含関係を明示

### 5.3 分母固定の思想

* 指標比較は**同一分母**でのみ意味を持つ
* 日次で universe を確定し、indicator は universe を参照する

---

## 6. Indicator設計

### 6.1 指標カテゴリ

* 価格系
* 出来高系
* 相対指標（RS等）
* 正規化指標（z-score）

### 6.2 指標設計原則

* raw / universe を変更しない
* すべて派生データとして生成
* 欠損は NaN のまま保持

---

## 7. 成果物（Export）

### 7.1 CSV

* 全件マージCSV
* 日付を主キーとする縦持ち

### 7.2 XLSX

* シート分割
* フィルタ・ピボット前提

### 7.3 manifest

* 実行日時
* 対象日付
* 行数
* ハッシュ

---

## 8. 実行環境

### 8.1 ローカル

* Python + venv
* デバッグ・検証用途

### 8.2 GitHub Actions

* 本番実行
* 定期実行（cron）
* 手動実行（workflow_dispatch）

---

## 9. 運用原則

* 再実行性を最優先
* 状態を持たない
* ログは成果物と同列に扱う

---

## 10. 将来拡張との境界

* 追加指標
* universeの多重定義
* 外部データ統合

これらはすべて**MVP外**とし、Decision-CandidateまたはADRで管理する。

---

## 11. 本書の更新ルール

* v1.x：MVP範囲内の明確化・補足
* v2.0：設計思想が変わる場合のみ

---

（以上）
