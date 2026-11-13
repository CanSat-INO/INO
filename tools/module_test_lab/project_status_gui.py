"""Compact project-wide status; no polling network calls and no automatic writes."""
from pathlib import Path
from PySide6.QtCore import QObject,Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QPushButton
import records
import project_store as store
import project_settings as settings
from project_auto_core import digest
from project_share_status import summarize


class ProjectStatusStrip(QObject):
    def __init__(self,host):
        super().__init__(host);self.host=host;self.signatures={};self.summary={};self.detail='';self.dialog=None;self.read_problem=False
        self.button=QPushButton('保存・共有の状態…');self.button.setObjectName('projectStatusDetails')
        self.button.setStyleSheet('padding: 3px 8px; font-size: 12px; min-height: 16px;')
        self.button.clicked.connect(self.show_details);host.statusBar().addPermanentWidget(self.button)
        host.ledger_changed.connect(self.local_changed)
        host.project_auto.state_changed.connect(self.sync_changed)
        host.navigation.tabs.currentChanged.connect(self.render)
        workflow=host.v20_workflow_tab
        workflow.state_changed.connect(self.render)
        host.v16_journal_tab.record_saved.connect(self.local_changed)
        self.local_changed()
    def local_changed(self,*_):
        # Refresh only on ledger/network events. Typing only renders cached counts.
        try:self.signatures={r['id']:digest(r) for r in records.load_records()}
        except (ValueError,OSError,KeyError,TypeError):
            self.read_problem=True
            self.detail='台帳を読み取れません。ホームの品質点検や保存先を確認してください。'
            self.render();return
        self.read_problem=False
        self.render()
    def sync_changed(self):self.local_changed()
    def render(self,*_):
        if self.read_problem:
            self.summary={'state':'unavailable','label':'台帳の読取待ち'}
            self.host.statusBar().showMessage('台帳：読取待ち ｜ 共有状態：未確認')
            self.host.statusBar().setToolTip(self.detail)
            self.button.setToolTip('台帳を読み取れないため共有状態は未確認です。')
            self.update_dialog()
            return
        auto=self.host.project_auto
        blocked={rid:value for rid,value in auto.blocked.items() if rid in self.signatures}
        conflicts=set(auto.conflicts)&set(self.signatures)
        self.summary=summarize(self.signatures,auto.confirmed,enabled=auto.checkbox.isChecked(),
            busy=auto.worker is not None,checked=auto.has_synced,problem=auto.last_problem,
            blocked=blocked,conflicts=conflicts)
        current=self.host.tabs.currentWidget();workflow=self.host.v20_workflow_tab;journal=self.host.v16_journal_tab
        prefix=''
        if current is workflow:
            draft='未保存' if workflow.saved_snapshot is None or workflow.saved_snapshot!=workflow._snapshot() else '保存済'
            changed=(workflow.record_id and journal.form_save_state.record_id==workflow.record_id
                     and journal.form_save_state.state(journal._form_data())=='changed')
            result='未保存の変更あり' if changed else '保存確認済' if workflow.record_id else '未保存'
            prefix=f'下書き：{draft}／結果：{result} ｜ '
        elif current is journal:
            result={'unsaved':'未保存','saved':'保存済','changed':'未保存の変更あり'}[journal.form_save_state.state(journal._form_data())]
            prefix=f'記録票：{result} ｜ '
        self.host.statusBar().showMessage(prefix+f"PC保存 {self.summary['local']}件 ｜ GitHub：{self.summary['label']}")
        try:
            value=settings.read(store.active_id())
            target=(value['repository']+' / '+value['branch']) if value['repository'] else '未設定：ホームの共有設定から指定してください'
            root=value['shared_root'] or '未設定（軽い記録の共有には不要）'
        except (ValueError,OSError) as exc:target='設定を読み取れません';root='共有設定を確認してください'
        last=auto.last_success.strftime('%Y-%m-%d %H:%M:%S') if auto.last_success else 'この起動では未確認'
        self.detail=(f'プロジェクト：{store.project_title()}\nPCの台帳保存先：{records.DATA_DIR}\n共有先：{target}\n\n'
            f"このPCの台帳：{self.summary['local']}件\nGitHub照合済み：{self.summary['shared']}件\n"
            f"共有待ち・未確認：{self.summary['pending']}件\n要確認：{self.summary['needs']}件\n"
            f'最終確認：{last}\n\nZIP保存先：{root}\n'
            'ZIP本体が他PCに到着したか・展開済みかは、この件数には含みません。\n'
            '未保存の入力は送信対象ではありません。共有確認は、この起動中に記録内容を照合した結果です。')
        if auto.last_problem:self.detail+='\n\n'+auto.last_problem['title']+'\n'+auto.last_problem['action']
        if blocked:self.detail+='\n\n共有できていない記録：'+str(next(iter(blocked.values())))[:400]+'\nZIP保存先・元の添付ファイルを確認してください。'
        if conflicts:self.detail+='\n\n同じIDで異なる内容があります。既存の記録は上書きしません。修正結果は新しい記録として保存してください。'
        if not auto.checkbox.isChecked():self.detail+='\n\n自動共有はOFFです。ホームで送信先・対象を確認してONにできます。'
        self.button.setToolTip(self.summary['label']);self.host.statusBar().setToolTip(self.detail)
        self.update_dialog()
    def update_dialog(self):
        if self.dialog is None:return
        text=self.dialog.findChild(QPlainTextEdit,'projectStatusDetailText')
        if text.toPlainText()!=self.detail:
            position=text.verticalScrollBar().value();text.setPlainText(self.detail);text.verticalScrollBar().setValue(position)
    def show_details(self):
        if self.dialog is not None:self.dialog.raise_();return self.dialog
        dialog=QDialog(self.host);dialog.setWindowTitle('保存・共有の状態');dialog.resize(640,400)
        layout=QVBoxLayout(dialog);text=QPlainTextEdit();text.setPlainText(self.detail);text.setObjectName('projectStatusDetailText')
        text.setReadOnly(True);layout.addWidget(text,1);row=QHBoxLayout();layout.addLayout(row)
        configure=QPushButton('共有設定…');row.addWidget(configure)
        def open_settings():
            from project_storage_gui import configure
            configure(self.host)
        configure.clicked.connect(open_settings)
        home=QPushButton('ホームで共有を操作');row.addWidget(home)
        home.clicked.connect(lambda:(dialog.accept(),self.host.navigation.show_home()))
        close=QPushButton('閉じる');close.clicked.connect(dialog.reject);row.addWidget(close)
        self.dialog=dialog
        def finished():self.dialog=None;dialog.deleteLater()
        dialog.finished.connect(finished);dialog.open();return dialog
