"""GUI for opt-in, local, trusted C++ landing logic evaluation (no Arduino SDK)."""
from __future__ import annotations
import csv
from pathlib import Path
import tempfile

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QLabel, QPushButton, QPlainTextEdit, QFileDialog,
    QMessageBox, QDoubleSpinBox, QSplitter,
)
from PySide6.QtCore import Qt

from cpp_landing_runner import DEMO_SOURCE, run_landing_cpp
from dashboard import TimePlot
from records import new_record, add_record


def _fmt(t):
    return "未取得" if t is None else f"{t:.3f}秒"


class CppLandingTab(QWidget):
    def __init__(self, on_saved=None, parent=None):
        super().__init__(parent)
        self.on_saved = on_saved
        self.input_path = None
        self.current_result = None
        outer = QVBoxLayout(self)
        title = QLabel("C++着地判定 / ホストPC試験（v4 第2段階）")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #17365e")
        outer.addWidget(title)
        hint = QLabel(
            "選択したローカルのC++判定コードをg++でコンパイルし、CSVの加速度・気圧値を順番に入力します。"
            " .ino全体やESP32固有APIは実行できません。信頼できるC++ファイルだけを選んでください。"
        )
        hint.setWordWrap(True)
        outer.addWidget(hint)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(2, 2, 2, 2)
        grp = QGroupBox("試験するコードとセンサーログ")
        form = QFormLayout(grp)
        csv_row = QWidget()
        csv_layout = QHBoxLayout(csv_row)
        csv_layout.setContentsMargins(0, 0, 0, 0)
        self.csv_path_label = QLineEdit()
        self.csv_path_label.setReadOnly(True)
        self.csv_path_label.setPlaceholderText("time_ms, imu_z_mps2 を含むCSV")
        csv_layout.addWidget(self.csv_path_label, 1)
        choose_csv_btn = QPushButton("参照…")
        choose_csv_btn.clicked.connect(self.select_csv)
        csv_layout.addWidget(choose_csv_btn)
        form.addRow("センサーCSV", csv_row)
        cpp_row = QWidget()
        cpp_layout = QHBoxLayout(cpp_row)
        cpp_layout.setContentsMargins(0, 0, 0, 0)
        self.cpp_path = QLineEdit(str(DEMO_SOURCE))
        self.cpp_path.setReadOnly(True)
        cpp_layout.addWidget(self.cpp_path, 1)
        choose_cpp_btn = QPushButton("参照…")
        choose_cpp_btn.clicked.connect(self.select_cpp)
        cpp_layout.addWidget(choose_cpp_btn)
        form.addRow("C++判定コード", cpp_row)
        self.tester = QLineEdit()
        self.tester.setPlaceholderText("例：着地検知担当")
        form.addRow("担当者", self.tester)
        self.scenario = QLineEdit()
        self.scenario.setPlaceholderText("例：正常着地・C++試験")
        form.addRow("試験ケース", self.scenario)
        self.version = QLineEdit()
        self.version.setPlaceholderText("例：landing_logic_v01 / commit")
        form.addRow("コードバージョン", self.version)
        self.truth = QLineEdit()
        self.truth.setPlaceholderText("任意。空欄ならCSVのtruth_contact列を使用")
        form.addRow("接地正解時刻（ms）", self.truth)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setDecimals(0)
        self.tolerance.setRange(0, 600000)
        self.tolerance.setValue(5000)
        self.tolerance.setSuffix(" ms")
        form.addRow("検知許容遅延", self.tolerance)
        left_layout.addWidget(grp)
        buttons = QHBoxLayout()
        run_btn = QPushButton("▶ C++コードを実行・評価")
        run_btn.clicked.connect(self.run_code)
        buttons.addWidget(run_btn)
        self.save_btn = QPushButton("結果を実験記録へ保存")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        buttons.addWidget(self.save_btn)
        left_layout.addLayout(buttons)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText("CSVを選び、C++判定コードを実行してください。")
        left_layout.addWidget(self.report, 1)
        split.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.addWidget(QLabel("計算結果グラフ（赤=接地時刻、緑=C++判定時刻）"))
        self.plot = TimePlot()
        right_layout.addWidget(self.plot, 1)
        right_info = QLabel("入力ログのlanding_detected列は無視し、C++の判定値で置き換えます。")
        right_info.setWordWrap(True)
        right_layout.addWidget(right_info)
        split.addWidget(right)
        split.setSizes([440, 650])
        outer.addWidget(split, 1)
        for signal in (self.tester.textChanged, self.scenario.textChanged,
                       self.version.textChanged, self.truth.textChanged,
                       self.tolerance.valueChanged):
            signal.connect(self.invalidate)

    def invalidate(self, *_):
        self.current_result = None
        self.save_btn.setEnabled(False)

    def select_csv(self):
        chosen, _ = QFileDialog.getOpenFileName(self, "センサーCSVを選択",
                                                str(Path.home()), "CSV (*.csv)")
        if chosen:
            self.input_path = Path(chosen)
            self.csv_path_label.setText(chosen)
            self.invalidate()
            self.plot.set_data({"trace": []})
            if not self.scenario.text().strip():
                self.scenario.setText(self.input_path.stem)

    def select_cpp(self):
        chosen, _ = QFileDialog.getOpenFileName(
            self, "信頼できるC++判定関数を選択", str(DEMO_SOURCE.parent), "C++ (*.cpp)")
        if chosen:
            self.cpp_path.setText(chosen)
            self.invalidate()

    def run_code(self):
        self.invalidate()
        if self.input_path is None:
            QMessageBox.information(self, "入力CSV", "先にセンサーCSVを選択してください。")
            return
        try:
            raw_truth = self.truth.text().strip()
            manual_truth = float(raw_truth) / 1000.0 if raw_truth else None
            result = run_landing_cpp(
                self.input_path, self.cpp_path.text(), manual_truth_s=manual_truth,
                allowed_delay_s=self.tolerance.value() / 1000.0,
            )
        except (OSError, ValueError, csv.Error) as exc:
            self.report.setPlainText("コンパイル・実行・解析に失敗しました。")
            QMessageBox.warning(self, "C++ホスト試験エラー", str(exc))
            return
        self.current_result = result
        result_data = result.summary
        self.report.setPlainText(
            f"C++実行評価: {result_data['status']}\n"
            f"理由: {result_data['reason']}\n\n"
            f"入力CSV: {result.original_name}\n"
            f"コンパイルしたコード: {result.source_name}\n"
            f"コードSHA256: {result.source_sha256}\n"
            f"データ行数: {result_data['log_rows']}\n"
            f"接地正解時刻: {_fmt(result_data['true_contact_s'])}\n"
            f"C++の最初の検知時刻: {_fmt(result_data['detected_time_s'])}\n"
            f"検知遅延: {_fmt(result_data['delay_s'])}\n"
            f"許容遅延: {_fmt(result_data['allowed_delay_s'])}\n\n"
            "これはホストPCでの単体試験です。ESP32-S3実機動作の保証ではありません。"
        )
        self.plot.set_data({
            "trace": list(result.log.rows),
            "contact_time": result_data["true_contact_s"],
            "detected_time": result_data["detected_time_s"],
        })
        self.save_btn.setEnabled(True)

    def save(self):
        if self.current_result is None or self.input_path is None:
            return
        result = self.current_result
        data = result.summary
        rec = new_record(
            module="着地検知", mode="外部シミュレーション",
            tester=self.tester.text().strip() or "未入力",
            scenario=self.scenario.text().strip() or self.input_path.stem,
            code_version=self.version.text().strip() or result.source_name,
            status=data["status"],
            expected=f"接地後{data['allowed_delay_s']:.3f}秒以内に着地検知",
            observed=f"C++検知時刻 {_fmt(data['detected_time_s'])} / {data['reason']}",
            notes=("ホストPC上で信頼できるC++判定ロジックを実行。"
                   "ESP32-S3実機試験ではない。"
                   f" C++ファイル={result.source_name} SHA256={result.source_sha256}. "
                   "元のC++コードそのものは添付していません。"),
            metrics={**{k: data[k] for k in (
                "true_contact_s", "detected_time_s", "delay_s", "allowed_delay_s",
                "log_rows", "extra_detection_events", "starts_detected")},
                "code_sha256": result.source_sha256},
        )
        try:
            with tempfile.TemporaryDirectory(prefix="cansat-cpp-result-") as dirname:
                result_csv = Path(dirname) / "cpp_landing_output.csv"
                result_csv.write_text(result.csv_text, encoding="utf-8")
                add_record(rec, [result_csv, self.input_path])
            if self.on_saved:
                self.on_saved()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "保存エラー", str(exc))
            return
        self.save_btn.setEnabled(False)
        QMessageBox.information(self, "保存完了",
            "C++出力CSVと入力CSV、評価結果を保存しました。"
            " 結果ダッシュボードから確認できます。GitHubへは自動送信されません。")
