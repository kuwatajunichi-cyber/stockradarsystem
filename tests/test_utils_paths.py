"""
paths ユーティリティのテスト。
ticker_for_code, load_codes_from_csv, find_latest_matching, find_latest_processed_jpx を検証する。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from stockradar.utils.paths import (
    find_latest_matching,
    find_latest_processed_jpx,
    load_codes_from_csv,
    ticker_for_code,
)


def test_ticker_for_code() -> None:
    """銘柄コードから Yahoo ティッカーが返ること。"""
    assert ticker_for_code("7203") == "7203.T"
    assert ticker_for_code("9984") == "9984.T"


def test_load_codes_from_csv_returns_codes(tmp_path: Path) -> None:
    """code 列ありの CSV から銘柄コードのリストが返ること。"""
    csv_path = tmp_path / "codes.csv"
    pd.DataFrame({"code": ["7203", "9984", "8035"]}).to_csv(csv_path, index=False)
    assert load_codes_from_csv(csv_path) == ["7203", "9984", "8035"]


def test_load_codes_from_csv_no_code_column_raises(tmp_path: Path) -> None:
    """code 列が無い CSV で ValueError になること。"""
    csv_path = tmp_path / "no_code.csv"
    pd.DataFrame({"name": ["A"], "value": [1]}).to_csv(csv_path, index=False)
    with pytest.raises(ValueError, match="code 列がありません"):
        load_codes_from_csv(csv_path)


def test_load_codes_from_csv_dropna_and_empty_stripped(tmp_path: Path) -> None:
    """空行・欠損は dropna で落ち、空白は strip されること。"""
    csv_path = tmp_path / "codes.csv"
    pd.DataFrame({
        "code": ["7203", None, "", "  9984  ", float("nan")],
    }).to_csv(csv_path, index=False)
    result = load_codes_from_csv(csv_path)
    # CSV 読み込みで数値列が float になるため str で "7203.0" 等になる
    assert result == ["7203.0", "9984.0"]


def test_find_latest_matching_returns_latest(tmp_path: Path) -> None:
    """パターンに合うディレクトリ内の最新ファイルパスが返ること。"""
    (tmp_path / "sets_20260101").mkdir()
    (tmp_path / "sets_20260201").mkdir()
    (tmp_path / "sets_20260101" / "equity_domestic.csv").write_text("dummy")
    (tmp_path / "sets_20260201" / "equity_domestic.csv").write_text("dummy")
    result = find_latest_matching(
        tmp_path,
        dir_pattern=r"sets_\d{8}",
        filename="equity_domestic.csv",
    )
    assert result is not None
    assert result == tmp_path / "sets_20260201" / "equity_domestic.csv"


def test_find_latest_matching_no_dir_returns_none(tmp_path: Path) -> None:
    """ベースディレクトリが無い場合は None。"""
    result = find_latest_matching(
        tmp_path / "nonexistent",
        dir_pattern=r"sets_\d{8}",
        filename="equity_domestic.csv",
    )
    assert result is None


def test_find_latest_matching_no_file_returns_none(tmp_path: Path) -> None:
    """パターンに合うディレクトリはあるが対象ファイルが無い場合は None。"""
    (tmp_path / "sets_20260101").mkdir()
    result = find_latest_matching(
        tmp_path,
        dir_pattern=r"sets_\d{8}",
        filename="equity_domestic.csv",
    )
    assert result is None


def test_find_latest_processed_jpx_returns_latest(tmp_path: Path) -> None:
    """data/processed/jpx 配下の jpx_list_*.csv の最新が返ること。"""
    processed = tmp_path / "data" / "processed" / "jpx"
    processed.mkdir(parents=True)
    (processed / "jpx_list_20260101.csv").write_text("dummy")
    (processed / "jpx_list_20260201.csv").write_text("dummy")
    result = find_latest_processed_jpx(tmp_path)
    assert result is not None
    assert result == processed / "jpx_list_20260201.csv"


def test_find_latest_processed_jpx_no_dir_returns_none(tmp_path: Path) -> None:
    """data/processed/jpx が無い場合は None。"""
    result = find_latest_processed_jpx(tmp_path)
    assert result is None


def test_find_latest_processed_jpx_no_csv_returns_none(tmp_path: Path) -> None:
    """ディレクトリはあるが jpx_list_*.csv が無い場合は None。"""
    (tmp_path / "data" / "processed" / "jpx").mkdir(parents=True)
    result = find_latest_processed_jpx(tmp_path)
    assert result is None
