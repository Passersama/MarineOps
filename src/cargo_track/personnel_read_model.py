"""Detached, selected-roster UI projection. No filesystem or SQLite access."""
from copy import deepcopy
from pathlib import Path
from .personnel_import import PersonnelError
from .personnel_service import PersonnelService


class PersonnelReadModel(PersonnelService):
    def __init__(self,path,state):
        self.path=Path(path)
        self.state=state

    def settings(self):return dict(self.state.get('settings',{}))
    def plans(self):return deepcopy(self.state.get('plans',[]))
    def passengers(self,plan_id):
        if plan_id and plan_id!=self.state.get('plan_id'):
            raise PersonnelError('The selected crew list is loading. Try again when it is ready.')
        return deepcopy(self.state.get('passengers',[])) if plan_id else []
    def passenger(self,identifier):
        row=next((r for r in self.state.get('passengers',[]) if r['id']==identifier),None)
        if row is None:raise PersonnelError('The crew entry changed. Refresh the list.')
        return deepcopy(row)
    def context(self,plan_id):
        value=self.state.get('context')
        if not value or value['plan_id']!=plan_id:
            raise PersonnelError('The selected crew list is loading. Try again when it is ready.')
        return deepcopy(value)
    def _alias_record(self,source,label):
        return next((r for r in self.state.get('aliases',[]) if r['source_path']==source and r['alias']==label),None)
    def berth_summaries(self):return deepcopy(self.state.get('versions',[]))
