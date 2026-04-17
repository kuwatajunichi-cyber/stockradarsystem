**Findings**

* High: 月次の本番エントリポイントは現状壊れています。monthly.yml (line 41) は scripts/run_monthly.py (line 41) を実行しますが、同スクリプトは初期化直後に無条件で sys.exit(EXIT_RUNTIME) しており、本処理 [1/5 ... 5/5] に到達しません。scripts/run_monthly.py (line 262)
* Medium-High: yfinance 取得は「古い残骸」ではなく、月次用と日次用の2系統を意図的に持っています。README.md (line 316) README.md (line 322) README.md (line 431) ただし両者は同じ data/cache/yf_daily 実体を共有しつつ、manifest 契約だけを分けています。fetch_yf_daily_for_universe.py (line 7) ensure_core_cache.py (line 72) そのため責務は「分離されている」が「独立していない」状態で、取得仕様や修正がドリフトしやすいです。yf_cache.py (line 180) yf_cache.py (line 308)
* Medium: 配布の degraded success 自体は設計意図と整合しています。README.md (line 128) ただし実装上は「最低1系統成功したか」を保証する責務がなく、upload_to_all_targets.py (line 43) は全ターゲット失敗でも 0 を返し得ます。upload_to_all_targets.py (line 178) 失敗可視化も warning ログ中心で、ワークフロー側で構造化判定しにくいです。daily.yml (line 663) monthly.yml (line 116)
* Medium: 配布レイヤの抽象化は途中までで止まっています。README はアップロード責務を upload_to_all_targets.py (line 1) に集約するとしていますが、実際の抽象 StorageAdapter は R2/Dropbox までで、Drive と GitHub Release は例外実装です。README.md (line 115) scripts/storage/base.py (line 10) さらに旧来の Drive 単独 CLI も残っており、配布責務の owner が1つに閉じていません。upload_to_work.py (line 26)
* Medium: レンダリングは「自動日次のローカル CSV モード」と「手動再実行の Drive 入力モード」の2モードが現役です。daily.yml (line 629) render_sheet.yml (line 84) 問題は2モードの存在ではなく、コードコメントが Drive モードを「将来削除予定」としており、実装と位置づけがずれていることです。render_sheet.py (line 381)
* Medium-Low: jobs 配下が「CLI エントリポイント」と「再利用される純ロジック」を混在させています。たとえば core_csv_selection.py (line 1) は pure logic ですが jobs 配下にあり、resolve_core_csv.py (line 20) から job モジュールとして参照されています。これは直ちに不具合ではありませんが、責務境界を曖昧にします。

**総評**

* 中核ドメイン層はおおむね整理されています。universe は銘柄集合の構成、indicators は算出、sources は外部取得、event_causes は拡張分析、utils は共通基盤、jobs は実行単位、scripts は運用インターフェース、.github/workflows はスケジューリングという骨格は読めます。
* MECE 性が崩れているのは主に「オーケストレーション層」と「公開/運用層」です。計算ロジックの重複よりも、実行経路・配布契約・手動運用経路の説明責任が分散しています。
* したがって、この repo の本質的な課題は「機能の重複」そのものより、「同じ目的を達成する複数経路を持つときに、どれが正系かを明確にしていない」点です。

**優先順位**

1. scripts/run_monthly.py (line 262) を修正し、月次の正系を復旧する。
2. 配布の成功契約を決める。  
   この repo の意図に沿うなら「GitHub Release のみ成功でも成功」とするか、「最低1系統成功で成功」とするかを明文化し、upload_to_all_targets.py (line 36) に機械可読な結果を返させる。
3. yfinance 二系統を正式アーキテクチャとして扱うなら、共有キャッシュの契約をさらに明示する。  
   たとえば「物理 cache は共有、意味論は manifest で分離」を README とコードコメントで統一し、共通取得ロジックの owner を yf_cache.py (line 208) に寄せる。
4. Render の Drive モードを残すなら、「将来削除予定」ではなく「手動 rerender 用のサポート経路」に表現を直す。
5. 配布アダプタ境界を整理する。  
   Drive/GitHub を抽象に含めるか、逆に「例外経路」として文書化するかを決める。

静的レビューのみで、ワークフロー実行や外部依存ジョブの動作確認まではしていません。
