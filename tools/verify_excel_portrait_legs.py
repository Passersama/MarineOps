"""Create a fictional multi-leg print fixture without opening user databases."""
from pathlib import Path
import copy
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from test_personnel_routes import PersonnelRouteTests
from cargo_track.berth_plan import export_plan, plan_assignments
from cargo_track.personnel_service import PersonnelService


def main():
    output = ROOT / 'output/excel-legs-20261025'
    output.mkdir(parents=True, exist_ok=True)
    fixture = PersonnelRouteTests()
    fixture.setUp()
    try:
        first, second, source = fixture.chain()
        for i in range(18):
            fixture.add('CHA', 'INN', f'Passenger {i+1:02d} Fictional Long English Name')
        numbers = []
        for i in range(8):
            numbers.append(fixture.f.command('create_transfer', {'description':f'Material {i+1:02d} 测试工程物资电缆配件 END{i+1:02d}',
                'from_location_id':fixture.f.a, 'to_location_id':fixture.f.c, 'comment':'', 'physical_id':''})['no'])
        live = fixture.source()
        source = {**live, 'stops':source['stops']}
        for i in range(7):
            source['stops'].append({**source['stops'][i % 3], 'id':f'plan:extra-{i}'})
        from cargo_track.berth_plan import generate_plan
        draft = generate_plan(source, fixture.service.crew_records(fixture.f.plan, source), numbers,
            '2026-10-25', fixture.service.port_name(source), mode='Final', personnel_plan_id=fixture.f.plan)
        assert not draft['issues'], draft['issues']
        draft['stops'][0]['comment'] = 'Fictional print check\nComments wrap automatically across this merged stop block.'
        saved = fixture.service.save_berth(draft, True)
        frozen = copy.deepcopy(saved)
        target = output / 'portrait-multileg-example.xlsx'
        export_plan(saved, target)
        assert frozen == fixture.service.berth_versions()[0]
        assert plan_assignments(saved)['Passengers:'+second]['pick'] == 'plan:second-niger'
        backup = output / 'fictional-personnel-backup.sqlite3'
        fixture.service.backup(backup)
        PersonnelService.validate_file(backup)
        (output / 'fixture-plan.json').write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'result':'PASS', 'fictional_data':True, 'workbook':str(target),
            'linked_leg_later_visit':True, 'saved_snapshot_unchanged':True, 'backup_valid':True,
            'stops':len(saved['stops']), 'materials':len(numbers)}, indent=2))
    finally:
        fixture.tearDown()


if __name__ == '__main__':main()
