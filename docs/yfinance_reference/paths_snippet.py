"""
ティッカー変換・CSV 銘柄読み込みのスニペット（スタンドアロン）。

他プロジェクトにコピーしてそのまま使える。stockradar に依存しない。
"""
from pathlib import Path

import pandas as pd


def ticker_for_code(code: str) -> str:
    """日本株の Yahoo ティッカー（例: 7203 -> 7203.T）を返す。"""
    return f"{code}.T"


def load_codes_from_csv(path: Path) -> list[str]:
    """
    CSV から code 列を読み込み、銘柄コードのリストを返す。

    Raises:
        ValueError: code 列が存在しない場合
    """
    df = pd.read_csv(path)
    if "code" not in df.columns:
        raise ValueError(f"入力CSVに code 列がありません: {path}")
    return [str(c).strip() for c in df["code"].dropna() if str(c).strip()]
