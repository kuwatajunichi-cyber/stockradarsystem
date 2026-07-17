from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "scripts" / "storage") not in sys.path:
    sys.path.insert(0, str(_REPO / "scripts" / "storage"))

from stockradar.storage.supabase_client import FakeSupabaseControlAdapter  # noqa: E402

import control_plane_cli  # noqa: E402


def _args(**overrides: object) -> object:
    base = {
        "stale_after_hours": 48.0,
        "dry_run": True,
        "fail_if_any": False,
        "workflow": None,
        "json_output": None,
    }
    base.update(overrides)

    class Args:
        pass

    args = Args()
    for key, value in base.items():
        setattr(args, key, value)
    return args


@pytest.mark.unit
def test_reconcile_dry_run_does_not_update_runs() -> None:
    fake = FakeSupabaseControlAdapter()
    fake.upsert_run(workflow="daily.yml", github_run_id=1, run_date="2026-07-01")
    fake.runs[("daily.yml", 1)]["started_at_utc"] = "2026-07-01T00:00:00+00:00"
    fake.update_run = MagicMock(side_effect=AssertionError("update_run must not be called"))  # type: ignore[method-assign]
    with patch.dict(os.environ, {"SUPABASE_CONTROL_FAKE": "1"}):
        with patch.object(control_plane_cli, "_adapter_from_env", return_value=fake):
            rc = control_plane_cli.cmd_reconcile_stale_runs(_args(dry_run=True))
    assert rc == 0


@pytest.mark.unit
def test_reconcile_fail_if_any_returns_2_on_dry_run() -> None:
    fake = FakeSupabaseControlAdapter()
    fake.upsert_run(workflow="daily.yml", github_run_id=1, run_date="2026-07-01")
    fake.runs[("daily.yml", 1)]["started_at_utc"] = "2026-07-01T00:00:00+00:00"
    with patch.dict(os.environ, {"SUPABASE_CONTROL_FAKE": "1"}):
        with patch.object(control_plane_cli, "_adapter_from_env", return_value=fake):
            rc = control_plane_cli.cmd_reconcile_stale_runs(_args(dry_run=True, fail_if_any=True))
    assert rc == 2
