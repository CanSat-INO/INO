"""Public/Private destination diagnostics are read-only and never grant consent."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_share_status import SetupIssue,check_destination,connection_text


class FakeAPI:
    repo='nanato333/WASA_Cansat_REGULUS'
    branch='master'
    def __init__(self,private=False,push=True,archived=False,missing=None):
        self.calls=[];self.private=private;self.push=push
        self.archived=archived;self.missing=missing
    def _api(self,method,path,*,allow_404=False):
        self.calls.append((method,path,allow_404))
        if path==f'repos/{self.repo}':
            if self.missing=='repo':return None
            value={'permissions':{'push':self.push},'archived':self.archived}
            if self.private is not None:value['private']=self.private
            return value
        if path==f'repos/{self.repo}/branches/{self.branch}':
            return None if self.missing=='branch' else {'name':self.branch}
        raise AssertionError(f'Unexpected API request: {method} {path}')


class ShareStatusTests(unittest.TestCase):
    def test_public_can_be_read_without_any_write_or_consent(self):
        api=FakeAPI(private=False,push=True)
        value=check_destination(api)
        self.assertIs(value['private'],False)
        self.assertIs(value['can_write'],True)
        self.assertIn('Public',connection_text(value))
        self.assertIn('同意',connection_text(value))
        self.assertEqual(len(api.calls),2)
        self.assertTrue(all(call[0]=='GET' for call in api.calls))

    def test_private_still_works(self):
        api=FakeAPI(private=True)
        value=check_destination(api)
        self.assertIs(value['private'],True)
        self.assertIn('Private',connection_text(value))
        self.assertTrue(all(method=='GET' for method,_,_ in api.calls))

    def test_missing_visibility_fails_closed(self):
        api=FakeAPI(private=None)
        with self.assertRaises(SetupIssue) as error:check_destination(api)
        self.assertEqual(error.exception.reason,'response')
        self.assertEqual(len(api.calls),1)

    def test_public_without_write_permission_is_diagnostic_only(self):
        api=FakeAPI(private=False,push=False)
        value=check_destination(api)
        self.assertIs(value['can_write'],False)
        self.assertIn('書込み権限はありません',connection_text(value))
        self.assertEqual(len(api.calls),2)

    def test_archived_public_is_read_only(self):
        api=FakeAPI(private=False,archived=True)
        value=check_destination(api)
        self.assertIs(value['can_write'],False)
        self.assertTrue(value['read_only_repository'])
        self.assertIn('アーカイブ',connection_text(value))

    def test_branch_missing_stays_failure_without_write(self):
        api=FakeAPI(private=False,missing='branch')
        with self.assertRaises(SetupIssue) as error:check_destination(api)
        self.assertEqual(error.exception.reason,'branch')
        self.assertTrue(all(method=='GET' for method,_,_ in api.calls))

    def test_repository_missing_stays_failure(self):
        api=FakeAPI(private=False,missing='repo')
        with self.assertRaises(SetupIssue) as error:check_destination(api)
        self.assertEqual(error.exception.reason,'repository')


if __name__=='__main__':unittest.main()
