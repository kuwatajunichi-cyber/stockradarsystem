# dc-001: 信頼性・実体リスクに基づく調査ルート制御

## Status

Pre-ADR / Issue Candidate

## 背景

現行システムは、日本株の調査候補を定量指標で抽出するバッチパイプラインであり、投資助言・売買シグナル・個別銘柄の定性評価はスコープ外である。

現行ユニバースは、月次処理で次の順に構成される。

1. JPX 銘柄一覧から一次ユニバースを作る。
2. `equity_domestic` に株価キャッシュを取得する。
3. `ipo` / `illiquid` / `core` に排他的に二次分割する。
4. 月次成果物として `equity_domestic_ipo_with_name.csv`、`equity_domestic_illiquid_with_name.csv`、`equity_domestic_core_with_name.csv` を保存する。
5. 日次処理では、月次 core に上場廃止等の patched universe を適用した core CSV を解決し、指標算出・イベント要因拡張・XLSX レンダリングへ渡す。

この構成では、RS や出来高 zscore の上位に、通常分析の前に最低限の信頼性・企業実体を確認すべき銘柄が混ざることがある。問題は「低位株かどうか」ではなく、通常のモメンタム分析に入る前に調査順序を変えるべきかどうかである。

## 目的

この候補は「ボロ株」を機械的に投資不適格と判定するものではない。

目的は、調査候補抽出システムの範囲内で次を実現することである。

- 明らかに比較母集団へ含めるべきでない銘柄を、狭い条件で除外する。
- 投機対象として残す価値がある銘柄は、除外せず `PRIOR_REVIEW` として通常分析より前に構造確認へ回す。
- 初期調査コストを下げる一方で、小型成長株・材料株・研究開発型企業の探索機会を壊さない。
- 判定理由を flags / manifest / CSV 列で監査可能にし、静かに除外しない。

したがって、本候補は投資適格判定ではなく、**調査フロー制御レイヤー**として扱う。

## 用語

### `UNIVERSE_EXCLUDE`

月次 core の比較母集団から除外する状態。

除外条件は狭く保つ。理由は、除外が RS ランキングや downstream の候補母集団そのものを変えるためである。

想定理由:

- `INFORMATION_FAILURE`: 監査意見不表明、不適正意見、有報提出不能、重大な内部統制不備、重大な過年度修正、特別注意銘柄など、投資判断の基礎情報を信頼できない状態。
- `SUBSTANCE_FAILURE`: 売上・粗利益の実質消失、営業実体喪失、上場殻化、長期の継続企業疑義・債務超過など、会社としての継続性や営業実体が著しく損なわれている状態。
- `LISTING_FAILURE`: 整理銘柄、監理銘柄、上場廃止猶予、重大な上場維持基準違反など、市場制度上通常の分析対象として扱いにくい状態。

### `PRIOR_REVIEW`

ユニバースには残すが、通常分析より前に構造確認を行う状態。

`PRIOR_REVIEW` は危険銘柄ラベルではない。分析順序を「事業 -> 業績 -> 需給」から、「資本政策 -> 監査 -> 事業変遷 -> 通常分析」へ切り替えるためのフラグである。

想定フラグ:

- `MS_WARRANT`
- `GC_MATERIAL_UNCERTAINTY`
- `SHARE_COUNT_DOUBLED_5Y`
- `REVERSE_SPLIT_AND_DILUTION`
- `OPERATING_CF_NEGATIVE_3Y`
- `BUSINESS_PIVOT_REPEAT`
- `SEGMENT_CHANGE_REPEAT`
- `NEW_THEME_BUSINESS`
- `COMPANY_NAME_CHANGED`
- `AUDITOR_CHANGED`
- `USE_OF_PROCEEDS_CHANGED`

### `NORMAL`

追加の先行確認なしに、現行どおり通常分析へ進む状態。

## 現行パイプラインへの組み込み案

### 推奨位置

月次ユニバース更新時に、`equity_domestic` の二次分割へ入る前の純粋な判定レイヤーとして入れる。

論理順序:

1. JPX 銘柄一覧 -> `equity_domestic`
2. 公式・契約済み・手動投入などの補助データから信頼性・実体リスクを判定
3. `UNIVERSE_EXCLUDE` を月次 core 候補から除外し、除外台帳へ出力
4. 残った `equity_domestic` を現行どおり `ipo` / `illiquid` / `core` に分割
5. `PRIOR_REVIEW` は除外せず、core/ipo/illiquid のメタデータとして保持

除外を流動性判定より前に置く理由は、信頼性・企業実体の問題が流動性とは独立しているためである。大型株でも除外候補はあり、小型株でも通常分析対象は多数存在する。

### 日次 patched universe との関係

日次の `daily_universe_patch.yml` は、月次 core に対して上場廃止等の差分除外を適用する別レイヤーである。

本候補の v1 は月次判定を正系とし、日次では次の方針に留める。

- 日次指標算出の入力 core CSV は、既存の `resolve_core_csv` 契約を維持する。
- `UNIVERSE_EXCLUDE` の月中変化を日次で扱う場合は、既存 patched universe と同じく patch 層に乗せるが、v1 では実装しない。
- 将来の日次差分対象は、監理・整理銘柄、特別注意銘柄、監査意見、GC、MS ワラント、第三者割当などに限定して再検討する。

### 成果物への出し方

最小実装では、月次成果物の互換性を壊さない。

- 既存3CSVのファイル名・必須ヘッダーは維持する。
- `equity_domestic_core_with_name.csv` に追加列を出す場合は、downstream のテンプレ・リンク生成・名前エイリアス処理への影響をテストで固定する。
- 除外銘柄は、別成果物 `equity_domestic_excluded_with_reason.csv` または manifest の `flags_summary` に保存する。
- ユーザー向け XLSX へ表示する場合も、初期版は「状態」「理由」の短い列に限定する。

## データソース方針

本リポジトリのデータ取得方針に従い、取得手段は Adapter / Protocol で差し替え可能にする。

初期版で許容する入力:

- JPX の公式情報: 上場銘柄マスター、整理・監理・特別注意等の制度情報。
- EDINET または契約済みデータ: 有価証券報告書、監査報告書、売上高、粗利益、営業 CF、純資産、発行済株式数、セグメント情報、GC 記載、監査意見。
- TDnet は公式 API または許諾済み経路を優先する。公開閲覧サイトの常時クローリングを前提にしない。
- PoC では手動投入 JSONL / CSV を Fake source として使い、判定ロジックを先に固定する。

初期版で避けること:

- 規約・robots・再配布条件が不明なサイトの自動収集を前提にした設計。
- PDF 本文の曖昧な自然言語解析に依存した除外判定。
- 個別銘柄の主観的な「危険」評価を CSV に混ぜること。

## v1 スコープ案

### 入力特徴

- 監査意見
- GC 重要な不確実性
- 売上高
- 粗利益
- 営業 CF
- 純資産
- 発行済株式数
- MS ワラント / 新株予約権に相当する資本政策イベント
- 監査法人変更
- 社名変更
- セグメント数・セグメント変遷
- 新規事業参入
- JPX 制度ステータス

### 判定設計

- `UNIVERSE_EXCLUDE` は適合率を優先する。
- `PRIOR_REVIEW` は再現率を優先する。
- `UNIVERSE_EXCLUDE` と `PRIOR_REVIEW` は排他的に扱う。除外銘柄は先行精査対象に混ぜない。
- `PRIOR_REVIEW` 内の危険度スコア化は v1 では行わず、理由コードの集合だけを出す。

### 非スコープ

- 投資適格・不適格の判定。
- 売買推奨・売買シグナル。
- リアルタイム更新。
- Web UI / ダッシュボード。
- 優先株順位、資金使途評価、関連当事者取引、M&A 失敗履歴、経営者評価などの重い定性評価。

## 実装Issueへ分解する場合の候補

### Issue 1: 判定契約とテストデータを定義する

- `UniverseRiskStatus` 相当の列挙値を定義する。
- 入力 JSONL / CSV の最小スキーマを定義する。
- 代表ケースを unit test で固定する。
- 判定時点後の情報を混入させないバックテスト方針を明文化する。

### Issue 2: 月次パイプラインへ dry-run 出力を追加する

- 現行3CSVを変えず、まずは `universe_review_flags.csv` を追加出力する。
- `code`, `status`, `reason_codes`, `source_as_of`, `evidence_refs` を含める。
- manifest に件数サマリを出す。
- CI では Fake source のみで Secrets なしに通す。

### Issue 3: `UNIVERSE_EXCLUDE` の本適用をゲート付きで導入する

- 環境変数または設定で `report_only` / `apply_exclude` を切り替える。
- `apply_exclude` 時のみ二次分割前の入力から除外する。
- 除外台帳を月次 Release / R2 monthly snapshot に含める。
- `run_monthly.py` の検証ゲートに、除外台帳の存在・非空時の理由コード整合を追加する。

### Issue 4: `PRIOR_REVIEW` の downstream 表示を検討する

- 日次 indicators CSV へ `review_status` / `review_reason_codes` を join するか検討する。
- XLSX テンプレに表示する場合は、「状態」「理由」の短い列に留める。
- event cause enrichment と役割が重ならないよう、ニュース要因ではなく構造確認フラグとして扱う。

## 検証計画

過去時点データを使い、次の期待結果を固定する。

### 1. 明確な企業実体・情報信頼性の失敗

例:

- 監査意見不表明
- 不適正意見
- 特別注意銘柄
- 有報提出不能または重大遅延
- 長期の債務超過・GC
- 主力事業喪失

期待結果: `UNIVERSE_EXCLUDE`

### 2. 株主価値毀損リスクは高いが投機対象として残す銘柄

例:

- 反復 MS ワラント
- 赤字バイオ
- 新興テーマ転換企業
- 再建型小売
- 大幅希薄化を伴う資本政策

期待結果: `PRIOR_REVIEW`

### 3. 正常な小型・材料株

例:

- 小型だが黒字
- 低位だが希薄化なし
- 単一事業の一時的な材料化
- 本業と連続した新規事業参入

期待結果: `NORMAL`

評価指標:

- `UNIVERSE_EXCLUDE` の適合率
- `PRIOR_REVIEW` の再現率
- `NORMAL` の誤除外率
- 1 銘柄あたり初期調査時間
- 先行精査後に調査打切りとなった比率

## 未決事項

1. GC 重要な不確実性を何期継続で `UNIVERSE_EXCLUDE` とするか。
2. 債務超過と営業 CF 赤字の組み合わせをどの期間で見るか。
3. 売上・粗利益の「実質消失」をどう定義するか。
4. セグメント過多・事業転換頻度をどの規模指標で補正するか。
5. 社名変更・定款変更の回数をどの程度重視するか。
6. MS ワラントを単独で `PRIOR_REVIEW` とするか。
7. 外国会社、金融業、REIT、ETF/ETN を初期対象に含めるか。
8. 事業テーマ辞書をどこまで広げるか。
9. 株式分割を発行済株式数増加から除外する補正方法。
10. 優先株・転換社債・新株予約権を初期版でどこまで扱うか。
11. `PRIOR_REVIEW` 内で危険度を段階表示するか。
12. 月次 snapshot と日次 patch の責務境界をどこまで広げるか。

## ADR 化の条件

次を満たした時点で、正式 ADR へ昇格させる。

- 入力データの合法・安定な供給経路が最低1つ確定している。
- `UNIVERSE_EXCLUDE` の v1 条件が、過去データで十分に狭く運用できることを確認している。
- 現行3CSV、R2/Supabase monthly snapshot、daily patched core、render_sheet への影響範囲がテストで固定されている。
- report-only 期間の運用結果から、誤除外が許容範囲であることを確認している。

## 参照

- `docs/user-facing-spec/universe_and_indicators_v1.2.md`
- `docs/contracts/daily_replay_and_monthly_universe.md`
- `docs/decision-candidates/dc-006-external-ingestion-feasibility.md`
- `scripts/run_monthly.py`
- `src/stockradar/universe/jpx_primary.py`
- `src/stockradar/universe/equity_secondary.py`
