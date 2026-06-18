from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from stockradar.jobs.update_kabutan_name_aliases import main


def _write_universe_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def test_update_alias_job_adds_and_reviews(tmp_path: Path, monkeypatch) -> None:
    core = tmp_path / "in" / "core.csv"
    illiquid = tmp_path / "in" / "illiquid.csv"
    ipo = tmp_path / "in" / "ipo.csv"
    _write_universe_csv(core, [{"code": "7203", "name": "トヨタ自動車"}])
    _write_universe_csv(illiquid, [{"code": "9432", "name": "NTT"}])
    _write_universe_csv(ipo, [{"code": "130A", "name": "Veritas In Silico"}])

    base_alias = tmp_path / "config" / "kabutan_name_aliases.yaml"
    base_alias.parent.mkdir(parents=True, exist_ok=True)
    base_alias.write_text("aliases_by_code:\n  '7203':\n    - トヨタ\n", encoding="utf-8")
    base_state = tmp_path / "cache" / "alias_state.json"
    base_state.parent.mkdir(parents=True, exist_ok=True)
    base_state.write_text(json.dumps({"aliases_by_code": {}}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        "stockradar.jobs.update_kabutan_name_aliases.fetch_kabutan_aliases_for_code",
        lambda code, **kwargs: {"7203": ["トヨタ自動車"], "9432": [], "130A": ["VIS"]}.get(code, []),
    )
    monkeypatch.setattr(
        "stockradar.jobs.update_kabutan_name_aliases.fetch_nikkei_aliases_for_code",
        lambda code, **kwargs: {"7203": ["トヨタ自動車"], "9432": [], "130A": []}.get(code, []),
    )
    monkeypatch.setattr(
        "stockradar.jobs.update_kabutan_name_aliases.fetch_tdnet_issuer_counts",
        lambda **kwargs: {"7203": {"トヨタ自動車": 3}},
    )

    out_alias = tmp_path / "out" / "kabutan_name_aliases.yaml"
    out_state = tmp_path / "out" / "alias_state.json"
    out_delta = tmp_path / "out" / "alias_delta.csv"
    out_summary = tmp_path / "out" / "alias_summary.json"
    main(
        [
            "--input-core",
            str(core),
            "--input-illiquid",
            str(illiquid),
            "--input-ipo",
            str(ipo),
            "--base-alias-yaml",
            str(base_alias),
            "--base-state-json",
            str(base_state),
            "--output-alias-yaml",
            str(out_alias),
            "--output-state-json",
            str(out_state),
            "--output-delta-csv",
            str(out_delta),
            "--output-summary-json",
            str(out_summary),
            "--run-date",
            "2026-03-07",
            "--media",
            "kabutan,nikkei,tdnet",
            "--sleep-ms",
            "0",
            "--sleep-jitter-ms",
            "0",
        ]
    )
    cfg = yaml.safe_load(out_alias.read_text(encoding="utf-8"))
    assert "aliases_by_code" in cfg
    assert "7203" in cfg["aliases_by_code"]
    assert "トヨタ自動車" in cfg["aliases_by_code"]["7203"]
    # low confidence (short ASCII) is review-only
    delta = pd.read_csv(out_delta)
    assert ((delta["code"].astype(str) == "130A") & (delta["action"] == "review")).any()
    summary = json.loads(out_summary.read_text(encoding="utf-8"))
    assert "media_stats" in summary
    assert "resolved_monthly_tag" in summary
    assert "upstream_run_id" in summary


def test_update_alias_job_is_deterministic(tmp_path: Path, monkeypatch) -> None:
    core = tmp_path / "in" / "core.csv"
    illiquid = tmp_path / "in" / "illiquid.csv"
    ipo = tmp_path / "in" / "ipo.csv"
    _write_universe_csv(core, [{"code": "7203", "name": "トヨタ自動車"}])
    _write_universe_csv(illiquid, [{"code": "9432", "name": "NTT"}])
    _write_universe_csv(ipo, [{"code": "130A", "name": "Veritas In Silico"}])

    base_alias = tmp_path / "config" / "kabutan_name_aliases.yaml"
    base_alias.parent.mkdir(parents=True, exist_ok=True)
    base_alias.write_text("aliases_by_code: {}\n", encoding="utf-8")
    base_state = tmp_path / "cache" / "alias_state.json"
    base_state.parent.mkdir(parents=True, exist_ok=True)
    base_state.write_text(json.dumps({"aliases_by_code": {}}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr("stockradar.jobs.update_kabutan_name_aliases.fetch_kabutan_aliases_for_code", lambda code, **kwargs: ["トヨタ自動車"])
    monkeypatch.setattr("stockradar.jobs.update_kabutan_name_aliases.fetch_nikkei_aliases_for_code", lambda code, **kwargs: ["トヨタ自動車"])
    monkeypatch.setattr("stockradar.jobs.update_kabutan_name_aliases.fetch_tdnet_issuer_counts", lambda **kwargs: {"7203": {"トヨタ自動車": 1}})

    out_alias1 = tmp_path / "out1" / "kabutan_name_aliases.yaml"
    out_state1 = tmp_path / "out1" / "alias_state.json"
    out_delta1 = tmp_path / "out1" / "alias_delta.csv"
    out_summary1 = tmp_path / "out1" / "alias_summary.json"
    args = [
        "--input-core",
        str(core),
        "--input-illiquid",
        str(illiquid),
        "--input-ipo",
        str(ipo),
        "--base-alias-yaml",
        str(base_alias),
        "--base-state-json",
        str(base_state),
        "--output-alias-yaml",
        str(out_alias1),
        "--output-state-json",
        str(out_state1),
        "--output-delta-csv",
        str(out_delta1),
        "--output-summary-json",
        str(out_summary1),
        "--run-date",
        "2026-03-07",
        "--media",
        "kabutan,nikkei,reuters,tdnet",
        "--sleep-ms",
        "0",
        "--sleep-jitter-ms",
        "0",
    ]
    main(args)

    out_alias2 = tmp_path / "out2" / "kabutan_name_aliases.yaml"
    out_state2 = tmp_path / "out2" / "alias_state.json"
    out_delta2 = tmp_path / "out2" / "alias_delta.csv"
    out_summary2 = tmp_path / "out2" / "alias_summary.json"
    args2 = list(args)
    args2[args2.index(str(out_alias1))] = str(out_alias2)
    args2[args2.index(str(out_state1))] = str(out_state2)
    args2[args2.index(str(out_delta1))] = str(out_delta2)
    args2[args2.index(str(out_summary1))] = str(out_summary2)
    main(args2)

    assert out_alias1.read_text(encoding="utf-8") == out_alias2.read_text(encoding="utf-8")


def test_update_alias_job_fail_on_anomaly(tmp_path: Path, monkeypatch) -> None:
    core = tmp_path / "in" / "core.csv"
    illiquid = tmp_path / "in" / "illiquid.csv"
    ipo = tmp_path / "in" / "ipo.csv"
    _write_universe_csv(core, [{"code": "7203", "name": "トヨタ自動車"}])
    _write_universe_csv(illiquid, [{"code": "9432", "name": "NTT"}])
    _write_universe_csv(ipo, [{"code": "130A", "name": "Veritas In Silico"}])

    base_alias = tmp_path / "config" / "kabutan_name_aliases.yaml"
    base_alias.parent.mkdir(parents=True, exist_ok=True)
    base_alias.write_text("aliases_by_code: {}\n", encoding="utf-8")
    base_state = tmp_path / "cache" / "alias_state.json"
    base_state.parent.mkdir(parents=True, exist_ok=True)
    base_state.write_text(json.dumps({"aliases_by_code": {}}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr("stockradar.jobs.update_kabutan_name_aliases.fetch_kabutan_aliases_for_code", lambda code, **kwargs: ["トヨタ自動車"])
    monkeypatch.setattr("stockradar.jobs.update_kabutan_name_aliases.fetch_nikkei_aliases_for_code", lambda code, **kwargs: ["トヨタ自動車"])
    monkeypatch.setattr("stockradar.jobs.update_kabutan_name_aliases.fetch_tdnet_issuer_counts", lambda **kwargs: {"7203": {"トヨタ自動車": 1}})

    out_alias = tmp_path / "out" / "kabutan_name_aliases.yaml"
    out_state = tmp_path / "out" / "alias_state.json"
    out_delta = tmp_path / "out" / "alias_delta.csv"
    out_summary = tmp_path / "out" / "alias_summary.json"
    try:
        main(
            [
                "--input-core",
                str(core),
                "--input-illiquid",
                str(illiquid),
                "--input-ipo",
                str(ipo),
                "--base-alias-yaml",
                str(base_alias),
                "--base-state-json",
                str(base_state),
                "--output-alias-yaml",
                str(out_alias),
                "--output-state-json",
                str(out_state),
                "--output-delta-csv",
                str(out_delta),
                "--output-summary-json",
                str(out_summary),
                "--run-date",
                "2026-03-07",
                "--media",
                "kabutan,nikkei,tdnet",
                "--sleep-ms",
                "0",
                "--sleep-jitter-ms",
                "0",
                "--fail-on-anomaly",
                "--added-aliases-max",
                "0",
            ]
        )
        raised = False
    except SystemExit as e:
        raised = True
        assert e.code == 1
    assert raised

