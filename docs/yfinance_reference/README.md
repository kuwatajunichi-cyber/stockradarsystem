# yfinance OHLCV 取得 — 実装参考（エージェント向け）

他リポジトリで **yfinance により日足 OHLCV（Open/High/Low/Close/Volume）を取得する機能** を実装する際の参考用です。このフォルダには stockradarsystem プロジェクトから抜粋したコードとスニペットを置いています。

> **注意**: この `docs/yfinance_reference/` 内のコピーは本番実装より更新が遅れることがあります。**挙動・契約の正は `src/stockradar/utils/yf_cache.py` および本番ジョブ**を参照してください（例: 日次 `_manifest.jsonl` とユニバース一括 `_manifest_universe.jsonl` の分離、`stale` / `insufficient` の区別）。

## 含まれるファイル

| ファイル | 説明 |
|----------|------|
| **yf_cache.py** | コア実装。1ティッカー取得・リトライ・キャッシュ/マニフェスト I/O・差分取得のロジック。**ここを最優先で参照すること。** |
| **fetch_yf_daily_for_universe.py** | 銘柄リストを入力にバッチで一括取得するジョブ。バッチ間スリープ・manifest による途中再開。 |
| **ensure_core_cache.py** | キャッシュが不足している銘柄だけ取得し、既存は差分更新するジョブ。`yf_cache.ensure_cache_with_incremental_fetch` の利用例。 |
| **config_snippet.py** | yfinance 用の設定のみ（環境変数 YF_* とキャッシュディレクトリ）。他プロジェクトではこの形で定数/設定に差し替え可能。 |
| **paths_snippet.py** | 日本株ティッカー変換（`7203` → `7203.T`）と CSV から銘柄コードを読む関数。他プロジェクトでそのまま or 簡略化して利用可能。 |

## 実装時のポイント（yfinance 仕様・落とし穴）

1. **`end` は exclusive**  
   `run_date` の日を含めたい場合は `end = run_date + 1日` で渡す（`yf_cache.py` 内コメント参照）。

2. **日本株などで `period` が空になることがある**  
   `t.history(period=period)` が空のときは、`start` / `end` を明示して `t.history(start=..., end=..., interval="1d", auto_adjust=True)` で再試行する（`yf_cache.py` および `fetch_yf_daily_for_universe.py` の該当箇所を参照）。

3. **必要な営業日数と period の対応**  
   1年で約245営業日しか返らないため、252日欲しい場合は `period="2y"` のように余裕を持たせる。`period_for_required_days()` のロジックを参照。

4. **複数ティッカー時は MultiIndex になることがある**  
   1銘柄ずつ取得する場合は通常の列名だが、`hist.columns` が MultiIndex の場合は `get_level_values(0)` で列名を揃える処理を入れている（両ファイル内を検索）。

5. **レート制限**  
   バッチ間でスリープ（例: 5秒）、1銘柄ずつリトライ＋バックオフ（例: 5, 15, 30秒）を推奨。`config_snippet.py` のデフォルト値を参考にできる。

## 他プロジェクトでの利用のしかた

- **コアロジックだけ欲しい場合**  
  `yf_cache.py` の `fetch_yf_data` と `period_for_required_days` をベースにし、`stockradar.config` の参照は自プロジェクトの設定や定数に差し替える。

- **銘柄リストの一括取得まで欲しい場合**  
  `fetch_yf_daily_for_universe.py` の `_fetch_one` と main のループを参考にし、入力 CSV パス・キャッシュディレクトリ・`ticker_for_code` を自プロジェクトに合わせる。

- **キャッシュ＋増分更新**  
  `ensure_cache_with_incremental_fetch`（`yf_cache.py`）の流れをそのまま参考にし、manifest のキー（`code` / `symbol`）やパスを自プロジェクトに統一する。

- **設定・ティッカー**  
  `config_snippet.py` と `paths_snippet.py` は依存がなく、そのままコピーして使える。必要に応じて環境変数名やデフォルト値だけ変更する。

## 元の場所（stockradarsystem）

- `src/stockradar/utils/yf_cache.py`
- `src/stockradar/jobs/fetch_yf_daily_for_universe.py`
- `src/stockradar/jobs/ensure_core_cache.py`
- 設定: `src/stockradar/config.py`（YF_* 関連）
- パス・ティッカー: `src/stockradar/utils/paths.py`

以上を、他リポジトリのエージェントが yfinance OHLCV 取得を実装するときの参照として利用してください。
