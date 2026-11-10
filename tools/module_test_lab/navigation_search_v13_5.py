"""v13.5: pure Python navigation keyword matcher (never loads Qt/IME).

Aliases route to EXISTING tabs; they do not indicate new sensor simulations
or device drivers. No external I/O, GUI or execution is performed here.
"""
from __future__ import annotations

import re
import unicodedata

# Keep tab labels in sync with app.py. New aliases require a real existing tab.
# These are navigation hints, not a claim that hardware is supported.
ALIASES: dict[str, tuple[str, ...]] = {
    "着地検知シミュレーション": (
        "着陸", "landing", "IMU", "加速度", "気圧", "センサー", "sensor", "BNO055", "BME280", "接地", "ノイズ"),
    "実験記録・チーム共有": (
        "ログ", "CSV", "ZIP", "GitHub", "履歴", "GNSS", "GPS", "衛星測位", "姿勢", "センサー", "sensor", "測定記録"),
    "結果ダッシュボード": (
        "dashboard", "可視化", "集計", "グラフ", "graph", "plot", "レポート", "ログ"),
    "Arduino/CSVログ解析": (
        "Arduino", "CSV", "ログ", "IMU", "加速度", "sensor", "センサー", "計測", "波形"),
    "C++着地判定": (
        "C++", "landing", "IMU", "加速度", "センサー", "判定ロジック"),
    "着地一括テスト": (
        "batch", "バッチ", "IMU", "加速度", "センサー", "一括実行"),
    "着地コード比較": (
        "C++", "バージョン", "version", "ソース", "差分"),
    "着地パラメータ探索": (
        "最適化", "optimizer", "しきい値", "閾値", "感度", "ノイズ"),
    "3モジュール・仮想CAN": (
        "CAN", "通信", "バス", "ネットワーク", "Main", "CAM", "Drive", "メッセージ", "タイムアウト"),
    "C++モジュール連携": (
        "C++", "CAN", "通信", "Main", "CAM", "Drive", "制御ロジック"),
    "異常分析": (
        "fault", "エラー", "障害", "故障", "失敗", "デバッグ", "タイムアウト"),
    "統合実験結果": (
        "集計", "レポート", "共有", "ログ", "ZIP", "GitHub", "合否"),
    "Main・CAM・Drive C++個別試験": (
        "C++", "Main", "CAM", "Drive", "制御", "カメラ", "モーター", "unit", "個別"),
    "シミュレーション共通基盤": (
        "機体", "設定", "パラメータ", "3D", "車輪", "地形", "質量", "共通", "姿勢"),
    "v12 実験管理・一括比較": (
        "実験", "管理", "履歴", "一括", "比較", "バッチ", "history"),
    "使い方・Arduinoとの接続": (
        "help", "ガイド", "Arduino", "USB", "接続", "セットアップ", "操作", "マニュアル"),
}

# Additive v15 aliases: keep the frozen legacy ALIASES registry stable for v13.5 tests.
V15_ALIASES = {
    "センサー実験・ログ解析": (
        "センサー", "ログ", "CSV", "グラフ", "計測", "測定", "実験", "データ品質",
        "BNO055", "IMU", "加速度", "角速度", "BME280", "気圧", "温度", "高度",
        "GNSS", "GPS", "緯度", "経度", "motor", "モーター", "Drive", "CAM", "カメラ", "認識率"),
}

# "CanSat" names the entire app: intentionally include all existing tabs.
APP_TERMS = frozenset(("cansat", "can-sat", "カンサット", "キャンサット"))


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text)).casefold().strip()


def _terms(query: str) -> list[str]:
    """Split whitespace and joined Japanese/ASCII queries like '着地CanSat'."""
    q = _normalize(query)
    # Divide at Japanese <-> ASCII letter transitions without splitting C++.
    q = re.sub(r'(?<=[^\x00-\x7f])(?=[a-z])|(?<=[a-z])(?=[^\x00-\x7f])', ' ', q)
    return [p for p in re.split(r'\s+', q) if p]


def matches_search(tab_title: str, category_label: str, query: str) -> bool:
    """Case-insensitive AND search over original title/category and curated aliases."""
    terms = _terms(query)
    if not terms:
        return True
    fields = (
        _normalize(tab_title),
        _normalize(category_label),
        *(_normalize(w) for w in ALIASES.get(tab_title, ())),
        *(_normalize(w) for w in V15_ALIASES.get(tab_title, ())),
    )
    return all(term in APP_TERMS or any(term in field for field in fields) for term in terms)
