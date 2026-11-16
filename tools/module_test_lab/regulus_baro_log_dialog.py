"""REGULUS HP203BシリアルログのGUI解析。"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QPlainTextEdit,
)

from regulus_baro_log import read_baro_log, parse_baro_text


class RegulusBaroLogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("REGULUS HP203B 気圧ログ解析")
        self.resize(850, 620)

        layout = QVBoxLayout(self)

        title = QLabel("REGULUS HP203B 気圧・高度ログ解析")
        title.setStyleSheet(
            "font-size: 19px; font-weight: bold;"
        )
        layout.addWidget(title)

        note = QLabel(
            "PlatformIOのシリアルモニターから保存した"
            "TXTログを読み取り、気圧・温度・高度を解析します。\n"
            "ESP32-S3への接続・書き込みは行いません。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "HP203Bのシリアルログを選択"
        )
        file_row.addWidget(self.path_edit)

        browse = QPushButton("参照")
        browse.clicked.connect(self.choose_file)
        file_row.addWidget(browse)
        layout.addLayout(file_row)

        buttons = QHBoxLayout()

        self.analyze_button = QPushButton("ログを解析")
        self.analyze_button.clicked.connect(self.analyze_file)
        buttons.addWidget(self.analyze_button)

        self.demo_button = QPushButton("模擬ログで試す")
        self.demo_button.clicked.connect(self.preview_example)
        buttons.addWidget(self.demo_button)

        layout.addLayout(buttons)

        self.status = QLabel("未解析")
        layout.addWidget(self.status)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

        self.path_edit.textChanged.connect(self.invalidate)

    def invalidate(self, *_):
        self.status.setText("未解析")
        self.output.clear()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "HP203Bログを選択",
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
            report = read_baro_log(path)
        except (ValueError, OSError, UnicodeError) as exc:
            self.status.setText("読み込みエラー")
            self.output.setPlainText(str(exc))
            return

        self.show_report(report, str(Path(path)))

    def preview_example(self):
        text = (
            "=== REGULUS HP203B Test ===\n"
            "HP203B initialized at 0x76\n"
            "pressure=1013.25 hPa "
            "temperature=24.50 C altitude=15.20 m\n"
            "pressure=1013.15 hPa "
            "temperature=24.70 C altitude=16.20 m\n"
        )
        report = parse_baro_text(text)
        self.show_report(
            report,
            "模擬ログ（実測データではありません）",
        )

    def show_report(self, report, source):
        descriptions = {
            "PARSED": "解析完了（精度は未判定）",
            "WARNING": "解析完了・警告あり",
            "NO_VALID_SAMPLES": "有効な測定値なし",
        }

        status = report["status"]
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
            f"不完全・不正数値: {report['malformed_samples']}",
            f"物理的に不適切な値: {report['invalid_values']}",
            f"その他の行: {report['ignored_lines']}",
            "",
            "【測定値の統計】",
        ]

        labels = {
            "pressure_hpa": "気圧 [hPa]",
            "temperature_c": "温度 [°C]",
            "altitude_m": "高度 [m]",
        }

        statistics = report["statistics"]

        if not statistics:
            lines.append("有効な測定値がありません")

        for key, label in labels.items():
            if key not in statistics:
                continue

            value = statistics[key]
            lines.extend([
                label,
                f"  最小値: {value['min']:.3f}",
                f"  最大値: {value['max']:.3f}",
                f"  平均値: {value['mean']:.3f}",
            ])

        lines += ["", "【高度の変化】"]

        change = report["altitude_change_m"]
        altitude_range = report["altitude_range_m"]

        if change is None:
            lines.append("計算不可")
        else:
            lines.append(
                f"高度変化量: {change:+.3f} m"
            )
            lines.append(
                f"高度の範囲: {altitude_range:.3f} m"
            )

        lines += ["", "【解析上の制限】"]
        lines.extend(report["limitations"])

        self.output.setPlainText("\n".join(lines))
