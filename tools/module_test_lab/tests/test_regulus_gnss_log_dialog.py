"""REGULUS GNSSログ解析GUIの回帰テスト。"""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from platformio_project_tab import PlatformIOProjectTab
from regulus_gnss_log_dialog import RegulusGNSSLogDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_all_sensor_buttons(qapp):
    tab = PlatformIOProjectTab()

    assert tab.imu_button.isEnabled()
    assert tab.baro_button.isEnabled()
    assert tab.gnss_button.isEnabled()


def test_demo_log(qapp):
    dialog = RegulusGNSSLogDialog()
    dialog.demo_button.click()

    result = dialog.output.toPlainText()

    assert dialog.status.text().startswith("解析完了")
    assert "取得件数: 1" in result
    assert "チェックサム正常: 1" in result
    assert "GNRMC: 1件" in result


def test_snapshot_file(qapp, tmp_path):
    file = tmp_path / "gnss.txt"
    file.write_text(
        "valid=1 fix=1 lat=35.0 lon=139.0 "
        "alt=20.0 m sats=8 age=100 ms "
        "chars=500 ok=10 failed=0\n",
        encoding="utf-8",
    )

    original = file.read_bytes()

    dialog = RegulusGNSSLogDialog()
    dialog.path_edit.setText(str(file))
    dialog.analyze_button.click()

    assert dialog.status.text().startswith("解析完了")
    assert "緯度: 35.0000000°" in dialog.output.toPlainText()
    assert file.read_bytes() == original


def test_raw_nmea_file(qapp, tmp_path):
    payload = "GNRMC,120000.00,V,,,,,,,161126,,,N"

    checksum = 0
    for char in payload:
        checksum ^= ord(char)

    file = tmp_path / "nmea.txt"
    file.write_text(
        f"${payload}*{checksum:02X}\n",
        encoding="utf-8",
    )

    dialog = RegulusGNSSLogDialog()
    dialog.path_edit.setText(str(file))
    dialog.analyze_button.click()

    assert dialog.status.text().startswith("解析完了")
    assert "測位なしの表示: 1" in dialog.output.toPlainText()


def test_missing_file(qapp, tmp_path):
    dialog = RegulusGNSSLogDialog()
    dialog.path_edit.setText(str(tmp_path / "missing.txt"))
    dialog.analyze_button.click()

    assert dialog.status.text() == "読み込みエラー"


def test_path_change_invalidates_result(qapp):
    dialog = RegulusGNSSLogDialog()
    dialog.demo_button.click()

    assert dialog.status.text().startswith("解析完了")

    dialog.path_edit.setText("/tmp/new_gnss_log.txt")

    assert dialog.status.text() == "未解析"
    assert dialog.output.toPlainText() == ""
