"""Exercise print pagination and non-Latin material wrapping with fictional data."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cargo_track.personnel_service import PersonnelService
from cargo_track.berth_plan import export_plan

output = ROOT / "artifacts" / "personnel-development"
native = json.loads((output / "native-visible.json").read_text(encoding="utf-8"))
service = PersonnelService(Path(native["data_directory"]) / "personnel-transfer.sqlite3")
try:
    original = next(p for p in service.berth_versions() if p["version"] == 1)
    plan = copy.deepcopy(original)
    template = plan["stops"][0]["drop_passengers"][0]
    plan["stops"][0]["drop_passengers"] = [dict(template, id=f"long-person-{i}", name=f"Fictional Passenger {i:02d}") for i in range(1, 46)]
    template = plan["stops"][0]["pick_materials"][0]
    plan["stops"][0]["pick_materials"] = [dict(template, id=f"long-cargo-{i}", name=f"Material {i:02d} "+"测试工程物资"*30+f" END{i:02d}") for i in range(1, 13)]
    export_plan(plan, output / "long-list-validation.xlsx")
    print("Fictional export: 45 passengers and 12 long material descriptions")
finally:
    service.close()
