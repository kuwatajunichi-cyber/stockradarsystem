"""
render_sheet の run() を FakeDriveAdapter でテストする（Secrets 不要）。
CSV 取得 → テンプレ流し込み → アップロードまでのロジックを検証する。
"""
from __future__ import annotations

from pathlib import Path

import pytest

# プロジェクトルートを path に追加（render_sheet が scripts を import するため）
_repo_root = Path(__file__).resolve().parent.parent
import sys
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.gdrive.drive_client import FakeDriveAdapter
from scripts.render_sheet.render_sheet import run


def test_run_with_fake_drive_adapter() -> None:
    """FakeDriveAdapter を渡して run() が完了し、URL を返すことを検証する。"""
    # テンプレートが存在することを前提（config/templates/indicators_template_v1.0.xlsx）
    template_path = _repo_root / "config" / "templates" / "indicators_template_v1.0.xlsx"
    if not template_path.exists():
        pytest.skip("テンプレートがありません: config/templates/indicators_template_v1.0.xlsx")

    csv_content = (
        "code,name,z_turnover_60\n"
        "7203,Toyota,0.5\n"
        "9984,SoftBank,-0.2\n"
    ).encode("utf-8-sig")
    # extract_file_id は 20〜50 文字の ID を要求する
    fake_csv_id = "fake-csv-id-12345678901234567"
    fake = FakeDriveAdapter()
    fake.put_file(fake_csv_id, csv_content, "indicators_20260222.csv")

    cfg = {
        "csv_drive_file_id": fake_csv_id,
        "output_folder_id": "fake-folder-id",
        "output_subfolder": None,
        "header_anchor_sheet_name": "indicators001",
        "template_path": "config/templates/indicators_template_v1.0.xlsx",
        "link_label_map": {},
        "sort_column": "z_turnover_60",
        "sort_ascending": False,
    }

    url = run(cfg, drive_adapter=fake)

    assert isinstance(url, str)
    assert "drive.google.com" in url or "file/d/" in url
    # アップロードが呼ばれていれば Fake にファイルが増えている（2件: CSV 登録 + XLSX アップロード）
    assert len(fake._files) >= 2
