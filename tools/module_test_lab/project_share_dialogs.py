"""Explicit, local project sharing actions used by the hub and dashboard."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox
import project_store as store
import project_share as sharing


def message(parent, title, text, *, confirm=False, warning=False):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.PlainText)
    box.setText(text)
    box.setIcon(QMessageBox.Question if confirm else QMessageBox.Warning if warning else QMessageBox.Information)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No if confirm else QMessageBox.Ok)
    if confirm:
        box.setDefaultButton(QMessageBox.No)
    return box.exec()


def export_project(parent, project_id):
    try:
        project = store.read_project(project_id)
        destination, _ = QFileDialog.getSaveFileName(parent, 'プロジェクト共有ファイルを保存',
            str(Path.home() / f'project-{project.id[:8]}.cansat-project.json'), sharing.FILTER)
        if not destination:
            return
        if not destination.endswith('.json'):
            destination += '.cansat-project.json'
        size = sharing.export_share(project.id, Path(destination))
        message(parent, '共有ファイルを保存しました',
                f'{project.name}\nID: {project.id}\n\n'
                f'保存先: {destination}\nサイズ: {size:,}バイト\n\n'
                'このファイルをメンバーへ渡してください。受け取った人はトップ画面の'
                '「共有ファイルから追加」で登録できます。\n'
                '含まれるのはプロジェクトID・名前・担当者・目的です。実験記録・添付は含まれません。')
    except (OSError, ValueError, UnicodeError) as exc:
        message(parent, '共有ファイルを保存できません', str(exc), warning=True)


def import_project(parent):
    """Return a registration only after preview and explicit local confirmation."""
    try:
        source, _ = QFileDialog.getOpenFileName(parent, '共有プロジェクトを追加', str(Path.home()), sharing.FILTER)
        if not source:
            return None
        document = sharing.read_share(Path(source))
        project = sharing.validate(document)
        text = (f'プロジェクト: {project["name"]}\n担当者・チーム: {project["owner"] or "未入力"}\n'
                f'目的: {project["purpose"] or "未入力"}\nID: {project["id"]}\n\n'
                'このPCに登録しますか？\n'
                '同じIDのプロジェクトがある場合は、そのプロジェクトを選択します。'
                '既存の記録・添付・プロジェクト情報は上書きしません。\n'
                '実験データは別途、既存の実験ZIPまたは手動GitHub共有で受け取ります。'
                'この操作だけではデータは同期されません。')
        if message(parent, '共有プロジェクトを確認', text, confirm=True) != QMessageBox.Yes:
            return None
        result = sharing.register(document)
        details = ('プロジェクトを追加しました。選択して開けます。' if result.created else
                   '同じIDのプロジェクトは登録済みです。既存のプロジェクトを選択しました。')
        if result.metadata_differs:
            details += '\n名前・担当者・目的が共有元と異なるため、このPCの情報をそのまま保持しました。'
        message(parent, 'プロジェクトの登録', details)
        return result
    except (OSError, ValueError, UnicodeError) as exc:
        message(parent, 'プロジェクトを追加できません', str(exc), warning=True)
        return None
