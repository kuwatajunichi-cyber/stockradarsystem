# OHLC Descriptor v1.2

> **設計正本**（`docs/` 直下）: ローソク形状・`candle_labels` / `price_text` の判定規則。実装は `src/stockradar/utils/candle_descriptor.py`。制限値幅は [JPX_limitTable.md](JPX_limitTable.md) と `config/jpx_limit_table.yaml`。

## 目的

出来高zscoreが高い銘柄について、「一本足の価格挙動」と「需給構造の含意」を簡潔に説明するための **判定ルール→自然言語対応表（辞書）**。

* 対象：日足1本（OHLC、前日終値）
* 方針：

  * **サイズ（相対）** と **形状（比率）** を分離
  * **異常系は事前ラベルで優先処理**
  * 自然言語は簡潔・用語中心

---

## 1. 特徴量定義（OHLC→派生）

日 i の OHLC を O,H,L,C、前日終値を prevC とする。

## 1.1 True Range（TR）

* `TR = max(H-L, abs(H-prevC), abs(L-prevC))`
* prevCが無い場合は `TR = H-L`

## 1.2 ローソク基本量

* `B  = abs(C-O)`（実体）
* `U  = H - max(O,C)`（上ヒゲ）
* `D  = min(O,C) - L`（下ヒゲ）
* `dir = sign(C-O)`（陽/陰/同値）

## 1.3 比率

* `br = B/TR`
* `ur = U/TR`
* `dr = D/TR`

## 1.4 相対スケール

* `ATR = EMA(TR, N)`（基準ATRは「前日まで」の系列で計算）
* `sr = TR / ATR_前日`
* `q_sr = percentile_rank(sr over M)`

※ 基準ATRは各日付で「前日時点のATR」を使用する（当日のTRを含めない）。これにより窓・サイズの判定が明確になる。

---

## 2. 異常ラベル（優先・近似）

※ ここでの異常は「確定」ではなく **疑い（スクリーニング用シグナル）**。

追加特徴量（近似判定用）：

* `gap = O-prevC`
* `gap_atr = abs(gap)/ATR_前日`
* `gap_dir = sign(gap)`（上窓/下窓の方向）
* `close_pos = (C-L)/(H-L)`（H==Lは除外）
* `hit_high = (C==H)`、`hit_low = (C==L)`（近似）

## 2.1 制限値幅テーブルによる判定（v1.2追加）

JPX制限値幅テーブル（`JPX_limitTable.md`参照）を使用して、前日終値から制限値幅を取得し、S高・S安の疑いを判定する。

**制限値幅の計算**:

* 前日終値（prevC）から基準値段を判定
* 基準値段に対応する制限値幅を取得
* `limit_high = prevC + 制限値幅`
* `limit_low = prevC - 制限値幅`

**判定パターン（優先順位：下から順に優先）**:

|キー|判定条件|価格挙動|需給含意|
|---|---|---|---|
|`LIMIT_HIGH_TOUCH`|`H >= limit_high`|S高タッチ疑い|高値に制限値幅到達|
|`LIMIT_LOW_TOUCH`|`L <= limit_low`|S安タッチ疑い|安値に制限値幅到達|
|`LIMIT_HIGH_TOUCH_STUCK`|`H >= limit_high AND C >= limit_high`|S高タッチ後張付き疑い|高値到達後、終値も制限高値維持|
|`LIMIT_LOW_TOUCH_STUCK`|`L <= limit_low AND C <= limit_low`|S安タッチ後張付き疑い|安値到達後、終値も制限安値維持|
|`LIMIT_HIGH_OPEN_ONLY`|`H >= limit_high AND O >= limit_high AND C < limit_high`|S高寄天疑い|寄り付きで高値到達、終値は戻り|
|`LIMIT_LOW_OPEN_ONLY`|`L <= limit_low AND O <= limit_low AND C > limit_low`|S安寄底疑い|寄り付きで安値到達、終値は戻り|
|`LIMIT_HIGH_FULL_STUCK`|`H >= limit_high AND O >= limit_high AND C >= limit_high AND L >= limit_high`|S高完全張り付き疑い|OHLC全てが制限高値に到達|
|`LIMIT_LOW_FULL_STUCK`|`H <= limit_low AND O <= limit_low AND C <= limit_low AND L <= limit_low`|S安完全張り付き疑い|OHLC全てが制限安値に到達|

**優先順位**: 同時に複数の条件を満たす場合、**下のものほど優先**して表示される（最後にチェックしたものが優先）。

## 2.2 その他の異常ラベル

|キー|判定（推奨）|価格挙動|需給含意|
|-----------------|--------------------------------------------------------------------------------------------|---------------|-----------------------|
|`INVALID_TR0`|`TR == 0`（ただし制限値幅ラベルが既にある場合はスキップ）|レンジ0|約定停滞・特殊日|
|~~`INVALID_NAN`~~|~~欠損またはATR≈0~~|~~判定不能~~|~~データ確認要~~|
|`ACTION_SUSPECT`|`gap_atr>=5 OR abs(O-prevC)/prevC>=0.30`|構造要因疑い|企業イベント/制度要因の可能性（需給評価保留）|
|`SPLIT_CONFIRMED`|（任意）yfinance等で split 取得時|分割明示|価格水準の構造変化|
|`GAP_DOMINANT`|`gap_atr>=1.0 AND abs(O-prevC)/TR>=0.6`|ギャップ主導|寄りで需給決着寄り|

推奨優先度：**制限値幅ラベル** > `INVALID_*` > `SPLIT_CONFIRMED` > `ACTION_SUSPECT` > `GAP_DOMINANT`

**v1.2変更点**:

* 制限値幅テーブルを使ったS高・S安判定を追加
* S高・S安ラベルは`INVALID_TR0`（レンジ0）より優先
* `LIMIT_SUSPECT`ラベルは削除（制限値幅テーブルによる細分化された判定に置き換え）

---

## 3. サイズ（相対）

|キー|判定|出力語|需給含意|
|------------------|---------------------|------|-----------|
|`RANGE_VERY_LARGE`|`q_sr >= 0.95`|極大の|需給大変動|
|`RANGE_LARGE`|`0.85 <= q_sr < 0.95`|大きな|強い方向性または乱高下|
|`RANGE_NORMAL`|`0.40 <= q_sr < 0.85`|（表示省略）|平常域の消化|
|`RANGE_SMALL`|`0.15 <= q_sr < 0.40`|小さな|吸収・拮抗|
|`RANGE_VERY_SMALL`|`q_sr < 0.15`|極小の|強い拮抗|

※ `RANGE_NORMAL` はキーは保持するが `price_text` では表示しない。

---

## 4. 形状ラベル（構文ベース）

価格挙動は原則として

> **「窓・サイズ・ヒゲ・実体・方向」**

の形式で生成する。

* `[窓]` は **上窓つき／下窓つき** のみ。窓が無い場合は出力しない。
* `[サイズ]` は「極大の／大きな／小さな／極小の」。`RANGE_NORMAL` はサイズ語を出力しない。

合成形状（ハンマー等）は使用しない。

---

## 4.0 窓（先頭に付与・窓がある時だけ）

**v1.1変更点**: 判定方法を変更。ATR基準からOHLCの最高値・最低値の比較に変更。

|キー|判定（v1.1以降）|出力語|
|----------|-------------------------------------------|----|
|`GAP_UP`|`前日の最低値 > 当日の最高値`|上窓つき|
|`GAP_DOWN`|`前日の最高値 < 当日の最低値`|下窓つき|

**判定ロジック**:

1. 前日と当日それぞれで、OHLCの最低値と最高値を確認
2. 前日の最高値よりも当日の最低値の方が高い場合 → **下窓つき**（GAP_DOWN）
3. 前日の最低値よりも当日の最高値の方が低い場合 → **上窓つき**（GAP_UP）

※ ATRは判定基準から外す（v1.1変更）。

---

## 4.1 方向（末尾に付与）

|キー|判定|出力語|
|----------|-------|---|
|`DIR_BULL`|`C > O`|陽線|
|`DIR_BEAR`|`C < O`|陰線|

---

## 4.2 実体（ヒゲの後に配置）

|キー|判定|出力語|
|--------------------|-----------------------------------|---|
|`DOJI`|`br <= 0.10`|十字線|
|`BODY_MARUBOZU_LIKE`|`br >= 0.70 AND max(ur,dr) <= 0.15`|丸坊主|
|`BODY_LONG`|`br >= 0.55`|長|
|`BODY_MIDDLE`|`0.25 < br < 0.55`|中|
|`BODY_SMALL`|`br <= 0.25`|短|

優先度：`DOJI` > `BODY_MARUBOZU_LIKE` > `BODY_LONG` > `BODY_SMALL` > `BODY_MIDDLE`

※ `DOJI`（十字線）の場合は方向語を付けない。`C == O` は十字線で吸収するため `DIR_FLAT` は使用しない。

---

## 4.3 ヒゲ（実体の前に配置）

|キー|判定|出力語|
|--------------------|---------------------------|------|
|`WICK_BOTH_LONG`|`ur >= 0.45 AND dr >= 0.45`|長い上下ヒゲ|
|`WICK_BOTH_PRESENT`|`ur >= 0.25 AND dr >= 0.25`|上下ヒゲ|
|`WICK_UPPER_LONG`|`ur >= 0.45`|長い上ヒゲ|
|`WICK_LOWER_LONG`|`dr >= 0.45`|長い下ヒゲ|
|`WICK_UPPER_PRESENT`|`0.25 <= ur < 0.45`|上ヒゲ|
|`WICK_LOWER_PRESENT`|`0.25 <= dr < 0.45`|下ヒゲ|

優先順位：

1. `WICK_BOTH_LONG`
2. `WICK_BOTH_PRESENT`
3. 片側LONG
4. 片側PRESENT

---

## 5. 商いの説明（需給含意）

価格挙動とは別に簡潔に出力。

|条件|出力語|
|-------|-------|
|極大・大レンジ|需給大変動|
|小・極小レンジ|強い拮抗|
|長い上ヒゲ|上値供給優勢|
|長い下ヒゲ|下値吸収優勢|
|長い上下ヒゲ|結論なき乱高下|
|丸坊主|一方向需給|
|十字線|均衡|

複数該当時は優先度順に最大2語まで。

---

## 6. 出力

* `candle_labels`（ラベル文字列、カンマ区切り）
* `price_text`（例："S高タッチ疑い" / "極大の長い上ヒゲ陰線" / "丸坊主陽線" / "レンジ0"）
* `volume_text`（将来実装予定）

---

## 7. 閾値（デフォルト）

* N = 14 or 20（ATR計算期間）
* M = 252（短期63）（percentile_rank計算窓）
* `RANGE_LARGE` = 0.85
* `RANGE_VERY_LARGE` = 0.95
* `RANGE_SMALL` = 0.40未満
* `RANGE_VERY_SMALL` = 0.15未満
* `CONSOLIDATION` = `q_sr < 0.25 AND br < 0.35`
* `BODY_MARUBOZU_LIKE` = `br>=0.70 AND max(ur,dr)<=0.15`
* `BODY_LONG` = `br>=0.55`
* `DOJI` = `br<=0.10`
* `WICK_*_LONG` = 0.45
* `WICK_*_PRESENT` = 0.25
* `GAP_DOMINANT` = `abs(O-prevC)/ATR_前日 >= 1.0`
* `ACTION_SUSPECT` = `gap_atr>=5 OR abs(O-prevC)/prevC>=0.30`

---

## 8. 運用ルール

* 異常ラベル最優先（制限値幅ラベル > レンジ0 > その他）
* price_textは構文固定
* 断定語は使用しない
* 価格挙動と需給含意は分離

---

## 9. バージョン変更履歴

## 9.1 v1.2変更点（S高・S安判定の細分化）

**v1.1**: `LIMIT_SUSPECT`ラベルで制限級の張り付き/極端決着疑いを判定

**v1.2**: JPX制限値幅テーブルを使用した細分化された判定に変更

* 8つの判定パターンに細分化
* 制限値幅テーブル（`JPX_limitTable.md`）を参照して前日終値から制限値幅を取得
* S高・S安ラベルは`INVALID_TR0`（レンジ0）より優先
* 同時に複数の条件を満たす場合、下のものほど優先して表示

## 9.2 v1.1変更点まとめ

### 9.2.1 窓の判定方法変更

**v1.0**: `gap > 0 AND gap_atr >= 1.0`（ATR基準）

**v1.1**: OHLCの最高値・最低値の比較

* 前日の最高値 < 当日の最低値 → 下窓つき（GAP_DOWN）
* 前日の最低値 > 当日の最高値 → 上窓つき（GAP_UP）
* ATRは判定基準から除外

### 9.2.2 INVALID_NANの出力OFF

**v1.0**: ATRがNaNまたは0以下の場合に「判定不能」を出力

**v1.1**: INVALID_NANの出力を一旦OFF（無効化）

### 9.2.3 ATR計算の基準変更

**v1.0**: 各日付で「その日までのTR」で計算したATRを使用

**v1.1**: 各日付で「前日時点のATR」を使用（当日のTRを含めない）

* これにより、当日のgap_atr・srは前日までのボラティリティ基準で評価される
* 窓・サイズの判定が明確になる
