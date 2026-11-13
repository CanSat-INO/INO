"""Display-only state: never saves records or chooses a user's experiment result."""
from copy import deepcopy


class FormSaveState:
    def __init__(self):
        self.saved_form=None
        self.record_id=None

    def mark_saved(self,form,record_id):
        self.saved_form=deepcopy(form)
        self.record_id=record_id

    def state(self,form):
        if self.saved_form is None:return 'unsaved'
        return 'saved' if self.saved_form==form else 'changed'


def recommended_action(*,has_csv,verified,analysis_opened,journal_opened,record_saved):
    if record_saved:return 'history'
    if not has_csv:return 'choose'
    if not verified:return 'verify'
    if journal_opened:return 'review'
    if not analysis_opened:return 'analysis'
    return 'journal'
