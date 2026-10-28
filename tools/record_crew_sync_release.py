"""Require measured regression, native UI, package and source equivalence evidence."""
from pathlib import Path
import hashlib
import json
import re
import types
import zipfile
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
VERSION='1.2.5'
VALID=ROOT/f'artifacts/validation-{VERSION}'
OUT=ROOT/f'output/crew-sync-{VERSION}'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def code_value(value):
    if isinstance(value,types.CodeType):
        return (value.co_code,tuple(code_value(v) for v in value.co_consts),value.co_names,
            value.co_varnames,value.co_freevars,value.co_cellvars,value.co_argcount,
            value.co_posonlyargcount,value.co_kwonlyargcount,value.co_flags)
    if isinstance(value,tuple):return tuple(code_value(v) for v in value)
    return value

log=(VALID/'full-tests-final.log').read_text(encoding='utf-8-sig')
assert re.search(r'\nOK\s*$',log),'Full regression suite did not finish cleanly'
count=int(re.findall(r'Ran (\d+) tests',log)[-1]);assert count>=270
delta=(VALID/'architecture-dashboard-final.log').read_text(encoding='utf-8-sig')
assert re.search(r'\nOK\s*$',delta),'Final Dashboard/architecture regression did not pass'
delta_count=int(re.findall(r'Ran (\d+) tests',delta)[-1]);assert delta_count>=34
native=read(OUT/'native-validation.json')
assert native['brand']=='MarineOps' and native['about_all_three_workspaces']
assert native['result']=='PASS' and native['platform']=='windows' and native['cargo_unchanged_by_crew_update']
assert native['approved_logo'] and len(native['theme_and_viewport_captures'])==12
packaged=read(VALID/'crew-sync-packaged-validation.json')
assert packaged['standalone_installer']==packaged['upgrade']=='PASS'
assert packaged['previous_version']=='1.2.4'
assert len(packaged['packages'])==2 and all(p['business_data_unchanged'] and p['cargo_file_unchanged'] for p in packaged['packages'])
exe=ROOT/'dist/MarineOps/MarineOps.exe'
assert all(p['sha256'].lower()==sha(exe) for p in packaged['packages'])
portable=ROOT/f'release/MarineOps-{VERSION}-Windows-x64.zip'
with zipfile.ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert hashlib.sha256(archive.read('MarineOps/MarineOps.exe')).hexdigest()==sha(exe)
    assert archive.read('MarineOps/_internal/assets/help/user-guide.html')==(ROOT/'assets/help/user-guide.html').read_bytes()
    assert 'From and To' in archive.read('MarineOps/CREW-SYNC.txt').decode()
    assert not any(n.lower().endswith(('.sqlite3','.sqlite','.db')) for n in archive.namelist())
    for name in ('marineops-symbol.png','marineops.ico'):
        assert archive.read('MarineOps/_internal/assets/branding/'+name)==(ROOT/'assets/branding'/name).read_bytes()
    assert not any('maritime-operations-logo' in name or 'cargo-track-lockup' in name for name in archive.namelist())
setup=ROOT/f'release/MarineOps-Setup-{VERSION}.exe'
assert portable.read_bytes() in setup.read_bytes()
container=CArchiveReader(str(exe))
pyz=container.open_embedded_archive(next(n for n in container.toc if n.endswith('.pyz')))
modules=sorted(p.stem for p in (ROOT/'src/cargo_track').glob('*.py')
               if p.stem not in {'__init__','pyi_rth_dll_dirs'})
for name in modules:
    source=ROOT/'src/cargo_track'/f'{name}.py'
    assert code_value(compile(source.read_text(encoding='utf-8'),'comparison','exec'))==code_value(pyz.extract('cargo_track.'+name)),name
assert code_value(compile((ROOT/'src/cargo_track/__init__.py').read_text(encoding='utf-8'),'comparison','exec'))==code_value(pyz.extract('cargo_track'))
import PySide6
assert PySide6.__version__=='6.8.3'
for component in ('QtCore.pyd','Qt6Core.dll'):
    assert sha(ROOT/'dist/MarineOps/_internal/PySide6'/component)==sha(Path(PySide6.__file__).parent/component)
paths=[setup,portable,exe]
report={'product':'MarineOps','version':VERSION,'date':'2026-10-28','result':'PASS','full_regression_tests':count,
    'final_architecture_dashboard_regression_tests':delta_count,
    'architecture_audit':read(ROOT/'output/architecture-audit-1.2.5/after.json'),
    'approved_logo_sha256':{name:sha(ROOT/'assets/branding'/name) for name in ('marineops-symbol.png','marineops.ico')},
    'runtime':'PySide6 6.8.3','native_ui':native,'packages':packaged,
    'compiled_modules_match_source':modules+['__init__'],'zip_integrity':'PASS','embedded_payload_matches_portable':True,
    'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'src/cargo_track').glob('*.py'))},
    'artifacts':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths],
    'user_data':'User database diagnostic was query-only and hashes were unchanged. All write, native UI and installer checks used isolated fictional data.',
    'limits':['Historical versions are retained; automatic Dashboard mode follows the current crew list.',
        'Actual Cargo source changes still require route review. Invalid passenger assignments remain review issues.',
        'Repeated vessel calls with independent ambiguous IDs require selecting the actual plan visit.',
        'Crew updates invalidate any previous minimum-call proof; use Auto plan again when a new optimality proof is needed.',
        'Packaged functional equivalence is verified by compiled-source comparison; installer and portable checks cover launch, single instance, clean close and legacy data preservation.']}
output=ROOT/f'release/MarineOps-release-validation-{VERSION}.json'
output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'result':'PASS','full_regression_tests':count,'manifest':str(output),'artifacts':report['artifacts']},indent=2))
