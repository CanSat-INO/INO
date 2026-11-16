"""REGULUS HP203Bログ解析GUIの回帰テスト。"""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regulus_baro_log_dialog import RegulusBaroLogDialog
from platformio_project_tab import PlatformIOProjectTab


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_platformio_has_sensor_buttons(qapp):
    tab = PlatformIOProjectTab()

    assert tab.imu_button.isEnabled()
    assert tab.baro_button.isEnabled()
    assert "HP203B" in tab.baro_button.text()


def test_demo_log(qapp):
    dialog = RegulusBaroLogDialog()
    dialog.demo_button.click()

    result = dialog.output.toPlainText()

    assert dialog.status.text().startswith("解析完了")
    assert "有効サンプル数: 2" in result
    assert "高度変化量: +1.000 m" in result
    assert "気圧 [hPa]" in result


def test_read_log_file(qapp, tmp_path):
    logfile = tmp_path / "baro.txt"
    logfile.write_text(
        "pressure=1013.25 hPa "
        "temperature=24.50 C altitude=15.20 m\n",
        encoding="utf-8",
    )

    before = logfile.read_bytes()

    dialog = RegulusBaroLogDialog()
    dialog.path_edit.setText(str(logfile))
    dialog.analyze_button.click()

    assert dialog.status.text().startswith("解析完了")
    assert "有効サンプル数: 1" in dialog.output.toPlainText()
    assert logfile.read_bytes() == before


def test_missing_file(qapp, tmp_path):
    dialog = RegulusBaroLogDialog()
    dialog.path_edit.setText(str(tmp_path / "missing.txt"))
    dialog.analyze_button.click()

    assert dialog.status.text() == "読み込みエラー"


def test_path_change_invalidates_result(qapp):
    dialog = RegulusBaroLogDialog()
    dialog.demo_button.click()

    assert dialog.status.text().startswith("解析完了")

    dialog.path_edit.setText("/tmp/new_baro_log.txt")

    assert dialog.status.text() == "未解析"
    assert dialog.output.toPlainText() == ""
