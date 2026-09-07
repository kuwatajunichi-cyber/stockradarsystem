"""CLI smoke: Track B mint redacts signed URL and fail-closes without fixture env."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_FIXTURE = {
    "object_key": "published/cli-demo.bin",
    "body": "hello-cli",
}


def test_cli_fake_unproven_without_allow_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIGNED_URL_FAKE", "1")
    monkeypatch.delenv("SIGNED_URL_MINT_ALLOW_FIXTURE", raising=False)
    fixture = tmp_path / "committed.json"
    fixture.write_text(json.dumps(_FIXTURE), encoding="utf-8")
    out_path = tmp_path / "grant.json"
    import scripts.storage.signed_url_mint_cli as mod

    code = mod.cmd_mint(
        mod.argparse.Namespace(
            request_id="cli-1",
            actor_ref="test",
            object_key="published/cli-demo.bin",
            source_table="",
            source_id="",
            operation="GetObject",
            ttl_seconds=300,
            entitlement_fixture="proven",
            fixture_committed_json=str(fixture),
            json_output=str(out_path),
        )
    )
    assert code == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["reason_code"] == "entitlement_unproven"
    assert not payload.get("signed_url")


def test_cli_fake_proven_with_allow_env_writes_url_only_to_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SIGNED_URL_FAKE", "1")
    monkeypatch.setenv("SIGNED_URL_MINT_ALLOW_FIXTURE", "1")
    fixture = tmp_path / "committed.json"
    fixture.write_text(json.dumps(_FIXTURE), encoding="utf-8")
    out_path = tmp_path / "grant.json"
    import scripts.storage.signed_url_mint_cli as mod

    code = mod.cmd_mint(
        mod.argparse.Namespace(
            request_id="cli-2",
            actor_ref="test",
            object_key="published/cli-demo.bin",
            source_table="",
            source_id="",
            operation="GetObject",
            ttl_seconds=300,
            entitlement_fixture="proven",
            fixture_committed_json=str(fixture),
            json_output=str(out_path),
        )
    )
    assert code == 0
    stdout = capsys.readouterr().out
    assert "X-Amz-Signature" not in stdout
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["mint_result"] == "issued"
    assert "r2.cloudflarestorage.com" in payload["signed_url"]
    public = json.loads(stdout.strip())
    assert "signed_url" not in public
    assert public["signed_url_present"] is True


def test_cli_rejects_put_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNED_URL_FAKE", "1")
    monkeypatch.setenv("SIGNED_URL_MINT_ALLOW_FIXTURE", "1")
    fixture = tmp_path / "committed.json"
    fixture.write_text(json.dumps(_FIXTURE), encoding="utf-8")
    out_path = tmp_path / "grant.json"
    import scripts.storage.signed_url_mint_cli as mod

    code = mod.cmd_mint(
        mod.argparse.Namespace(
            request_id="cli-3",
            actor_ref="test",
            object_key="published/cli-demo.bin",
            source_table="",
            source_id="",
            operation="PutObject",
            ttl_seconds=300,
            entitlement_fixture="proven",
            fixture_committed_json=str(fixture),
            json_output=str(out_path),
        )
    )
    assert code == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["reason_code"] == "operation_rejected"
