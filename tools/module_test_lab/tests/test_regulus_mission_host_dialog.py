"""REGULUSミッション仮想試験GUIのテスト。"""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from platformio_project_tab import PlatformIOProjectTab
from regulus_mission_host_dialog import (
    RegulusMissionHostDialog,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_platformio_button(qapp):
    tab = PlatformIOProjectTab()

    assert tab.mission_host_button.isEnabled()
    assert tab.gnss_button.isEnabled()
    assert tab.baro_button.isEnabled()
    assert tab.imu_button.isEnabled()


def test_consent_and_project_change(qapp):
    dialog = RegulusMissionHostDialog()

    dialog.path_edit.setText("/tmp/regulus-a")

    assert not dialog.run_button.isEnabled()

    dialog.start_test()
    assert dialog.worker is None

    dialog.consent_check.setChecked(True)

    assert dialog.run_button.isEnabled()

    dialog.path_edit.setText("/tmp/regulus-b")

    assert not dialog.consent_check.isChecked()
    assert not dialog.run_button.isEnabled()
    assert dialog.status.text() == "未実行"


def test_display_success(qapp):
    dialog = RegulusMissionHostDialog()

    dialog.show_report({
        "status": "PASS",
        "project": "/tmp/example",
        "source_sha256": "abc123",
        "passed": 7,
        "failed": 0,
        "skipped": 0,
        "checks": [
            {
                "result": "PASS",
                "name": "初期状態はBOOT",
            }
        ],
        "limitations": ["実機試験ではない"],
    })

    output = dialog.output.toPlainText()

    assert "PASS" in dialog.status.text()
    assert "成功: 7件" in output
    assert "[PASS] 初期状態はBOOT" in output
    assert "abc123" in output
    assert "実機試験ではない" in output


def test_compile_error_display(qapp):
    dialog = RegulusMissionHostDialog()

    dialog.show_report({
        "status": "COMPILE_FAILED",
        "checks": [],
        "details": "synthetic compiler error",
    })

    assert "COMPILE FAILED" in dialog.status.text()
    assert "synthetic compiler error" in (
        dialog.output.toPlainText()
    )


def test_runtime_error_display(qapp):
    dialog = RegulusMissionHostDialog()
    dialog.show_error("synthetic runtime error")

    assert dialog.status.text() == "試験エラー"
    assert "synthetic runtime error" in (
        dialog.output.toPlainText()
    )
