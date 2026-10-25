"""Read-only experiment dashboard for CanSat Module Test Lab v3.

No GitHub writes and no new mandatory third-party libraries beyond PySide6.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QSplitter, QTabWidget, QTextEdit, QGroupBox,
)

import dashboard_data as data


def _label(text, bold=False):
    label = QLabel(text)
    label.setWordWrap(True)
    if bold:
        label.setStyleSheet("font-weight: 700; color: #16365f;")
    return label


def _nice(value):
    return "—" if value is None else f"{value:.2f}"


class TimePlot(QWidget):
    """Two compact 2D signal traces; dynamic contact/detection event markers."""
    def __init__(self):
        super().__init__()
        self.data = None
        self.setMinimumHeight(240)

    def set_data(self, packet):
        self.data = packet
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        packet = self.data or {}
        trace = packet.get("trace", [])
        if not trace:
            p.setPen(QColor("#667788"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "グラフ表示できるCSVログがありません。")
            p.end()
            return
        w, h = self.width(), self.height()
        x0, x1 = 63.0, max(64.0, float(w) - 18.0)
        times = [r["time_s"] for r in trace]
        lo_t, hi_t = min(times), max(times)
        if lo_t == hi_t:
            hi_t += 1.0
        def xx(t): return x0 + (t - lo_t) * (x1 - x0) / (hi_t - lo_t)
        p.setFont(QFont("Sans Serif", 9))
        for idx, (key, caption, color) in enumerate([
                ("imu_z_mps2", "IMU Z加速度 (m/s²)", "#2272bc"),
                ("pressure_pa", "気圧 (Pa)", "#8361ae")]):
            y0 = 22 + idx * (h - 24) / 2
            ph = max(65, (h - 24) / 2 - 39)
            series = [(r["time_s"], r[key]) for r in trace if r.get(key) is not None]
            p.setPen(QColor("#19324d")); p.drawText(int(x0), int(y0 - 6), caption)
            if not series:
                p.setPen(QColor("#7e8b98")); p.drawText(int(x0+20), int(y0 + 34), "このログには該当データがありません")
                continue
            values = [v for _, v in series]
            min_v, max_v = min(values), max(values)
            span = max(0.01, max_v - min_v)
            min_v -= span * .07; max_v += span * .07
            def yy(v): return y0 + ph - (v - min_v) / (max_v - min_v) * ph
            p.setPen(QPen(QColor("#e6eaf0"), 1))
            for k in range(4):
                y = y0 + ph*k/3
                p.drawLine(QPointF(x0, y), QPointF(x1, y))
            p.setPen(QColor("#617082")); p.drawText(2, int(y0+11), f"{max_v:.1f}")
            p.drawText(2, int(y0+ph), f"{min_v:.1f}")
            for event_key, shade in [("contact_time", "#d65141"), ("detected_time", "#189b80")]:
                tm = packet.get(event_key)
                if tm is None or tm < lo_t or tm > hi_t:
                    continue
                p.setPen(QPen(QColor(shade), 1.5, Qt.DashLine))
                x = xx(tm)
                p.drawLine(QPointF(x, y0), QPointF(x, y0+ph))
            p.setPen(QPen(QColor(color), 1.7))
            last = None
            step = max(1, len(series) // 2600)
            plotted = series[::step]
            if plotted[-1] != series[-1]: plotted.append(series[-1])
            for t, value in plotted:
                pt = QPointF(xx(t), yy(value))
                if last is not None: p.drawLine(last, pt)
                last = pt
            p.setPen(QColor("#637084"))
            for k in range(5):
                t = lo_t + k * (hi_t-lo_t)/4
                p.drawText(int(xx(t)-10), int(y0+ph+17), f"{t:.1f}")
            p.drawText(int(x1-17), int(y0+ph+29), "秒")
        p.end()


class DelayPlot(QWidget):
    """Small time-ordered comparison for explicitly recorded delay metrics."""
    def __init__(self):
        super().__init__()
        self.points = []
        self.setMinimumHeight(160)

    def set_records(self, records):
        self.points = data.delay_points(records, max_points=16)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        if not self.points:
            p.setPen(QColor("#677588"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "比較可能な検知遅延の数値がありません。\n（未記録の値は推測しません）")
            p.end(); return
        p.setFont(QFont("Sans Serif", 9))
        mx = max(0.1, max(abs(val) for _, val, _ in self.points))
        left, right, top = 145.0, float(self.width()) - 68, 14
        space = max(50.0, right-left)
        row_h = min(27, max(14, (self.height()-top-8)/len(self.points)))
        for idx, (title, val, _) in enumerate(self.points):
            y = top + idx*row_h
            p.setPen(QColor("#4a596e"))
            p.drawText(6, int(y+row_h*.7), title[:21])
            width = min(space, abs(val)/mx*space)
            p.fillRect(int(left), int(y+2), int(width), max(6, int(row_h-6)),
                       QColor("#4c89c2" if val >= 0 else "#c96353"))
            p.setPen(QColor("#183b5c"))
            p.drawText(int(min(left+width+5, self.width()-62)), int(y+row_h*.7), f"{val:.2f}s")
        p.end()


class DashboardTab(QWidget):
    """Filtered list, summary and read-only historical sensor log viewer."""
    def __init__(self, on_download=None, parent=None):
        super().__init__(parent)
        self.records = []
        self.filtered = []
        self.by_id = {}
        lay = QVBoxLayout(self)
        heading = QLabel("実験結果ダッシュボード")
        heading.setStyleSheet("font-size: 17px; color: #17365e; font-weight: bold;")
        lay.addWidget(heading)
        info = _label("GitHubから取得した記録も、ローカル台帳の記録もここに表示します。実機試験と参考モデルは区別してください。")
        info.setStyleSheet("color: #607083;")
        lay.addWidget(info)
        filters = QHBoxLayout()
        self.source = QComboBox(); self.source.addItems(["すべて", "参考モデルのみ", "参考モデル以外"])
        self.module = QComboBox(); self.module.addItems(["すべて"])
        self.status = QComboBox(); self.status.addItems(["すべて", "成功", "失敗", "未判定"])
        self.tester = QLineEdit(); self.tester.setPlaceholderText("担当者名で検索")
        for caption, widget in [("データ種別", self.source), ("機能", self.module),
                                ("判定", self.status), ("担当者", self.tester)]:
            filters.addWidget(QLabel(caption)); filters.addWidget(widget, 1)
        reload_btn = QPushButton("一覧を更新")
        reload_btn.clicked.connect(self.reload)
        filters.addWidget(reload_btn)
        if on_download:
            get_btn = QPushButton("GitHubから取得")
            get_btn.clicked.connect(lambda checked=False: on_download("download"))
            filters.addWidget(get_btn)
        lay.addLayout(filters)
        self.source.currentIndexChanged.connect(self.apply_filters)
        self.module.currentIndexChanged.connect(self.apply_filters)
        self.status.currentIndexChanged.connect(self.apply_filters)
        self.tester.textChanged.connect(self.apply_filters)

        card_row = QHBoxLayout()
        self.card_labels = {}
        for key, title in [("total", "表示中の実験"), ("success", "成功"),
                           ("failed", "失敗"), ("rate", "判定済み成功率"),
                           ("sources", "参考 / その他")]:
            card = QGroupBox(title)
            v = QVBoxLayout(card)
            value = QLabel("—")
            value.setAlignment(Qt.AlignCenter)
            value.setStyleSheet("font-size: 23px; font-weight: 700; color: #17365e;")
            v.addWidget(value)
            card_row.addWidget(card)
            self.card_labels[key] = value
        lay.addLayout(card_row)

        splitter = QSplitter(Qt.Horizontal)
        table_container = QWidget(); tl = QVBoxLayout(table_container)
        tl.setContentsMargins(1,1,1,1)
        tl.addWidget(_label("実験一覧（行を選ぶと詳細が表示されます）", True))
        self.table = QTableWidget()
        headers = ["日時", "機能", "種別", "担当者", "判定", "検知遅延(s)", "試験ケース"]
        self.table.setColumnCount(len(headers)); self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for i, width in enumerate([140,90,115,100,60,105,140]):
            self.table.setColumnWidth(i, width)
        self.table.itemSelectionChanged.connect(self.select_record)
        tl.addWidget(self.table, 1)
        splitter.addWidget(table_container)

        tabs = QTabWidget()
        detail_page = QWidget(); dr = QVBoxLayout(detail_page)
        dr.setContentsMargins(6,6,6,6)
        self.detail = QTextEdit(); self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(200)
        dr.addWidget(self.detail)
        self.trace_note = QLabel("記録を選択してください")
        self.trace_note.setWordWrap(True)
        self.trace_note.setStyleSheet("color: #586b7d;")
        dr.addWidget(self.trace_note)
        self.plot = TimePlot(); dr.addWidget(self.plot, 1)
        tabs.addTab(detail_page, "実験の詳細・センサーグラフ")

        compare_page = QWidget(); cr = QVBoxLayout(compare_page)
        cr.addWidget(_label("着地検知遅延の比較（保存済みの数値がある記録のみ）", True))
        self.delay_plot = DelayPlot(); cr.addWidget(self.delay_plot, 1)
        cr.addWidget(_label("機能別の集計", True))
        self.group_table = QTableWidget()
        self.group_table.setColumnCount(5)
        self.group_table.setHorizontalHeaderLabels(["機能", "総数", "成功", "失敗", "成功率※"])
        self.group_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.group_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        cr.addWidget(self.group_table, 1)
        cr.addWidget(_label("※成功率は成功÷(成功＋失敗)。未判定は分母に含めません。", False))
        tabs.addTab(compare_page, "比較・機能別集計")
        splitter.addWidget(tabs)
        splitter.setSizes([510, 600])
        lay.addWidget(splitter, 1)
        self.reload()

    def reload(self, records=None):
        if records is None:
            from records import load_records
            try: records = load_records()
            except Exception as exc:
                self.detail.setPlainText(f"実験台帳の読み込みに失敗: {exc}")
                return
        self.records = list(records)
        current_module = self.module.currentText()
        self.module.blockSignals(True)
        self.module.clear(); self.module.addItem("すべて")
        self.module.addItems(sorted({str(r.get("module", "")) for r in self.records if r.get("module")}))
        idx = self.module.findText(current_module)
        self.module.setCurrentIndex(max(0, idx))
        self.module.blockSignals(False)
        self.apply_filters()

    def apply_filters(self, *_):
        old_selection = None
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if rows:
            cell = self.table.item(rows[0].row(), 0)
            old_selection = cell.data(Qt.UserRole) if cell else None
        self.filtered = data.filter_records(self.records, module=self.module.currentText(),
                         source=self.source.currentText(), status=self.status.currentText(),
                         tester=self.tester.text())
        result = data.summary(self.filtered)
        for key, value in [("total", str(result["total"])), ("success", str(result["success"])),
                           ("failed", str(result["failed"])),
                           ("rate", "—" if result["success_rate"] is None else f"{result['success_rate']:.0f}%"),
                           ("sources", f"{result['reference']} / {result['non_reference']}")]:
            self.card_labels[key].setText(value)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.filtered))
        selected_row = None
        self.by_id = {str(r.get("id")): r for r in self.filtered}
        for row, r in enumerate(self.filtered):
            delay = data.number((r.get("metrics") or {}).get("delay_s"))
            values = [str(r.get("created_at", ""))[:16], str(r.get("module", "")),
                      "参考モデル" if data.is_reference(r) else "参考以外",
                      str(r.get("tester", "")), str(r.get("status", "未判定")),
                      _nice(delay), str(r.get("scenario", ""))]
            for i, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if i == 0: cell.setData(Qt.UserRole, r.get("id"))
                if i == 4 and text == "成功": cell.setForeground(QBrush(QColor("#16803e")))
                if i == 4 and text == "失敗": cell.setForeground(QBrush(QColor("#b51c1c")))
                self.table.setItem(row, i, cell)
            if r.get("id") == old_selection:
                selected_row = row
        self.table.blockSignals(False)
        self.delay_plot.set_records(self.filtered)
        groups = data.module_summary(self.filtered)
        self.group_table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            rate = "—" if group["success_rate"] is None else f"{group['success_rate']:.0f}%"
            for col, val in enumerate([group["module"], group["total"], group["success"], group["failed"], rate]):
                self.group_table.setItem(row, col, QTableWidgetItem(str(val)))
        if selected_row is not None:
            self.table.selectRow(selected_row)
        elif self.filtered:
            self.table.selectRow(0)
        else:
            self.detail.setPlainText("該当する記録がありません。フィルターを変更してください。")
            self.trace_note.setText("—")
            self.plot.set_data(None)

    def select_record(self):
        selected = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not selected: return
        item = self.table.item(selected[0].row(), 0)
        rec = self.by_id.get(item.data(Qt.UserRole)) if item else None
        if rec is None: return
        metrics = rec.get("metrics") or {}
        if not isinstance(metrics, dict): metrics = {}
        attachments = rec.get("attachments") or []
        if not isinstance(attachments, list): attachments = []
        fields = [("日時", rec.get("created_at", "")), ("機能", rec.get("module", "")),
                  ("試験の種類", rec.get("mode", "")), ("担当者", rec.get("tester", "")),
                  ("試験ケース", rec.get("scenario", "")), ("結果", rec.get("status", "")),
                  ("コード版", rec.get("code_version", "")),
                  ("期待する動作", rec.get("expected", "")), ("観測結果", rec.get("observed", "")),
                  ("メモ", rec.get("notes", "")),
                  ("検知遅延", _nice(data.number(metrics.get("delay_s"))) + " 秒"),
                  ("添付ファイル", ", ".join(str(a.get("name", "")) for a in attachments if isinstance(a, dict)) or "なし"),
                  ("実験ID", rec.get("id", ""))]
        blocks = [f"<b>{escape(str(k))}：</b>{escape(str(v))}" for k,v in fields]
        if data.is_reference(rec):
            blocks.insert(0, "<b style='color:#98571c'>参考モデルの結果です。ESP32-S3実機の試験結果ではありません。</b>")
        self.detail.setHtml("<div style='font-size:12px; line-height:1.55'>" + "<br>".join(blocks) + "</div>")
        packet = data.read_trace(rec)
        legend = []
        if packet.get("contact_time") is not None: legend.append("赤線＝真の接地")
        if packet.get("detected_time") is not None: legend.append("緑線＝検知")
        if packet.get("detected_source"): legend.append(packet["detected_source"])
        msg = packet.get("message", "")
        self.trace_note.setText(msg + ("  |  " + " / ".join(legend) if legend else ""))
        self.plot.set_data(packet)
