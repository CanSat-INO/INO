"""REGULUS IMUログ解析GUIの回帰テスト。"""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regulus_imu_log_dialog import RegulusIMULogDialog
from platformio_project_tab import PlatformIOProjectTab


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_platformio_has_imu_button(qapp):
    tab = PlatformIOProjectTab()
    assert tab.imu_button.isEnabled()
    assert "IMU" in tab.imu_button.text()


def test_mock_log(qapp):
    dialog = RegulusIMULogDialog()
    dialog.demo_button.click()

    assert dialog.status.text().startswith("解析完了")
    assert "有効サンプル数: 2" in dialog.output.toPlainText()
    assert "加速度ノルム" in dialog.output.toPlainText()


def test_real_file_format(qapp, tmp_path):
    logfile = tmp_path / "imu.txt"
    logfile.write_text(
        "=== REGULUS QMI8658 Test ===\n"
        "A[m/s2] 0.000 0.000 9.810 "
        "G[dps] 0.100 0.200 -0.100\n",
        encoding="utf-8",
    )

    dialog = RegulusIMULogDialog()
    dialog.path_edit.setText(str(logfile))
    dialog.analyze_button.click()

    assert dialog.status.text().startswith("解析完了")
    assert "有効サンプル数: 1" in dialog.output.toPlainText()


def test_missing_file_error(qapp, tmp_path):
    dialog = RegulusIMULogDialog()
    dialog.path_edit.setText(str(tmp_path / "missing.txt"))
    dialog.analyze_button.click()

    assert dialog.status.text() == "読み込みエラー"
