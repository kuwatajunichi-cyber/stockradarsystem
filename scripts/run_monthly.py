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

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# PYTHONPATH が設定されていない場合、src を追加
if "PYTHONPATH" in os.environ:
    src_path = os.environ["PYTHONPATH"]
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
else:
    # スクリプトの位置から src を推測
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    src_dir = repo_root / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

print(f"PYTHONPATH env: {os.environ.get('PYTHONPATH', '(未設定)')}", file=sys.stderr, flush=True)
print(f"sys.path (先頭3つ): {sys.path[:3]}", file=sys.stderr, flush=True)
print(f"カレントディレクトリ: {Path.cwd()}", file=sys.stderr, flush=True)

try:
    from stockradar.utils.manifest import (
        compute_sha256,
        create_manifest,
        verify_manifest,
        write_manifest,
    )
    print("インポート成功: stockradar.utils.manifest", file=sys.stderr, flush=True)
except ImportError as e:
    print(f"インポートエラー: {e}", file=sys.stderr, flush=True)
    print(f"sys.path: {sys.path}", file=sys.stderr, flush=True)
    manifest_path = Path("src/stockradar/utils/manifest.py")
    if manifest_path.exists():
        print(f"ファイルは存在します: {manifest_path.absolute()}", file=sys.stderr, flush=True)
    else:
        print(f"ファイルが見つかりません: {manifest_path.absolute()}", file=sys.stderr, flush=True)
        # リポジトリルートから探す
        repo_root = Path(__file__).parent.parent
        alt_path = repo_root / "src" / "stockradar" / "utils" / "manifest.py"
        if alt_path.exists():
            print(f"代替パスで見つかりました: {alt_path.absolute()}", file=sys.stderr, flush=True)
    sys.exit(2)

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
            encoding="utf-8",
            errors="replace",
            cwd=Path.cwd(),
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode, output
    except Exception as e:
        return 1, f"実行エラー: {type(e).__name__}: {e}"


def copy_to_staging(source: Path, dest_name: str) -> Path:
    """ファイルを staging にコピーし、パスを返す。"""
    import shutil
    try:
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        dest = STAGING_DIR / dest_name
        shutil.copy2(source, dest)
        return dest
    except Exception as e:
        raise RuntimeError(f"コピーエラー ({source} -> {dest_name}): {e}") from e


def find_latest_secondary_outputs() -> tuple[dict[str, Path], list[str]]:
    """
    最新の sets_secondary_* から 3CSV を探す。
    Returns:
        (found_files, debug_messages)
    """
    debug: list[str] = []
    jpx_dir = Path("data/universe/jpx")
    if not jpx_dir.exists():
        debug.append(f"ディレクトリが存在しません: {jpx_dir}")
        return {}, debug
    debug.append(f"検索対象: {jpx_dir}")
    candidates = sorted(
        [d for d in jpx_dir.iterdir() if d.is_dir() and d.name.startswith("sets_secondary_")],
        reverse=True,
    )
    if not candidates:
        debug.append("sets_secondary_* ディレクトリが見つかりません")
        return {}, debug
    latest_dir = candidates[0]
    debug.append(f"最新ディレクトリ: {latest_dir}")
    out: dict[str, Path] = {}
    for name in LATEST_3CSV:
        path = latest_dir / name
        if path.exists():
            out[name] = path
            debug.append(f"見つかった: {name}")
        else:
            debug.append(f"見つからない: {name} (パス={path})")
    return out, debug


def collect_inputs_for_manifest() -> list[dict[str, str]]:
    """manifest 用の入力情報を収集（簡易版）。"""
    inputs: list[dict[str, str]] = []
    repo_root = Path.cwd().resolve()
    # JPX processed CSV
    processed_dir = repo_root / "data" / "processed" / "jpx"
    if processed_dir.exists():
        for p in sorted(processed_dir.glob("jpx_list_*.csv"), reverse=True):
            if p.exists():
                # 絶対パスに変換
                p_abs = p.resolve()
                # 相対パスを計算（両方絶対パスにしてから）
                try:
                    rel_path = p_abs.relative_to(repo_root)
                except ValueError:
                    # 相対パスで取得できない場合は、repo_root からの相対パスを手動計算
                    try:
                        rel_path_str = str(p_abs).replace(str(repo_root), "").lstrip("/\\")
                        rel_path = Path(rel_path_str) if rel_path_str else Path(p.name)
                    except Exception:
                        rel_path = Path(p.name)
                inputs.append(
                    {
                        "path": str(rel_path).replace("\\", "/"),
                        "size_bytes": str(p_abs.stat().st_size),
                        "sha256": compute_sha256(p_abs),
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

        # ヘッダ確認（code,name 必須。URL列含む場合は code,name,kabutan_main,...）
        with open(csv_path, encoding="utf-8-sig") as f:
            header = f.readline().strip()
            if not header.startswith("code,name"):
                errors.append(f"CSV ヘッダが不正: {csv_name} (先頭が 'code,name' である必要あり, 実='{header[:80]}...' 等)")
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
    # 最初に標準エラーに出力（ログファイルがまだないため）
    print(f"=== 月次実行開始 run_id={RUN_ID} ===", file=sys.stderr, flush=True)
    print(f"カレントディレクトリ: {Path.cwd()}", file=sys.stderr, flush=True)
    print(f"STAGING_DIR: {STAGING_DIR.absolute()}", file=sys.stderr, flush=True)
    print(f"LOGS_DIR: {LOGS_DIR.absolute()}", file=sys.stderr, flush=True)

    try:
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOGS_DIR / "run.log"
        print(f"ログファイル: {log_path.absolute()}", file=sys.stderr, flush=True)

        def log(msg: str) -> None:
            print(msg, flush=True)
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")
            except Exception as e:
                print(f"ログ書き込みエラー: {e}", file=sys.stderr, flush=True)

        log(f"=== 月次実行開始 run_id={RUN_ID} ===")
        log(f"カレントディレクトリ: {Path.cwd()}")
        log(f"STAGING_DIR: {STAGING_DIR.absolute()}")
    except Exception as e:
        print(f"初期化エラー: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

    # 1. update_jpx_url_cache
    log("1/5: update_jpx_url_cache")
    code, output = run_job("stockradar.jobs.update_jpx_url_cache")
    log(f"出力:\n{output}")
    if code != 0:
        log(f"エラー: update_jpx_url_cache が失敗 (code={code})")
        sys.exit(2)

    # 2. fetch_jpx_list
    log("2/5: fetch_jpx_list")
    code, output = run_job("stockradar.jobs.fetch_jpx_list")
    log(f"出力:\n{output}")
    if code != 0:
        log(f"エラー: fetch_jpx_list が失敗 (code={code})")
        sys.exit(2)

    # 3. build_universe_from_jpx
    log("3/5: build_universe_from_jpx")
    code, output = run_job("stockradar.jobs.build_universe_from_jpx")
    log(f"出力:\n{output}")
    if code != 0:
        log(f"エラー: build_universe_from_jpx が失敗 (code={code})")
        sys.exit(2)

    # 4. fetch_yf_daily_for_universe
    log("4/5: fetch_yf_daily_for_universe")
    code, output = run_job("stockradar.jobs.fetch_yf_daily_for_universe")
    log(f"出力:\n{output}")
    if code != 0:
        log(f"エラー: fetch_yf_daily_for_universe が失敗 (code={code})")
        sys.exit(2)

    # 5. split_equity_domestic_secondary
    log("5/5: split_equity_domestic_secondary")
    code, output = run_job("stockradar.jobs.split_equity_domestic_secondary")
    log(f"出力:\n{output}")
    if code != 0:
        log(f"エラー: split_equity_domestic_secondary が失敗 (code={code})")
        sys.exit(2)

    # 最新の sets_secondary_* から 3CSV を staging にコピー
    log("成果物を staging にコピー中...")
    secondary_outputs, debug_msgs = find_latest_secondary_outputs()
    for msg in debug_msgs:
        log(f"  {msg}")
    if len(secondary_outputs) != 3:
        log(f"エラー: 3CSV が見つかりません (見つかった数={len(secondary_outputs)}, 期待=3)")
        log(f"見つかったファイル: {list(secondary_outputs.keys())}")
        sys.exit(2)

    try:
        inputs = collect_inputs_for_manifest()
        log(f"入力ファイル数: {len(inputs)}")
    except Exception as e:
        log(f"入力収集エラー: {type(e).__name__}: {e}")
        import traceback
        log(traceback.format_exc())
        sys.exit(2)

    flags_summary: dict[str, str] = {}

    for csv_name, source_path in secondary_outputs.items():
        try:
            log(f"処理中: {csv_name} (source={source_path})")
            if not source_path.exists():
                log(f"エラー: ソースファイルが存在しません: {source_path}")
                sys.exit(2)
            dest_path = copy_to_staging(source_path, csv_name)
            log(f"コピー完了: {source_path} -> {dest_path}")

            # manifest 生成
            log(f"manifest 生成開始: {csv_name}")
            manifest = create_manifest(
                output_path=dest_path,
                run_id=RUN_ID,
                inputs=inputs,
                flags_summary=flags_summary,
                repo_root=Path.cwd(),
            )
            manifest_path = STAGING_DIR / f"{csv_name}.manifest.json"
            write_manifest(manifest_path, manifest)
            log(f"manifest 生成完了: {manifest_path}")
        except Exception as e:
            log(f"エラー ({csv_name}): {type(e).__name__}: {e}")
            import traceback
            log(traceback.format_exc())
            print(f"エラー ({csv_name}): {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            sys.exit(2)

    # 検証ゲート
    try:
        log("検証ゲート実行中...")
        is_valid, errors = verify_gate(STAGING_DIR)
        if not is_valid:
            log("検証ゲート失敗:")
            for err in errors:
                log(f"  - {err}")
            sys.exit(2)
        log("検証ゲート通過")
    except Exception as e:
        log(f"検証ゲート実行エラー: {type(e).__name__}: {e}")
        import traceback
        log(traceback.format_exc())
        print(f"検証ゲート実行エラー: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

    # latest ポインタ更新
    try:
        log("latest ポインタ更新中...")
        LATEST_DIR.mkdir(parents=True, exist_ok=True)
        LATEST_POINTER.write_text(RUN_ID, encoding="utf-8")
        log(f"LATEST_RUN_ID.txt 更新: {RUN_ID}")
    except Exception as e:
        log(f"latest ポインタ更新エラー: {type(e).__name__}: {e}")
        import traceback
        log(traceback.format_exc())
        print(f"latest ポインタ更新エラー: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

    log("=== 月次実行完了 ===")
    print(f"run_id={RUN_ID}")
    print(f"staging={STAGING_DIR}")
    print(f"latest={LATEST_POINTER}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("中断されました", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"予期しないエラー: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(2)
