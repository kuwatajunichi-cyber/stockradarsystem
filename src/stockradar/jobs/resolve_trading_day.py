"""
営業日判定ジョブ（Job1）。

Asia/Tokyo基準で run_date を決定し、東証営業日（XTKS）か判定する。
休場なら以降ジョブをスキップ（success扱い）。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

import pytz
from exchange_calendars import get_calendar

CALENDAR_NAME = "XTKS"  # 東京証券取引所


def resolve_trading_day(run_date: date | None = None) -> tuple[date, bool]:
    """
    営業日を判定する。

    Args:
        run_date: 判定対象日（None時はAsia/Tokyoの今日）

    Returns:
        (run_date, is_open): run_date（YYYY-MM-DD形式の日付）、is_open（営業日ならTrue）
    """
    if run_date is None:
        # Asia/Tokyoの現在日時を取得
        tz = pytz.timezone("Asia/Tokyo")
        now = datetime.now(tz)
        run_date = now.date()

    cal = get_calendar(CALENDAR_NAME)
    is_open = cal.is_session(run_date)

    return run_date, is_open


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Resolve trading day and check if market is open.")
    parser.add_argument(
        "--date",
        type=str,
        help="判定対象日（YYYY-MM-DD形式。省略時はAsia/Tokyoの今日）",
    )
    args = parser.parse_args(argv)

    if args.date:
        try:
            run_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"エラー: 日付形式が不正です: {args.date} (期待: YYYY-MM-DD)", file=sys.stderr)
            sys.exit(1)
    else:
        run_date = None

    try:
        run_date, is_open = resolve_trading_day(run_date)
        print(f"run_date={run_date.isoformat()}")
        print(f"is_open={is_open}")
        if not is_open:
            print("休場日のため、以降のジョブをスキップします。", file=sys.stderr)
            sys.exit(0)  # success扱い
    except Exception as e:
        print(f"エラー: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
