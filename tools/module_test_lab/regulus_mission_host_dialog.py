"""REGULUS実コードの仮想ミッション試験GUI。"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from regulus_mission_host import run_mission_host


class MissionHostWorker(QThread):
    """GUIをブロックせずにPC用C++試験を実行する。"""

    report_ready = Signal(object)
    error_ready = Signal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project

    def run(self):
        try:
            report = run_mission_host(
                self.project,
                trusted=True,
            )
        except Exception as exc:
            self.error_ready.emit(str(exc))
        else:
            self.report_ready.emit(report)


class RegulusMissionHostDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "REGULUS ミッション仮想試験"
        )
        self.resize(850, 650)

        self._running = False
        self.worker = None

        layout = QVBoxLayout(self)

        title = QLabel(
            "REGULUS ミッション制御の実コード試験"
        )
        title.setStyleSheet(
            "font-size: 19px; font-weight: bold;"
        )
        layout.addWidget(title)

        info = QLabel(
            "REGULUSのMissionController.cppと"
            "MissionState.cppをPCでコンパイルして実行します。\n"
            "Arduino・Preferences・モーター・データ管理は"
            "PC用の模擬処理に置き換えます。\n"
            "実機への接続・書き込みは行いません。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        row = QHBoxLayout()

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "REGULUSのPlatformIOプロジェクトフォルダ"
        )
        row.addWidget(self.path_edit)

        self.browse_button = QPushButton(
            "フォルダを選択"
        )
        self.browse_button.clicked.connect(
            self.choose_folder
        )
        row.addWidget(self.browse_button)

        layout.addLayout(row)

        warning = QLabel(
            "注意：C++コードはPC上でネイティブ実行され、"
            "完全な隔離環境ではありません。\n"
            "自分で信頼できると確認したソースコードだけを"
            "試験してください。"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        self.consent_check = QCheckBox(
            "上記のC++コードをPCでコンパイル・実行することに同意します"
        )
        layout.addWidget(self.consent_check)

        self.run_button = QPushButton(
            "ミッション仮想試験を実行"
        )
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(
            self.start_test
        )
        layout.addWidget(self.run_button)

        self.status = QLabel("未実行")
        layout.addWidget(self.status)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

        self.path_edit.textChanged.connect(
            self.on_project_changed
        )
        self.consent_check.toggled.connect(
            self.update_run_button
        )

        default = (
            Path.home()
            / "INO-module-lab/reference/regulus"
        )
        if default.is_dir():
            self.path_edit.setText(str(default))

    def update_run_button(self, *_):
        allowed = (
            bool(self.path_edit.text().strip())
            and self.consent_check.isChecked()
            and not self._running
        )
        self.run_button.setEnabled(allowed)

    def on_project_changed(self, *_):
        # 実行対象が変わったら必ず再同意。
        self.consent_check.setChecked(False)
        self.status.setText("未実行")
        self.output.clear()
        self.update_run_button()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "REGULUSプロジェクトを選択",
            self.path_edit.text() or str(Path.home()),
        )
        if folder:
            self.path_edit.setText(folder)

    def start_test(self):
        if (
            self._running
            or not self.consent_check.isChecked()
            or not self.path_edit.text().strip()
        ):
            return

        project = str(
            Path(
                self.path_edit.text().strip()
            ).expanduser().resolve()
        )

        self._running = True
        self.path_edit.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.consent_check.setEnabled(False)
        self.update_run_button()

        self.status.setText("PC試験を実行中")
        self.output.setPlainText(
            "対象: " + project + "\n"
            "C++のコンパイルと仮想試験を実行しています。"
        )

        self.worker = MissionHostWorker(
            project,
            self,
        )
        self.worker.report_ready.connect(
            self.show_report
        )
        self.worker.error_ready.connect(
            self.show_error
        )
        self.worker.finished.connect(
            self.finish_test
        )
        self.worker.start()

    def show_report(self, report):
        status = report.get("status", "UNKNOWN")
        descriptions = {
            "PASS": "PASS：全項目成功",
            "FAIL": "FAIL：試験失敗",
            "INCOMPLETE": "INCOMPLETE：未実施項目あり",
            "COMPILE_FAILED": "COMPILE FAILED：コンパイル失敗",
        }

        self.status.setText(
            descriptions.get(status, status)
        )

        lines = [
            "【実行対象】",
            report.get(
                "project",
                self.path_edit.text(),
            ),
            "",
            "【判定】",
            descriptions.get(status, status),
            "",
            f"成功: {report.get('passed', 0)}件",
            f"失敗: {report.get('failed', 0)}件",
            f"スキップ: {report.get('skipped', 0)}件",
            "",
            "【項目別結果】",
        ]

        checks = report.get("checks", [])
        if checks:
            for check in checks:
                lines.append(
                    f"[{check['result']}] {check['name']}"
                )
        else:
            lines.append("項目別結果なし")

        lines += [
            "",
            "【MissionController.cppのSHA-256】",
            report.get(
                "source_sha256",
                "取得なし",
            ),
        ]

        if report.get("details"):
            lines += [
                "",
                "【コンパイルエラー】",
                report["details"],
            ]

        if report.get("errors"):
            lines += [
                "",
                "【標準エラー出力】",
                report["errors"],
            ]

        if report.get("limitations"):
            lines += [
                "",
                "【試験の制限】",
                *report["limitations"],
            ]

        self.output.setPlainText(
            "\n".join(lines)
        )

    def show_error(self, message):
        self.status.setText("試験エラー")
        self.output.setPlainText(
            "試験を完了できませんでした。\n\n"
            + message
        )

    def finish_test(self):
        self._running = False
        self.path_edit.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.consent_check.setEnabled(True)
        self.update_run_button()

    def reject(self):
        if self._running:
            self.status.setText(
                "試験実行中は画面を閉じられません"
            )
            return
        super().reject()

    def closeEvent(self, event):
        if self._running:
            event.ignore()
            self.status.setText(
                "試験実行中は画面を閉じられません"
            )
            return
        super().closeEvent(event)
