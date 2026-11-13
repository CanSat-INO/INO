"""Local destinations and explicitly registered model/data ZIPs."""
from datetime import datetime
from pathlib import Path
import copy
from PySide6.QtCore import Qt,QObject,QThread,Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QFormLayout,QHBoxLayout,QVBoxLayout,QLineEdit,
    QLabel,QSpinBox,QPushButton,QFileDialog,QMessageBox,QGroupBox,QListWidget,QListWidgetItem,QInputDialog)
import project_settings as settings
import project_store as store
import project_transport as transport
import shared_packages as packages
import records
from project_share_dialogs import message


def size(value):return f'{value/1024**2:.1f} MiB' if value>=1024**2 else f'{value/1024:.1f} KiB'


def configure(host):
    auto=host.project_auto
    panel=host.project_packages
    if not auto.manual_allowed() or panel.worker is not None or getattr(host,'_sync_worker',None) is not None:
        message(host,'共有処理中','自動共有をOFFにし、通信・ZIP処理の終了後に設定してください。');return
    pid=store.active_id()
    try:project=store.read_project(pid);old=settings.read(pid)
    except (ValueError,OSError) as exc:message(host,'設定を開けません',str(exc),warning=True);return
    dialog=QDialog(host);dialog.setWindowTitle('プロジェクトの共有設定');dialog.resize(650,330)
    form=QFormLayout(dialog)
    year=QSpinBox();year.setRange(1999,2200);year.setSpecialValueText('未設定');year.setValue(project.year or 1999)
    team=QLineEdit(project.team);team.setMaxLength(80)
    form.addRow('年度',year);form.addRow('班',team)
    repo=QLineEdit(old['repository']);repo.setPlaceholderText('例：CanSat-INO/INO またはリポジトリURL')
    repo.setObjectName('projectStorageRepository')
    branch=QLineEdit(old['branch']);form.addRow('GitHub共有先',repo);form.addRow('ブランチ',branch)
    root=QLineEdit(old['shared_root']);root.setPlaceholderText('未設定でも始められます')
    root.setObjectName('projectStorageRoot')
    row=QHBoxLayout();row.addWidget(root,1);choose=QPushButton('場所を選ぶ…');row.addWidget(choose)
    def choose_root():
        value=QFileDialog.getExistingDirectory(dialog,'このPCから開ける共有フォルダー',root.text())
        if value:root.setText(value)
    choose.clicked.connect(choose_root);form.addRow('重いZIPの保存先',row)
    hint=QLabel('この場所はこのPCだけの設定です。別PCでも同じZIPが見える場所を各自指定してください。\n'
        '通常のローカルフォルダーを選ぶだけでは、他PCへ共有・同期されません。\n'
        'GitHubは非公開リポジトリを指定します。保存後、自動共有はOFFのままです。')
    hint.setWordWrap(True);form.addRow(hint)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);form.addRow(buttons)
    def save():
        try:
            # Validate metadata before saving either setting.
            value=year.value() if year.value()!=1999 else None
            store.project_year(value);store._text(team.text(),'班',80)
            settings.save(pid,repo.text().strip(),branch.text().strip(),root.text().strip())
            store.update_group(pid,value,team.text())
            auto.cache={};auto.confirmed={};auto.last_signature=None
            auto.status.setText('設定を保存しました。自動共有OFF：必要な場合に有効にしてください。')
            panel.refresh();dialog.accept()
        except (ValueError,OSError) as exc:message(dialog,'保存できません',str(exc),warning=True)
    buttons.accepted.connect(save);buttons.rejected.connect(dialog.reject);dialog.exec()


class FileJob(QThread):
    succeeded=Signal(object);failed=Signal(object)
    def __init__(self,function,parent):super().__init__(parent);self.function=function
    def run(self):
        try:self.succeeded.emit(self.function(self.isInterruptionRequested))
        except Exception as exc:self.failed.emit(exc)


class PackagesPanel(QGroupBox):
    def __init__(self,host):
        super().__init__('モデル・大きいログのZIP');self.host=host;self.worker=None;self.closing=False
        layout=QVBoxLayout(self);row=QHBoxLayout();self.buttons=[]
        for label,callback in (('ファイルをZIP登録…',lambda:self.register(False)),
                ('モデルフォルダーをZIP登録…',lambda:self.register(True)),
                ('一覧を更新',self.refresh)):
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button);self.buttons.append(button)
        layout.addLayout(row)
        self.items=QListWidget();self.items.setMaximumHeight(105);self.items.setObjectName('projectZipList');layout.addWidget(self.items)
        row=QHBoxLayout()
        for label,callback in (('選択ZIPを検証して開く',self.open_selected),('選択ZIPの添付をこのPCへ復元',self.restore_selected)):
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button);self.buttons.append(button)
        layout.addLayout(row)
        self.status=QLabel();self.status.setTextFormat(Qt.PlainText);self.status.setWordWrap(True);layout.addWidget(self.status)
        self.refresh()
    def refresh(self):
        self.items.clear()
        try:
            root=settings.read(store.active_id())['shared_root']
            for record in records.load_records():
                refs=[(r,None) for r in record.get('shared_files',[])]
                value=transport.load(record)
                if value:refs.append((value['shared_zip'],value))
                for ref,value in refs:
                    packages.validate_reference(ref,record['project_id'],record['id'])
                    exists=bool(root) and packages.locate(root,ref,record['project_id'],record['id']).is_file()
                    label=f"{record.get('scenario') or ref['name']} ｜ {size(ref['bytes'])} ｜ {'未検証' if exists else 'ファイル待ち'}"
                    item=QListWidgetItem(label);item.setData(Qt.UserRole,(copy.deepcopy(record),ref,value));self.items.addItem(item)
            self.status.setText('ZIP保存先：'+(root or '未設定（ホームの共有設定で指定できます）')+
                '\nZIP本体はGitHubへ送りません。新しいZIPを登録したときに、保存先の容量を使います。')
        except (ValueError,OSError,KeyError,TypeError) as exc:self.status.setText('ZIPの設定・登録情報を確認してください：'+str(exc))
    def run_job(self,function,success):
        if self.worker is not None:return
        worker=FileJob(function,self);self.worker=worker
        for button in self.buttons:button.setEnabled(False)
        self.status.setText('ZIPを処理しています… 元のファイルは変更しません。')
        worker.succeeded.connect(success);worker.failed.connect(self.failed);worker.finished.connect(self.finished);worker.start()
    def failed(self,error):
        self.status.setText(str(error))
        if not self.closing:message(self.host,'ZIP処理を完了できません',str(error),warning=True)
    def finished(self):
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
        for button in self.buttons:button.setEnabled(True)
        if self.closing:self.host.close()
    def register(self,folder):
        try:root=packages.root_folder(settings.read(store.active_id())['shared_root'])
        except (ValueError,OSError) as exc:message(self.host,'保存先を指定してください',str(exc));return
        if folder:
            path=QFileDialog.getExistingDirectory(self.host,'共有するモデルのフォルダー');sources=[path] if path else []
        else:sources,_=QFileDialog.getOpenFileNames(self.host,'共有するログ・資料を選ぶ')
        if not sources:return
        label,ok=QInputDialog.getText(self.host,'資料の名前','台帳に表示する資料名',text=Path(sources[0]).name)
        if not ok:return
        try:
            store._text(label,'資料名',120,True);files,total=packages.collect(sources,folder)
        except (ValueError,OSError) as exc:message(self.host,'登録できません',str(exc),warning=True);return
        text=(f'{label}\n{len(files)}ファイル、元データ {size(total)}\n保存先：{root}\n\n'
              'ここに新しいZIPを作成します。元データは残ります。\n'
              '自動共有がONの場合、資料名・ファイル名・確認用ハッシュをGitHubに送ります。\n登録しますか？')
        if message(self.host,'共有ZIPを作成',text,confirm=True)!=QMessageBox.Yes:return
        record=records.new_record(module='その他',mode='共有資料',scenario=label)
        def done(ref):
            try:
                record['shared_files']=[ref];records.add_record(record)
                self.host.refresh_ledger();self.host.v16_journal_tab.reload();self.host.project_dashboard.refresh();self.refresh()
            except (ValueError,OSError) as exc:self.failed(exc)
        self.run_job(lambda cancel:packages.create(root,record['project_id'],record['id'],sources,folder=folder,cancelled=cancel),done)
    def selected(self):
        item=self.items.currentItem()
        if item is None:message(self.host,'ZIPを選択','一覧から資料を選んでください。');return None
        return item.data(Qt.UserRole)
    def open_selected(self):
        value=self.selected()
        if value is None:return
        record,ref,_=value
        try:root=settings.read(store.active_id())['shared_root']
        except (ValueError,OSError) as exc:self.failed(exc);return
        def done(path):
            self.status.setText('サイズ・SHA256・ZIP内の全ファイルを検証しました。')
            if not self.closing:QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.run_job(lambda cancel:packages.verify(root,ref,record['project_id'],record['id'],cancelled=cancel),done)
    def restore_selected(self):
        selected=self.selected()
        if selected is None:return
        record,ref,value=selected
        if value is None:message(self.host,'資料ZIP','モデル・資料ZIPは「検証して開く」から開き、必要な場所へ展開してください。');return
        if message(self.host,'添付をこのPCへ復元',f"元データ {size(ref['source_bytes'])} をこのPCの添付フォルダーへ追加します。既存ファイルは上書きしません。\n続けますか？",confirm=True)!=QMessageBox.Yes:return
        try:root=settings.read(store.active_id())['shared_root']
        except (ValueError,OSError) as exc:self.failed(exc);return
        self.run_job(lambda cancel:transport.restore(root,record,value,cancelled=cancel),lambda _:self.status.setText('添付を復元しました。既存の解析画面から使えます。'))
    def before_close(self):
        if self.worker is None:return False
        self.closing=True;self.worker.requestInterruption();return True
    def resume(self):self.closing=False
