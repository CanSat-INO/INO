"""Connection diagnostics perform GET only; share labels never infer success."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_share_status import check_destination,connection_text,guidance,SetupIssue,summarize
from project_auto_core import ProjectAPI,SyncError


class API:
    repo='club/ino';branch='data/2026'
    def __init__(self,repo=None,branch=None):
        self.repository={'private':True,'permissions':{'pull':True,'push':True}} if repo is None else repo
        self.branch_result={'name':self.branch} if branch is None else branch;self.calls=[]
    def _api(self,method,path,**kwargs):
        self.calls.append((method,path));assert method=='GET'
        return self.repository if path==f'repos/{self.repo}' else self.branch_result


class ShareStatusTests(unittest.TestCase):
    def test_connection_uses_two_gets_and_encodes_branch_without_sending(self):
        api=API();result=check_destination(api)
        self.assertEqual(api.calls,[('GET','repos/club/ino'),('GET','repos/club/ino/branches/data%2F2026')])
        self.assertTrue(result['can_write']);self.assertIn('送信しません',connection_text(result))
    def test_read_only_permission_is_distinct_from_connection_failure(self):
        result=check_destination(API(repo={'private':True,'permissions':{'push':False,'pull':True}}))
        self.assertFalse(result['can_write']);self.assertIn('書込み権限はありません',connection_text(result))
    def test_missing_permission_is_not_claimed_to_be_writable(self):
        result=check_destination(API(repo={'private':True}))
        self.assertIsNone(result['can_write']);self.assertIn('確認できません',connection_text(result))
    def test_archived_repository_is_not_claimed_to_be_writable(self):
        result=check_destination(API(repo={'private':True,'archived':True,'permissions':{'push':True}}))
        self.assertFalse(result['can_write']);self.assertIn('アーカイブ',connection_text(result))
    def test_public_repository_probe_is_read_only(self):
        api=API(repo={'private':False})
        result=check_destination(api)
        self.assertIs(result['private'],False)
        self.assertIsNone(result['can_write'])
        self.assertEqual(api.calls,[
            ('GET','repos/club/ino'),
            ('GET','repos/club/ino/branches/data%2F2026')
        ])
        self.assertIn('【Public：一般公開】',connection_text(result))
        self.assertIn('送信しません',connection_text(result))
    def test_repository_and_branch_missing_have_separate_actions(self):
        api=API();api.repository=None
        with self.assertRaises(SetupIssue) as caught:check_destination(api)
        self.assertEqual(caught.exception.reason,'repository')
        api=API();api.branch_result=None
        with self.assertRaises(SetupIssue) as caught:check_destination(api)
        self.assertEqual(caught.exception.reason,'branch')
        self.assertIn('ブランチ',guidance(caught.exception)['action'])
    def test_http_auth_permission_rate_and_conflict_errors_are_distinct(self):
        for code,headers,reason in ((401,'','auth'),(403,'','permission'),(403,'X-RateLimit-Remaining: 0\n','rate'),(429,'Retry-After: 180\n','rate'),(409,'','conflict'),(503,'','network')):
            with self.subTest(code=code,reason=reason):
                with self.assertRaises(SyncError) as caught:ProjectAPI.parse_response(f'HTTP/2.0 {code} Error\n{headers}\n{{"secret":"never show"}}',1)
                self.assertEqual(caught.exception.reason,reason);self.assertNotIn('never show',str(caught.exception))
    def test_cli_login_hint_is_classified_without_exposing_stderr(self):
        api=ProjectAPI(repository='club/ino')
        response=SimpleNamespace(returncode=4,stdout='',stderr='Run gh auth login; secret-token')
        with patch('project_auto_core.subprocess.run',return_value=response):
            with self.assertRaises(SyncError) as caught:api._api('GET','repos/club/ino')
        self.assertEqual(caught.exception.reason,'auth');self.assertNotIn('secret-token',str(caught.exception))
    def test_missing_cli_and_network_timeout_provide_actionable_reasons(self):
        import subprocess
        api=ProjectAPI(repository='club/ino')
        for error,reason in ((FileNotFoundError(),'cli_missing'),(subprocess.TimeoutExpired('gh',15),'network')):
            with patch('project_auto_core.subprocess.run',side_effect=error):
                with self.assertRaises(SyncError) as caught:api._api('GET','repos/club/ino')
            self.assertEqual(caught.exception.reason,reason);self.assertTrue(guidance(caught.exception)['action'])
    def test_restart_without_confirmations_is_unknown_not_shared(self):
        result=summarize({'a':'v1'},{},enabled=True)
        self.assertEqual(result['state'],'unknown');self.assertEqual(result['shared'],0)
    def test_local_changes_and_deleted_records_do_not_reuse_stale_confirmation(self):
        result=summarize({'a':'v2','b':'v1'},{'a':'v1','b':'v1','deleted':'v1'},enabled=True,checked=True)
        self.assertEqual((result['shared'],result['pending'],result['local']),(1,1,2));self.assertEqual(result['state'],'pending')
    def test_all_matching_confirmations_are_needed_for_shared_label(self):
        result=summarize({'a':'v1','b':'v2'},{'a':'v1','b':'v2'},enabled=True,checked=True)
        self.assertEqual(result['state'],'shared');self.assertEqual(result['shared'],2)
    def test_empty_offline_disabled_and_conflict_are_not_reported_as_all_shared(self):
        self.assertEqual(summarize({},{},enabled=True,checked=True)['state'],'empty')
        self.assertEqual(summarize({'a':'v1'},{'a':'v1'},enabled=False,checked=True)['state'],'off')
        self.assertEqual(summarize({'a':'v1'},{'a':'v1'},enabled=True,checked=True,problem={'kind':'network'})['state'],'problem')
        result=summarize({'a':'v1','b':'v1'},{'a':'v1'},enabled=True,checked=True,blocked={'b':'missing folder'},conflicts={'a'})
        self.assertEqual((result['state'],result['needs'],result['shared']),('attention',2,0))


if __name__=='__main__':unittest.main()
