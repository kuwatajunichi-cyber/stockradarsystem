# Web UI as-of プロトタイプ（叩き台）

**Track D ではない / 仕様正本ではない / live_gate_5d を閉じない**

これは localhost で叩く **ユーザビリティ／ビジネス要件の検証用叩き台** である。
`pr-5d-web-ui` / `live_gate_5d` / Phase 5 overall / Issue #93 を閉じる証拠には使わない。

## 本番隔離（P-ISO）

本節は実装・運用・レビューの **入出力契約** である。

### MUST

- **P-ISO-1 書き込み先.** `data/output/staging/web_ui_asof/` / `prototypes/web-ui-asof/` / `scripts/prototype_web_ui_asof/` のみ。
- **P-ISO-2 freeze 入力.** CSV と OHLC/指数 cache は読み専用。yfinance 禁止。足りなければ FAIL。
- **P-ISO-3 初期取得.** GET/コピーのみ。本番 pointer CAS を動かさない。
- **P-ISO-4 取得手段.** S3 GetObject / GHA artifact。mint CLI 禁止。
- **P-ISO-5 bind.** `127.0.0.1` のみ。
- **P-ISO-6 ゲート.** `pr-5d-web-ui` / `live_gate_5d` / Phase 5 overall / Issue #93 を閉じない。
- **P-ISO-7 式の置き場.** `rs_sma75_*` はfreeze 内だけ。
- **P-ISO-8 再凍結.** 専用 sqlite をローカルで作り直す。
- **P-ISO-9 CI.** fixture のみ。
- **P-ISO-10 作業セッション.** 同機で daily/monthly / put-immutable / upload を起動しない。

### MUST NOT

- **P-ISO-11..16** 本番配布・put-immutable・mint・0.0.0.0公開・助言UI・Web UI完了声明

## 使い方

```bash
# プロトタイプは asof/ 配下に複数日の YYYY-MM-DD.sqlite を置く（例: 3営業日）
python scripts/prototype_web_ui_asof/freeze.py --csv data/output/staging/web_ui_asof/indicators_event_enriched_YYYYMMDD.csv --as-of 2026-08-13 --out data/output/staging/web_ui_asof/asof/2026-08-13.sqlite
python scripts/prototype_web_ui_asof/freeze.py --csv data/output/staging/web_ui_asof/indicators_event_enriched_YYYYMMDD.csv --as-of 2026-08-14 --out data/output/staging/web_ui_asof/asof/2026-08-14.sqlite
python scripts/prototype_web_ui_asof/freeze.py --csv data/output/staging/web_ui_asof/indicators_event_enriched_YYYYMMDD.csv --as-of 2026-08-17 --out data/output/staging/web_ui_asof/asof/2026-08-17.sqlite
python scripts/prototype_web_ui_asof/serve.py --sqlite-dir data/output/staging/web_ui_asof/asof --port 8765
```
表示: http://127.0.0.1:8765/  
UI の「日付」プルダウンで as-of を切り替え（表・グラフ全体がその日時点）。

### 表示契約（叩き台）

- 表のデフォルト列: XLSX v1.4 相当（`link_buffett` 除外、`rs_sma75_*` 追加）。数値は `+0.0` / `±0`。
- 指標・価格情報は **cache を as-of で再計算**。ニュース等は CSV 由来（日付がずれる場合あり）。
- グラフ: 共通 60 営業日軸、目盛 [-1,1]、凡例、可視行のみ描画。
- 検証メモ: [VALIDATION_NOTES.md](VALIDATION_NOTES.md)
