"""Verify the final artifacts and record only evidence from the current update."""
from pathlib import Path
import hashlib
import json
import re
import types
import zipfile

from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/berth-optimizer-release-20261012'
VALID=ROOT/'artifacts/validation-1.2.1'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_code(code):
    def constant(value):
        if isinstance(value,types.CodeType):return semantic_code(value)
        if isinstance(value,tuple):return [constant(v) for v in value]
        if isinstance(value,frozenset):return sorted((constant(v) for v in value),key=repr)
        if isinstance(value,bytes):return {'bytes':value.hex()}
        if value is Ellipsis:return {'ellipsis':True}
        return value
    return {'code':code.co_code.hex(),'consts':[constant(c) for c in code.co_consts],
            'names':code.co_names,'vars':code.co_varnames,'free':code.co_freevars,'cells':code.co_cellvars,
            'args':code.co_argcount,'pos':code.co_posonlyargcount,'kw':code.co_kwonlyargcount,
            'flags':code.co_flags,'exceptions':code.co_exceptiontable.hex()}


HOTFIX=ROOT/'output/personnel-leg-hotfix-20261012'
COMBINED=ROOT/'output/dashboard-combined-personnel-20261012'
VOYAGE=ROOT/'output/voyage-progress-20261012'
log=(VOYAGE/'full-tests.log').read_text(encoding='utf-8-sig')
assert log.rstrip().endswith('OK')
total=int(re.findall(r'Ran (\d+) tests',log)[-1]);assert total==202
ui_log=(OUT/'ui-tests-final.log').read_text(encoding='utf-8-sig')
assert ui_log.rstrip().endswith('OK') and 'Ran 28 tests' in ui_log
dashboard_log=(COMBINED/'dashboard-tests.log').read_text(encoding='utf-8-sig')
assert dashboard_log.rstrip().endswith('OK') and 'Ran 15 tests' in dashboard_log
native=read(OUT/'native-checks.json');assert native['result']=='PASS' and native['platform']=='windows'
assert native['minimum_calls']==5 and native['dashboard_boarding']==2 and native['dashboard_leaving']==1
assert native['latest_plan_follows_new_save_after_roster_edit'] and native['explicit_history_selection_retained']
dashboard=read(ROOT/'output/dashboard-release-20261012/native-checks.json');assert dashboard['final']=='PASS'
assert dashboard['combined_roster']=={'rows':47,'boarding':28,'leaving':19,'movement_column_visible':True}
combined=read(COMBINED/'combined-panel-checks.json')
assert combined['result']=='PASS' and combined['platform']=='windows' and len(combined['checks'])==12
assert all(c['rows']==3 and c['boarding']==2 and c['leaving']==1 and not c['horizontal_scroll'] for c in combined['checks'])
legacy=read(ROOT/'output/dashboard-release-20261012/legacy-native/native-checks.json')
assert legacy['personnel_24_visits_visible_without_scrolling'] and legacy['pickup_command_works']
voyage=read(VOYAGE/'native-checks.json');assert voyage['result']=='PASS' and voyage['platform']=='windows'
assert voyage['qt_mouse_start_and_drop_events'] and voyage['reorder_persisted'] and voyage['current_stop_identity_preserved']
assert voyage['historical_done_excluded'] and voyage['all_transfers_excludes_done'] and len(voyage['scenarios'])==12
packages=read(VALID/'packaged-voyage-progress-validation.json');assert packages['standalone_installer']=='PASS'
assert len(packages['packages'])==2 and packages['upgrade_data_preservation']=='PASS'
assert all(p['launch']=='PASS' and p['single_instance']=='PASS' and p['file_version']=='1.2.1' and
           p['cargo_hash_unchanged'] and p['personnel_hash_unchanged'] for p in packages['packages'])
upgrade=read(VALID/'upgrade-1.2.0-to-1.2.1.json');assert upgrade['installed_upgrade']=='PASS'
assert upgrade['nested_database_install_guard']=='PASS'
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):
    assert upgrade['before'][name]['sha256']==upgrade['after'][name]['sha256']
first=read(VALID/'first-run-validation.json');assert first['result']=='PASS' and first['personnel_database_not_created']

exe=ROOT/'dist/CargoTrack/CargoTrack.exe';portable=ROOT/'release/CargoTrack-1.2.1-Windows-x64.zip'
assert sha(exe)==sha(VALID/'installed/CargoTrack/CargoTrack.exe')
assert sha(exe)==sha(Path(upgrade['installed_directory'])/'CargoTrack/CargoTrack.exe')
with zipfile.ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert hashlib.sha256(archive.read('CargoTrack/CargoTrack.exe')).hexdigest()==sha(exe)
    assert archive.read('CargoTrack/_internal/assets/help/user-guide.html')==(ROOT/'assets/help/user-guide.html').read_bytes()
    assert b'automatic planning' in archive.read('CargoTrack/AUTO-PLANNING.txt')
    assert not any(n.lower().endswith(('.sqlite3','.sqlite','.db')) for n in archive.namelist())
container=CArchiveReader(str(exe));pyz=container.open_embedded_archive(next(n for n in container.toc if n.endswith('.pyz')))
modules=['berth_optimizer','berth_optimization_validation','berth_optimization_ui','dashboard_data',
         'dashboard_ui','personnel_ui','personnel_service','berth_plan','personnel_routes','ui','route_layout']
for name in modules:
    key='cargo_track.'+name;assert key in pyz.toc,key
    code=compile((ROOT/'src/cargo_track'/f'{name}.py').read_text(encoding='utf-8'),'comparison','exec',optimize=0)
    assert semantic_code(code)==semantic_code(pyz.extract(key)),f'Packaged module differs from current source: {key}'

paths=['release/CargoTrack-Setup-1.2.1.exe','release/CargoTrack-1.2.1-Windows-x64.zip','dist/CargoTrack/CargoTrack.exe',
       'assets/help/user-guide.html','tools/build_release.py']+['src/cargo_track/'+name+'.py' for name in modules]
report={'version':'1.2.1','date':'2026-10-12','result':'PASS',
        'scope':'Current-voyage cargo summary, unfinished All transfers count, personnel person-leg plan progress and Cargo sidebar drag reorder',
        'tests':{'complete_suite':total,'prior_affected_ui_suite':28,
                 'complete_suite_log':str((VOYAGE/'full-tests.log').relative_to(ROOT))},
        'legacy_leg_hotfix_native':read(HOTFIX/'native-checks.json'),
        'optimizer_native_prior':native,'dashboard_native':dashboard,'combined_panel_native_prior':combined,'legacy_native_prior':legacy,'voyage_progress_native':voyage,
        'packages':packages,'upgrade':upgrade,'first_run':first,'performance':read(OUT/'performance.json'),
        'compiled_modules_match_current_source':modules,'portable_integrity':'PASS','package_contains_no_business_databases':True,
        'files':{p:{'bytes':(ROOT/p).stat().st_size,'sha256':sha(ROOT/p)} for p in paths},
        'user_data':'Not replaced; isolated fictional validation datasets and copies only',
        'limits':['One transfer vessel, sufficient capacity, no time windows','Port-origin first legs are planned as loaded before departure',
                  'Limited searches identify candidates without claiming minimum calls','Dashboard shows saved-plan movements, not execution records',
                  'Personnel completion is inferred from drop calls before the selected plan visit, not actual execution',
                  'Drag initiation and drop events were tested in native Qt with the blocking OS drag loop replaced; physical desktop mouse automation was unavailable',
                  'Physical multi-monitor DPI and Narrator speech were not measured']}
target=ROOT/'release/release_validation-1.2.1.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'version':'1.2.1','result':'PASS','tests':total,'compiled_source_match':True,'manifest':str(target)},indent=2))
