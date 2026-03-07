"""CLI パースヘルパーのテスト。"""
from __future__ import annotations

import sys
from datetime import date
from io import StringIO
from unittest.mock import patch

import pytest

from stockradar.utils.cli_parse import parse_run_date_opt


def test_parse_run_date_opt_none_returns_none() -> None:
    """None を渡すと None を返す。"""
    assert parse_run_date_opt(None) is None


def test_parse_run_date_opt_empty_returns_none() -> None:
    """空文字を渡すと None を返す。"""
    assert parse_run_date_opt("") is None
    assert parse_run_date_opt("   ") is None


def test_parse_run_date_opt_valid_returns_date() -> None:
    """有効な YYYY-MM-DD を渡すと date を返す。"""
    assert parse_run_date_opt("2026-02-11") == date(2026, 2, 11)
    assert parse_run_date_opt("  2026-03-01  ") == date(2026, 3, 1)


def test_parse_run_date_opt_invalid_exits_with_1() -> None:
    """不正な形式を渡すと sys.exit(1) する。"""
    with patch.object(sys, "stderr", new_callable=StringIO):
        with pytest.raises(SystemExit) as exc_info:
            parse_run_date_opt("2026/02/11")
        assert exc_info.value.code == 1


def test_parse_run_date_opt_invalid_message_contains_expected() -> None:
    """不正時にエラーメッセージに期待形式が含まれる。"""
    stderr = StringIO()
    with patch.object(sys, "stderr", stderr):
        with pytest.raises(SystemExit):
            parse_run_date_opt("invalid", param_name="--run-date")
    assert "YYYY-MM-DD" in stderr.getvalue()
    assert "invalid" in stderr.getvalue()
