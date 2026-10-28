"""Frontend state; business and publication checks stay in the services."""
from dataclasses import dataclass

@dataclass
class PlanViewState:
    dirty:bool=False
    issue_count:int=0
    has_plan:bool=False
    snapshot_id:str|None=None
    working_draft_id:str|None=None
    source_epoch:int=0
    editing:bool=False
    save_state:str='idle'
    export_state:str='idle'
    busy:bool=False
    source_invalid:bool=False
