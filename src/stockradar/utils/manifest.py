"""
成果物の隣に配置する manifest（レベル1）生成ユーティリティ。
標準ライブラリのみ使用（hashlib, json, pathlib）。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def compute_sha256(path: Path) -> str:
    """ファイルの SHA256 を計算する。"""
    try:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        raise RuntimeError(f"SHA256計算エラー ({path}): {e}") from e


def get_git_commit() -> str | None:
    """現在の git commit hash を取得。失敗時は None。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def create_manifest(
    output_path: Path,
    run_id: str,
    inputs: list[dict[str, Any]],
    flags_summary: dict[str, Any] | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    manifest オブジェクトを生成する。

    Args:
        output_path: 成果物ファイルのパス（repo相対パスとして記録）
        run_id: 実行ID
        inputs: 入力ファイル情報のリスト（各要素は path, size_bytes, sha256, source_url?, retrieved_at_utc?）
        flags_summary: フラグサマリ（fallback/override採用など）
        repo_root: リポジトリルート（未指定時は output_path から推測）

    Returns:
        manifest 辞書（schema_version=1）
    """
    if repo_root is None:
        repo_root = Path.cwd()
    output_path = Path(output_path).resolve()
    repo_root = Path(repo_root).resolve()

    try:
        rel_path = output_path.relative_to(repo_root)
    except ValueError:
        rel_path = Path(output_path.name)

    size_bytes = output_path.stat().st_size if output_path.exists() else 0
    try:
        sha256 = compute_sha256(output_path) if output_path.exists() and size_bytes > 0 else ""
    except Exception as e:
        raise RuntimeError(f"manifest生成時のSHA256計算エラー: {e}") from e

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": {
            "path": str(rel_path).replace("\\", "/"),
            "size_bytes": size_bytes,
            "sha256": sha256,
        },
        "inputs": inputs,
        "flags_summary": flags_summary or {},
        "code": {
            "git_commit": get_git_commit(),
        },
    }
    return manifest


def write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    """manifest を JSON ファイルに書き込む。"""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def verify_manifest(manifest_path: Path, output_path: Path) -> tuple[bool, str]:
    """
    manifest と実ファイルの整合性を検証する。

    Returns:
        (is_valid, error_message)
    """
    if not manifest_path.exists():
        return False, f"manifest が存在しません: {manifest_path}"

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"manifest の JSON パースに失敗: {e}"

    if manifest.get("schema_version") != 1:
        return False, f"schema_version が不正: {manifest.get('schema_version')}"

    if not output_path.exists():
        return False, f"成果物ファイルが存在しません: {output_path}"

    actual_size = output_path.stat().st_size
    expected_size = manifest.get("output", {}).get("size_bytes", 0)
    if actual_size != expected_size:
        return False, f"ファイルサイズ不一致: 実={actual_size} 期待={expected_size}"

    expected_sha256 = manifest.get("output", {}).get("sha256", "")
    if expected_sha256:
        actual_sha256 = compute_sha256(output_path)
        if actual_sha256 != expected_sha256:
            return False, f"SHA256不一致: 実={actual_sha256[:16]}... 期待={expected_sha256[:16]}..."

    return True, ""
