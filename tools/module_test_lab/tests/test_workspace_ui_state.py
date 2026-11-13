"""Display-state regressions, independent of Qt and the real ledger."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_ui_state import FormSaveState,recommended_action


class WorkspaceStateTests(unittest.TestCase):
    def test_populated_form_is_unsaved_until_success_is_reported(self):
        state=FormSaveState();form={'name':'run','observed':'pass'}
        self.assertEqual(state.state(form),'unsaved');self.assertIsNone(state.record_id)
        self.assertEqual(form,{'name':'run','observed':'pass'})
    def test_editing_after_save_and_reverting_have_distinct_states(self):
        state=FormSaveState();form={'name':'run','observed':'first','status':'未判定'}
        state.mark_saved(form,'a'*32);self.assertEqual(state.state(form),'saved')
        form['observed']='revised';self.assertEqual(state.state(form),'changed')
        self.assertEqual(state.record_id,'a'*32)
        form['observed']='first';self.assertEqual(state.state(form),'saved')
    def test_snapshot_is_independent_of_mutable_form_and_next_experiment(self):
        state=FormSaveState();form={'metrics':{'value':1}}
        state.mark_saved(form,'a'*32);form['metrics']['value']=2
        self.assertEqual(state.state(form),'changed')
        other=FormSaveState();self.assertEqual(other.state(form),'unsaved')
        state.mark_saved(form,'b'*32);self.assertEqual(state.record_id,'b'*32)
        self.assertEqual(state.state(form),'saved');self.assertIsNone(other.record_id)
    def action(self,**changes):
        value=dict(has_csv=True,verified=True,analysis_opened=False,journal_opened=False,record_saved=False)
        value.update(changes);return recommended_action(**value)
    def test_guidance_selects_or_verifies_before_suggesting_analysis(self):
        self.assertEqual(self.action(has_csv=False,verified=False),'choose')
        self.assertEqual(self.action(verified=False),'verify')
        self.assertEqual(self.action(),'analysis')
        self.assertEqual(self.action(analysis_opened=True),'journal')
    def test_existing_journal_input_is_reviewed_without_repeating_handoff(self):
        self.assertEqual(self.action(journal_opened=True),'review')
        self.assertEqual(self.action(journal_opened=True,analysis_opened=True),'review')
    def test_saved_record_does_not_require_visiting_analysis(self):
        self.assertEqual(self.action(record_saved=True),'history')
        self.assertEqual(self.action(record_saved=True,journal_opened=True),'history')


if __name__=='__main__':unittest.main()
