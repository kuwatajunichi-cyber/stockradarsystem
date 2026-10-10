# Web Awesome 表層デザイン評価プロトタイプ

本番Web UIの機能・DOM・表示内容・グラフ実装を変更せず、UIライブラリの表層だけを比較する独立プロトタイプです。

## 比較ページ

ヘッダーの「UIライブラリ」で切り替えます。いずれも同じ本番画面です。

| ライブラリ | URL |
| --- | --- |
| Web Awesome 3.14.0 | http://127.0.0.1:5173/ |
| Spectrum Web Components 1.11.2 | http://127.0.0.1:5173/spectrum/ |
| UI5 Web Components 2.26.0 | http://127.0.0.1:5173/ui5/ |
| Vaadin 24.4.0 | http://127.0.0.1:5173/vaadin/ |
| Lion 0.21.1 | http://127.0.0.1:5173/lion/ |

Lionは視覚テーマを持たない白ラベル部品です。タブは `lion-tabs` を使い、ページ配色だけ評価用にINGオレンジで着せています。他の4つは各ライブラリのダークテーマを使います。

## 同一性の範囲

- `workers/web-ui-static/assets/index.html` を同期し、評価用アセット参照だけを差し替えます。
- 本番 `app.js` と `styles.css` をバイト単位でコピーして使用します。
- 表、ソート、数値フィルター、お気に入り、列設定、タブ操作、スプリッター、チャート描画は本番 `app.js` の実装です。
- ライブラリのタブは本番のタブボタンへクリックを委譲し、URL解決は再実装しません。
- 本番API、BFF、Supabase、R2には接続しません。表示データは評価用の固定データで、投資助言ではありません。

本番Web UIとPhase 5のgate statusは変更しません。`live_gate_5d` は開いたままです。

## 実行

```bash
cd prototypes/web-ui-webawesome
npm install
npm run dev
```

ビルド:

```bash
npm run build
npm run preview
```

`dev` と `build` は、実行前に本番アセットを自動同期します。依存ファイルはViteがローカルへバンドルするため、実行時にCDNを参照しません。
