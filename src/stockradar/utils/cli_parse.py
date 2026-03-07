"""
CLI 引数パース用ユーティリティ。

--run-date 等の日付オプションを統一して扱う。
"""
from __future__ import annotations

import sys
from datetime import date


RUN_DATE_ERROR_MSG = "エラー: 日付形式が不正です: {value} (期待: YYYY-MM-DD)"


def parse_run_date_opt(value: str | None, param_name: str = "--run-date") -> date | None:
    """
    --run-date 相当のオプション値を date にパースする。

    Args:
        value: オプション文字列（None または空は None を返す）
        param_name: エラーメッセージ用のパラメータ名

    Returns:
        パース成功時は date。value が None/空の場合は None。

    Raises:
        SystemExit: パース失敗時に stderr にメッセージを出力して sys.exit(1)
    """
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        msg = f"エラー: {param_name} の形式が不正です: {value} (期待: YYYY-MM-DD)"
        print(msg, file=sys.stderr)
        sys.exit(1)
