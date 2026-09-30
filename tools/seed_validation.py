"""Create fictional data only in the named release-test directory."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from cargo_track.domain import Command
from cargo_track.service import ApplicationService

path=ROOT/"artifacts"/"validation-1.0.5"/"data"/"cargo-track.sqlite3"
service=ApplicationService(path);service.open()
if service.workspace_snapshot()["counts"]["all"]==0:
    seq=0
    def command(op,payload):
        global seq
        seq+=1
        return service.handle(Command(f"validation-{seq}",op,payload)).result
    first=command("create_vessel",{"name":"BGP Victor"})["id"]
    second=command("create_vessel",{"name":"CHA"})["id"]
    command("create_voyage",{"name":"Validation route"})
    stop=command("add_stop",{"vessel_id":first})["stop_id"]
    command("add_stop",{"vessel_id":second})
    command("choose_stop",{"stop_id":stop})
    for description in ("Hydraulic pump","Control panel","Cable drums","Tool cases","Filters","Sensor kit"):
        command("create_transfer",{"description":description,"from_location_id":first,"to_location_id":second,"physical_id":"TEST ONLY","comment":"Fictional validation cargo"})
service.close()
print(path)

