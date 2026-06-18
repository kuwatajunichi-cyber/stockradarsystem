from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from stockradar.utils.manifest import create_manifest, verify_manifest

pytestmark = pytest.mark.unit


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_create_manifest_schema_version_and_nested_output(tmp_path: Path) -> None:
    output = tmp_path / "out.csv"
    _write_bytes(output, b"hello,world\n")
    inputs: list[dict[str, Any]] = [
        {"path": "in.csv", "size_bytes": 3, "sha256": "abc"},
    ]
    flags = {"fallback_used": False}

    manifest = create_manifest(
        output_path=output,
        run_id="run-001",
        inputs=inputs,
        flags_summary=flags,
        repo_root=tmp_path,
    )

    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == "run-001"
    assert manifest["inputs"] == inputs
    assert manifest["flags_summary"] == flags
    assert manifest["output"]["path"] == "out.csv"
    assert manifest["output"]["size_bytes"] == len(b"hello,world\n")
    assert len(manifest["output"]["sha256"]) == 64
    assert "created_at_utc" in manifest


def test_verify_manifest_ok(tmp_path: Path) -> None:
    output = tmp_path / "data.csv"
    _write_bytes(output, b"payload")
    manifest = create_manifest(output, "run-002", inputs=[], repo_root=tmp_path)
    manifest_path = tmp_path / "data.csv.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    ok, msg = verify_manifest(manifest_path, output)
    assert ok is True
    assert msg == ""


def test_verify_manifest_size_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "data.csv"
    _write_bytes(output, b"payload")
    manifest = create_manifest(output, "run-003", inputs=[], repo_root=tmp_path)
    manifest["output"]["size_bytes"] = 999
    manifest_path = tmp_path / "data.csv.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    ok, msg = verify_manifest(manifest_path, output)
    assert ok is False
    assert "size" in msg.lower() or "\u30b5\u30a4\u30ba" in msg


def test_verify_manifest_sha_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "data.csv"
    _write_bytes(output, b"payload")
    manifest = create_manifest(output, "run-004", inputs=[], repo_root=tmp_path)
    manifest["output"]["sha256"] = "0" * 64
    manifest_path = tmp_path / "data.csv.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    ok, msg = verify_manifest(manifest_path, output)
    assert ok is False
    assert "sha256" in msg.lower()


def test_verify_manifest_schema_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "data.csv"
    _write_bytes(output, b"payload")
    manifest = create_manifest(output, "run-005", inputs=[], repo_root=tmp_path)
    manifest["schema_version"] = 99
    manifest_path = tmp_path / "data.csv.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    ok, msg = verify_manifest(manifest_path, output)
    assert ok is False
    assert "schema_version" in msg
