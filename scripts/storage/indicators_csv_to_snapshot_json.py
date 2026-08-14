"""Convert daily indicators CSV to derived snapshot JSON (Phase 4.5)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from stockradar.metrics.normalize_instrument_code import normalize_instrument_code
from stockradar.metrics.registry_spec import load_metric_set_spec


def indicators_csv_to_snapshot(csv_path: Path, metric_set_yaml: Path) -> dict[str, dict[str, object]]:
    spec = load_metric_set_spec(metric_set_yaml)
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype={"code": str})
    if "code" not in df.columns:
        raise ValueError("indicators CSV requires code column")
    missing_cols = [member.metric_key for member in spec.members if member.metric_key not in df.columns]
    if missing_cols:
        raise ValueError(f"indicators CSV missing catalog columns: {missing_cols}")
    out: dict[str, dict[str, object]] = {}
    for _, row in df.iterrows():
        code = normalize_instrument_code(str(row["code"]))
        values: dict[str, object] = {}
        for member in spec.members:
            col = member.metric_key
            if col not in df.columns:
                continue
            val = row[col]
            if pd.isna(val):
                values[col] = None
            elif member.value_type == "int":
                values[col] = int(val)
            elif member.value_type == "float":
                values[col] = float(val)
            else:
                values[col] = val
        out[code] = values
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Indicators CSV to snapshot JSON")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--metric-set-yaml", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    snapshot = indicators_csv_to_snapshot(Path(args.csv), Path(args.metric_set_yaml))
    Path(args.output).write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(snapshot)} instruments to {args.output}")


if __name__ == "__main__":
    main()
