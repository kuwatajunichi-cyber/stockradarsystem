"""Build synthetic XTKS caches + enriched CSV for prototype unit tests."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from stockradar.indicators.date_anchor import merged_close
from stockradar.indicators.rs import compute_rs_from_merged
from stockradar.indicators.zscore import compute_zscore_turnover_from_prepared
from stockradar.prototype_web_ui_asof.axis import xtks_axis_dates

AS_OF = date(2024, 12, 30)
ROOT = Path(__file__).resolve().parent


def _sessions_ending(as_of: date, n: int = 340) -> list[date]:
    import exchange_calendars as xcals

    cal = xcals.get_calendar("XTKS")
    start = as_of - timedelta(days=max(n * 3, 500))
    sessions = cal.sessions_in_range(str(start), str(as_of))
    dates = [ts.date() for ts in sessions if ts.date() <= as_of]
    if len(dates) < n:
        raise RuntimeError(f"need {n} sessions, got {len(dates)}")
    return dates[-n:]


def _synth_ohlc(dates: list[date], seed: int, start_px: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.012, size=len(dates))
    close = start_px * np.cumprod(1.0 + rets)
    vol = rng.integers(100_000, 900_000, size=len(dates)).astype(float)
    vol[-1] *= 3.5
    idx = pd.to_datetime(dates)
    return pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.01,
            "Low": close * 0.98,
            "Close": close,
            "Volume": vol,
        },
        index=idx,
    )


def build() -> Path:
    dates = _sessions_ending(AS_OF, 340)
    daily = ROOT / "yf_daily"
    index = ROOT / "yf_index"
    daily.mkdir(parents=True, exist_ok=True)
    index.mkdir(parents=True, exist_ok=True)

    topix = _synth_ohlc(dates, seed=1, start_px=2500.0)
    nikkei = _synth_ohlc(dates, seed=2, start_px=38000.0)
    s7203 = _synth_ohlc(dates, seed=3, start_px=2800.0)
    s9984 = _synth_ohlc(dates, seed=4, start_px=9000.0)
    axis = xtks_axis_dates(AS_OF, n=60)
    drop_day = axis[10]
    s9984 = s9984.drop(index=pd.Timestamp(drop_day), errors="ignore")

    topix.to_csv(index / "topix.csv")
    nikkei.to_csv(index / "nikkei.csv")
    s7203.to_csv(daily / "7203.csv")
    s9984.to_csv(daily / "9984.csv")

    rows = []
    for code, df in [("7203", s7203), ("9984", s9984)]:
        z = compute_zscore_turnover_from_prepared(df, 60, AS_OF)
        z_val = float(z.iloc[0]) if not z.empty and pd.notna(z.iloc[0]) else None
        merged = merged_close(
            pd.DataFrame({"Close": df["Close"]}),
            pd.DataFrame({"Close": topix["Close"]}),
        )
        rs = compute_rs_from_merged(merged, [31], AS_OF)
        rs31 = None
        if not rs.empty:
            v = rs.iloc[0].get("rs31")
            if v is not None and pd.notna(v):
                rs31 = float(v)
        rows.append(
            {
                "date": AS_OF.isoformat(),
                "code": code,
                "name": f"Fixture {code}",
                "z_turnover_60": z_val,
                "rs31_topix": rs31,
                "link_buffett": f"https://example.invalid/buffett/{code}",
                "research_prompt_block": f'{{"code":"{code}"}}',
            }
        )
    csv_path = ROOT / "indicators_event_enriched_fixture.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    (ROOT / "AS_OF.txt").write_text(AS_OF.isoformat() + "\n", encoding="utf-8")
    return csv_path


if __name__ == "__main__":
    print("built", build())
