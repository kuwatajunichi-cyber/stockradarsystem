# Workflow Preflight Contract

## 目的

品質検査に失敗した変更を本処理へ流入させない。

## 契約

- 本番系workflowは、共通 preflight を通過しない限り本処理ジョブを起動しない。
- preflight は最低限 `lint`, `type check`, `contract smoke`, `workflow lint` を含む。
- preflight 失敗時は fail-fast し、後続ジョブは `needs` で抑止される。

## 実装原則

- 品質ゲート定義は再利用可能な共通workflowへ集約する。
- 各運用workflowは共通preflightを参照し、重複定義を避ける。

## 検証

- preflight intentionally-fail テストで本体起動抑止を確認する。
- actionlint/shellcheck でworkflow記述品質を継続監視する。
