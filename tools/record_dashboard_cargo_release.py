"""Fail-closed acceptance for the Dashboard/Cargo independence hotfix."""
from pathlib import Path
import hashlib
import json
import re
import types
import zipfile
from PyInstaller.archive.readers import CArchiveReader
import PySide6

ROOT=Path(__file__).resolve().parents[1];VERSION='1.2.6'
VALID=ROOT/f'artifacts/validation-{VERSION}';OUT=ROOT/f'output/dashboard-fix-{VERSION}'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def code_value(value):
    if isinstance(value,types.CodeType):
        return (value.co_code,tuple(code_value(v) for v in value.co_consts),value.co_names,
                value.co_varnames,value.co_freevars,value.co_cellvars,value.co_argcount,
                value.co_posonlyargcount,value.co_kwonlyargcount,value.co_flags)
    if isinstance(value,tuple):return tuple(code_value(v) for v in value)
    return value

log=(VALID/'full-tests-final.log').read_text(encoding='utf-8-sig')
assert re.search(r'\nOK\s*$',log),'Full regression did not finish cleanly'
count=int(re.findall(r'Ran (\d+) tests',log)[-1]);assert count>=279
focused=(OUT/'focused-tests.log').read_text(encoding='utf-8-sig')
assert re.search(r'\nOK\s*$',focused)
native=read(OUT/'native-validation.json')
assert native['result']=='PASS' and native['platform']=='windows'
for key in ('original_blank_reproduced','legacy_plan_after_cargo_pickup','current_roster_refreshed',
            'dashboard_about_right_of_settings','about_dialog_opened','real_route_change_still_blocked',
            'review_message_above_counts','personnel_database_unchanged'):assert native[key],key
assert (native['boarding'],native['leaving'],native['roster_rows'])==(3,2,5)
live=read(OUT/'live-after.json');assert live['status']=='ready' and live['databases_unchanged']
packaged=read(VALID/'crew-sync-packaged-validation.json')
assert packaged['standalone_installer']==packaged['upgrade']=='PASS'
assert packaged['previous_version']=='1.2.5'
assert len(packaged['packages'])==2
exe=ROOT/'dist/MarineOps/MarineOps.exe'
assert all(p['business_data_unchanged'] and p['cargo_file_unchanged'] and p['sha256'].lower()==sha(exe)
           for p in packaged['packages'])
portable=ROOT/f'release/MarineOps-{VERSION}-Windows-x64.zip'
with zipfile.ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert hashlib.sha256(archive.read('MarineOps/MarineOps.exe')).hexdigest()==sha(exe)
    assert not any(n.lower().endswith(('.sqlite3','.sqlite','.db')) for n in archive.namelist())
    for name in ('marineops-symbol.png','marineops.ico'):
        assert archive.read('MarineOps/_internal/assets/branding/'+name)==(ROOT/'assets/branding'/name).read_bytes()
setup=ROOT/f'release/MarineOps-Setup-{VERSION}.exe'
assert portable.read_bytes() in setup.read_bytes()
container=CArchiveReader(str(exe));pyz=container.open_embedded_archive(next(n for n in container.toc if n.endswith('.pyz')))
modules=sorted(p.stem for p in (ROOT/'src/cargo_track').glob('*.py') if p.stem!='pyi_rth_dll_dirs')
for name in modules:
    source=ROOT/'src/cargo_track'/f'{name}.py'
    packed='cargo_track' if name=='__init__' else 'cargo_track.'+name
    assert code_value(compile(source.read_text(encoding='utf-8'),'comparison','exec'))==code_value(pyz.extract(packed)),name
assert PySide6.__version__=='6.8.3'
for name in ('QtCore.pyd','Qt6Core.dll'):
    assert sha(ROOT/'dist/MarineOps/_internal/PySide6'/name)==sha(Path(PySide6.__file__).parent/name)
report={'result':'PASS','product':'MarineOps','version':VERSION,'date':'2026-10-28',
        'full_regression_tests':count,'focused_tests':int(re.findall(r'Ran (\d+) tests',focused)[-1]),
        'native_ui':native,'current_user_data_readonly':live,'packages':packaged,
        'compiled_modules_match_source':modules,'zip_integrity':'PASS','embedded_payload_matches_portable':True,
        'runtime':'PySide6 6.8.3','source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'src/cargo_track').glob('*.py'))},
        'artifacts':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in (setup,portable,exe)],
        'scope':'Actual user database access was query-only. All write, UI and upgrade checks used isolated fictional data.',
        'limits':['Planned personnel movements are not executed boarding evidence.',
                  'Actual route, voyage, fleet, relevant setting or restore changes still require review.',
                  'Legacy snapshots without complete safe command history remain blocked instead of showing unverified names.']}
target=ROOT/f'release/MarineOps-release-validation-{VERSION}.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'result':'PASS','full_regression_tests':count,'manifest':str(target),'artifacts':report['artifacts']},indent=2))
