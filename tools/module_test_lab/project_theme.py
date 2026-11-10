"""Dark UI chrome with readable light plotting canvases in existing analyzers."""
from __future__ import annotations
import re

SPACE_STYLE = '''
QMainWindow, QWidget#projectHub { background: #07101D; }
QWidget#projectHubBody { background: #07101D; }
QWidget { color: #DFEAF5; font-size: 13px; }
QLabel { color: #DFEAF5; background: transparent; }
QLabel#moduleLabTitle { color: #ECF6FC; font-size: 24px; font-weight: 700; padding: 3px 0; }
QLabel#moduleLabSubtitle, QLabel#projectHint { color: #A9BED2; font-size: 12px; }
QLabel#projectHeading { color: #EDF6FD; font-size: 27px; font-weight: 700; }
QLabel#projectEyebrow { color: #7BDFF4; font-size: 11px; }
QLabel#projectEmpty { background: #0B1829; color: #A9BED2; border: 1px solid #304B65; padding: 12px; border-radius: 3px; }
QGroupBox { background: #101E30; color: #DCEBF7; border: 1px solid #35506A;
 border-top: 2px solid #587D99; border-radius: 4px; margin-top: 14px; padding: 14px 10px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #DCEBF7; }
QPushButton { background: #162A40; color: #E3EFF9; border: 1px solid #405C77;
 border-radius: 4px; padding: 8px 12px; min-height: 20px; font-weight: 500; }
QPushButton:hover { background: #23425B; border-color: #80CDE0; }
QPushButton:pressed { background: #294F68; }
QPushButton:focus { border: 2px solid #7BDFF4; }
QPushButton[v13Role="primary"], QPushButton#projectCreate, QPushButton#projectOpen {
 background: #7BDFF4; color: #082332; border: 1px solid #7BDFF4; font-weight: 600; }
QPushButton[v13Role="success"] { background: #164F50; color: #E4F7F0; border: 1px solid #51978E; }
QPushButton[v13Role="danger"] { background: #442731; color: #FFD6DE; border: 1px solid #9C5D6A; }
QPushButton:disabled, QPushButton[v13Role="primary"]:disabled, QPushButton[v13Role="success"]:disabled,
QPushButton#projectCreate:disabled, QPushButton#projectOpen:disabled {
 background: #142234; color: #8296AA; border-color: #30455B; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
 background: #081321; color: #E6F0F9; border: 1px solid #45627D; border-radius: 3px;
 padding: 6px 8px; selection-background-color: #315E79; selection-color: #FFFFFF; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 2px solid #7BDFF4; }
QComboBox QAbstractItemView { background: #102339; color: #E3EFF9; selection-background-color: #315E79; }
QComboBox::drop-down { border: none; width: 22px; }
QListWidget, QTableView, QTableWidget { background: #0B1829; alternate-background-color: #11233A;
 color: #E3EDF7; border: 1px solid #304B65; gridline-color: #29415A;
 selection-background-color: #315976; selection-color: #FFFFFF; }
QListWidget::item { padding: 13px 10px; border-bottom: 1px solid #293E54; }
QListWidget::item:selected { background: #24445E; color: #FFFFFF; }
QTableWidget::item { padding: 4px; }
QHeaderView::section { background: #1B334D; color: #DDEDF8; padding: 7px; border: 1px solid #2B465F; font-weight: 600; }
QScrollArea, QTabWidget::pane { border: none; background: transparent; }
QScrollBar:vertical { background: #0C1929; width: 13px; }
QScrollBar::handle:vertical { background: #46627C; min-height: 28px; border-radius: 4px; }
QScrollBar:horizontal { background: #0C1929; height: 13px; }
QScrollBar::handle:horizontal { background: #46627C; min-width: 28px; border-radius: 4px; }
QSplitter::handle { background: #2D465E; }
QMenu, QMessageBox { background: #102035; color: #E5F0F8; }
QMenu::item { padding: 8px 18px; }
QMenu::item:selected { background: #294A65; }
QStatusBar { background: #081522; color: #AECCDD; }
QLabel#v13ExperimentStatus { background: #102D43; color: #D4EAF9; border: 1px solid #3D6885; padding: 8px; border-radius: 3px; }
QToolTip { background: #203B54; color: #FFFFFF; border: 1px solid #80B4CA; padding: 5px; }
'''


def apply_space_theme(window):
    from PySide6.QtWidgets import QWidget, QScrollArea
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPalette, QColor
    window.setStyleSheet(SPACE_STYLE)
    palette = window.palette()
    for role, color in ((QPalette.Window, '#07101D'), (QPalette.WindowText, '#DFEAF5'),
                        (QPalette.Base, '#0B1829'), (QPalette.Text, '#DFEAF5'),
                        (QPalette.Button, '#162A40'), (QPalette.ButtonText, '#DFEAF5')):
        palette.setColor(role, QColor(color))
    window.setPalette(palette)
    # Convert old inline QSS only. Existing QPainter plot colors remain intact.
    def foreground(match):
        color = match.group(1)
        mean = sum(int(color[i:i+2], 16) for i in (1, 3, 5)) / 765
        return 'color: #DDECF8' if mean < .65 else match.group(0)
    def background(match):
        color = match.group(2)
        mean = sum(int(color[i:i+2], 16) for i in (1, 3, 5)) / 765
        return match.group(1) + ': #11263B' if mean > .68 else match.group(0)
    for widget in window.findChildren(QWidget):
        css = widget.styleSheet()
        if css:
            css = re.sub(r'(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{6})', foreground, css)
            css = re.sub(r'(background(?:-color)?)\s*:\s*(#[0-9a-fA-F]{6})', background, css)
            widget.setStyleSheet(css)
    # QScrollArea sets autoFillBackground on its content widget. Styling only
    # the QMainWindow leaves that content using the platform's light palette.
    surfaces = []
    if window.centralWidget() is not None:
        surfaces.append(window.centralWidget())
    for area in window.findChildren(QScrollArea):
        surfaces.append(area.viewport())
        if area.widget() is not None:
            surfaces.append(area.widget())
    selectors = []
    seen = set()
    for surface in surfaces:
        if id(surface) in seen:
            continue
        seen.add(id(surface))
        if not surface.objectName():
            surface.setObjectName('projectSurface' + str(len(seen)))
        surface_palette = surface.palette()
        surface_palette.setColor(QPalette.Window, QColor('#07101D'))
        surface_palette.setColor(QPalette.Base, QColor('#07101D'))
        surface.setPalette(surface_palette)
        surface.setAutoFillBackground(True)
        surface.setAttribute(Qt.WA_StyledBackground, True)
        name = surface.objectName()
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            selectors.append('QWidget#' + name + ' { background: #07101D; }')
    window.setStyleSheet(SPACE_STYLE + '\n' + '\n'.join(selectors))
