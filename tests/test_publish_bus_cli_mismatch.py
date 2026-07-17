from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "scripts" / "storage") not in sys.path:
    sys.path.insert(0, str(_REPO / "scripts" / "storage"))

from stockradar.storage.supabase_client import FakeSupabaseControlAdapter
import publish_bus_cli


def _commit_args(**overrides: object) -> object:
    base = {
        "workflow": "daily.yml",
        "github_run_id": "100",
        "run_date": "2026-07-15",
        "logical_kind": "indicators_csv",
        "visibility": "work",
        "local_path": "",
        "filename": "indicators.csv",
        "content_type": None,
        "phase4_rollout_stage": "4c",
        "json_output": None,
    }
    base.update(overrides)

    class Args:
        pass

    args = Args()
    for key, value in base.items():
        setattr(args, key, value)
    return args


@pytest.fixture
def tmp_csv(tmp_path: Path) -> Path:
    path = tmp_path / "indicators.csv"
    path.write_text("code,value\n1,2\n", encoding="utf-8")
    return path


@pytest.mark.unit
def test_publish_mismatch_returns_exit_2_without_r2_put(tmp_csv: Path) -> None:
    fake = FakeSupabaseControlAdapter()
    run = fake.upsert_run(workflow="daily.yml", github_run_id=100, run_date="2026-07-15")
    from stockradar.storage.daily_publish_manifest import resolve_publish_object_key

    object_key = resolve_publish_object_key(
        run_date="2026-07-15",
        visibility="work",
        filename="indicators.csv",
    )
    pid = "pub-1"
    fake.publish_status[pid] = {
        "id": pid,
        "run_id": run["id"],
        "workflow": "daily.yml",
        "github_run_id": 100,
        "run_date": "2026-07-15",
        "logical_kind": "indicators_csv",
        "visibility": "work",
        "object_key": object_key,
        "manifest_object_key": "published/work/2026-07-15/manifest.json",
        "size_bytes": 999,
        "sha256": "deadbeef",
        "content_type": "text/csv",
        "status": "committed",
    }
    r2_mock = MagicMock()
    with patch.object(publish_bus_cli, "_adapter_supabase", return_value=fake):
        with patch.object(publish_bus_cli, "_r2", return_value=r2_mock):
            rc = publish_bus_cli.cmd_commit(_commit_args(local_path=str(tmp_csv)))
    assert rc == 2
    r2_mock.put_object.assert_not_called()


@pytest.mark.unit
def test_publish_idempotent_match_returns_exit_0(tmp_csv: Path) -> None:
    fake = FakeSupabaseControlAdapter()
    run = fake.upsert_run(workflow="daily.yml", github_run_id=100, run_date="2026-07-15")
    from stockradar.storage.daily_publish_manifest import resolve_publish_object_key
    from stockradar.utils.manifest import compute_sha256

    sha = compute_sha256(str(tmp_csv))
    size = tmp_csv.stat().st_size
    object_key = resolve_publish_object_key(
        run_date="2026-07-15",
        visibility="work",
        filename="indicators.csv",
    )
    pid = "pub-1"
    fake.publish_status[pid] = {
        "id": pid,
        "run_id": run["id"],
        "workflow": "daily.yml",
        "github_run_id": 100,
        "run_date": "2026-07-15",
        "logical_kind": "indicators_csv",
        "visibility": "work",
        "object_key": object_key,
        "manifest_object_key": "published/work/2026-07-15/manifest.json",
        "size_bytes": size,
        "sha256": sha,
        "content_type": "text/csv",
        "status": "committed",
    }
    r2_mock = MagicMock()
    with patch.object(publish_bus_cli, "_adapter_supabase", return_value=fake):
        with patch.object(publish_bus_cli, "_r2", return_value=r2_mock):
            rc = publish_bus_cli.cmd_commit(_commit_args(local_path=str(tmp_csv)))
    assert rc == 0