"""Fail closed when producing the 1.2.4 evidence manifest."""
from pathlib import Path
import hashlib
import json
import re
import types
import zipfile
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
VERSION='1.2.4'
VALID=ROOT/f'artifacts/validation-{VERSION}'
OUT=ROOT/f'output/text-case-{VERSION}'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def code_value(value):
    if isinstance(value,types.CodeType):
        return (value.co_code,tuple(code_value(v) for v in value.co_consts),value.co_names,
            value.co_varnames,value.co_freevars,value.co_cellvars,value.co_argcount,
            value.co_posonlyargcount,value.co_kwonlyargcount,value.co_flags)
    if isinstance(value,tuple):return tuple(code_value(v) for v in value)
    return value

log=(VALID/'full-tests.log').read_text(encoding='utf-8-sig')
assert re.search(r'\nOK\s*$',log), 'Full regression suite did not finish cleanly'
count=int(re.findall(r'Ran (\d+) tests',log)[-1]);assert count>=241
targeted=(VALID/'text-case-tests.log').read_text(encoding='utf-8-sig')
assert re.search(r'\nOK\s*$',targeted)
native=read(OUT/'native-validation.json');assert native['result']=='PASS' and native['platform']=='windows'
packaged=read(VALID/'text-case-packaged-validation.json')
assert packaged['standalone_installer']==packaged['upgrade']=='PASS'
assert packaged['previous_version']=='1.2.3' and packaged['legacy_fixture_origin']
assert len(packaged['packages'])==2 and all(p['databases_unchanged'] for p in packaged['packages'])
exe=ROOT/'dist/CargoTrack/CargoTrack.exe'
assert all(p['sha256'].lower()==sha(exe) for p in packaged['packages'])
portable=ROOT/f'release/CargoTrack-{VERSION}-Windows-x64.zip'
with zipfile.ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert hashlib.sha256(archive.read('CargoTrack/CargoTrack.exe')).hexdigest()==sha(exe)
    assert archive.read('CargoTrack/_internal/assets/help/user-guide.html')==(ROOT/'assets/help/user-guide.html').read_bytes()
    assert 'Keep my spelling' in archive.read('CargoTrack/TEXT-CASING.txt').decode()
    assert not any(n.lower().endswith(('.sqlite3','.sqlite','.db')) for n in archive.namelist())
setup=ROOT/f'release/CargoTrack-Setup-{VERSION}.exe'
assert portable.read_bytes() in setup.read_bytes(), 'Installer payload differs from portable ZIP'
container=CArchiveReader(str(exe))
pyz=container.open_embedded_archive(next(n for n in container.toc if n.endswith('.pyz')))
modules=['text_case','text_case_ui','personnel_import','personnel_service','personnel_ui','service','ui','worker','berth_plan']
for name in modules:
    source=ROOT/'src/cargo_track'/f'{name}.py'
    assert code_value(compile(source.read_text(encoding='utf-8'),'comparison','exec',optimize=0))==code_value(pyz.extract('cargo_track.'+name)),name
version_source=ROOT/'src/cargo_track/__init__.py'
assert code_value(compile(version_source.read_text(encoding='utf-8'),'comparison','exec'))==code_value(pyz.extract('cargo_track'))
paths=[setup,portable,exe]
report={'version':VERSION,'date':'2026-10-26','result':'PASS','full_regression_tests':count,
    'targeted_tests':int(re.findall(r'Ran (\d+) tests',targeted)[-1]),
    'native_ui':native,'packages':packaged,'compiled_modules_match_source':modules+['__init__'],
    'zip_integrity':'PASS','embedded_payload_matches_portable':True,
    'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'src/cargo_track').glob('*.py'))},
    'artifacts':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths],
    'user_data':'All verification used isolated fictional fixtures. No user databases or source workbooks were modified.',
    'limits':['Casing is an offline rule set with known abbreviation and exception tables; unfamiliar brands or personal spellings may require Keep my spelling.',
        'Functional UI acceptance uses Windows Qt source execution; packaged checks cover installed and portable launch, single instance, clean close, legacy data hashes, and compiled-source equivalence.',
        'Existing records require reviewing and applying proposed changes; historical saved plans retain their original text. Generate and save a new plan for updated names.']}
output=ROOT/f'release/release_validation-{VERSION}.json'
output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'result':'PASS','full_regression_tests':count,'manifest':str(output),'artifacts':report['artifacts']},indent=2))
