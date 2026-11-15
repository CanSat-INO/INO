"""CanSat Simulation用 ROS 2・Gazebo環境診断画面。"""

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RosGazeboDiagnosticsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._started = False

        layout = QVBoxLayout(self)

        title = QLabel("ROS 2・Gazebo 環境診断")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(
            "インストール状況を確認します。"
            "ソフトウェアのインストールや設定変更は行いません。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.status = QLabel("未診断")
        layout.addWidget(self.status)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText("画面を開くと診断を開始します。")
        layout.addWidget(self.details)

        self.button = QPushButton("再診断")
        self.button.clicked.connect(self.run_diagnosis)
        layout.addWidget(self.button)

        self.process = QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_process)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._started:
            self._started = True
            self.run_diagnosis()

    def run_diagnosis(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return

        script = Path(__file__).with_name(
            "ros_gazebo_diagnostics.py"
        )

        if not script.is_file():
            self.status.setText("診断プログラムが見つかりません")
            return

        self.button.setEnabled(False)
        self.status.setText("診断中...")
        self.details.setPlainText("ROS 2とGazeboを確認しています。")

        self.process.start(
            sys.executable,
            ["-B", str(script)],
        )

    def _finished(self, exit_code, exit_status):
        self.button.setEnabled(True)

        if (
            exit_code != 0
            or exit_status != QProcess.ExitStatus.NormalExit
        ):
            self.status.setText("診断に失敗しました")
            self.details.setPlainText(
                bytes(self.process.readAllStandardError())
                .decode("utf-8", errors="replace")
            )
            return

        try:
            output = bytes(
                self.process.readAllStandardOutput()
            ).decode("utf-8")
            result = json.loads(output)
        except (ValueError, UnicodeError) as exc:
            self.status.setText("診断結果を読み取れません")
            self.details.setPlainText(str(exc))
            return

        self.status.setText("診断完了")
        self.details.setPlainText(self.format_report(result))

    def _error(self, error):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.button.setEnabled(True)
            self.status.setText(
                "診断プログラムを起動できません: "
                + self.process.errorString()
            )

    @staticmethod
    def format_report(result):
        ros = (
            "利用可能（環境設定の読み込み後）"
            if result.get("ros2") == "available_after_setup"
            else "未確認・利用不可"
        )

        gazebo = (
            "コマンド検出（起動は未検証）"
            if result.get("gazebo") == "command_detected"
            else "コマンド未検出"
        )

        bridge = (
            "パッケージ導入済み（通信は未検証）"
            if result.get("ros_gz_bridge")
            else "パッケージ未検出"
        )

        lines = [
            "【システム】",
            f"OS: {result.get('os', '不明')}",
            f"WSL: {'検出' if result.get('wsl') else '未検出'}",
            f"Python: {result.get('python', '不明')}",
            "",
            "【ROS 2】",
            f"状態: {ros}",
            f"種類: {result.get('ros_distro') or '未検出'}",
            f"設定: {result.get('ros_setup') or '未検出'}",
            "",
            "【Gazebo】",
            f"状態: {gazebo}",
            f"ROS–Gazebo連携: {bridge}",
            "",
            "【開発環境】",
            f"colcon: {'検出済み' if result.get('colcon') else '未検出'}",
        ]

        for note in result.get("notes", []):
            lines.append(f"注意: {note}")

        lines.append("")
        lines.append(
            "※ Gazeboの画面起動や実機との通信は"
            "この診断では確認していません。"
        )

        return "\n".join(lines)

    def _stop_process(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
