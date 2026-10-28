"""v13 visual theme for the independent CanSat Module Test Lab.

Presentation only: no changes to simulation, files, network, or experiment logic.
Maintain text labels in addition to color cues for accessibility.
"""
from __future__ import annotations

# Category key -> (Japanese label, accent, pale background, brief hint).
CATEGORIES = {
    "landing": ("着地・解析", "#087565", "#E7F8F3", "着地判定や実験条件を評価"),
    "control": ("制御・通信", "#155DE5", "#EAF2FF", "Main / CAM / Driveと仮想CANを検証"),
    "camera": ("カメラ", "#7144B5", "#F2ECFC", "画像認識との連携に向けた機能"),
    "drive": ("走行", "#087D65", "#E8F7F0", "Drive・モーターの動作を確認"),
    "fault": ("異常解析", "#C45308", "#FFF1E5", "失敗や異常の原因を追跡"),
    "results": ("結果・共有", "#7138CD", "#F2EAFE", "結果を比較、保存、共有"),
    "simulation": ("共通基盤", "#087DB7", "#E9F7FF", "機体と環境の条件を管理"),
    "guide": ("ガイド", "#52657E", "#F0F3F8", "操作や接続の説明を確認"),
}


def category_for(name: str) -> str:
    """Stable categorization of legacy navigation tab labels."""
    text = str(name).casefold()
    if "センサー実験" in text:
        return "simulation"
    if "異常" in text or "fault" in text:
        return "fault"
    if "カメラ" in text or "画像" in text:
        return "camera"
    if "drive" in text and "main" not in text and "cam" not in text:
        return "drive"
    if any(word in text for word in ("can", "モジュール", "main", "制御", "通信")):
        return "control"
    if any(word in text for word in ("ダッシュボード", "統合実験結果", "実験管理", "実験記録", "共有")):
        return "results"
    if any(word in text for word in ("共通基盤", "3d", "モデル管理")):
        return "simulation"
    if any(word in text for word in ("使い方", "接続", "ガイド")):
        return "guide"
    return "landing"


def button_role(text: str) -> str:
    """Choose visual emphasis from an existing button label; behavior is unchanged."""
    label = str(text).strip()
    if any(word in label for word in ("削除", "全消去", "消去", "クリア")):
        return "danger"
    if any(word in label for word in ("▶", "実行", "解析", "分析", "一括試験", "一括テスト")):
        return "primary"
    if any(word in label for word in ("保存", "出力", "エクスポート", "登録", "共有ZIP")):
        return "success"
    return "neutral"


def style_action_buttons(root) -> None:
    """Apply QSS roles once after all legacy pages have been constructed.

    Existing object names, signal/slot connections and button texts are preserved.
    """
    from PySide6.QtWidgets import QPushButton

    for button in root.findChildren(QPushButton):
        if button.objectName().startswith("moduleNavigation"):
            continue
        button.setProperty("v13Role", button_role(button.text()))
    # Re-polish after dynamic properties to ensure selectors apply on Qt 6.
    for button in root.findChildren(QPushButton):
        if button.objectName().startswith("moduleNavigation"):
            continue
        button.style().unpolish(button)
        button.style().polish(button)


MAIN_STYLESHEET = """
QMainWindow { background: #F5F8FD; }
QWidget { color: #182B49; font-size: 13px; }
QLabel { color: #203755; }
QLabel#moduleLabTitle { font-size: 26px; font-weight: 800; color: #102D5B; padding: 4px 0; }
QLabel#moduleLabSubtitle { color: #4A637E; font-size: 12px; padding-bottom: 5px; }
QGroupBox {
    font-weight: 700; color: #193F77;
    background: #FFFFFF; border: 1px solid #CEDAE9;
    border-top: 3px solid #9FC3F2;
    border-radius: 9px; margin-top: 14px; padding: 12px 9px 10px 9px;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #193F77; }
QPushButton {
    background: #EAF1FA; border: 1px solid #BACBE0;
    border-radius: 7px; color: #203755;
    padding: 8px 11px; font-weight: 650; min-height: 18px;
}
QPushButton:hover { background: #DCEAFB; border-color: #6193D4; }
QPushButton:pressed { background: #C6DCF8; }
QPushButton:focus { border: 2px solid #2459C5; }
QPushButton:disabled { background: #F0F3F8; border-color: #DCE3EC; color: #8895A8; }
QPushButton[v13Role="primary"] {
    background: #255BC5; color: #FFFFFF; border: 1px solid #204DA3; font-weight: 750;
}
QPushButton[v13Role="primary"]:hover { background: #17489E; }
QPushButton[v13Role="primary"]:pressed { background: #133878; }
QPushButton[v13Role="success"] {
    background: #087D65; color: #FFFFFF; border: 1px solid #076750;
}
QPushButton[v13Role="success"]:hover { background: #06614D; }
QPushButton[v13Role="success"]:pressed { background: #044636; }
QPushButton[v13Role="danger"] {
    background: #FFF1F1; color: #9D2635; border: 1px solid #EAB6BC;
}
QPushButton[v13Role="danger"]:hover { background: #FFE1E5; border-color: #CA6977; }
QPushButton[v13Role="primary"]:disabled,
QPushButton[v13Role="success"]:disabled,
QPushButton[v13Role="danger"]:disabled {
    background: #F0F3F8; color: #8895A8; border: 1px solid #DCE3EC;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background: #FFFFFF; color: #1C2D46;
    selection-background-color: #B4D5FA; selection-color: #122541;
    border: 1px solid #B6C8DE; border-radius: 6px; padding: 5px 7px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 2px solid #3B7BCE;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled { background: #EFF3F8; color: #8895A8; }
QComboBox::drop-down { border: none; width: 22px; }
QTableWidget, QTableView {
    background: #FFFFFF; alternate-background-color: #F3F7FC;
    color: #172B49; gridline-color: #DFE8F2;
    border: 1px solid #CCDAE9; border-radius: 6px;
    selection-background-color: #C8E1FF; selection-color: #12294A;
}
QTableWidget::item { padding: 3px 4px; }
QTableWidget::item:selected { background: #C8E1FF; color: #12294A; }
QHeaderView::section {
    background: #DFEBFA; color: #173B6B;
    font-weight: 750; padding: 6px 5px;
    border: none; border-right: 1px solid #C5D7EA;
    border-bottom: 1px solid #B3C9E3;
}
QTabWidget::pane { border: 0; }
QScrollArea { background: transparent; border: none; }
QSplitter::handle { background: #D9E4F0; }
QSplitter::handle:hover { background: #A2BFE2; }
QScrollBar:vertical { background: #F0F4F9; width: 13px; }
QScrollBar::handle:vertical { background: #B3C8E2; border-radius: 5px; min-height: 24px; }
QScrollBar:horizontal { background: #F0F4F9; height: 13px; }
QScrollBar::handle:horizontal { background: #B3C8E2; border-radius: 5px; min-width: 24px; }
QMenu { background: #FFFFFF; color: #1A3559; border: 1px solid #CAD8E9; padding: 5px; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #DCEAFF; color: #173F7A; }
QLabel#v13ExperimentStatus {
    background: #EAF3FF; color: #1E497A; border: 1px solid #C9DCF5;
    border-radius: 6px; padding: 8px;
}
"""
