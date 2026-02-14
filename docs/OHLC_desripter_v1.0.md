# 目的

出来高zscoreが高い銘柄について、「一本足の価格挙動」と「需給構造の含意」を簡潔に説明するための **判定ルール→自然言語対応表（辞書）**。

* 対象：日足1本（OHLC、前日終値）
* 方針：

  * **サイズ（相対）** と **形状（比率）** を分離
  * **異常系は事前ラベルで優先処理**
  * 自然言語は簡潔・用語中心

---

# 1. 特徴量定義（OHLC→派生）

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

* `ATR = EMA(TR, N)`
* `sr = TR / ATR`
* `q_sr = percentile_rank(sr over M)`

---

# 2. 異常ラベル（優先・近似）

※ ここでの異常は「確定」ではなく **疑い（スクリーニング用シグナル）**。

追加特徴量（近似判定用）：

* `gap = O-prevC`
* `gap_atr = abs(gap)/ATR`
* `gap_dir = sign(gap)`（上窓/下窓の方向）
* `close_pos = (C-L)/(H-L)`（H==Lは除外）
* `hit_high = (C==H)`、`hit_low = (C==L)`（近似）

| キー                | 判定（推奨）                                                                                       | 価格挙動            | 需給含意                    |
| ----------------- | -------------------------------------------------------------------------------------------- | --------------- | ----------------------- |
| `INVALID_TR0`     | `TR == 0`                                                                                    | レンジ0            | 約定停滞・特殊日                |
| `INVALID_NAN`     | 欠損またはATR≈0                                                                                   | 判定不能            | データ確認要                  |
| `LIMIT_SUSPECT`   | `(sr>=3 AND (hit_high OR hit_low)) OR (gap_atr>=2.5 AND (close_pos>=0.9 OR close_pos<=0.1))` | 制限級の張り付き/極端決着疑い | 需給が価格制約に達した可能性          |
| `ACTION_SUSPECT`  | `gap_atr>=5 OR abs(O-prevC)/prevC>=0.30`                                                     | 構造要因疑い          | 企業イベント/制度要因の可能性（需給評価保留） |
| `SPLIT_CONFIRMED` | （任意）yfinance等で split 取得時                                                                     | 分割明示            | 価格水準の構造変化               |
| `GAP_DOMINANT`    | `gap_atr>=1.0 AND abs(O-prevC)/TR>=0.6`                                                      | ギャップ主導          | 寄りで需給決着寄り               |

推奨優先度：`INVALID_*` > `SPLIT_CONFIRMED` > `ACTION_SUSPECT` > `LIMIT_SUSPECT` > `GAP_DOMINANT`

---

# 3. サイズ（相対）

| キー                 | 判定                    | 出力語    | 需給含意        |
| ------------------ | --------------------- | ------ | ----------- |
| `RANGE_VERY_LARGE` | `q_sr >= 0.95`        | 極大の    | 需給大変動       |
| `RANGE_LARGE`      | `0.85 <= q_sr < 0.95` | 大きな    | 強い方向性または乱高下 |
| `RANGE_NORMAL`     | `0.40 <= q_sr < 0.85` | （表示省略） | 平常域の消化      |
| `RANGE_SMALL`      | `0.15 <= q_sr < 0.40` | 小さな    | 吸収・拮抗       |
| `RANGE_VERY_SMALL` | `q_sr < 0.15`         | 極小の    | 強い拮抗        |

※ `RANGE_NORMAL` はキーは保持するが `price_text` では表示しない。

---

# 4. 形状ラベル（構文ベース）

価格挙動は原則として

> **「[窓][サイズ][ヒゲ][実体][方向]」**

の形式で生成する。

* `[窓]` は **上窓つき／下窓つき** のみ（前日終値 prevC とのギャップ方向）。窓が無い場合は出力しない。
* `[サイズ]` は「極大の／大きな／小さな／極小の」。`RANGE_NORMAL` はサイズ語を出力しない。

合成形状（ハンマー等）は使用しない。

---

## 4.0 窓（先頭に付与・窓がある時だけ）

| キー         | 判定                           | 出力語  |
| ---------- | ---------------------------- | ---- |
| `GAP_UP`   | `gap > 0 AND gap_atr >= 1.0` | 上窓つき |
| `GAP_DOWN` | `gap < 0 AND gap_atr >= 1.0` | 下窓つき |

※ `gap_atr` 閾値（既定=1.0）は調整可能。"窓"として出すのは十分な乖離がある場合のみ。

---

## 4.1 方向（末尾に付与）

| キー         | 判定      | 出力語 |
| ---------- | ------- | --- |
| `DIR_BULL` | `C > O` | 陽線  |
| `DIR_BEAR` | `C < O` | 陰線  |

---

## 4.2 実体（ヒゲの後に配置）

| キー                   | 判定                                  | 出力語 |
| -------------------- | ----------------------------------- | --- |
| `DOJI`               | `br <= 0.10`                        | 十字線 |
| `BODY_MARUBOZU_LIKE` | `br >= 0.70 AND max(ur,dr) <= 0.15` | 丸坊主 |
| `BODY_LONG`          | `br >= 0.55`                        | 長   |
| `BODY_MIDDLE`        | `0.25 < br < 0.55`                  | 中   |
| `BODY_SMALL`         | `br <= 0.25`                        | 短   |

優先度：`DOJI` > `BODY_MARUBOZU_LIKE` > `BODY_LONG` > `BODY_SMALL` > `BODY_MIDDLE`

※ `DOJI`（十字線）の場合は方向語を付けない。`C == O` は十字線で吸収するため `DIR_FLAT` は使用しない。

---

## 4.3 ヒゲ（実体の前に配置）

| キー                   | 判定                          | 出力語    |
| -------------------- | --------------------------- | ------ |
| `WICK_BOTH_LONG`     | `ur >= 0.45 AND dr >= 0.45` | 長い上下ヒゲ |
| `WICK_BOTH_PRESENT`  | `ur >= 0.25 AND dr >= 0.25` | 上下ヒゲ   |
| `WICK_UPPER_LONG`    | `ur >= 0.45`                | 長い上ヒゲ  |
| `WICK_LOWER_LONG`    | `dr >= 0.45`                | 長い下ヒゲ  |
| `WICK_UPPER_PRESENT` | `0.25 <= ur < 0.45`         | 上ヒゲ    |
| `WICK_LOWER_PRESENT` | `0.25 <= dr < 0.45`         | 下ヒゲ    |

優先順位：

1. `WICK_BOTH_LONG`
2. `WICK_BOTH_PRESENT`
3. 片側LONG
4. 片側PRESENT

---

# 5. 商いの説明（需給含意）

価格挙動とは別に簡潔に出力。

| 条件      | 出力語     |
| ------- | ------- |
| 極大・大レンジ | 需給大変動   |
| 小・極小レンジ | 強い拮抗    |
| 長い上ヒゲ   | 上値供給優勢  |
| 長い下ヒゲ   | 下値吸収優勢  |
| 長い上下ヒゲ  | 結論なき乱高下 |
| 丸坊主     | 一方向需給   |
| 十字線     | 均衡      |

複数該当時は優先度順に最大2語まで。

---

# 6. 出力

* `candle_labels`
* `price_text`（例："極大の長い上ヒゲ陰線" / "丸坊主陽線"）
* `volume_text`

---

# 7. 閾値（デフォルト）

* N = 14 or 20
* M = 252（短期63）
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
* `GAP_DOMINANT` = `abs(O-prevC)/ATR >= 1.0`

---

# 8. 運用ルール

* 異常ラベル最優先
* price_textは構文固定
* 断定語は使用しない
* 価格挙動と需給含意は分離
