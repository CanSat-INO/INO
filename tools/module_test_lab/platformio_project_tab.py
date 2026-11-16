"""PlatformIOプロジェクトの確認とPCロジック試験GUI。"""

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QPlainTextEdit, QCheckBox, QMessageBox,
)


class PlatformIOProjectTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel("PlatformIO プロジェクト検証")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel(
            "プロジェクトの構成を確認し、対応するC++判断ロジックを"
            "PC上で検証します。ESP32への書き込みは行いません。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()
        self.path_edit = QLineEdit()

        default = (
            Path.home() / "INO-module-lab"
            / "reference" / "regulus"
        )
        if (default / "platformio.ini").is_file():
            self.path_edit.setText(str(default))

        self.path_edit.setPlaceholderText(
            "platformio.iniがあるフォルダを選択"
        )
        row.addWidget(self.path_edit)

        browse = QPushButton("参照")
        browse.clicked.connect(self.choose_project)
        row.addWidget(browse)
        layout.addLayout(row)

        self.inspect_button = QPushButton(
            "プロジェクト構成を確認"
        )
        self.inspect_button.clicked.connect(
            lambda: self.start_check(False)
        )
        layout.addWidget(self.inspect_button)

        self.trusted = QCheckBox(
            "選択したC++コードを信頼し、PC上で"
            "コンパイル・実行することに同意します"
        )
        layout.addWidget(self.trusted)

        self.test_button = QPushButton(
            "REGULUS MissionStateをPC試験"
        )
        self.test_button.setEnabled(False)
        self.trusted.toggled.connect(
            self.update_test_button
        )
        self.test_button.clicked.connect(
            lambda: self.start_check(True)
        )
        layout.addWidget(self.test_button)

        self.status = QLabel("未実行")
        layout.addWidget(self.status)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

        self.process = QProcess(self)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.path_edit.textChanged.connect(self.project_changed)

        self.testing = False

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.stop_process)

    def update_test_button(self, checked=None):
        self.test_button.setEnabled(
            self.trusted.isChecked()
            and self.process.state()
                == QProcess.ProcessState.NotRunning
        )

    def project_changed(self, _text):
        self.trusted.setChecked(False)
        self.update_test_button()

    def choose_project(self):
        directory = QFileDialog.getExistingDirectory(
            self, "PlatformIOプロジェクトを選択",
            self.path_edit.text() or str(Path.home())
        )
        if directory:
            self.path_edit.setText(directory)

    def start_check(self, testing):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return

        root = Path(
            self.path_edit.text().strip()
        ).expanduser().resolve()

        if not (root / "platformio.ini").is_file():
            QMessageBox.warning(
                self, "確認",
                "platformio.iniがあるフォルダを指定してください。"
            )
            return

        if testing and not self.trusted.isChecked():
            QMessageBox.warning(
                self, "確認",
                "信頼できるコードであることを確認してください。"
            )
            return

        script = Path(__file__).with_name(
            "platformio_project_probe.py"
        )

        if not script.is_file():
            QMessageBox.warning(
                self, "確認", "検証モジュールが見つかりません。"
            )
            return

        self.testing = testing

        args = ["-B", str(script), str(root)]
        if testing:
            args.append("--test-mission-state")

        self.inspect_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.status.setText("PC試験中..." if testing else "確認中...")
        self.output.setPlainText("処理を実行しています。")

        self.process.start(sys.executable, args)

    def finished(self, exit_code, exit_status):
        self.inspect_button.setEnabled(True)
        self.update_test_button()

        if (
            exit_code != 0
            or exit_status != QProcess.ExitStatus.NormalExit
        ):
            error = bytes(
                self.process.readAllStandardError()
            ).decode("utf-8", errors="replace")
            self.status.setText("検証に失敗しました")
            self.output.setPlainText(error)
            return

        try:
            raw = bytes(
                self.process.readAllStandardOutput()
            ).decode("utf-8")
            data = json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            self.status.setText("結果を読み取れません")
            self.output.setPlainText(str(exc))
            return

        lines = [
            "【プロジェクト】",
            data.get("project", ""),
            "",
            "【開発環境】",
        ]

        for env in data.get("environments", []):
            lines.append(
                f"{env['name']} / "
                f"{env['board']} / {env['framework']}"
            )

        lines += ["", "【ソースコード】"]

        for group, files in data.get("files", {}).items():
            lines.append(f"{group}: {len(files)}ファイル")
            for name in files:
                lines.append(f"  {name}")

        result = data.get("mission_state_test")

        if result is not None:
            lines += [
                "",
                "【REGULUS MissionState試験】",
                f"結果: {result.get('status', '不明')}",
                result.get("output", ""),
                result.get("reason", ""),
                result.get("details", ""),
            ]
            self.status.setText(
                f"PC試験: {result.get('status', '不明')}"
            )
        else:
            self.status.setText("プロジェクト確認完了")

        self.output.setPlainText("\n".join(lines))

    def process_error(self, error):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.inspect_button.setEnabled(True)
            self.update_test_button()
            self.status.setText(
                "実行エラー: " + self.process.errorString()
            )

    def stop_process(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
