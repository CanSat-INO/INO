"""CanSat Module Test Lab v3: standalone, GitHub/ZIP-sharable test ledger.
Run with an existing PySide6 venv; no ROS 2 import or service required.
"""
from __future__ import annotations
import sys
from pathlib import Path
from project_store import export_path
import zipfile
from datetime import datetime

from project_store import bootstrap_cli
if __name__ == "__main__":
    bootstrap_cli()

from PySide6.QtCore import Qt, QRect, QPointF, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QLineEdit, QLabel, QPushButton, QTextEdit, QPlainTextEdit,
    QDoubleSpinBox, QSpinBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox, QTabWidget, QSplitter,
    QHeaderView
)
from gui_theme_v13 import MAIN_STYLESHEET, style_action_buttons
from module_navigation import ModuleNavigation
from unified_results_tab import UnifiedResultsTab
from module_cpp_individual_tab import IndividualCppTab
from v14_host_tab import HostCppV14Tab
from v14_1_logic_tab import PortableModulesTab
from v15_sensor_tab import SensorCsvV15Tab
from v16_experiment_tab import ExperimentJournalV16Tab
from v17_phase_tab import PhaseSimulationV17Tab
from v18_bus_tab import VirtualBusV18Tab
from v19_compare_tab import ExperimentCompareV19Tab
from v20_workflow_tab import WorkflowV20Tab
from v21_quality_tab import QualityV21Tab
from simulation_common_tab import SimulationCommonTab
from experiment_management_tab import ExperimentManagementTab
from landing_sim import Config, SCENARIOS, make_trace, reference_detect, CONTACT_TIME
from github_sync import GitHubSync, REPO_DEFAULT, BRANCH_DEFAULT
from record_trash import delete_selected, restore_archive, TrashError
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

    def __init__(self, action: str, ids: list[str] | None = None, destination=None):
        super().__init__()
        self.action = action
        self.ids = ids or []
        self.destination = destination or (REPO_DEFAULT,BRANCH_DEFAULT)

    def run(self):
        try:
            sync = GitHubSync(*self.destination)
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
    ledger_changed = Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CanSat Module Test Lab  |  個別実験と結果集約")
        self.resize(1120, 770)
        self.setStyleSheet(MAIN_STYLESHEET)
        self.trace = None
        self.reference_result = None
        self._sync_worker = None
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        h = QLabel("CanSat Module Test Lab")
        h.setObjectName("moduleLabTitle")
        outer.addWidget(h)
        info = QLabel("統合ROS 2シミュレーターとは独立した実験環境  |  結果をZIP / GitHubで共有 → 1か所に集約")
        info.setObjectName("moduleLabSubtitle")
        outer.addWidget(info)
        self.navigation = ModuleNavigation(self); outer.addWidget(self.navigation, 1); self.tabs = self.navigation.tabs
        self.build_sim_tab(); self.build_ledger_tab(); self.build_dashboard_tab(); self.build_arduino_csv_tab(); self.build_cpp_landing_tab(); self.build_landing_batch_tab(); self.build_landing_compare_tab(); self.build_landing_optimizer_tab(); self.build_module_network_tab(); self.build_cpp_module_tab(); self.build_module_fault_tab(); self.build_unified_results_tab(); self.build_individual_cpp_tab(); self.build_v14_host_tab(); self.build_v14_1_modules_tab(); self.build_v15_sensor_tab(); self.build_v16_journal_tab(); self.build_v17_phase_tab(); self.build_v18_bus_tab(); self.build_v19_compare_tab(); self.build_v20_workflow_tab(); self.build_v21_quality_tab(); self.build_simulation_common_tab(); self.build_experiment_management_tab(); self.build_guide_tab(); self.build_ros_gazebo_diagnostics_tab(); self.build_platformio_project_tab()
        self.refresh_ledger()
        style_action_buttons(self)
        from detached_tab_ui import install_detached_tab_ui
        install_detached_tab_ui(self)
        self.statusBar().showMessage(f"実験記録の保存先: {DATA_DIR} | GitHub同期は手動です")

    def build_ros_gazebo_diagnostics_tab(self):
        from ros_gazebo_diagnostics_gui import RosGazeboDiagnosticsTab
        self.ros_gazebo_diagnostics_tab = RosGazeboDiagnosticsTab()
        self.tabs.addTab(self.ros_gazebo_diagnostics_tab, '環境診断')

    def build_platformio_project_tab(self):
        from platformio_project_tab import PlatformIOProjectTab
        self.platformio_project_tab = PlatformIOProjectTab()
        self.tabs.addTab(self.platformio_project_tab, 'PlatformIOコード検証')

    def build_sim_tab(self):
        tab = QWidget(); self.tabs.addTab(tab, "着地検知シミュレーション")
        from PySide6.QtWidgets import QBoxLayout, QScrollArea, QFrame
        from landing_responsive import LandingLayoutController

        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        horizontal = QBoxLayout(QBoxLayout.LeftToRight, content)
        horizontal.setContentsMargins(9, 9, 9, 9)

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

        scroll.setWidget(content)
        self._landing_scroll = scroll
        self._landing_content_layout = horizontal
        self._landing_layout_controller = LandingLayoutController(
            scroll, horizontal, left, threshold=900
        )

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
        self.summary.setWordWrap(True)
        self.summary.setMinimumWidth(0)
        self.summary.setStyleSheet("font-weight: bold; color: #17365e; padding: 9px;")
        lay.addWidget(self.summary)
        storage_row = QVBoxLayout()
        self.storage_path_label = QLabel(f"ローカル実験記録: {DATA_DIR}")
        self.storage_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.storage_path_label.setWordWrap(True)
        self.storage_path_label.setMinimumWidth(0)
        storage_row.addWidget(self.storage_path_label)
        storage_buttons = QHBoxLayout()
        copy_path_button = QPushButton("保存先をコピー")
        copy_path_button.clicked.connect(lambda: QApplication.clipboard().setText(str(DATA_DIR)))
        storage_buttons.addWidget(copy_path_button)
        backup_button = QPushButton("バックアップZIPを作成")
        backup_button.clicked.connect(self.backup_local_experiments)
        storage_buttons.addWidget(backup_button)
        storage_row.addLayout(storage_buttons)
        lay.addLayout(storage_row)
        action_rows = QVBoxLayout()
        actions = [("＋ 実機・外部試験を登録", self.add_manual),
                   ("選択結果を共有ZIPに出力", self.share_selected),
                   ("共有ZIPを取り込む", self.import_shared),
                   ("CSVで全結果を出力", self.export_table),
                   ("更新", self.refresh_ledger)]
        for pos, (name, callback) in enumerate(actions):
            if pos % 2 == 0:
                action_row = QHBoxLayout()
                action_rows.addLayout(action_row)
            b = QPushButton(name)
            b.clicked.connect(callback)
            action_row.addWidget(b)
        lay.addLayout(action_rows)
        github_row = QVBoxLayout()
        self.github_location = QLabel(f"GitHub保存先: {REPO_DEFAULT} / {BRANCH_DEFAULT}")
        self.github_location.setStyleSheet("color: #17365e; font-weight: bold;")
        self.github_location.setWordWrap(True)
        self.github_location.setMinimumWidth(0)
        github_row.addWidget(self.github_location)
        github_buttons_row = QHBoxLayout()
        self.github_buttons = []
        for label, action in [("接続確認", "check"),
                              ("選択結果をGitHubに送信", "upload"),
                              ("チーム結果をGitHubから取得", "download")]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, a=action: self.start_github_sync(a))
            self.github_buttons.append(button)
            github_buttons_row.addWidget(button)
        github_row.addLayout(github_buttons_row)
        lay.addLayout(github_row)
        self.github_status = QLabel("GitHub同期は手動実行です。gh auth login済みのアカウントを使用します。")
        self.github_status.setStyleSheet("color: #566576;")
        self.github_status.setWordWrap(True)
        lay.addWidget(self.github_status)
        # Keep data-management actions visible even when the ledger table is tall.
        cleanup_row = QVBoxLayout()
        cleanup_info = QLabel('選択した記録はローカルからのみ削除。復元用ZIPを必ず残します。GitHub上は変更しません。')
        cleanup_info.setWordWrap(True)
        cleanup_row.addWidget(cleanup_info)
        cleanup_buttons = QHBoxLayout()
        self.delete_local_button = QPushButton('選択記録を削除（退避）')
        self.delete_local_button.clicked.connect(lambda checked=False: self.delete_local_selected())
        cleanup_buttons.addWidget(self.delete_local_button)
        restore_button = QPushButton('退避ZIPから復元')
        restore_button.clicked.connect(self.restore_local_archive)
        cleanup_buttons.addWidget(restore_button)
        cleanup_row.addLayout(cleanup_buttons)
        lay.addLayout(cleanup_row)
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
        note.setWordWrap(True)
        lay.addWidget(note)

    def build_v14_1_modules_tab(self):
        self.v14_1_modules_tab = PortableModulesTab()
        self.tabs.addTab(self.v14_1_modules_tab, '着地・Drive・CAM・Main ロジック検証')

    def build_v15_sensor_tab(self):
        self.v15_sensor_tab = SensorCsvV15Tab()
        self.tabs.addTab(self.v15_sensor_tab, 'センサー実験・ログ解析')

    def build_v17_phase_tab(self):
        self.v17_phase_tab = PhaseSimulationV17Tab()
        self.tabs.addTab(self.v17_phase_tab, 'フェーズ別ミッション・仮想試験')

    def build_v18_bus_tab(self):
        self.v18_bus_tab = VirtualBusV18Tab()
        self.tabs.addTab(self.v18_bus_tab, 'Main・CAM・Drive 仮想通信検証（v18）')

    def build_v19_compare_tab(self):
        self.v19_compare_tab = ExperimentCompareV19Tab()
        self.tabs.addTab(self.v19_compare_tab, '実験管理・仮想ログ比較（v19）')

    def build_v21_quality_tab(self):
        self.v21_quality_tab = QualityV21Tab()
        self.tabs.addTab(self.v21_quality_tab, '共通基盤・全体品質チェック（v21）')

    def build_v20_workflow_tab(self):
        self.v20_workflow_tab = WorkflowV20Tab(host=self)
        self.tabs.addTab(self.v20_workflow_tab, '共通基盤・実験ワークフロー（v20）')

    def build_v16_journal_tab(self):
        self.v16_journal_tab = ExperimentJournalV16Tab(host=self)
        self.tabs.addTab(self.v16_journal_tab, "実験記録・コード版管理（v16）")

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

    def build_v14_host_tab(self):
        self.v14_host_tab = HostCppV14Tab()
        self.tabs.addTab(self.v14_host_tab, 'Main・CAM・Drive C++実コード検証')

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
        self.ledger_changed.emit()

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

    def delete_local_selected(self, record_ids=None):
        """Always back up selected experiments before local-only deletion."""
        # QPushButton.clicked may supply a checked bool: never treat it as record IDs.
        if isinstance(record_ids, bool):
            record_ids = None
        if self._sync_worker is not None:
            QMessageBox.warning(self, '同期中', 'GitHub同期が終わってから削除してください。')
            return
        try:
            from project_settings import current_destination
            repository,branch=current_destination()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,'共有先を指定してください',str(exc));return
        ids = list(dict.fromkeys(record_ids if record_ids is not None else self.selected_ids()))
        if not ids:
            QMessageBox.information(self, '記録未選択', '削除する実験の行を選択してください。複数選択できます。')
            return
        if QMessageBox.question(self, 'ローカル削除の確認',
                f'選択した {len(ids)} 件の実験記録と添付を、このPCの一覧から削除します。\n'
                '削除前に復元用ZIPを作ります。GitHub上のデータは削除しません。\n'
                '他のPCの記録にも影響しません。実行しますか？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            result = delete_selected(ids)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.refresh_ledger()
            if hasattr(self, 'v16_journal_tab'):
                self.v16_journal_tab.reload()
            QMessageBox.warning(self, '削除の安全確認', f'{exc}\n削除前の台帳と退避ZIPを確認してください。')
            return
        self.refresh_ledger()
        if hasattr(self, 'v16_journal_tab'):
            self.v16_journal_tab.reload()
        QMessageBox.information(self, 'ローカル削除完了',
            f"{result['deleted']}件を一覧から削除しました。\n"
            f"復元用ZIP: {result['archive']}\n"
            'GitHub上のデータは変更していません。\n'
            '退避ZIPは容量を使うため、保管状況も確認してください。')

    def restore_local_archive(self):
        if self._sync_worker is not None:
            QMessageBox.warning(self, '同期中', 'GitHub同期の完了後に復元してください。')
            return
        from project_store import trash_dir
        folder = str(trash_dir())
        path, _ = QFileDialog.getOpenFileName(self, '退避ZIPを選んで復元', folder, 'ZIP (*.zip)')
        if not path:
            return
        if QMessageBox.question(self, '復元の確認',
                '選んだZIPの記録と添付をローカル台帳に戻します。既存データは上書きしません。\n復元しますか？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            result = restore_archive(Path(path))
        except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as exc:
            self.refresh_ledger()
            QMessageBox.warning(self, '復元を中止', str(exc))
            return
        self.refresh_ledger()
        if hasattr(self, 'v16_journal_tab'):
            self.v16_journal_tab.reload()
        QMessageBox.information(self, '復元完了', f"{result['restored']}件を復元しました。\n退避ZIPはそのまま残します。")

    def share_selected(self):
        ids = self.selected_ids()
        if not ids:
            QMessageBox.information(self, "選択", "共有する結果の行を選択してください。複数選択できます。")
            return
        suggested = export_path("cansat-module-results.zip")
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

    def start_github_sync(self, action, record_ids=None):
        auto = getattr(self, 'project_auto', None)
        if auto is not None and not auto.manual_allowed():
            QMessageBox.information(self, "自動共有を利用中", "手動同期を使う場合はホームで自動共有をOFFにし、通信の終了を待ってください。")
            return
        if self._sync_worker is not None:
            QMessageBox.information(self, "GitHub同期中", "前の通信が終わるまでお待ちください。")
            return
        try:
            from project_settings import current_destination
            repository,branch=current_destination()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,'共有先を指定してください',str(exc));return
        ids = list(dict.fromkeys(record_ids if record_ids is not None else
                                 (self.selected_ids() if action == "upload" else [])))
        if action == "upload" and not ids:
            QMessageBox.information(self, "実験を選択", "GitHubに送信する実験結果の行を選択してください。")
            return
        if action == "upload":
            try:
                local = {r['id']: r for r in load_records()}
            except (ValueError, OSError, KeyError, TypeError) as exc:
                QMessageBox.warning(self, "台帳の読み込みエラー", str(exc))
                return
            selected = [local[rid] for rid in ids if rid in local]
            if len(selected) != len(ids):
                QMessageBox.warning(self, "共有できません", "選択した実験がローカル台帳にありません。")
                return
            summary = []
            for rec in selected[:8]:
                names = ', '.join(a.get('name', '') for a in rec.get('attachments', [])) or 'なし'
                summary.append(f"・{rec.get('scenario', '名称なし')[:50]}  [添付: {names[:110]}]")
            if len(selected) > 8:
                summary.append(f"…ほか {len(selected) - 8} 件")
            question = (f"{len(ids)}件の実験記録を {repository} / {branch} へ直接送信します。\n" +
                        "\n".join(summary) + "\n\n"
                        "添付したCSV・ソースコードも送信対象です。\n"
                        "個人情報・パスワード・トークンなどを含まないか確認しましたか？\n"
                        "公開リポジトリへの送信は禁止します。同じIDは上書きしません。")
            if QMessageBox.question(self, "GitHub送信の最終確認", question,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        for btn in self.github_buttons:
            btn.setEnabled(False)
        if hasattr(self, 'v16_journal_tab'):
            self.v16_journal_tab.set_sync_busy(True)
            self.v16_journal_tab.set_sync_status("GitHubと通信中です。完了までアプリを閉じないでください。")
        self.github_status.setText("GitHubと通信しています。完了するまでアプリを閉じないでください。")
        worker = GitHubSyncWorker(action, ids,(repository,branch))
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
            if hasattr(self, 'v16_journal_tab'):
                self.v16_journal_tab.reload()
            msg = (f"GitHub上の実験: {result['remote']}件\n"
                   f"新規取り込み: {result['added']}件\n"
                   f"同一IDの重複: {result['skipped']}件\n"
                   f"同一IDで内容が異なる記録（未上書き）: {result['conflicts']}件\n"
                   f"このPCで削除済みのため取得しない記録: {result.get('skipped_deleted', 0)}件")
            msg += f"\n別プロジェクトのため取得しない記録: {result.get('skipped_project', 0)}件"
            if result.get('backup'):
                msg += f"\n取得前のバックアップ: {result['backup']}"
        if hasattr(self, 'v16_journal_tab'):
            self.v16_journal_tab.set_sync_status(msg)
        self.github_status.setText(msg.replace("\n", "  |  "))
        QMessageBox.information(self, "GitHub同期結果", msg)

    def _on_sync_failure(self, message):
        # A network error after one successful import can leave newly added
        # records in the local ledger; refresh both views to show the truth.
        self.refresh_ledger()
        self.github_status.setText("GitHub同期に失敗しました。既存の実験台帳は削除していません。")
        if hasattr(self, 'v16_journal_tab'):
            self.v16_journal_tab.reload()
            self.v16_journal_tab.set_sync_status("GitHub同期エラー：" + message)
        QMessageBox.warning(self, "GitHub同期エラー", message)

    def _on_sync_finish(self):
        for btn in self.github_buttons:
            btn.setEnabled(True)
        if hasattr(self, 'v16_journal_tab'):
            self.v16_journal_tab.set_sync_busy(False)
        worker = self._sync_worker
        self._sync_worker = None
        if worker is not None:
            worker.deleteLater()

    # INO_EXIT_SAFETY_V1
    def backup_local_experiments(self):
        """Make a non-destructive ZIP snapshot of saved records and attachments."""
        import os
        import zipfile
        temp_path = None
        try:
            load_records()  # Confirm the current record file is readable.
            from project_store import backup_dir as project_backup_dir
            backup_dir = project_backup_dir()
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            target = backup_dir / f"ino_experiments_{stamp}.zip"
            temp_path = backup_dir / f".ino_experiments_{stamp}.partial"
            with temp_path.open("xb") as output:
                if hasattr(os, "fchmod"):
                    os.fchmod(output.fileno(), 0o600)
                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
                    z.write(DATA_DIR / "records.json", "records.json")
                    for source in sorted(ATTACHMENTS_DIR.rglob("*")):
                        if source.is_file() and not source.is_symlink():
                            arcname = Path("attachments") / source.relative_to(ATTACHMENTS_DIR)
                            z.write(source, str(arcname))
            with zipfile.ZipFile(temp_path, "r") as z:
                corrupted = z.testzip()
                if corrupted is not None:
                    raise ValueError(f"バックアップの検証に失敗: {corrupted}")
            os.replace(temp_path, target)
            QMessageBox.information(self, "バックアップ完了",
                                    f"保存済みの実験記録と添付ファイルをバックアップしました。\n{target}")
        except Exception as exc:
            QMessageBox.warning(self, "バックアップ失敗",
                                f"バックアップを作成できませんでした。元データは変更していません。\n{exc}")
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def closeEvent(self, event):
        connection_dialog=getattr(self,'project_connection_dialog',None)
        if connection_dialog is not None and connection_dialog.before_host_close():
            event.ignore();return
        packages=getattr(self,'project_packages',None)
        if packages is not None and packages.before_close():
            event.ignore();return
        auto = getattr(self, 'project_auto', None)
        if auto is not None and auto.before_close():
            event.ignore()
            return
        if self._sync_worker is not None and self._sync_worker.isRunning():
            if auto is not None:
                auto.resume()
            if packages is not None:packages.resume()
            event.ignore()
            QMessageBox.information(self, "GitHub同期中", "通信が完了してからアプリを閉じてください。")
            return
        choice = QMessageBox.question(
            self, "Test Labを終了",
            "Test Labを終了しますか？\n\n"
            "画面上の未保存の入力内容は保存されません。\n"
            "保存済みの実験記録はローカルに残ります。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if choice != QMessageBox.Yes:
            if auto is not None:
                auto.resume()
            if packages is not None:packages.resume()
            event.ignore()
            return
        detached = getattr(self, "detached_tab_manager", None)
        if detached is not None and not detached.close_all():
            if auto is not None:
                auto.resume()
            if packages is not None:
                packages.resume()
            event.ignore()
            QMessageBox.warning(
                self,
                "終了できません",
                "別ウィンドウを元のタブへ戻せませんでした。"
            )
            return

        super().closeEvent(event)

    def export_table(self):
        path, _ = QFileDialog.getSaveFileName(self, "集計CSVの保存先", export_path("cansat-experiment-summary.csv"), "CSV (*.csv)")
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
        text.setPlainText("""【CanSat Simulation の目的】
このアプリはCanSat開発の実験・検証・解析・記録を支援するツールです。
実験前の仮想試験、ログの確認、実験記録の保存と比較を行います。

【重要：実機検証との違い】
・仮想試験のPASSは、実機での成功を保証しません。
・多くの仮想試験は単純化したモデルや仮想メッセージを使用します。
・ROS 2/RViz2/Gazeboとの統合シミュレーションとは別の機能です。
・本アプリの仮想通信は、実際のCAN/TWELITE通信品質を測定しません。
・.ino全体やESP32-S3のハードウェア依存機能を、そのままPCで実行できるわけではありません。

【基本的な実験の進め方】
1. 目的に合った機能を「機能一覧」から開きます。
2. 実機を使用する場合は、担当者がArduino IDEやPlatformIOで準備します。
3. センサー・着地・モーターなどを個別に試験します。
4. 実験結果をCSVなどで記録し、必要な項目を確認します。
5. 「実験記録・コード版管理（v16）」に試験結果を登録します。
6. 必要に応じてログ比較やチーム共有を行います。

【センサーデータの確認】
「センサー実験・ログ解析」では、CSVの読み込み、グラフ表示、
基本統計やデータ品質の確認を行えます。
CSVの列名・単位・時刻の形式を確認してください。
グラフが表示されたことだけでは、測定の正しさは保証されません。

【着地検知・個別試験】
「着地検知シミュレーション」などでは参考モデルを試せます。
着地検知の閾値や判定条件を変えて結果を比較できます。
実際のセンサー特性や機体の安全性は別途検証してください。

【Main・CAM・Driveの仮想通信】
「3モジュール・仮想CAN」では仮想メッセージの送受信、
欠落、タイムアウト、状態遷移を確認できます。
「C++モジュール連携」「異常分析」なども利用できます。
ここでの成功・失敗は、仮想条件に基づく評価です。

【PC用C++コードの検証】
「Main・CAM・Drive C++個別試験」や
「Main・CAM・Drive C++実コード検証」などを利用できます。
ホストPCで実行可能なC++コードを対象とする機能です。
実機のArduino/ESP32環境とは動作条件が異なります。
実行するコードは内容を理解した信頼できるものに限ってください。

【フェーズ別・通信条件の検証】
「フェーズ別ミッション・仮想試験（v17）」では、
着地から目標への接近までの仮想的な状態遷移を確認します。
「Main・CAM・Drive 仮想通信検証（v18）」では、
仮想通信の遅延・欠落・ACKなどの条件を確認します。
どちらも実機の動作保証を目的とするものではありません。

【ログの比較】
「実験管理・仮想ログ比較（v19）」では、
実験CSVと参考CSVの時系列を比較できます。
比較する信号の物理量・単位を必ず確認してください。
MAEやRMSEが小さいだけでは、実機の合格判定にはなりません。

【実験ワークフロー（v20）】
「共通基盤・実験ワークフロー（v20）」は、
CSV確認、解析、記録、比較への入口です。
作業メモやCSVの場所などを下書きとして保存できます。
下書きJSONと実験記録、CSV本体は区別してください。

【実験記録・コード版管理（v16）】
実験名、対象機能、担当者、コード版、使用機器、
期待する動作、観測結果、手動評価などを記録します。
必要に応じてログCSVやコードファイルを添付できます。
成功・失敗は実際の観測結果を踏まえて判断してください。
保存済み記録を削除・共有・復元する場合は対象を確認してください。

【品質チェック（v21）】
「共通基盤・全体品質チェック（v21）」では、
実験台帳、共有ZIP、インストール構成、
サンプルCSVなどを点検できます。
点検結果のOKはファイル整合性などの確認であり、
機体や実験の安全性を保証しません。

【GitHub共有】
共有先・ブランチ・公開範囲を事前に確認してください。
送信対象と添付資料に機密情報がないか確認してください。
Publicリポジトリに送信した内容は公開される可能性があります。
自動共有の設定状態もプロジェクトごとに確認してください。
GitHubから参加したことと、公開送信への同意は別です。
既存の実験記録やコード版を上書きしないよう注意してください。

【よくある確認事項】
・CSVの時刻が秒かミリ秒か
・センサー値の単位と列名が正しいか
・実験で使用したコード版を記録したか
・仮想データと実測データを区別したか
・共有前に送信先とファイル内容を確認したか

【最後に】
このアプリは開発・検証を支援するためのツールです。
最終的な性能や安全性は、実機での測定・確認が必要です。""")
        layout.addWidget(text)


def main():
    import gc

    app = QApplication([])
    if "--project" in sys.argv or "--legacy" in sys.argv:
        from project_shell import install_project_shell
        window = TestLab()
        install_project_shell(window)
    else:
        from project_hub import ProjectHub
        app.setQuitOnLastWindowClosed(False)
        window = ProjectHub(Path(__file__).resolve())

    # Qt終了時にウィンドウの削除を予約する
    app.aboutToQuit.connect(window.deleteLater)

    window.showMaximized()

    result = app.exec()

    # Python終了前に参照を整理する
    del window
    gc.collect()

    del app
    gc.collect()

    raise SystemExit(result)


if __name__ == "__main__":
    main()
