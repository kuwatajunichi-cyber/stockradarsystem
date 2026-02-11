"""
月次実行の統合スクリプト。

実行順序:
1. update_jpx_url_cache
2. fetch_jpx_list
3. build_universe_from_jpx
4. fetch_yf_daily_for_universe
5. split_equity_domestic_secondary

最終成果物（Latest 3CSV）を data/output/staging/<run_id>/ に出力し、
検証ゲート通過後に data/output/latest/LATEST_RUN_ID.txt を更新する。
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from stockradar.utils.manifest import (
    compute_sha256,
    create_manifest,
    verify_manifest,
    write_manifest,
)

RUN_ID_PREFIX = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
RUN_ID = f"{RUN_ID_PREFIX}_{uuid.uuid4().hex[:8]}"

STAGING_DIR = Path("data/output/staging") / RUN_ID
LATEST_DIR = Path("data/output/latest")
LATEST_POINTER = LATEST_DIR / "LATEST_RUN_ID.txt"
LOGS_DIR = Path("logs") / RUN_ID

LATEST_3CSV = [
    "equity_domestic_ipo_with_name.csv",
    "equity_domestic_illiquid_with_name.csv",
    "equity_domestic_core_with_name.csv",
]


def run_job(module: str, args: list[str] | None = None) -> tuple[int, str]:
    """ジョブを実行し、終了コードと出力を返す。"""
    cmd = [sys.executable, "-m", module] + (args or [])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        return result.returncode, result.stdout + result.stderr
    except Exception as e:
        return 1, str(e)


def copy_to_staging(source: Path, dest_name: str) -> Path:
    """ファイルを staging にコピーし、パスを返す。"""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    dest = STAGING_DIR / dest_name
    import shutil

    shutil.copy2(source, dest)
    return dest


def find_latest_secondary_outputs() -> dict[str, Path]:
    """最新の sets_secondary_* から 3CSV を探す。"""
    jpx_dir = Path("data/universe/jpx")
    if not jpx_dir.exists():
        return {}
    candidates = sorted(
        [d for d in jpx_dir.iterdir() if d.is_dir() and d.name.startswith("sets_secondary_")],
        reverse=True,
    )
    if not candidates:
        return {}
    latest_dir = candidates[0]
    out: dict[str, Path] = {}
    for name in LATEST_3CSV:
        path = latest_dir / name
        if path.exists():
            out[name] = path
    return out


def collect_inputs_for_manifest() -> list[dict[str, str]]:
    """manifest 用の入力情報を収集（簡易版）。"""
    inputs: list[dict[str, str]] = []
    # JPX processed CSV
    processed_dir = Path("data/processed/jpx")
    if processed_dir.exists():
        for p in sorted(processed_dir.glob("jpx_list_*.csv"), reverse=True):
            if p.exists():
                inputs.append(
                    {
                        "path": str(p.relative_to(Path.cwd())).replace("\\", "/"),
                        "size_bytes": str(p.stat().st_size),
                        "sha256": compute_sha256(p),
                    }
                )
                break
    return inputs


def verify_gate(staging_dir: Path) -> tuple[bool, list[str]]:
    """
    検証ゲート: 3CSV と manifest の存在・整合性を確認。

    Returns:
        (is_valid, error_messages)
    """
    errors: list[str] = []
    for csv_name in LATEST_3CSV:
        csv_path = staging_dir / csv_name
        manifest_path = staging_dir / f"{csv_name}.manifest.json"

        if not csv_path.exists():
            errors.append(f"CSV が存在しません: {csv_name}")
            continue

        size = csv_path.stat().st_size
        if size == 0:
            errors.append(f"CSV が空です: {csv_name}")
            continue

        # ヘッダ確認
        with open(csv_path, encoding="utf-8-sig") as f:
            header = f.readline().strip()
            if header != "code,name":
                errors.append(f"CSV ヘッダが不正: {csv_name} (期待='code,name', 実='{header}')")
            # 行数確認（ヘッダ除く）
            lines = sum(1 for _ in f)
            if lines < 10:
                errors.append(f"CSV 行数不足: {csv_name} (実={lines}, 最小=10)")

        # manifest 検証
        if not manifest_path.exists():
            errors.append(f"manifest が存在しません: {manifest_path.name}")
            continue

        is_valid, msg = verify_manifest(manifest_path, csv_path)
        if not is_valid:
            errors.append(f"manifest 検証失敗 ({csv_name}): {msg}")

    return len(errors) == 0, errors


def main() -> None:
    """メイン実行。"""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "run.log"

    def log(msg: str) -> None:
        print(msg, flush=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")

    log(f"=== 月次実行開始 run_id={RUN_ID} ===")

    # 1. update_jpx_url_cache
    log("1/5: update_jpx_url_cache")
    code, output = run_job("stockradar.jobs.update_jpx_url_cache")
    log(output)
    if code != 0:
        log(f"エラー: update_jpx_url_cache が失敗 (code={code})")
        sys.exit(1)

    # 2. fetch_jpx_list
    log("2/5: fetch_jpx_list")
    code, output = run_job("stockradar.jobs.fetch_jpx_list")
    log(output)
    if code != 0:
        log(f"エラー: fetch_jpx_list が失敗 (code={code})")
        sys.exit(1)

    # 3. build_universe_from_jpx
    log("3/5: build_universe_from_jpx")
    code, output = run_job("stockradar.jobs.build_universe_from_jpx")
    log(output)
    if code != 0:
        log(f"エラー: build_universe_from_jpx が失敗 (code={code})")
        sys.exit(1)

    # 4. fetch_yf_daily_for_universe
    log("4/5: fetch_yf_daily_for_universe")
    code, output = run_job("stockradar.jobs.fetch_yf_daily_for_universe")
    log(output)
    if code != 0:
        log(f"エラー: fetch_yf_daily_for_universe が失敗 (code={code})")
        sys.exit(1)

    # 5. split_equity_domestic_secondary
    log("5/5: split_equity_domestic_secondary")
    code, output = run_job("stockradar.jobs.split_equity_domestic_secondary")
    log(output)
    if code != 0:
        log(f"エラー: split_equity_domestic_secondary が失敗 (code={code})")
        sys.exit(1)

    # 最新の sets_secondary_* から 3CSV を staging にコピー
    log("成果物を staging にコピー中...")
    secondary_outputs = find_latest_secondary_outputs()
    if len(secondary_outputs) != 3:
        log(f"エラー: 3CSV が見つかりません (見つかった数={len(secondary_outputs)})")
        sys.exit(1)

    inputs = collect_inputs_for_manifest()
    flags_summary: dict[str, str] = {}

    for csv_name, source_path in secondary_outputs.items():
        dest_path = copy_to_staging(source_path, csv_name)
        log(f"コピー: {source_path} -> {dest_path}")

        # manifest 生成
        manifest = create_manifest(
            output_path=dest_path,
            run_id=RUN_ID,
            inputs=inputs,
            flags_summary=flags_summary,
            repo_root=Path.cwd(),
        )
        manifest_path = STAGING_DIR / f"{csv_name}.manifest.json"
        write_manifest(manifest_path, manifest)
        log(f"manifest 生成: {manifest_path}")

    # 検証ゲート
    log("検証ゲート実行中...")
    is_valid, errors = verify_gate(STAGING_DIR)
    if not is_valid:
        log("検証ゲート失敗:")
        for err in errors:
            log(f"  - {err}")
        sys.exit(1)

    # latest ポインタ更新
    log("latest ポインタ更新中...")
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_POINTER.write_text(RUN_ID, encoding="utf-8")
    log(f"LATEST_RUN_ID.txt 更新: {RUN_ID}")

    log("=== 月次実行完了 ===")
    print(f"run_id={RUN_ID}")
    print(f"staging={STAGING_DIR}")
    print(f"latest={LATEST_POINTER}")


if __name__ == "__main__":
    main()
