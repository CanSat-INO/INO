"""Qt widget for reviewing existing Arduino/host-produced landing CSV logs.

No serial port, .ino execution or GitHub network access occurs in this tab.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QComboBox,
    QLineEdit, QLabel, QPushButton, QPlainTextEdit, QFileDialog, QMessageBox,
    QDoubleSpinBox, QSplitter, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt

from arduino_csv import read_csv, analyze
from dashboard import TimePlot
from records import new_record, add_record


def _time(value):
    return "未取得" if value is None else f"{value:.3f} 秒"


class ArduinoCsvTab(QWidget):
    """Analyze a recorded CSV and register the report in the existing ledger."""
    def __init__(self, on_saved=None, parent=None):
        super().__init__(parent)
        self.on_saved = on_saved
        self.file_path: Path | None = None
        self.log = None
        self.result = None
        layout = QVBoxLayout(self)
        heading = QLabel("Arduino / 外部CSVログ解析")
        heading.setStyleSheet("font-size: 17px; font-weight: 700; color: #17365e;")
        layout.addWidget(heading)
        hint = QLabel(
            "Arduino担当者が実行して出力したログを読み取り、着地検知時刻を検証します。"
            " この画面では .ino は実行しません。正解時刻がない場合は『未判定』になります。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #5b6778;")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(2, 2, 2, 2)

        config = QGroupBox("CSVファイル・試験条件")
        form = QFormLayout(config)
        select_row = QWidget()
        select_lay = QHBoxLayout(select_row)
        select_lay.setContentsMargins(0, 0, 0, 0)
        self.path_text = QLineEdit()
        self.path_text.setReadOnly(True)
        self.path_text.setPlaceholderText("UTF-8のCSVを選択してください")
        select_lay.addWidget(self.path_text, 1)
        select_btn = QPushButton("参照…")
        select_btn.clicked.connect(self.choose_file)
        select_lay.addWidget(select_btn)
        form.addRow("CSVログ", select_row)

        self.mode = QComboBox()
        self.mode.addItems(["外部シミュレーション", "Arduino実機試験"])
        self.tester = QLineEdit()
        self.tester.setPlaceholderText("例：着地検知担当")
        self.scenario = QLineEdit()
        self.scenario.setPlaceholderText("例：落下テストNo.3")
        self.code = QLineEdit()
        self.code.setPlaceholderText("例：landing_v03 / commit ID")
        self.truth_ms = QLineEdit()
        self.truth_ms.setPlaceholderText("任意。空欄ならCSVのtruth_contact列を使用")
        self.delay_ms = QDoubleSpinBox()
        self.delay_ms.setDecimals(0)
        self.delay_ms.setRange(0, 600000)
        self.delay_ms.setValue(5000)
        self.delay_ms.setSuffix(" ms")
        self.delay_ms.setSingleStep(100)
        for label, w in [
            ("データの種類", self.mode), ("担当者", self.tester),
            ("試験ケース", self.scenario), ("Arduinoコード版", self.code),
            ("真の接地時刻（ms）", self.truth_ms),
            ("検知の許容遅延", self.delay_ms),
        ]:
            form.addRow(label, w)
        left_lay.addWidget(config)
        button_bar = QHBoxLayout()
        run = QPushButton("▶ CSVを解析")
        run.clicked.connect(self.run_analysis)
        button_bar.addWidget(run)
        self.save_btn = QPushButton("結果を実験記録に保存")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_result)
        button_bar.addWidget(self.save_btn)
        left_lay.addLayout(button_bar)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setPlaceholderText("CSVを選択して『解析』を押すと結果が表示されます。")
        left_lay.addWidget(self.summary, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(2, 2, 2, 2)
        graph_title = QLabel("加速度・気圧グラフ（赤=真の接地、緑=ログ中の検知）")
        graph_title.setWordWrap(True)
        right_lay.addWidget(graph_title)
        self.plot = TimePlot()
        right_lay.addWidget(self.plot, 1)
        self.plot_note = QLabel("グラフはCSVのセンサー列がある場合に表示されます。")
        self.plot_note.setWordWrap(True)
        right_lay.addWidget(self.plot_note)
        splitter.addWidget(right)
        splitter.setSizes([400, 650])

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(splitter)
        layout.addWidget(scroll, 1)

        self._csv_scroll = scroll
        self._csv_splitter = splitter
        self._csv_narrow = None
        self._update_responsive_layout()
        for signal in (self.truth_ms.textChanged, self.mode.currentIndexChanged,
                       self.delay_ms.valueChanged, self.code.textChanged,
                       self.tester.textChanged, self.scenario.textChanged):
            signal.connect(self.invalidate)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_csv_splitter"):
            self._update_responsive_layout()

    def _update_responsive_layout(self):
        narrow = self.width() < 900

        if self._csv_narrow == narrow:
            return

        self._csv_narrow = narrow
        splitter = self._csv_splitter

        splitter.setOrientation(
            Qt.Vertical if narrow else Qt.Horizontal
        )

        # 上下表示では両方の領域の高さを確保する
        splitter.setMinimumHeight(860 if narrow else 0)
        splitter.setSizes(
            [470, 390] if narrow else [400, 650]
        )

    def invalidate(self, *_):
        self.result = None
        self.save_btn.setEnabled(False)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "着地検知ログを選択", str(Path.home()), "CSV (*.csv)")
        if path:
            self.file_path = Path(path)
            self.path_text.setText(str(self.file_path))
            self.log = None
            self.invalidate()
            self.summary.setPlainText("CSVを選択しました。『CSVを解析』を押してください。")
            self.plot.set_data({"trace": []})
            if not self.scenario.text().strip():
                self.scenario.setText(self.file_path.stem)

    def run_analysis(self):
        if self.file_path is None:
            QMessageBox.information(self, "CSVを選択", "先にCSVログを選択してください。")
            return
        self.invalidate()
        try:
            self.log = read_csv(self.file_path)
            manual = self.truth_ms.text().strip()
            truth = float(manual) / 1000.0 if manual else None
            self.result = analyze(self.log, expected_time_s=truth,
                                  allowed_delay_s=self.delay_ms.value()/1000.0)
        except (OSError, ValueError, OverflowError) as exc:
            self.summary.setPlainText("解析できませんでした。")
            QMessageBox.warning(self, "CSV解析エラー", str(exc))
            return
        res = self.result
        note = (
            f"解析結果: {res['status']}\n"
            f"理由: {res['reason']}\n\n"
            f"ファイル: {self.log.source_name}\n"
            f"データ行数: {res['log_rows']}\n"
            f"真の接地時刻: {_time(res['true_contact_s'])}\n"
            f"CSVに記録された最初の検知: {_time(res['detected_time_s'])}\n"
            f"検知遅延: {_time(res['delay_s'])}\n"
            f"許容遅延: {_time(res['allowed_delay_s'])}\n"
            f"追加の立ち上がり回数: {res['extra_detection_events']}\n\n"
            "注意: CSVに書かれた値の解析です。実行したArduinoコード自体の正しさは保証しません。"
        )
        self.summary.setPlainText(note)
        self.plot.set_data({
            "trace": list(self.log.rows),
            "contact_time": res["true_contact_s"],
            "detected_time": res["detected_time_s"],
        })
        self.plot_note.setText(
            "赤い線は正解として与えられた時刻、緑の線はログに記録された検知時刻です。"
            " 正解時刻はCSVのtruth_contact列、または手入力から取得します。"
        )
        self.save_btn.setEnabled(True)

    def save_result(self):
        if self.result is None or self.file_path is None or self.log is None:
            return
        report = self.result
        source = self.mode.currentText()
        explanation = ("CSVに記録された着地判定を検証。"
                       "Arduinoプログラムの自動実行はしていません。"
                       "真の接地時刻は手入力またはCSVのtruth_contact列。")
        record = new_record(
            module="着地検知", mode=source,
            tester=self.tester.text().strip() or "未入力",
            scenario=self.scenario.text().strip() or self.file_path.stem,
            code_version=self.code.text().strip() or "未入力",
            status=report["status"],
            expected=f"接地後{report['allowed_delay_s']:.3f}秒以内に検知",
            observed=(f"判定時刻 {_time(report['detected_time_s'])} / {report['reason']}"),
            notes=explanation,
            metrics={k: report[k] for k in (
                "true_contact_s", "detected_time_s", "delay_s", "allowed_delay_s",
                "log_rows", "extra_detection_events", "starts_detected")},
        )
        try:
            add_record(record, [self.file_path])
            if self.on_saved:
                self.on_saved()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "実験記録への保存に失敗", str(exc))
            return
        self.save_btn.setEnabled(False)
        QMessageBox.information(
            self, "保存完了",
            "CSVと解析結果を実験台帳に保存しました。\n"
            "『結果ダッシュボード』に表示されます。\n"
            "GitHubへのアップロードは手動です。")
