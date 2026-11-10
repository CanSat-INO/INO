"""Regression tests for Qt clicked(bool) -> delete_selected_local wiring.

These tests do not require Qt and never operate on production data.
"""
from __future__ import annotations
import ast
from pathlib import Path
import types
import unittest
from unittest import mock

SRC=Path(__file__).resolve().parents[1] / 'app.py'

class DeleteClickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree=ast.parse(SRC.read_text(encoding='utf-8'))
        cls.window=next(c for c in cls.tree.body if isinstance(c, ast.ClassDef) and c.name=='TestLab')

    def test_button_wiring_does_not_pass_checked_bool_as_id_list(self):
        method=next(f for f in self.window.body if isinstance(f,ast.FunctionDef) and f.name=='build_ledger_tab')
        connections=[n for n in ast.walk(method) if isinstance(n,ast.Call)
                     and isinstance(n.func,ast.Attribute) and n.func.attr=='connect']
        matching=[n for n in connections if isinstance(n.func.value,ast.Attribute)
                  and n.func.value.attr=='clicked' and isinstance(n.func.value.value,ast.Attribute)
                  and n.func.value.value.attr=='delete_local_button']
        self.assertEqual(len(matching),1)
        self.assertEqual(len(matching[0].args),1)
        callback=matching[0].args[0]
        self.assertIsInstance(callback,ast.Lambda)
        self.assertEqual([p.arg for p in callback.args.args],['checked'])
        self.assertIsInstance(callback.body,ast.Call)
        self.assertIsInstance(callback.body.func,ast.Attribute)
        self.assertEqual(callback.body.func.attr,'delete_local_selected')
        self.assertEqual(callback.body.args,[])
        self.assertEqual(callback.body.keywords,[])

    def _method(self, **kwargs):
        f=next(f for f in self.window.body if isinstance(f,ast.FunctionDef) and f.name=='delete_local_selected')
        module=ast.Module(body=[f],type_ignores=[])
        m=types.SimpleNamespace(Yes=1,No=2, question=mock.Mock(return_value=kwargs.get('confirm',2)),
                                information=mock.Mock(),warning=mock.Mock())
        delete=mock.Mock(return_value={'deleted':1,'archive':'/tmp/TEST_ONLY.zip'})
        env={'QMessageBox':m,'delete_selected':delete}
        ns={}
        exec(compile(ast.fix_missing_locations(module),'<isolated_delete_method>','exec'), env,ns)
        return ns['delete_local_selected'],m,delete

    def test_checked_false_uses_selected_rows_and_still_requires_confirmation(self):
        function, msg, delete = self._method(confirm=2)
        self_obj=types.SimpleNamespace(_sync_worker=None, selected_ids=lambda:['a'*32],
                refresh_ledger=mock.Mock(),v16_journal_tab=types.SimpleNamespace(reload=mock.Mock()))
        function(self_obj, False)
        msg.question.assert_called_once()
        delete.assert_not_called()
        self_obj.refresh_ledger.assert_not_called()

    def test_no_selected_rows_shows_message_without_deleting(self):
        function,msg,delete=self._method(confirm=1)
        self_obj=types.SimpleNamespace(_sync_worker=None,selected_ids=lambda:[])
        function(self_obj,False)
        msg.information.assert_called_once()
        msg.question.assert_not_called()
        delete.assert_not_called()

    def test_explicit_selected_record_ids_supported_for_journal_tab(self):
        function,msg,delete=self._method(confirm=1)
        self_obj=types.SimpleNamespace(_sync_worker=None,selected_ids=lambda:[],
                refresh_ledger=mock.Mock(),v16_journal_tab=types.SimpleNamespace(reload=mock.Mock()))
        function(self_obj,record_ids=['a'*32])
        delete.assert_called_once_with(['a'*32])
        self_obj.refresh_ledger.assert_called_once()
        self_obj.v16_journal_tab.reload.assert_called_once()
        msg.information.assert_called_once()

if __name__=='__main__':
    unittest.main()
