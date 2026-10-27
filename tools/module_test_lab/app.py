"""CanSat Module Test Lab v3: standalone, GitHub/ZIP-sharable test ledger.
Run with an existing PySide6 venv; no ROS 2 import or service required.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QRect, QPointF, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QLineEdit, QLabel, QPushButton, QTextEdit, QPlainTextEdit,
    QDoubleSpinBox, QSpinBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox, QTabWidget, QSplitter,
    QHeaderView
)
from module_navigation import ModuleNavigation
from unified_results_tab import UnifiedResultsTab
from module_cpp_individual_tab import IndividualCppTab
from simulation_common_tab import SimulationCommonTab
from experiment_management_tab import ExperimentManagementTab
from landing_sim import Config, SCENARIOS, make_trace, reference_detect, CONTACT_TIME
from github_sync import GitHubSync, REPO_DEFAULT, BRANCH_DEFAULT
from dashboard import DashboardTab
from arduino_csv_tab import ArduinoCsvTab
from cpp_landing_tab import CppLandingTab
from landing_batch_tab import LandingBatchTab
from landing_compare_tab import LandingCompareTab
from landing_optimizer_tab import LandingOptimizerTab
from module_network_tab import ModuleNetworkTab
from cpp_module_tab import CppModuleTab
from module_fault_tab import ModuleFaultTab
from records import (
    DATA_DIR, ATTACHMENTS_DIR, load_records, new_record, add_record, store_trace,
    export_bundle, import_bundle, export_csv
)

MODULES = ["着地検知", "GNSS・姿勢", "モーター制御", "パラシュート分離",
           "クローラー展開", "通信・テレメトリ", "カメラ・経路探索", "統合", "その他"]
MODES = ["Arduino実機試験", "外部シミュレーション", "ROS 2統合試験", "その他"]
STATUSES = ["成功", "失敗", "未判定"]


def float_spin(value, low, high, decimals=2, suffix=""):
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(low, high)
    spin.setSingleStep(0.1 if decimals <= 2 else .01)
    spin.setValue(value)
    spin.setSuffix(suffix)
    return spin


class SensorPlot(QWidget):
    """Small dependency-free pair of timelines: IMU acceleration and pressure."""
    def __init__(self):
        super().__init__()
        self.trace = []
        self.result = None
        self.threshold = 12.5
        self.setMinimumSize(470, 350)

    def set_trace(self, trace, result, threshold):
        self.trace = trace
        self.result = result
        self.threshold = threshold
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        if not self.trace:
            p.setPen(QColor("#707984"))
            p.drawText(self.rect(), Qt.AlignCenter, "左側でシナリオを選び『実行』を押してください")
            p.end()
            return
        w, h = self.width(), self.height()
        left, right, top = 58, 20, 24
        width = max(100, w - left - right)
        panel_h = (h - 76) / 2
        end_t = max(1.0, self.trace[-1]["time_s"])

        def plot_panel(idx, title, data, color, minimum=None, maximum=None):
            y0 = top + idx * (panel_h + 28)
            box_h = panel_h - 10
            vals = [v for _, v in data]
            if not vals:
                return
            mn = min(vals) if minimum is None else minimum
            mx = max(vals) if maximum is None else maximum
            span = max(.001, mx - mn)
            mn -= span * .08
            mx += span * .08
            def xx(t): return left + width * float(t) / end_t
            def yy(v): return y0 + box_h - box_h * (v - mn) / (mx - mn)
            p.setPen(QPen(QColor("#e0e4e9"), 1))
            for i in range(5):
                gy = y0 + i * box_h / 4
                p.drawLine(QPointF(left, gy), QPointF(left+width, gy))
            p.setPen(QPen(QColor("#334155"), 1))
            p.drawRect(QRect(left, int(y0), int(width), int(box_h)))
            p.setPen(QColor("#172c48"))
            p.setFont(QFont("Sans Serif", 9, QFont.Bold))
            p.drawText(left, int(y0 - 6), title)
            p.setFont(QFont("Sans Serif", 8))
            p.drawText(4, int(y0 + 12), f"{mx:.0f}")
            p.drawText(4, int(y0 + box_h), f"{mn:.0f}")
            if idx == 0:
                threshold_y = yy(self.threshold)
                if y0 <= threshold_y <= y0+box_h:
                    p.setPen(QPen(QColor("#ec9b2f"), 1, Qt.DashLine))
                    p.drawLine(QPointF(left, threshold_y), QPointF(left+width, threshold_y))
            for event_t, ev_color in [(CONTACT_TIME, "#d04b39"),
                                       (self.result.get("detected_time_s") if self.result else None, "#1a9976")]:
                if event_t is None: continue
                p.setPen(QPen(QColor(ev_color), 1.5, Qt.DashLine))
                xxv = xx(event_t)
                p.drawLine(QPointF(xxv, y0), QPointF(xxv, y0+box_h))
            p.setPen(QPen(QColor(color), 2.1))
            last = None
            for t, v in data:
                pt = QPointF(xx(t), yy(v))
                if last is not None:
                    p.drawLine(last, pt)
                last = pt
            p.setPen(QColor("#586475"))
            for i in range(5):
                t = i * end_t / 4
                p.drawText(int(xx(t)-8), int(y0+box_h+14), f"{t:.0f}")
            p.drawText(int(left + width - 10), int(y0+box_h+24), "秒")

        plot_panel(0, "IMU Z加速度 (m/s²)",
                   [(r["time_s"], r["imu_z_mps2"]) for r in self.trace], "#2476c8")
        plot_panel(1, "BME280 気圧 (Pa)",
                   [(r["time_s"], r["pressure_pa"]) for r in self.trace if r["pressure_pa"] is not None], "#7f62b1")
        p.end()


class ManualRecordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("チームメンバーの実験結果を登録")
        self.resize(550, 480)
        self.attachment = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.module = QComboBox(); self.module.addItems(MODULES)
        self.mode = QComboBox(); self.mode.addItems(MODES)
        self.tester = QLineEdit(); self.tester.setPlaceholderText("例：制御班 A")
        self.scenario = QLineEdit(); self.scenario.setPlaceholderText("例：落下試験 No.3")
        self.code = QLineEdit(); self.code.setPlaceholderText("例：landing_v03 / Git commit ID")
        self.status = QComboBox(); self.status.addItems(STATUSES)
        self.expected = QLineEdit(); self.expected.setPlaceholderText("想定される動作")
        self.observed = QLineEdit(); self.observed.setPlaceholderText("実際に確認した動作・測定値")
        self.note = QTextEdit(); self.note.setMaximumHeight(90)
        for label, widget in [("担当機能", self.module), ("実験方法", self.mode),
                              ("実験者", self.tester), ("試験ケース", self.scenario),
                              ("コード版", self.code), ("結果", self.status),
                              ("期待する動作", self.expected), ("観測結果", self.observed),
                              ("メモ", self.note)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        attach_row = QHBoxLayout()
        self.attach_label = QLabel("ログ添付なし（任意）")
        choose = QPushButton("CSV / TXT / LOGを添付")
        choose.clicked.connect(self.choose_attachment)
        attach_row.addWidget(choose); attach_row.addWidget(self.attach_label, 1)
        layout.addLayout(attach_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_attachment(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "実験ログを選択", "", "ログ (*.csv *.txt *.log *.json);;すべてのファイル (*)")
        if path:
            self.attachment = Path(path)
            self.attach_label.setText(self.attachment.name)

    def get_record(self):
        return new_record(module=self.module.currentText(), mode=self.mode.currentText(),
                          tester=self.tester.text().strip(), scenario=self.scenario.text().strip(),
                          code_version=self.code.text().strip(), status=self.status.currentText(),
                          expected=self.expected.text().strip(), observed=self.observed.text().strip(),
                          notes=self.note.toPlainText().strip())


class GitHubSyncWorker(QThread):
    """Network synchronization runs outside the UI thread."""
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, action: str, ids: list[str] | None = None):
        super().__init__()
        self.action = action
        self.ids = ids or []

    def run(self):
        try:
            sync = GitHubSync(REPO_DEFAULT, BRANCH_DEFAULT)
            if self.action == "check":
                result = {"connection": sync.check_access()}
            elif self.action == "upload":
                result = sync.upload(self.ids)
            elif self.action == "download":
                result = sync.download()
            else:
                raise ValueError("Unknown synchronization action")
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class TestLab(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CanSat Module Test Lab  |  個別実験と結果集約")
        self.resize(1120, 770)
        self.setStyleSheet("""
            QMainWindow { background: #f6f8fc; }
            QGroupBox { font-weight: bold; border: 1px solid #d5dce6;
                        border-radius: 7px; margin-top: 13px; padding: 12px; background: white; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 3px; }
            QPushButton { padding: 7px 11px; }
            QTableWidget { background: white; gridline-color: #e6e9ef; }
        """)
        self.trace = None
        self.reference_result = None
        self._sync_worker = None
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        h = QLabel("CanSat Module Test Lab")
        h.setStyleSheet("font-size: 22px; font-weight: bold; color: #17365e; margin: 5px 0;")
        outer.addWidget(h)
        info = QLabel("統合ROS 2シミュレーターとは独立した実験環境  |  結果をZIP / GitHubで共有 → 1か所に集約")
        info.setStyleSheet("color: #526274; margin-bottom: 8px;")
        outer.addWidget(info)
        self.navigation = ModuleNavigation(self); outer.addWidget(self.navigation, 1); self.tabs = self.navigation.tabs
        self.build_sim_tab(); self.build_ledger_tab(); self.build_dashboard_tab(); self.build_arduino_csv_tab(); self.build_cpp_landing_tab(); self.build_landing_batch_tab(); self.build_landing_compare_tab(); self.build_landing_optimizer_tab(); self.build_module_network_tab(); self.build_cpp_module_tab(); self.build_module_fault_tab(); self.build_unified_results_tab(); self.build_individual_cpp_tab(); self.build_simulation_common_tab(); self.build_experiment_management_tab(); self.build_guide_tab()
        self.refresh_ledger()

    def build_sim_tab(self):
        tab = QWidget(); self.tabs.addTab(tab, "着地検知シミュレーション")
        horizontal = QHBoxLayout(tab)
        left = QWidget(); left.setMaximumWidth(360)
        left_lay = QVBoxLayout(left)
        setup = QGroupBox("仮想センサーデータの条件")
        form = QFormLayout(setup)
        self.scenario = QComboBox()
        for name, (title, _) in SCENARIOS.items(): self.scenario.addItem(title, name)
        self.tester = QLineEdit("")
        self.tester.setPlaceholderText("実験者・担当者（任意）")
        self.impact = float_spin(12.5, 1, 100, 2, " m/s²")
        self.descent = float_spin(2, .01, 100, 2, " Pa")
        self.stable = float_spin(.5, 0, 20, 2, " Pa")
        self.stable_count = QSpinBox(); self.stable_count.setRange(1, 10); self.stable_count.setValue(3)
        for label, widget in [("ケース", self.scenario), ("実験者", self.tester),
                              ("IMU衝撃しきい値", self.impact), ("下降時の気圧変化", self.descent),
                              ("気圧安定しきい値", self.stable), ("安定確認の回数", self.stable_count)]:
            form.addRow(label, widget)
        left_lay.addWidget(setup)
        run = QPushButton("▶ 参考アルゴリズムで実行")
        run.clicked.connect(self.run_reference)
        self.save_reference = QPushButton("この結果を台帳に保存")
        self.save_reference.setEnabled(False)
        self.save_reference.clicked.connect(self.record_reference)
        left_lay.addWidget(run); left_lay.addWidget(self.save_reference)
        self.sim_result = QPlainTextEdit(); self.sim_result.setReadOnly(True)
        self.sim_result.setMinimumHeight(180)
        left_lay.addWidget(self.sim_result, 1)
        desc = QLabel("※これは仮の参考判定アルゴリズムです。\nESP32-S3の実際の .ino コードは実行していません。")
        desc.setWordWrap(True); desc.setStyleSheet("color: #8a5020;")
        left_lay.addWidget(desc)
        horizontal.addWidget(left)
        graph_container = QGroupBox("仮想データと判定結果  （赤線＝接地、緑線＝判定）")
        gr = QVBoxLayout(graph_container)
        self.plot = SensorPlot(); gr.addWidget(self.plot)
        horizontal.addWidget(graph_container, 1)

    def run_reference(self):
        code = self.scenario.currentData()
        cfg = Config(self.impact.value(), self.descent.value(), self.stable.value(), self.stable_count.value())
        trace = make_trace(code)
        result = reference_detect(trace, cfg)
        self.trace = trace
        self.reference_result = result
        self.reference_cfg = cfg
        self.plot.set_trace(trace, result, cfg.impact_threshold)
        name, description = SCENARIOS[code]
        dt = result['detected_time_s']
        self.sim_result.setPlainText(
            f"シナリオ：{name}\n{description}\n\n"
            f"真の接地時刻：{CONTACT_TIME:.1f} 秒\n"
            f"参考判定：{'成功' if result['passed'] else '失敗'}\n"
            f"判定時刻：{'未検知' if dt is None else str(dt) + ' 秒'}\n"
            f"検知遅延：{result['delay_s'] if dt is not None else '—'} 秒\n"
            f"衝撃候補時刻：{result['impact_events_s']}\n\n"
            "※正解はシナリオ生成時に既知の接地時刻です。\n"
            "※Arduinoの担当者が作ったコードの動作結果ではありません。"
        )
        self.save_reference.setEnabled(True)

    def record_reference(self):
        if not self.trace or not self.reference_result: return
        code = self.scenario.currentData()
        title = SCENARIOS[code][0]
        r = self.reference_result
        record = new_record(
            tester=self.tester.text().strip() or "未入力",
            mode="仮想参考モデル", module="着地検知", scenario=title,
            code_version="landing_sim.py 参考モデル v1（Arduino非実行）",
            status="成功" if r["passed"] else "失敗",
            expected=f"真の接地10.0秒以降、15.0秒までに検知",
            observed=(f"検知時刻 {r['detected_time_s']} 秒" if r['detected_time_s'] is not None else "未検知"),
            notes="参考シミュレーション。実機試験結果ではありません。",
            metrics={"detected_time_s": r["detected_time_s"], "delay_s": r["delay_s"],
                     "true_contact_s": CONTACT_TIME,
                     "imu_threshold_mps2": self.reference_cfg.impact_threshold,
                     "pressure_descent_pa": self.reference_cfg.descent_delta_pa,
                     "pressure_stable_pa": self.reference_cfg.stable_delta_pa,
                     "stable_samples": self.reference_cfg.stable_samples},
        )
        try:
            store_trace(record, self.trace)
            add_record(record)
            self.refresh_ledger()
            self.save_reference.setEnabled(False)
            QMessageBox.information(self, "保存完了", "参考判定の結果と仮想センサーデータを保存しました。\n『実験記録』タブで確認できます。")
        except Exception as exc:
            QMessageBox.critical(self, "保存エラー", str(exc))

    def build_ledger_tab(self):
        tab = QWidget(); self.tabs.addTab(tab, "実験記録・チーム共有")
        lay = QVBoxLayout(tab)
        self.summary = QLabel("")
        self.summary.setStyleSheet("font-weight: bold; color: #17365e; padding: 9px;")
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        actions = [("＋ 実機・外部試験を登録", self.add_manual),
                   ("選択結果を共有ZIPに出力", self.share_selected),
                   ("共有ZIPを取り込む", self.import_shared),
                   ("CSVで全結果を出力", self.export_table),
                   ("更新", self.refresh_ledger)]
        for name, callback in actions:
            b = QPushButton(name); b.clicked.connect(callback); row.addWidget(b)
        lay.addLayout(row)
        github_row = QHBoxLayout()
        self.github_location = QLabel(f"GitHub保存先: {REPO_DEFAULT} / {BRANCH_DEFAULT}")
        self.github_location.setStyleSheet("color: #17365e; font-weight: bold;")
        github_row.addWidget(self.github_location, 1)
        self.github_buttons = []
        for label, action in [("接続確認", "check"),
                              ("選択結果をGitHubに送信", "upload"),
                              ("チーム結果をGitHubから取得", "download")]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, a=action: self.start_github_sync(a))
            self.github_buttons.append(button)
            github_row.addWidget(button)
        lay.addLayout(github_row)
        self.github_status = QLabel("GitHub同期は手動実行です。gh auth login済みのアカウントを使用します。")
        self.github_status.setStyleSheet("color: #566576;")
        lay.addWidget(self.github_status)
        self.table = QTableWidget()
        cols = ["日時", "モジュール", "実験方法", "担当者", "試験ケース", "コード版", "結果", "観測値", "ID"]
        self.table.setColumnCount(len(cols)); self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for i, w in enumerate([155,100,150,90,125,170,70,205,160]):
            self.table.setColumnWidth(i, w)
        self.table.setAlternatingRowColors(True)
        lay.addWidget(self.table, 1)
        note = QLabel("共有ZIPとGitHub同期を併用できます。GitHubに送信する前にログ中の秘密情報を確認してください。同一IDは上書きしません。")
        note.setStyleSheet("color: #566576;")
        lay.addWidget(note)

    def build_simulation_common_tab(self):
        self.simulation_common_tab = SimulationCommonTab()
        self.tabs.addTab(self.simulation_common_tab, 'シミュレーション共通基盤')

    def build_experiment_management_tab(self):
        self.experiment_management_tab = ExperimentManagementTab(
            config_provider=self.simulation_common_tab._read_config,
            open_config_tab=lambda: self.navigation.open_tab(
                self.tabs.indexOf(self.simulation_common_tab)),
        )
        self.tabs.addTab(self.experiment_management_tab, 'v12 実験管理・一括比較')

    def build_individual_cpp_tab(self):
        self.individual_cpp_tab = IndividualCppTab()
        self.tabs.addTab(self.individual_cpp_tab, "Main・CAM・Drive C++個別試験")

    def build_unified_results_tab(self):
        self.unified_results_tab = UnifiedResultsTab(self)
        self.tabs.addTab(self.unified_results_tab, "統合実験結果")

    def build_module_fault_tab(self):
        self.module_fault_tab = ModuleFaultTab()
        self.tabs.addTab(self.module_fault_tab, "異常分析")

    def build_cpp_module_tab(self):
        self.cpp_module_tab = CppModuleTab()
        self.tabs.addTab(self.cpp_module_tab, "C++モジュール連携")

    def build_module_network_tab(self):
        self.module_network_tab = ModuleNetworkTab()
        self.tabs.addTab(self.module_network_tab, "3モジュール・仮想CAN")

    def build_landing_optimizer_tab(self):
        self.landing_optimizer_tab = LandingOptimizerTab(on_saved=self.refresh_ledger)
        self.tabs.addTab(self.landing_optimizer_tab, "着地パラメータ探索")

    def build_landing_compare_tab(self):
        self.landing_compare_tab = LandingCompareTab(on_saved=self.refresh_ledger)
        self.tabs.addTab(self.landing_compare_tab, "着地コード比較")

    def build_landing_batch_tab(self):
        self.landing_batch_tab = LandingBatchTab(on_saved=self.refresh_ledger)
        self.tabs.addTab(self.landing_batch_tab, "着地一括テスト")

    def build_cpp_landing_tab(self):
        self.cpp_landing_tab = CppLandingTab(on_saved=self.refresh_ledger)
        self.tabs.addTab(self.cpp_landing_tab, "C++着地判定")

    def build_arduino_csv_tab(self):
        self.arduino_csv_tab = ArduinoCsvTab(on_saved=self.refresh_ledger)
        self.tabs.addTab(self.arduino_csv_tab, "Arduino/CSVログ解析")

    def build_dashboard_tab(self):
        self.dashboard = DashboardTab(on_download=self.start_github_sync)
        self.tabs.addTab(self.dashboard, "結果ダッシュボード")

    def refresh_ledger(self):
        try: self.records = sorted(load_records(), key=lambda x: x.get("created_at", ""), reverse=True)
        except Exception as exc:
            QMessageBox.critical(self, "台帳エラー", str(exc)); return
        self.table.setRowCount(len(self.records))
        for i, rec in enumerate(self.records):
            cells = [rec.get("created_at", "")[:19], rec.get("module", ""), rec.get("mode", ""),
                     rec.get("tester", ""), rec.get("scenario", ""), rec.get("code_version", ""),
                     rec.get("status", ""), rec.get("observed", ""), rec.get("id", "")[:12]]
            for j, value in enumerate(cells):
                item = QTableWidgetItem(str(value))
                if j == 6 and str(value) == "成功": item.setForeground(QBrush(QColor("#15803d")))
                if j == 6 and str(value) == "失敗": item.setForeground(QBrush(QColor("#b91c1c")))
                self.table.setItem(i, j, item)
        success = sum(r.get("status") == "成功" for r in self.records)
        failed = sum(r.get("status") == "失敗" for r in self.records)
        self.summary.setText(f"保存済み {len(self.records)} 件   |   成功 {success} 件   |   失敗 {failed} 件   |   未判定 {len(self.records)-success-failed} 件   |   データ保存先: {DATA_DIR}")
        if hasattr(self, "dashboard"):
            self.dashboard.reload(self.records)

    def add_manual(self):
        dialog = ManualRecordDialog(self)
        if dialog.exec() != QDialog.Accepted: return
        record = dialog.get_record()
        try:
            add_record(record, [dialog.attachment] if dialog.attachment else [])
            self.refresh_ledger()
            QMessageBox.information(self, "保存", "実験記録を保存しました。")
        except Exception as exc:
            QMessageBox.critical(self, "保存エラー", str(exc))

    def selected_ids(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return [self.records[i]["id"] for i in rows]

    def share_selected(self):
        ids = self.selected_ids()
        if not ids:
            QMessageBox.information(self, "選択", "共有する結果の行を選択してください。複数選択できます。")
            return
        suggested = str(Path.home() / "cansat-module-results.zip")
        path, _ = QFileDialog.getSaveFileName(self, "チーム共有ZIPの保存先", suggested, "ZIP (*.zip)")
        if not path: return
        try:
            n = export_bundle(ids, Path(path))
            QMessageBox.information(self, "共有ファイル作成", f"{n}件をZIPにまとめました。\n{path}\nこのZIPを相手へ渡してください。")
        except Exception as exc:
            QMessageBox.critical(self, "共有エラー", str(exc))

    def import_shared(self):
        path, _ = QFileDialog.getOpenFileName(self, "相手から受け取ったZIPを選択", "", "ZIP (*.zip)")
        if not path: return
        try:
            r = import_bundle(Path(path))
            self.refresh_ledger()
            QMessageBox.information(self, "集約完了",
                f"追加: {r['added']}件\n同一IDで重複スキップ: {r['skipped']}件\n内容が異なる同一ID（未上書き）: {r['conflicts']}件")
        except Exception as exc:
            QMessageBox.critical(self, "取り込みエラー", str(exc))

    def start_github_sync(self, action):
        if self._sync_worker is not None:
            return
        ids = self.selected_ids() if action == "upload" else []
        if action == "upload" and not ids:
            QMessageBox.information(self, "実験を選択", "GitHubに送信する実験結果の行を選択してください。")
            return
        if action == "upload":
            question = (f"{len(ids)}件の実験結果を非公開リポジトリ {REPO_DEFAULT} の "
                        f"{BRANCH_DEFAULT} ブランチへ直接追加します。\n"
                        "添付ログも送信されます。個人情報・認証情報を含まないか確認しましたか？\n"
                        "同じ実験IDの既存記録は上書きしません。")
            if QMessageBox.question(self, "GitHub送信の確認", question,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        for btn in self.github_buttons:
            btn.setEnabled(False)
        self.github_status.setText("GitHubと通信しています。完了するまでアプリを閉じないでください。")
        worker = GitHubSyncWorker(action, ids)
        self._sync_worker = worker
        worker.succeeded.connect(lambda result, a=action: self._on_sync_success(a, result))
        worker.failed.connect(self._on_sync_failure)
        worker.finished.connect(self._on_sync_finish)
        worker.start()

    def _on_sync_success(self, action, result):
        if action == "check":
            msg = f"GitHub接続に成功しました。\n{result['connection']}"
        elif action == "upload":
            msg = (f"送信した実験: {result['uploaded']}件\n"
                   f"登録済みで送信不要: {result['skipped']}件\n"
                   "GitHub上の experiments/records に記録されます。")
        else:
            self.refresh_ledger()
            msg = (f"GitHub上の実験: {result['remote']}件\n"
                   f"新規取り込み: {result['added']}件\n"
                   f"同一IDの重複: {result['skipped']}件\n"
                   f"同一IDで内容が異なる記録（未上書き）: {result['conflicts']}件")
        self.github_status.setText(msg.replace("\n", "  |  "))
        QMessageBox.information(self, "GitHub同期結果", msg)

    def _on_sync_failure(self, message):
        self.github_status.setText("GitHub同期に失敗しました。ローカルの実験台帳は残っています。")
        QMessageBox.warning(self, "GitHub同期エラー", message)

    def _on_sync_finish(self):
        for btn in self.github_buttons:
            btn.setEnabled(True)
        worker = self._sync_worker
        self._sync_worker = None
        if worker is not None:
            worker.deleteLater()

    def closeEvent(self, event):
        if self._sync_worker is not None and self._sync_worker.isRunning():
            event.ignore()
            QMessageBox.information(self, "GitHub同期中", "通信が完了してからアプリを閉じてください。")
            return
        super().closeEvent(event)

    def export_table(self):
        path, _ = QFileDialog.getSaveFileName(self, "集計CSVの保存先", str(Path.home()/"cansat-experiment-summary.csv"), "CSV (*.csv)")
        if not path: return
        try:
            n = export_csv(Path(path))
            QMessageBox.information(self, "CSV出力", f"全{n}件を書き出しました。\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "CSV出力エラー", str(exc))

    def build_guide_tab(self):
        tab = QWidget(); self.tabs.addTab(tab, "使い方・Arduinoとの接続")
        layout = QVBoxLayout(tab)
        text = QPlainTextEdit(); text.setReadOnly(True)
        text.setPlainText("""【役割分担】
・Arduino IDEの実機プログラムは担当者が開発します。
・このアプリは統合ROS 2/RViz2シミュレーターとは別物です。
・この版では、仮想IMU/BME280の参考判定、CSVログ解析、実験記録の集約を提供します。
・.inoをそのまま読み込んで実行する機能は、まだありません。

【試験の流れ】
1. 参考判定を試したい場合は「着地検知シミュレーション」で条件を選びます。
2. 「参考アルゴリズムで実行」を押し、グラフ・結果を確認します。
3. 保存すると、条件・判定時刻・入力トレースCSVが記録されます。
4. Arduino担当者の実験は「実験記録」で「実機・外部試験を登録」を選び、コード版とログを記入します。
5. チームに送る結果を選び、共有ZIPを出力します。
6. 集約担当者は共有ZIPを取り込み、CSVで全結果を出力します。

【GitHub共有（v2）】
・Ubuntuで gh auth login 済みであることを確認してください。
・「接続確認」で CanSat-INO/INO の参照権限を確認します。
・記録行を選んで「選択結果をGitHubに送信」→ 内容確認 → 送信します。
・他メンバーの実験は「チーム結果をGitHubから取得」で取り込みます。
・保存先は非公開リポジトリ CanSat-INO/INO の main ブランチです。
・個々の実験を experiments/records/ID.json に独立して保存します。
・添付は experiments/attachments/ID/ 配下に保存します（1ファイル900KB以内）。
・ローカル記録は ~/cansat_module_lab_data に残り、既存IDは上書きしません。
・GitHub同期は手動実行であり、操作しない限りアップロードしません。
・ソースコードのGit操作やGitHub Projectsの更新はしません。

【Arduino/外部CSVログ解析（v4）】
・対応するCSVを取り込み、着地検知と接地の正解時刻を比較します。
・解析結果は実験台帳に保存し、従来どおりGitHubへ手動共有できます。
ファイル名例: landing_run_003.csv
列名: time_ms,imu_z_mps2,pressure_pa,landing_detected
単位: ミリ秒, m/s^2, Pa, 0または1

【C++着地判定のホストPC試験（v4 第2段階）】
・Arduinoの判定部分を分離した信頼できるC++ファイル(.cpp)をg++で実行します。
・CSVのIMU値をC++に入力し、得られた判定を接地時刻と比較します。
・Arduino/ESP32のハードウェア依存APIや.ino全体の実行には対応しません。
・コードはPCで実行されるため、信頼できるファイルのみ選択してください。

【記録すること】
モジュール名、試験ケース、担当者、コード版/Git commit、期待する動作、
実測結果、成功/失敗、ログ。実際のマイコンの試験と仮想参考モデルを混同しないでください。

【ファイルの保存先】
~/cansat_module_lab_data/records.json
~/cansat_module_lab_data/attachments/

【次期拡張】
実機依存部を分離したArduino C++判定ロジックの仮想実行、
シリアルログのリアルタイム受信などを追加します。

【注意】
共有ZIPおよびGitHubの実験記録は実験データです。実行形式のコードを自動実行しません。
個人情報・秘密情報が含まれるログは、共有前に内容を確認してください。""")
        layout.addWidget(text)


def main():
    import gc

    app = QApplication([])
    window = TestLab()

    # Qt終了時にウィンドウの削除を予約する
    app.aboutToQuit.connect(window.deleteLater)

    window.show()

    result = app.exec()

    # Python終了前に参照を整理する
    del window
    gc.collect()

    del app
    gc.collect()

    raise SystemExit(result)


if __name__ == "__main__":
    main()
