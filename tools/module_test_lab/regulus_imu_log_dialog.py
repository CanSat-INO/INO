"""REGULUS QMI8658シリアルログの解析画面。"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog,
    QPlainTextEdit,
)

from regulus_imu_log import read_imu_log, parse_imu_text


class RegulusIMULogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("REGULUS IMUログ解析")
        self.resize(850, 620)

        layout = QVBoxLayout(self)

        title = QLabel("REGULUS QMI8658 IMUログ解析")
        title.setStyleSheet(
            "font-size: 19px; font-weight: bold;"
        )
        layout.addWidget(title)

        note = QLabel(
            "PlatformIOのシリアルモニターで保存した"
            "TXTログを解析します。\n"
            "実機への接続・書き込みは行いません。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "シリアルログのTXTファイルを指定"
        )
        row.addWidget(self.path_edit)

        browse = QPushButton("参照")
        browse.clicked.connect(self.choose_file)
        row.addWidget(browse)

        layout.addLayout(row)

        actions = QHBoxLayout()

        self.analyze_button = QPushButton(
            "ログを解析"
        )
        self.analyze_button.clicked.connect(
            self.analyze_file
        )
        actions.addWidget(self.analyze_button)

        self.demo_button = QPushButton(
            "模擬ログで試す"
        )
        self.demo_button.clicked.connect(
            self.preview_example
        )
        actions.addWidget(self.demo_button)

        layout.addLayout(actions)

        self.status = QLabel("未解析")
        layout.addWidget(self.status)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

        self.path_edit.textChanged.connect(
            self.invalidate
        )

    def invalidate(self, *_):
        self.status.setText("未解析")
        self.output.clear()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "REGULUS IMUログを選択",
            str(Path.home()),
            "ログ (*.txt *.log);;すべてのファイル (*)",
        )
        if path:
            self.path_edit.setText(path)

    def analyze_file(self):
        path = self.path_edit.text().strip()

        if not path:
            self.status.setText(
                "ログファイルを指定してください"
            )
            return

        try:
            report = read_imu_log(path)
        except (ValueError, OSError, UnicodeError) as exc:
            self.status.setText("読み込みエラー")
            self.output.setPlainText(str(exc))
            return

        self.show_report(report, str(Path(path)))

    def preview_example(self):
        sample = (
            "=== REGULUS QMI8658 Test ===\n"
            "QMI8658 initialized at 0x6A\n"
            "A[m/s2] 0.000 0.000 9.810 "
            "G[dps] 0.100 0.200 -0.100\n"
            "A[m/s2] 0.100 0.000 9.800 "
            "G[dps] 0.200 0.100 0.000\n"
        )

        report = parse_imu_text(sample)
        self.show_report(
            report,
            "模擬ログ（実測データではありません）",
        )

    def show_report(self, report, source):
        status = report["status"]

        descriptions = {
            "PARSED": "解析完了（精度は未判定）",
            "WARNING": "解析完了・警告あり",
            "NO_VALID_SAMPLES": "有効な測定値なし",
        }

        self.status.setText(
            descriptions.get(status, status)
        )

        lines = [
            "【解析対象】",
            source,
            "",
            "【解析結果】",
            f"有効サンプル数: {report['sample_count']}",
            f"読み取り失敗: {report['read_failures']}",
            f"初期化失敗: {report['initialization_failures']}",
            f"不正なデータ行: {report['malformed_samples']}",
            f"その他の行: {report['ignored_lines']}",
            "",
            "【測定値の統計】",
        ]

        labels = {
            "ax": "加速度X [m/s²]",
            "ay": "加速度Y [m/s²]",
            "az": "加速度Z [m/s²]",
            "gx": "角速度X [deg/s]",
            "gy": "角速度Y [deg/s]",
            "gz": "角速度Z [deg/s]",
            "accel_norm_mps2": "加速度ノルム [m/s²]",
            "gyro_norm_dps": "角速度ノルム [deg/s]",
        }

        statistics = report["statistics"]

        if not statistics:
            lines.append("有効な測定値がありません")

        for key, label in labels.items():
            if key not in statistics:
                continue

            value = statistics[key]
            lines.append(
                f"{label}\n"
                f"  最小: {value['min']:.3f} / "
                f"最大: {value['max']:.3f} / "
                f"平均: {value['mean']:.3f}"
            )

        lines += ["", "【解析上の制限】"]
        lines.extend(report["limitations"])

        self.output.setPlainText("\n".join(lines))
