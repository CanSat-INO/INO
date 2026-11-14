"""Read-only connection diagnostics and conservative, session-only share labels."""
from urllib.parse import quote


class SetupIssue(ValueError):
    def __init__(self,reason):
        self.reason=reason
        super().__init__(guidance(self)['title'])


def guidance(error):
    reason=getattr(error,'reason','unknown')
    choices={
        'auth':('GitHubへのログインを確認してください','Ubuntuで gh auth status を確認し、必要なら gh auth login でログインしてください。'),
        'cli_missing':('GitHub接続用のghが見つかりません','このPCのセットアップ担当者に、GitHub CLI（gh）の設定を確認してもらってください。'),
        'permission':('共有先への権限を確認してください','ログイン中のアカウントに、この班のリポジトリへの権限があるか担当者へ確認してください。'),
        'rate':('GitHubの通信制限で待機しています','待機時間が過ぎてから再確認してください。自動共有は待機後に再試行します。待機中もPC内で作業を続けられます。'),
        'network':('GitHubに接続できません','ネットワーク・VPN・GitHubへの接続を確認してください。PC内への保存は続けられます。'),
        'repository':('リポジトリを参照できません','班から案内されたリンク、ログイン中のアカウント、非公開リポジトリの閲覧権限を確認してください。'),
        'branch':('指定したブランチを参照できません','詳細設定のブランチ名と、内容を閲覧する権限を班の担当者に確認してください。'),
        'public':('この共有先は公開リポジトリです','公開データは誰でも閲覧できます。送信には別途、明示的な同意が必要です。この確認ではデータを送信していません。'),
        'conflict':('GitHubの更新が競合しています','待機後の再確認でも解消しなければ担当者へ連絡してください。同じ記録を上書きしません。'),
        'response':('GitHubの応答を確認できません','接続状態とGitHub CLIの設定を確認してください。'),
        'unknown':('共有の確認が必要です','ホームの共有状態・共有設定を確認してください。PC内への保存は続けられます。'),
    }
    title,action=choices.get(reason,choices['unknown'])
    return {'kind':reason if reason in choices else 'unknown','title':title,'action':action}


def check_destination(api):
    """Only two GETs: never try a write, create a file, or enable synchronization."""
    repo=api._api('GET',f'repos/{api.repo}',allow_404=True)
    if repo is None:raise SetupIssue('repository')
    if not isinstance(repo,dict):raise SetupIssue('response')
    # Public is valid as a destination. Unknown visibility is NOT valid.
    # This function is read-only; upload authorization is checked elsewhere.
    if type(repo.get('private')) is not bool:raise SetupIssue('response')
    branch=api._api('GET',f'repos/{api.repo}/branches/{quote(api.branch,safe="")}',allow_404=True)
    if branch is None:raise SetupIssue('branch')
    if not isinstance(branch,dict) or branch.get('name')!=api.branch:raise SetupIssue('response')
    permissions=repo.get('permissions')
    can_write=None
    if isinstance(permissions,dict):
        if any(permissions.get(k) is True for k in ('push','admin','maintain')):can_write=True
        elif permissions.get('push') is False:can_write=False
    archived=repo.get('archived') is True or repo.get('disabled') is True
    if archived:can_write=False
    return {'repository':api.repo,'branch':api.branch,'private':repo['private'],
            'can_read':True,'can_write':can_write,'read_only_repository':archived}


def connection_text(result):
    """Show visibility prominently without suggesting that probing granted consent."""
    visibility = result.get('private')
    if visibility is False:
        header = ('【Public：一般公開】ここへ送信したプロジェクト情報、実験記録、添付ファイルは'
                  '誰でも閲覧できます。\n'
                  'この接続確認・設定保存では送信しません。公開送信には別途、明示的な同意が必要です。\n')
    elif visibility is True:
        header = '【Private：非公開】接続確認・設定保存では送信しません。\n'
    else:
        header = '【公開状態は未確認】送信を始めないでください。\n'
    write=result['can_write']
    if result.get('read_only_repository'):
        detail='参照できますが、このリポジトリはアーカイブ等で書込みできない状態です。班の担当者に保存先を確認してください。'
    elif write is True:
        detail=('接続確認済み：参照できます。GitHubが書込み権限ありと報告しています。\n'
                '保護ルールによって実際の書込みが制限される場合があります。')
    elif write is False:
        detail=('接続確認済み：参照できます。実験を送信する書込み権限はありません。\n'
                '結果を送る場合は、班の担当者に書込み権限を確認してください。')
    else:
        detail=('接続確認済み：参照できます。書込み権限はこの応答では確認できません。\n'
                '送信する場合は、班の担当者に書込み権限を確認してください。')
    return header+detail


def summarize(signatures,confirmed,*,enabled,busy=False,checked=False,problem=None,blocked=(),conflicts=()):
    ids=set(signatures)
    matched={rid for rid in ids if confirmed.get(rid)==signatures[rid]}
    needs=(set(blocked)|set(conflicts))&ids
    matched-=needs
    pending=len(ids-matched-needs)
    counts={'local':len(ids),'shared':len(matched),'pending':pending,'needs':len(needs)}
    if problem:state='problem';label='接続待ち・要確認'
    elif needs:state='attention';label=f'要確認 {len(needs)}件'
    elif busy:state='syncing';label='共有を確認中'
    elif not enabled:state='off';label='自動共有OFF'
    elif not ids:state='empty';label='共有する記録なし'
    elif not checked:state='unknown';label='共有状態は未確認'
    elif pending:state='pending';label=f'共有待ち・未確認 {pending}件'
    else:state='shared';label=f'共有確認済み {len(matched)}件'
    return {**counts,'state':state,'label':label}
