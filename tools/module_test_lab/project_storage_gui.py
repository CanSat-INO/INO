"""Local destinations and explicitly registered model/data ZIPs."""
from datetime import datetime
from pathlib import Path
import copy
import time
from PySide6.QtCore import Qt,QObject,QThread,Signal,QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QFormLayout,QHBoxLayout,QVBoxLayout,QLineEdit,
    QLabel,QWidget,QSpinBox,QPushButton,QFileDialog,QMessageBox,QGroupBox,QListWidget,QListWidgetItem,QInputDialog)
import project_settings as settings
import project_store as store
import project_transport as transport
import shared_packages as packages
import records
from project_share_status import check_destination,connection_text,guidance
from project_auto_core import ProjectAPI
from project_share_dialogs import message


def size(value):return f'{value/1024**2:.1f} MiB' if value>=1024**2 else f'{value/1024:.1f} KiB'


def configure(host):
    auto=host.project_auto
    if not auto.manual_allowed() or host.project_packages.worker is not None or getattr(host,'_sync_worker',None) is not None:
        message(host,'共有処理中','自動共有をOFFにし、通信・ZIP処理の終了後に設定してください。');return
    try:dialog=ShareSettingsDialog(host)
    except (ValueError,OSError) as exc:message(host,'設定を開けません',str(exc),warning=True);return
    host.project_connection_dialog=dialog
    try:dialog.exec()
    finally:host.project_connection_dialog=None;dialog.deleteLater()


class ShareSettingsDialog(QDialog):
    def __init__(self,host):
        super().__init__(host);self.host=host;self.worker=None;self.closing=False;self.close_host=False;self.probe_result=None
        self.pid=store.active_id();project=store.read_project(self.pid);old=settings.read(self.pid)
        self.setWindowTitle('プロジェクトの共有設定');self.resize(670,430)
        form=QFormLayout(self)
        self.repo=QLineEdit(old['repository']);self.repo.setPlaceholderText('班のGitHubリポジトリURLを貼り付けてください')
        self.repo.setObjectName('projectStorageRepository');form.addRow('班のGitHubリンク',self.repo)
        self.check_button=QPushButton('接続・権限を確認（送信しません）')
        self.check_button.setObjectName('projectConnectionCheck');self.check_button.clicked.connect(self.check_connection);form.addRow(self.check_button)
        self.result=QLabel('未確認でも保存できます。自動共有はOFFのままです。')
        self.result.setObjectName('projectConnectionResult');self.result.setWordWrap(True);self.result.setTextFormat(Qt.PlainText);form.addRow(self.result)
        details_button=QPushButton('詳細設定（ブランチ・年度・班）');details_button.setCheckable(True);form.addRow(details_button)
        details=QWidget();detail_form=QFormLayout(details);detail_form.setContentsMargins(0,0,0,0)
        self.branch=QLineEdit(old['branch']);self.branch.setObjectName('projectStorageBranch');detail_form.addRow('ブランチ',self.branch)
        self.year=QSpinBox();self.year.setRange(1999,2200);self.year.setSpecialValueText('未設定');self.year.setValue(project.year or 1999)
        self.team=QLineEdit(project.team);self.team.setMaxLength(80)
        detail_form.addRow('年度',self.year);detail_form.addRow('班',self.team);form.addRow(details)
        details.hide();details_button.toggled.connect(details.setVisible)
        self.root=QLineEdit(old['shared_root']);self.root.setObjectName('projectStorageRoot');self.root.setPlaceholderText('未設定でも始められます')
        row=QHBoxLayout();row.addWidget(self.root,1);choose=QPushButton('場所を選ぶ…');row.addWidget(choose)
        def choose_root():
            value=QFileDialog.getExistingDirectory(self,'このPCから開ける共有フォルダー',self.root.text())
            if value:self.root.setText(value)
        choose.clicked.connect(choose_root);form.addRow('ZIP保存先（任意）',row)
        hint=QLabel('軽い記録はGitHub、重い添付はZIPで共有します。ZIPの場所は後で設定できます。\n'
            '各PCで同じZIPが見える場所を指定してください。ローカルフォルダーを選ぶだけでは他PCへ同期されません。')
        hint.setWordWrap(True);form.addRow(hint)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);form.addRow(self.buttons)
        self.buttons.accepted.connect(self.save_settings);self.buttons.rejected.connect(self.reject)
        self.editors=(self.repo,self.branch,self.year,self.team,self.root,choose,details_button,self.check_button)
        self.repo.textChanged.connect(self.invalidate_probe);self.branch.textChanged.connect(self.invalidate_probe)
    def invalidate_probe(self,*_):
        self.probe_result=None
        self.result.setText('入力した共有先は未確認です。「接続・権限を確認」で参照だけの確認ができます。')
    def check_connection(self):
        if self.worker is not None:return
        self.probe_result=None
        try:repo,branch=settings.destination(self.repo.text(),self.branch.text())
        except ValueError as exc:self.result.setText(str(exc));return
        remaining=getattr(self.host,'project_probe_next_allowed',0)-time.monotonic()
        if remaining>0:
            self.result.setText(f'GitHubの通信制限で待機中です。あと{int(remaining)+1}秒以上待って確認してください。');return
        self.result.setText('共有先を確認しています。実験データは送信しません…')
        for widget in self.editors:widget.setEnabled(False)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
        self.worker=FileJob(lambda cancel:check_destination(ProjectAPI(repository=repo,branch=branch,cancelled=cancel)),self)
        self.worker.succeeded.connect(self.checked);self.worker.failed.connect(self.failed);self.worker.finished.connect(self.finished_check);self.worker.start()
    def checked(self,result):
        if self.closing:return
        self.probe_result=result;self.result.setText(connection_text(result))
    def failed(self,error):
        if self.closing:return
        issue=guidance(error)
        if issue['kind']=='rate':self.host.project_probe_next_allowed=time.monotonic()+max(60,getattr(error,'retry_after',60))
        self.result.setText(issue['title']+'\n'+issue['action'])
    def finished_check(self):
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
        for widget in self.editors:widget.setEnabled(True)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
        if self.closing:
            QDialog.reject(self)
            if self.close_host:QTimer.singleShot(0,self.host.close)
    def reject(self):
        if self.worker is not None:
            self.closing=True;self.worker.requestInterruption();self.result.setText('接続確認を停止してから閉じます…');return
        super().reject()
    def before_host_close(self):
        if self.worker is None:return False
        self.close_host=True;self.reject();return True
    def save_settings(self):
        if self.worker is not None or self.closing:return
        try:
            year=self.year.value() if self.year.value()!=1999 else None
            store.project_year(year);store._text(self.team.text(),'班',80)
            settings.save(self.pid,self.repo.text().strip(),self.branch.text().strip(),self.root.text().strip())
            store.update_group(self.pid,year,self.team.text())
            self.host.project_auto.reset_confirmation()
            self.host.project_auto.status.setText('設定を保存しました。自動共有OFF：必要な場合に有効にしてください。')
            self.host.project_packages.refresh();self.accept()
        except (ValueError,OSError) as exc:message(self,'保存できません',str(exc),warning=True)


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
