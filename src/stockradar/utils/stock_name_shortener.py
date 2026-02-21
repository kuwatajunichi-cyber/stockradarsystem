"""
銘柄名の短縮処理。

_with_name.csv 出力時に jpx_list の銘柄名を短縮する。
2段階: ①半角変換 ②辞書参照変換
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# ①半角に変換する語（全角→半角カタカナ）
# 編集時は対応する半角文字列もセットで更新すること
# ---------------------------------------------------------------------------
_HALFWIDTH_REPLACEMENTS: dict[str, str] = {
    "ホールディングス": "ﾎｰﾙﾃﾞｨﾝｸﾞｽ",
    "グループ": "ｸﾞﾙｰﾌﾟ",
    "インターナショナル": "ｲﾝﾀｰﾅｼｮﾅﾙ",
    "コーポレーション": "ｺｰﾎﾟﾚｰｼｮﾝ",
}

# 英数字・全角スペースの半角変換用
_ZENKAKU_TO_HANKAKU = str.maketrans(
    "\u3000"  # 全角スペース
    + "０１２３４５６７８９"
    + "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    + "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    " "
    + "0123456789"
    + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    + "abcdefghijklmnopqrstuvwxyz",
)


# ---------------------------------------------------------------------------
# ②辞書参照で変換するマッピング（編集しやすいよう独立して定義）
# 初版1件。追加時はここにエントリを足す。
# ---------------------------------------------------------------------------
NAME_SHORTEN_DICT: dict[str, str] = {
    "エヌ・ティ・ティ・": "NTT",
}


def shorten_stock_name(name: str) -> str:
    """
    銘柄名を短縮する。

    ①以下を半角に変換: ホールディングス, グループ, インターナショナル,
      コーポレーション, 英数字, 全角スペース
    ②辞書（NAME_SHORTEN_DICT）を参照して置換

    Args:
        name: 元の銘柄名（jpx_list の銘柄名列）

    Returns:
        短縮後の銘柄名
    """
    if not name:
        return name

    # ①半角変換
    result = name
    for zen, han in _HALFWIDTH_REPLACEMENTS.items():
        result = result.replace(zen, han)
    result = result.translate(_ZENKAKU_TO_HANKAKU)

    # ②辞書参照で変換
    for pattern, replacement in NAME_SHORTEN_DICT.items():
        result = result.replace(pattern, replacement)

    return result
