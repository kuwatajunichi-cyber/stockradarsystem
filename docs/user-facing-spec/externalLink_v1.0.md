# externalLink v1.0

前提：  
用途は「スクリーニング後に複数銘柄を高速確認するための外部リンク整備」。  
評価軸は ①役割の明確性 ②重複の少なさ ③URLのルール生成可否。

* * *

## 株探

### 役割

#### 一次確認ハブ（価格＋材料）

* ロウソク足・出来高を即表示

* 決算速報・材料履歴が時系列で整理

* 進捗率・コンセンサス比較が視覚的に分かりやすい

### 強み

* ログイン不要

* ページ遷移が速い

* 複数銘柄横断に最適

### 弱み

* 高度インジケータは限定的

* 財務深掘りには不十分

### URLフォーマット

基本ページ

<https://kabutan.jp/stock/?code={code}>

チャート直

<https://kabutan.jp/stock/chart?code={code}>

ニュース直

<https://kabutan.jp/stock/news?code={code}>

* * *

## みんかぶ

### 役割

#### 会社概要・四季報要約確認

* 主力事業の一文要約

* 四季報テキスト（簡易）

* 個人投資家予想

### 強み

* 日本語で即「何の会社か」分かる

* 文章情報が短い

### 弱み

* 投稿ノイズ

* チャートは弱い

### URLフォーマット

<https://minkabu.jp/stock/{code}>

* * *

## バフェット・コード

### 役割

#### 財務構造の検証

* ROE推移

* セグメント構造

* キャッシュフロー

* 長期財務可視化

### 強み

* 構造理解に強い

* IR BANKよりUI整理されている

### 弱み

* 速報用途ではない

* 一部機能は有料

### URLフォーマット

<https://www.buffett-code.com/company/{code}>

* * *

## Yahoo!ファイナンス

### 役割

#### 総合ポータル（仁義枠＋基準参照）

* yfinanceのデータソース

* 板・チャート・ニュース一覧

* コンセンサス

### 強み

* 総合性

* UI安定

* 日本株利用者の標準基準

### 弱み

* 各機能で専門サイトに劣る

* 差別化は弱い

### URLフォーマット

<https://finance.yahoo.co.jp/quote/{code}.T>

* * *

## 機能分離マップ

|サイト|主用途|フェーズ|重複度|
|--------|-----|----|---|
|株探|価格＋材料|初期判断|低|
|みんかぶ|事業理解|補助理解|中|
|バフェットコード|財務検証|深掘り|低|
|Yahoo|総合参照|補完|中|

* * *

## 推奨表示順（現在の設計思想に整合）

1. 株探（チャート＋材料）

2. みんかぶ（会社概要）

3. バフェットコード（財務）

4. Yahoo!ファイナンス（総合・仁義枠）

* * *

## ルールベースURL生成まとめ

kabutan_main  = f"<https://kabutan.jp/stock/?code={code}>"  
kabutan_chart = f"<https://kabutan.jp/stock/chart?code={code}>"
kabutan_news = f"<https://kabutan.jp/stock/news?code={code}>"
minkabu       = f"<https://minkabu.jp/stock/{code}>"  
buffett       = f"<https://www.buffett-code.com/company/{code}>"  
yahoo         = f"<https://finance.yahoo.co.jp/quote/{code}.T>"

すべて銘柄コード（4桁整数）から自動生成可能。
