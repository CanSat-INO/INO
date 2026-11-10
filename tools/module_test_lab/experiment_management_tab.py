"""v12 experiment-plan and deterministic virtual-CAN batch GUI (PySide6)."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QMessageBox, QPlainTextEdit, QSplitter,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from simulation_common import CommonFormatError
from experiment_management import (
    ExperimentError, MAX_CASES, new_plan, make_case, validate_plan, plan_json,
    parse_plan, read_text_limited, default_scenario_plan, run_plan, batch_json,
    batch_csv, list_history, load_history, save_history,
)


class ExperimentManagementTab(QWidget):
    def __init__(self, *, config_provider, open_config_tab=None, parent=None):
        super().__init__(parent)
        self.config_provider = config_provider
        self.open_config_tab = open_config_tab
        self.plan = new_plan()
        self.batch = None
        self.history_rows = []
        root = QVBoxLayout(self)
        heading = QLabel('v12 実験管理・一括実行')
        heading.setStyleSheet('font-size: 18px; font-weight: bold; color: #17365e;')
        root.addWidget(heading)
        note = QLabel('v11の「シミュレーション共通基盤」で設定した条件を登録し、仮想CAN試験をまとめて実行します。'
                      '質量・タイヤ径・地形などは記録のみで、仮想CANの評価には影響しません。'
                      '既存の着地一括テスト・統合実験台帳とは別の機能です。')
        note.setWordWrap(True)
        root.addWidget(note)
        namebar = QHBoxLayout()
        namebar.addWidget(QLabel('実験名'))
        self.name_edit = QLineEdit(self.plan['name'])
        self.name_edit.setPlaceholderText('例: タイヤ径と通信異常シナリオ比較')
        self.name_edit.textChanged.connect(self._on_plan_edit)
        namebar.addWidget(self.name_edit, 1)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText('条件名（例: 車輪60mm、正常）')
        namebar.addWidget(QLabel('条件名'))
        namebar.addWidget(self.label_edit, 1)
        root.addLayout(namebar)
        row = QHBoxLayout()
        for title, action in (
            ('共通設定を開く', self.go_to_config),
            ('＋ 現在のv11設定を追加', self.add_current),
            ('＋ 全8シナリオを追加', self.add_all),
            ('選択条件を削除', self.remove_selected),
            ('条件を全消去', self.clear_cases),
        ):
            button = QPushButton(title); button.clicked.connect(action); row.addWidget(button)
        root.addLayout(row)
        controls = QHBoxLayout()
        for title, action in (
            ('実験計画JSON保存', self.save_plan),
            ('実験計画JSON読込', self.load_plan),
            ('▶ 一括実行・履歴保存', self.execute),
            ('比較CSV出力', self.export_csv),
            ('詳細JSON出力', self.export_json),
        ):
            button = QPushButton(title)
            button.clicked.connect(action)
            controls.addWidget(button)
            if title == '比較CSV出力': self.csv_button = button
            if title == '詳細JSON出力': self.json_button = button
        root.addLayout(controls)
        self.status = QLabel('v11の設定画面で条件を調整 → この画面で登録してください。')
        self.status.setObjectName('v13ExperimentStatus')
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        splitter = QSplitter(Qt.Vertical)
        upper = QWidget()
        upper_lay = QVBoxLayout(upper); upper_lay.setContentsMargins(0, 0, 0, 0)
        upper_lay.addWidget(QLabel('実験条件と比較結果（行を選択するとイベント詳細を表示）'))
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            'No.','条件名','仮想CANシナリオ','質量(kg)','車輪径(mm)','段差(mm)',
            '評価','Main','CAM','Drive','欠落 / Timeout / イベント',
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.show_events)
        upper_lay.addWidget(self.table)
        splitter.addWidget(upper)

        lower = QWidget()
        lower_lay = QHBoxLayout(lower); lower_lay.setContentsMargins(0, 0, 0, 0)
        left = QGroupBox('保存済み履歴（ローカルのみ）')
        left_lay = QVBoxLayout(left)
        history_tools = QHBoxLayout()
        refresh = QPushButton('履歴を更新'); refresh.clicked.connect(self.refresh_history)
        restore = QPushButton('選択履歴を表示'); restore.clicked.connect(self.restore_history)
        history_tools.addWidget(refresh); history_tools.addWidget(restore)
        left_lay.addLayout(history_tools)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(['日時','実験名','条件数','成功 / 失敗'])
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.cellDoubleClicked.connect(lambda *_: self.restore_history())
        left_lay.addWidget(self.history_table)
        lower_lay.addWidget(left, 2)
        right = QGroupBox('選択条件の仮想CANイベント')
        right_lay = QVBoxLayout(right)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setPlaceholderText('実行するとここに時系列イベントが表示されます。')
        right_lay.addWidget(self.events)
        lower_lay.addWidget(right, 3)
        splitter.addWidget(lower)
        splitter.setSizes([420, 260])
        root.addWidget(splitter, 1)
        self._update_table()
        self.refresh_history()

    def _on_plan_edit(self, *_):
        self._invalidate()

    def _invalidate(self):
        self.batch = None
        self.csv_button.setEnabled(False)
        self.json_button.setEnabled(False)
        self.events.clear()
        self._update_table()

    def _read_common(self):
        try:
            return self.config_provider()
        except (CommonFormatError, ValueError) as exc:
            QMessageBox.warning(self, 'v11設定エラー', str(exc))
            return None

    def go_to_config(self, *_):
        if self.open_config_tab:
            self.open_config_tab()

    def add_current(self, *_):
        if len(self.plan['cases']) >= MAX_CASES:
            QMessageBox.warning(self, '追加不可', f'条件は最大{MAX_CASES}件です。'); return
        cfg = self._read_common()
        if cfg is None: return
        from module_network import SCENARIO_BY_KEY
        suggestion = SCENARIO_BY_KEY[cfg['scenario']['key']].name
        label = self.label_edit.text().strip() or f'{suggestion} #{len(self.plan["cases"])+1}'
        try:
            self.plan['cases'].append(make_case(cfg, label))
        except (ExperimentError, CommonFormatError) as exc:
            QMessageBox.warning(self, '条件エラー', str(exc)); return
        self.label_edit.clear()
        self._invalidate()
        self.status.setText(f'{label} を追加しました（v11設定をコピーしました）。')

    def add_all(self, *_):
        if len(self.plan['cases']) + 8 > MAX_CASES:
            QMessageBox.warning(self, '追加不可', f'条件は最大{MAX_CASES}件です。'); return
        cfg = self._read_common()
        if cfg is None: return
        plan = default_scenario_plan(config=cfg)
        self.plan['cases'].extend(plan['cases'])
        self._invalidate()
        self.status.setText('現在の機体設定を固定して、仮想CANの8シナリオを追加しました。')

    def remove_selected(self, *_):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            self.status.setText('削除する条件行を選択してください。'); return
        for index in rows:
            if index < len(self.plan['cases']):
                del self.plan['cases'][index]
        self._invalidate()
        self.status.setText(f'{len(rows)}件の条件を削除しました。')

    def clear_cases(self, *_):
        if self.plan['cases'] and QMessageBox.question(self, '条件の全消去', '登録済み条件を全て消去しますか？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.plan['cases'].clear()
        self._invalidate()
        self.status.setText('条件を全消去しました。保存済み履歴は削除されません。')

    def _current_plan(self):
        return validate_plan({**self.plan, 'name': self.name_edit.text()})

    def _update_table(self):
        cases = self.plan['cases']
        outcomes = self.batch['outcomes'] if self.batch is not None else None
        self.table.blockSignals(True)
        self.table.setRowCount(len(cases))
        for i, case in enumerate(cases):
            cfg = case['config']
            outcome = outcomes[i]['summary'] if outcomes else None
            cells = [str(i+1),case['label'],cfg['scenario']['key'],
                     f"{cfg['robot']['mass_kg']:.4g}",
                     f"{cfg['robot']['wheel_diameter_m']*1000:.3f}",
                     f"{cfg['environment']['step_height_m']*1000:.3f}",
                     outcome['evaluation'] if outcome else '未実行',
                     outcome['main_state'] if outcome else '—',
                     outcome['cam_state'] if outcome else '—',
                     outcome['drive_state'] if outcome else '—',
                     (f"{outcome['loss_count']} / {outcome['timeout_count']} / {outcome['event_count']}"
                      if outcome else '—')]
            for j, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                if outcome and j == 6:
                    cell.setForeground(QColor('#166534' if value == '成功' else
                                               '#A61B2B' if value == '失敗' else '#805000'))
                    cell.setBackground(QColor('#E7F6ED' if value == '成功' else
                                               '#FFF0F0' if value == '失敗' else '#FFF3DB'))
                self.table.setItem(i, j, cell)
        self.table.clearSelection()
        self.table.blockSignals(False)
        self.csv_button.setEnabled(self.batch is not None)
        self.json_button.setEnabled(self.batch is not None)

    def execute(self, *_):
        try:
            plan = self._current_plan()
            batch = run_plan(plan)
            path = save_history(batch)
        except (ExperimentError, CommonFormatError, OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, '実行・履歴保存エラー', str(exc)); return
        self.plan = batch['plan']
        self.batch = batch
        self._update_table()
        self.refresh_history()
        self._show_summary(f'実行し、履歴を保存しました: {path.name}')

    def _show_summary(self, lead):
        if self.batch is None: return
        result = [o['summary']['evaluation'] for o in self.batch['outcomes']]
        self.status.setText(f"{lead}  |  条件{len(result)}件：成功{result.count('成功')}件、"
                            f"失敗{result.count('失敗')}件、未判定{result.count('未判定')}件。"
                            ' この割合は仮想CANシナリオの集計で、走破性や実機成功率ではありません。')

    def show_events(self):
        self.events.clear()
        if self.batch is None: return
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not rows: return
        outcome = self.batch['outcomes'][rows[0]]
        run = outcome['run']
        lines = [f"条件: {outcome['label']} / シナリオ: {outcome['scenario_key']}",
                 f"評価: {outcome['summary']['evaluation']}",
                 '※物理運動なし（位置・姿勢・速度は未計算）', '']
        for e in run['samples']:
            lines.append(f"{e['time_s']:7.3f}s | {e['source']} → {e['target']} | "
                         f"{e['event']} | {e['message']} | {e['detail']}")
        self.events.setPlainText('\n'.join(lines))

    def save_plan(self, *_):
        try: text = plan_json(self._current_plan())
        except (ExperimentError, CommonFormatError) as exc:
            QMessageBox.warning(self,'条件エラー',str(exc)); return
        path, _ = QFileDialog.getSaveFileName(self,'実験計画JSON保存',export_path('cansat_v12_plan.json'),'JSON (*.json)')
        if not path: return
        try:
            Path(path).write_text(text,encoding='utf-8')
            self.status.setText(f'実験計画を保存しました: {path}')
        except OSError as exc: QMessageBox.warning(self,'保存エラー',str(exc))

    def load_plan(self, *_):
        path, _ = QFileDialog.getOpenFileName(self,'実験計画JSON読込','','JSON (*.json)')
        if not path: return
        try: plan = parse_plan(read_text_limited(path))
        except (ExperimentError, CommonFormatError, OSError, UnicodeError) as exc:
            QMessageBox.warning(self,'読込エラー',str(exc)); return
        self.plan = plan
        self.name_edit.blockSignals(True); self.name_edit.setText(plan['name']); self.name_edit.blockSignals(False)
        self._invalidate()
        self.status.setText(f'実験計画を読み込みました: {path}（以前の実行表示を破棄）')

    def _export(self, kind, converter):
        if self.batch is None:
            QMessageBox.warning(self,'未実行','先に一括実行してください。'); return
        path, _ = QFileDialog.getSaveFileName(self,'実験結果出力',export_path(f'cansat_v12_comparison.{kind}'),
                                             f'{kind.upper()} (*.{kind})')
        if not path: return
        try:
            Path(path).write_text(converter(self.batch),encoding='utf-8-sig' if kind == 'csv' else 'utf-8')
            self.status.setText(f'結果を出力しました: {path}（物理演算未実施）')
        except (OSError, ExperimentError) as exc:
            QMessageBox.warning(self,'出力エラー',str(exc))

    def export_csv(self, *_): self._export('csv',batch_csv)
    def export_json(self, *_): self._export('json',batch_json)

    def refresh_history(self, *_):
        self.history_rows = list_history()
        self.history_table.setRowCount(len(self.history_rows))
        for i, row in enumerate(self.history_rows):
            for j, val in enumerate([row['created_at'][:19],row['name'],str(row['count']),
                                      f"{row['success']} / {row['failure']}"]):
                self.history_table.setItem(i,j,QTableWidgetItem(val))

    def restore_history(self, *_):
        row = self.history_table.currentRow()
        if row < 0 or row >= len(self.history_rows):
            QMessageBox.information(self,'履歴選択','表示する履歴行を選択してください。'); return
        try: batch = load_history(self.history_rows[row]['id'])
        except (OSError, UnicodeError, ExperimentError) as exc:
            QMessageBox.warning(self,'履歴読込エラー',str(exc)); return
        self.batch = batch
        self.plan = batch['plan']
        self.name_edit.blockSignals(True); self.name_edit.setText(self.plan['name']); self.name_edit.blockSignals(False)
        self._update_table()
        self._show_summary('保存済み履歴を表示中（再実行は新しい履歴として保存）')
