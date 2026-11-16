"""REGULUS GNSSシリアルログの読み取り専用GUI。"""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QPlainTextEdit,
)

from regulus_gnss_log import read_gnss_log, parse_gnss_text


class RegulusGNSSLogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("REGULUS GNSSログ解析")
        self.resize(850, 650)

        layout = QVBoxLayout(self)

        title = QLabel("REGULUS GNSSログ解析")
        title.setStyleSheet(
            "font-size: 19px; font-weight: bold;"
        )
        layout.addWidget(title)

        note = QLabel(
            "PlatformIOのシリアルモニターから保存した"
            "NMEAまたはMAX-M10Mのログを解析します。\n"
            "ESP32への接続・書き込みは行いません。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "GNSSシリアルログを選択"
        )
        row.addWidget(self.path_edit)

        browse = QPushButton("参照")
        browse.clicked.connect(self.choose_file)
        row.addWidget(browse)

        layout.addLayout(row)

        buttons = QHBoxLayout()

        self.analyze_button = QPushButton("ログを解析")
        self.analyze_button.clicked.connect(
            self.analyze_file
        )
        buttons.addWidget(self.analyze_button)

        self.demo_button = QPushButton("模擬ログで試す")
        self.demo_button.clicked.connect(
            self.preview_example
        )
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
            "GNSSログを選択",
            str(Path.home()),
            "ログ (*.txt *.log *.nmea);;すべてのファイル (*)",
        )
        if path:
            self.path_edit.setText(path)

    def analyze_file(self):
        path = self.path_edit.text().strip()

        if not path:
            self.status.setText("ログファイルを指定してください")
            return

        try:
            report = read_gnss_log(path)
        except (ValueError, OSError, UnicodeError) as exc:
            self.status.setText("読み込みエラー")
            self.output.setPlainText(str(exc))
            return

        self.show_report(report, str(Path(path)))

    def preview_example(self):
        # 実測値ではなく、画面確認用の模擬データ。
        snapshot = (
            "valid=1 fix=1 lat=35.0000000 "
            "lon=139.0000000 alt=20.0 m "
            "sats=8 age=100 ms chars=500 ok=10 failed=0"
        )

        payload = "GNRMC,120000.00,V,,,,,,,161126,,,N"
        checksum = 0
        for char in payload:
            checksum ^= ord(char)

        nmea = f"${payload}*{checksum:02X}"

        report = parse_gnss_text(snapshot + "\n" + nmea)

        self.show_report(
            report,
            "模擬ログ（実測データではありません）",
        )

    def show_report(self, report, source):
        descriptions = {
            "PARSED": "解析完了（測位精度は未判定）",
            "WARNING": "解析完了・警告あり",
            "NO_VALID_DATA": "有効なGNSSデータなし",
        }

        self.status.setText(
            descriptions.get(report["status"], report["status"])
        )

        lines = [
            "【解析対象】",
            source,
            "",
            "【解析済みGNSSデータ】",
            f"取得件数: {report['snapshot_count']}",
            f"測位成功の報告: {report['reported_fix_count']}",
            f"測位不可の報告: {report['reported_no_fix_count']}",
            f"測位状態の矛盾: {report['inconsistent_fix_count']}",
            f"不正なデータ行: {report['malformed_snapshots']}",
            "",
            "【NMEAデータ】",
            f"チェックサム正常: {report['nmea_count']}",
            f"チェックサム不一致: {report['nmea_bad_checksum']}",
            f"不完全なNMEA文: {report['nmea_malformed']}",
            f"測位ありの表示: {report['nmea_fix_indications']}",
            f"測位なしの表示: {report['nmea_no_fix_indications']}",
            "",
            "【NMEA文の種類】",
        ]

        types = report["nmea_sentence_types"]

        if types:
            for name, count in sorted(types.items()):
                lines.append(f"{name}: {count}件")
        else:
            lines.append("有効なNMEA文なし")

        lines += ["", "【最新の解析済みデータ行】"]

        last = report["last_snapshot"]

        if last is None:
            lines.append("取得なし")
        else:
            lines += [
                f"valid: {last['valid']}",
                f"fix: {last['fix']}",
                f"緯度: {last['latitude']:.7f}°",
                f"経度: {last['longitude']:.7f}°",
                f"高度: {last['altitude_m']:.3f} m",
                f"衛星数: {last['satellites']}",
                f"受信経過表示: {last['age_ms']} ms",
                f"文字数: {last['chars']}",
                f"チェックサム正常累計: {last['passed_checksum']}",
                f"チェックサム失敗累計: {last['failed_checksum']}",
            ]

        lines += [
            "",
            f"その他の行: {report['ignored_lines']}",
            "",
            "【解析上の制限】",
        ]

        lines.extend(report["limitations"])

        self.output.setPlainText("\n".join(lines))
