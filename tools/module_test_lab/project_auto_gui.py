"""Background network jobs, foreground ledger merges, and opt-in controls."""
from datetime import datetime
import copy
import time
from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QGroupBox,QVBoxLayout,QHBoxLayout,QCheckBox,QLabel,QPushButton,QListWidget,QListWidgetItem,QMessageBox,QLineEdit,QWidget
import project_auto_core as core
import project_store as store
import project_share
from project_share_dialogs import message
import records
import project_settings as settings
import project_transport as transport
from project_share_status import guidance


class Job(QThread):
    succeeded=Signal(object)
    failed=Signal(object)
    def __init__(self,function,parent,destination):
        super().__init__(parent);self.function=function;self.destination=destination
    def run(self):
        try:
            api=core.ProjectAPI(repository=self.destination[0],branch=self.destination[1],cancelled=self.isInterruptionRequested)
            self.succeeded.emit(self.function(api))
        except Exception as exc:self.failed.emit(exc)


class Background(QObject):
    def __init__(self,host,status,interval=5000):
        super().__init__(host)
        self.host=host;self.status=status;self.worker=None;self.closing=False
        self.next_allowed=0;self.failures=0
        self.timer=QTimer(self);self.timer.setInterval(interval);self.timer.timeout.connect(self.tick)
    def run_job(self,function,success):
        if self.worker is not None:return
        worker=Job(function,self,self.destination());self.worker=worker
        worker.succeeded.connect(success);worker.failed.connect(self.failed)
        worker.finished.connect(self.finished);worker.start()
    def destination(self):
        return settings.current_destination()
    def failed(self,error):
        if isinstance(error,core.Cancelled):return
        self.failures+=1
        wait=max(getattr(error,'retry_after',0),min(900,60*2**min(self.failures-1,4)))
        self.next_allowed=time.monotonic()+wait
        issue=guidance(error)
        self.status.setText(f"同期保留：{issue['title']}\n{issue['action']}\n詳細：{str(error)[:400]}\n{wait}秒以上待って再確認します。保存はPC内で継続できます。")
    def finished(self):
        worker=self.worker;self.worker=None
        if worker:worker.deleteLater()
        if self.closing:self.host.close()
    def before_close(self):
        self.timer.stop()
        if self.worker is not None:
            self.closing=True;self.worker.requestInterruption()
            self.status.setText('通信を停止してから終了します。保存済みデータはPC内に残ります。')
            return True
        return False
    def resume(self):
        self.closing=False;self.timer.start()


class ProjectController(Background):
    state_changed=Signal()
    def __init__(self,host,status,checkbox,button):
        super().__init__(host,status)
        self.checkbox=checkbox;self.button=button;self.cache={};self.confirmed={}
        self.last_attempt=0;self.last_signature=None;self.soon=False
        self.project_id=store.active_id()
        self.last_problem=None;self.blocked={};self.conflicts=set();self.has_synced=False;self.last_success=None
        error=None
        try:value=core.enabled(self.project_id)
        except (ValueError,OSError) as exc:value=False;error=str(exc)
        checkbox.setChecked(value);button.setEnabled(value)
        checkbox.toggled.connect(self.toggle);button.clicked.connect(self.request_now)
        if not value:status.setText('自動共有OFF：記録はこのPCに保存します。')
        if error:status.setText('自動共有の設定を確認してください：'+error)
        self.timer.start();QTimer.singleShot(0,self.tick)

    def request_public_consent(self):
        """Check remote visibility in a background worker before prompting."""
        if self.worker is not None or getattr(self.host,'_sync_worker',None) is not None:
            message(self.host,'通信中','現在の同期が終わってから公開設定を確認してください。')
            return
        try:self.destination()
        except (ValueError,OSError) as exc:
            message(self.host,'共有先が未設定です',str(exc),warning=True);return
        self.status.setText('GitHubの公開設定と書き込み権限を確認中…')
        self.run_job(lambda api:api.repository_info(require_push=True),self.finish_public_consent)

    def finish_public_consent(self,info):
        repo,branch=info['repository'],info['branch']
        try:
            if not settings.same_destination(self.destination(),(repo,branch)):
                raise ValueError('共有先が変更されました。公開への同意をやり直してください。')
            if info['private']:
                self.status.setText('共有先はPrivateです。公開への同意は不要です。')
                return
            project=store.read_project(self.project_id)
            text=(f'【一般公開されます】\n送信先：{repo}\nブランチ：{branch}\n'
                  f'プロジェクト：{project.name}（ID: {self.project_id}）\n\n'
                  '次の内容は、GitHubを閲覧できる世界中の人に公開されます。\n'
                  '・プロジェクト情報（名前、年度、担当者など）\n'
                  '・既存の全実験記録（測定値、メモ、担当者など）\n'
                  '・900KB以下の添付ファイル（CSV等）\n'
                  '・今後保存する実験記録と添付ファイル\n'
                  '・大きなZIPの別途保存先を使う場合、その参照情報\n\n'
                  '送信後に設定をOFFにしても、GitHub上の公開データや履歴は消えません。\n'
                  '秘密情報・個人情報が含まれていないことを確認してください。\n\n'
                  'この送信先への公開を明示的に許可しますか？')
            if message(self.host,'Publicリポジトリへの公開に同意する',text,confirm=True)!=QMessageBox.Yes:
                self.status.setText('公開への同意はキャンセルされました。送信は許可されていません。')
                return
            settings.set_public_consent(self.project_id,repo,branch)
            self.last_attempt=0;self.next_allowed=0;self.failures=0
            self.status.setText('この送信先への公開同意を保存しました。自動共有がONなら同期します。')
            if self.checkbox.isChecked():QTimer.singleShot(100,self.tick)
        except (OSError,ValueError) as exc:
            message(self.host,'公開設定を保存できません',str(exc),warning=True)

    def toggle(self,value):
        if value:
            if getattr(self.host,'_sync_worker',None) is not None:
                message(self.host,'手動同期中','手動同期が終わってから自動共有を有効にしてください。')
                self.checkbox.blockSignals(True);self.checkbox.setChecked(False);self.checkbox.blockSignals(False);return
            try:repo,branch=self.destination()
            except (ValueError,OSError) as exc:
                self.checkbox.blockSignals(True);self.checkbox.setChecked(False);self.checkbox.blockSignals(False)
                message(self.host,'共有先が未設定です',str(exc));return
            project=store.read_project(self.project_id)
            text=(f'「{project.name}」のプロジェクト情報と、保存済みの全実験記録・添付、今後保存する記録を'
                  f' {repo} / {branch} のGitHubへ自動送信します。\n'
                  'リポジトリを閲覧できる班員が受け取れます。未保存の入力は送信しません。\n'
                  '受信した記録・添付の分だけ、このPCの保存容量を使います。\n'
                  '900KBを超える添付は設定した共有フォルダーへZIPで保存します。未設定なら送信保留になります。\n'
                  'ZIPは確認・復元を選ぶまでこのPCへ展開しません。同一IDの変更や削除は他PCへ反映しません。\n'
                  'Publicへの送信には、画面の「公開送信の同意」から別途許可が必要です。\n\n有効にしますか？')
            if message(self.host,'自動共有を有効にする',text,confirm=True)!=QMessageBox.Yes:
                self.checkbox.blockSignals(True);self.checkbox.setChecked(False);self.checkbox.blockSignals(False);return
        try:core.set_enabled(self.project_id,value)
        except (ValueError,OSError) as exc:
            self.checkbox.blockSignals(True);self.checkbox.setChecked(not value);self.checkbox.blockSignals(False)
            message(self.host,'設定を保存できません',str(exc),warning=True);return
        self.button.setEnabled(value)
        self.last_problem=None
        if not value:
            if self.worker:self.worker.requestInterruption()
            self.status.setText('自動共有OFF：送信を停止します。既にGitHubに保存されたデータは残ります。')
        else:
            self.last_signature=None;self.last_attempt=0;self.tick()
        self.state_changed.emit()
    def reset_confirmation(self):
        self.cache={};self.confirmed={};self.last_signature=None
        self.last_problem=None;self.blocked={};self.conflicts=set();self.has_synced=False;self.last_success=None
        self.state_changed.emit()
    def finished(self):
        super().finished()
        self.state_changed.emit()
    def manual_allowed(self):
        return not self.checkbox.isChecked() and self.worker is None
    def failed(self,error):
        super().failed(error)
        if isinstance(error,core.Cancelled):return
        self.last_problem=guidance(error)
        self.state_changed.emit()
        try:
            pending=sum(self.confirmed.get(r['id'])!=core.digest(r) for r in records.load_records())
            self.status.setText(self.status.text()+f'\n未送信・要確認：{pending}件')
        except (ValueError,OSError,KeyError,TypeError):pass
    def request_now(self):
        if time.monotonic()<self.next_allowed:return
        self.last_attempt=0;self.tick()
    def tick(self):
        if (self.closing or not self.checkbox.isChecked() or self.worker is not None
                or getattr(self.host,'_sync_worker',None) is not None):return
        now=time.monotonic()
        if now<self.next_allowed:return
        try:
            from record_trash import deleted_ids
            with records.transaction():
                local=copy.deepcopy(records.load_records());deleted=deleted_ids()
            signature=tuple((r['id'],core.digest(r)) for r in local)
            changed=signature!=self.last_signature
            if self.last_attempt and now-self.last_attempt<(5 if changed or self.soon else core.INTERVAL):return
            doc=core.document(store.read_project(self.project_id))
        except (ValueError,OSError,KeyError,TypeError) as exc:self.failed(exc);return
        self.last_signature=signature;self.last_attempt=now;self.soon=False
        self.status.setText('GitHubと自動共有中… PC内への保存は続けられます。')
        cache=dict(self.cache);root=records.ATTACHMENTS_DIR
        try:
            project_config=settings.read(self.project_id)
            shared_root=project_config['shared_root']
            public_consent=project_config['public_consent']
        except (ValueError,OSError) as exc:self.failed(exc);return
        self.run_job(lambda api:api.cycle(doc,local,root,deleted,cache,shared_root,public_consent),self.success)
        self.state_changed.emit()
    def success(self,result):
        if not self.checkbox.isChecked() or self.closing:return
        try:
            received=core.receive(result['received'])
            with records.transaction():
                snapshot={r['id']:r for r in records.load_records()}
                for record,value in result.get('transports',[]):
                    if snapshot.get(record['id'])==record:transport.save(record,value)
            self.cache=result['cache'];self.confirmed.update(result['confirmed'])
            conflicts=set(result['conflicts'])|set(received['conflicts'])
            for rid in conflicts|set(result['blocked']):self.confirmed.pop(rid,None)
            current=records.load_records()
            incoming={entry[0]['id']:core.digest(entry[0]) for entry in result['received']}
            for rec in current:
                if incoming.get(rec['id'])==core.digest(rec):self.confirmed[rec['id']]=incoming[rec['id']]
            pending=sum(self.confirmed.get(r['id'])!=core.digest(r) for r in current)
            self.soon=pending>len(conflicts)+len(result['blocked'])
            self.failures=0;self.next_allowed=0
            self.last_problem=None;self.blocked=dict(result['blocked']);self.conflicts=conflicts
            self.has_synced=True;self.last_success=datetime.now().astimezone()
            text=(f'最終同期 {datetime.now().astimezone():%H:%M:%S} ｜ 未送信・要確認 {pending}件'
                  f' ｜ 受信 {received["added"]}件 ｜ 競合 {len(conflicts)}件')
            if result['blocked']:text+='\n未送信：'+next(iter(result['blocked'].values()))
            if result['metadata_differs']:text+='\nプロジェクト名・担当者等はこのPCの情報を保持しています。'
            self.status.setText(text)
            if received['added']:
                self.host.refresh_ledger();self.host.v16_journal_tab.reload()
                self.host.project_dashboard.refresh()
                self.host.project_packages.refresh()
            self.state_changed.emit()
        except (ValueError,OSError,KeyError,TypeError) as exc:self.failed(exc)


class AutoPanel(QGroupBox):
    def __init__(self,host):
        super().__init__('班との自動共有')
        layout=QVBoxLayout(self);row=QHBoxLayout()
        checkbox=QCheckBox('このプロジェクトをGitHubと自動共有')
        checkbox.setObjectName('projectAutoEnabled');row.addWidget(checkbox,1)
        button=QPushButton('今すぐ同期');button.setObjectName('projectAutoNow');row.addWidget(button)
        layout.addLayout(row)
        public_button=QPushButton('公開送信の同意（Publicのみ）')
        public_button.setObjectName('projectPublicConsent')
        layout.addWidget(public_button)
        status=QLabel();status.setTextFormat(Qt.PlainText);status.setWordWrap(True)
        status.setObjectName('projectAutoStatus');layout.addWidget(status)
        host.project_auto=ProjectController(host,status,checkbox,button)
        public_button.clicked.connect(host.project_auto.request_public_consent)


class CatalogPanel(QGroupBox):
    def __init__(self,host):
        super().__init__('班のリンクから参加')
        self.host=host;self.docs={};self.cache={};self.last_attempt=0
        self.source_private=None  # Unknown is treated as public for auto-enable safety.
        try:self.source=settings.catalog()
        except (ValueError,OSError):self.source={'repository':'','branch':'main','enabled':False}
        layout=QVBoxLayout(self)
        hint=QLabel('班から案内されたGitHubリポジトリのリンクを貼り付けて、プロジェクトを探してください。')
        hint.setWordWrap(True); layout.addWidget(hint)
        source_row=QHBoxLayout()
        self.repository=QLineEdit(self.source['repository'])
        self.repository.setPlaceholderText('例：https://github.com/CanSat-INO/INO')
        self.repository.setAccessibleName('班のGitHubリポジトリのリンク')
        self.repository.setObjectName('projectCatalogRepository');source_row.addWidget(self.repository,3)
        self.search_button=QPushButton('プロジェクトを探す')
        self.search_button.setObjectName('projectCatalogSearch')
        self.search_button.clicked.connect(self.search);source_row.addWidget(self.search_button)
        self.repository.returnPressed.connect(self.search)
        layout.addLayout(source_row)
        details=QPushButton('詳細設定（通常は変更不要）')
        details.setObjectName('projectCatalogDetails');details.setCheckable(True);layout.addWidget(details)
        self.details_area=QWidget()
        detail_layout=QHBoxLayout(self.details_area);detail_layout.setContentsMargins(0,0,0,0)
        detail_layout.addWidget(QLabel('班から指定されたブランチ'))
        self.branch=QLineEdit(self.source['branch']);self.branch.setObjectName('projectCatalogBranch')
        detail_layout.addWidget(self.branch,1)
        layout.addWidget(self.details_area);self.details_area.hide()
        details.toggled.connect(self.details_area.setVisible)
        self.checkbox=QCheckBox('参加候補の一覧を自動更新する（約60秒ごと）')
        self.checkbox.setObjectName('projectCatalogEnabled');layout.addWidget(self.checkbox)
        self.items=QListWidget();self.items.setMaximumHeight(110);self.items.setMinimumHeight(60)
        self.items.setObjectName('projectCatalogList');layout.addWidget(self.items)
        self.join=QPushButton('選択した共有プロジェクトに参加して開く')
        self.join.setObjectName('projectCatalogJoin');self.join.setEnabled(False);layout.addWidget(self.join)
        self.status=QLabel('リンクを入れて「プロジェクトを探す」を押してください。');self.status.setTextFormat(Qt.PlainText);self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.background=CatalogController(self)
        self.items.currentItemChanged.connect(lambda current,previous:self.join.setEnabled(current is not None))
        self.join.clicked.connect(self.join_project)
        self.checkbox.toggled.connect(self.toggle)
        try:self.checkbox.setChecked(core.catalog_enabled())
        except (ValueError,OSError) as exc:self.status.setText(str(exc))
        self.items.setVisible(self.checkbox.isChecked());self.join.setVisible(self.checkbox.isChecked())
    def set_source(self):
        if self.background.worker is not None:
            message(self.host,'取得中','通信の終了後に取得先を変更してください。');return False
        try:
            repo,branch=settings.destination(self.repository.text(),self.branch.text())
            settings.catalog(False,repository=repo,branch=branch,enabled=False)
            self.source=settings.catalog();self.checkbox.setChecked(False)
            self.docs={};self.cache={};self.items.clear();self.join.setEnabled(False)
            self.source_private=None
            self.status.setText(f'共有先：{repo} / {branch}')
            return True
        except (ValueError,OSError) as exc:
            message(self.host,'リンクを確認してください',str(exc),warning=True)
            return False
    def search(self):
        if self.set_source():
            self.checkbox.setChecked(True)
            if self.background.worker is None and self.background.next_allowed>time.monotonic():
                self.status.setText('通信の待機中です。少し待つと自動で再確認します。')
    def toggle(self,value):
        try:core.set_catalog_enabled(value)
        except (OSError,ValueError) as exc:
            self.checkbox.blockSignals(True);self.checkbox.setChecked(not value);self.checkbox.blockSignals(False)
            self.status.setText(str(exc));return
        self.items.setVisible(value);self.join.setVisible(value)
        if value:self.last_attempt=0;self.background.tick()
        else:
            if self.background.worker:self.background.worker.requestInterruption()
            self.status.setText('一覧の自動更新は停止中です。「プロジェクトを探す」で再確認できます。')
    def joined_catalog(self,result):
        if not self.checkbox.isChecked() or self.background.closing:return
        self.cache=result['cache'];self.source_private=result.get('private') is True
        selected=self.items.currentItem()
        selected_id=selected.data(Qt.UserRole) if selected else None
        self.items.clear();self.docs={}
        for doc in result['projects']:
            p=project_share.validate(doc);self.docs[p['id']]=doc
            item=QListWidgetItem(p['name']+' ｜ '+str(p.get('year','年度未設定'))+' '+p.get('team','')+' ｜ '+(p['owner'] or '担当者未入力')+' ｜ '+p['id'][:8])
            item.setData(Qt.UserRole,p['id']);self.items.addItem(item)
            if p['id']==selected_id:self.items.setCurrentItem(item)
        self.background.failures=0;self.background.next_allowed=0
        self.status.setText(f'{len(self.docs)}件見つかりました。プロジェクトを選んで参加してください。' if self.docs else '共有プロジェクトはまだありません。作成した人に、プロジェクトのホームで自動共有をONにしてもらってください。')
    def join_project(self):
        item=self.items.currentItem()
        if item is None:return
        doc=self.docs[item.data(Qt.UserRole)];p=project_share.validate(doc)
        share_policy=('Privateのため参加後に自動共有を有効にします。'
                      if self.source_private else 'Publicまたは公開状態未確認のため、参加後の自動共有はOFFです。')
        auto_policy=('自動共有を有効にすると、このPCの既存・今後の記録と添付がGitHubへ送信されます。'
                     if self.source_private else
                     'Publicでは参加しても自動送信されません。公開同意と自動共有の操作が別途必要です。')
        text=(f'「{p["name"]}」に参加して開きます。{share_policy}\n'
              f'共有先: {self.source["repository"]} / {self.source["branch"]}\n'
              f'年度・班: {p.get("year","未設定")} {p.get("team","")}\n担当者: {p["owner"] or "未入力"}\nID: {p["id"]}\n'
              f'{auto_policy}\n'
              '受信したデータの分だけ、このPCの保存容量を使います。\n'
              '既存の同じIDの記録・プロジェクト情報は上書きしません。\n\n参加しますか？')
        if message(self.host,'共有プロジェクトへ参加',text,confirm=True)!=QMessageBox.Yes:return
        try:
            repo,branch=settings.destination(self.source['repository'],self.source['branch'])
            directory=store.base_dir()/'projects'/p['id']/'project.json'
            previous=settings.read(p['id']) if directory.exists() else None
            if previous and previous['repository'] and not settings.same_destination((previous['repository'],previous['branch']),(repo,branch)):
                raise ValueError('同じIDのプロジェクトが別のGitHub共有先に登録済みです。ホームの共有設定から確認してください。')
            result=project_share.register(doc)
            settings.save(result.project.id,repo,branch,previous['shared_root'] if previous else '')
            core.set_enabled(result.project.id,self.source_private is True)
            self.host.reload();self.host.launch(result.project.id)
        except (OSError,ValueError) as exc:message(self.host,'参加できません',str(exc),warning=True)


class CatalogController(Background):
    def __init__(self,panel):
        super().__init__(panel.host,panel.status,core.INTERVAL*1000)
        self.panel=panel;self.timer.start();QTimer.singleShot(0,self.tick)
    def destination(self):
        return self.panel.source['repository'],self.panel.source['branch']
    def tick(self):
        panel=self.panel;now=time.monotonic()
        if (self.closing or not panel.checkbox.isChecked() or self.worker is not None
                or not panel.host.isVisible() or now<self.next_allowed
                or (panel.last_attempt and now-panel.last_attempt<core.INTERVAL)):return
        panel.last_attempt=now;self.status.setText('GitHubの共有プロジェクトを取得中…')
        cache=dict(panel.cache)
        self.run_job(lambda api:api.catalog(cache),panel.joined_catalog)
