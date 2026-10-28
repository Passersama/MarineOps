"""Record current crew-change fixes, isolated tests and rebuilt release evidence."""
from pathlib import Path
import hashlib,json,re,types,zipfile,sys
from PyInstaller.archive.readers import CArchiveReader
ROOT=Path(__file__).resolve().parents[1]
MATCHING='--matching' in sys.argv
OUT=ROOT/('output/crew-assignment-matching-20261021' if MATCHING else 'output/crew-change-defaults-20261021');VALID=ROOT/'artifacts/validation-1.2.1'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def semantic(code):
    def constant(value):
        if isinstance(value,types.CodeType):return semantic(value)
        if isinstance(value,tuple):return [constant(v) for v in value]
        if isinstance(value,frozenset):return sorted((constant(v) for v in value),key=repr)
        if isinstance(value,bytes):return {'bytes':value.hex()}
        if value is Ellipsis:return {'ellipsis':True}
        return value
    return {'code':code.co_code.hex(),'consts':[constant(c) for c in code.co_consts],
            'names':code.co_names,'vars':code.co_varnames,'free':code.co_freevars,'cells':code.co_cellvars,
            'args':code.co_argcount,'pos':code.co_posonlyargcount,'kw':code.co_kwonlyargcount,
            'flags':code.co_flags,'exceptions':code.co_exceptiontable.hex()}
tests={}
for name,expected in (('targeted-tests.log',37 if MATCHING else 32),('related-tests.log',109)):
    log=(OUT/name).read_text(encoding='utf-8-sig');assert log.rstrip().endswith('OK')
    tests[name]=int(re.findall(r'Ran (\d+) tests',log)[-1]);assert tests[name]==expected
native=read(ROOT/'output/crew-change-defaults-20261021/native-checks.json')
assert native['result']=='PASS' and native['platform']=='windows'
assert native['sign_on']==native['sign_off']==native['port_returns']==8 and native['review_assignments']==0
assert native['saved_and_reopened'] and native['excel_export'] and native['cargo_unchanged'] and native['original_workbook_unchanged']
current=None
if MATCHING:
    current=read(OUT/'current-crew-readonly.json')
    assert current['result']=='PASS' and current['review_assignments']==0
    assert current['valid_route_assignments']==current['matched_vessels']==current['crew_records']
    assert current['cargo_unchanged'] and current['personnel_unchanged']
packages=read(VALID/('packaged-crew-matching-validation.json' if MATCHING else 'packaged-crew-defaults-validation.json'))
assert packages['standalone_installer']=='PASS' and packages['upgrade_data_preservation']=='PASS'
assert len(packages['packages'])==2
assert all(p['launch']=='PASS' and p['single_instance']=='PASS' and p['file_version']=='1.2.1'
           and p['cargo_hash_unchanged'] and p['personnel_hash_unchanged'] for p in packages['packages'])
upgrade=read(VALID/'upgrade-1.2.0-to-1.2.1.json');assert upgrade['installed_upgrade']=='PASS'
assert upgrade['nested_database_install_guard']=='PASS'
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):assert upgrade['before'][name]['sha256']==upgrade['after'][name]['sha256']
first=read(VALID/'first-run-validation.json');assert first['result']=='PASS' and first['personnel_database_not_created']
exe=ROOT/'dist/CargoTrack/CargoTrack.exe';portable=ROOT/'release/CargoTrack-1.2.1-Windows-x64.zip'
assert sha(exe)==sha(VALID/'installed/CargoTrack/CargoTrack.exe')
assert sha(exe)==sha(Path(upgrade['installed_directory'])/'CargoTrack/CargoTrack.exe')
with zipfile.ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert hashlib.sha256(archive.read('CargoTrack/CargoTrack.exe')).hexdigest()==sha(exe)
    assert archive.read('CargoTrack/_internal/assets/help/user-guide.html')==(ROOT/'assets/help/user-guide.html').read_bytes()
    assert not any(n.lower().endswith(('.sqlite3','.sqlite','.db')) for n in archive.namelist())
container=CArchiveReader(str(exe));pyz=container.open_embedded_archive(next(n for n in container.toc if n.endswith('.pyz')))
modules=['personnel_import','personnel_service','personnel_ui','personnel_routes','berth_plan',
         'berth_optimizer','berth_optimization_validation','berth_optimization_ui','dashboard_data','dashboard_ui','ui','route_layout']
for name in modules:
    source=ROOT/'src/cargo_track'/f'{name}.py'
    assert semantic(compile(source.read_text(encoding='utf-8'),'comparison','exec',optimize=0))==semantic(pyz.extract('cargo_track.'+name)),name
paths=['release/CargoTrack-Setup-1.2.1.exe','release/CargoTrack-1.2.1-Windows-x64.zip','dist/CargoTrack/CargoTrack.exe',
       'assets/help/user-guide.html']+['src/cargo_track/'+name+'.py' for name in modules]
report={'version':'1.2.1','date':'2026-10-21','result':'PASS',
        'scope':('Crew vessel short-name resolution, imported Sign-on/Sign-off direction retention, automatic mapping preview and persistence' if MATCHING else
                 'Crew-change port defaults, one-sided Sign-on/Sign-off columns, legacy source-value recovery and initial return-port visit'),
        'tests':{'affected_tests':sum(tests.values()),'logs':tests,'directory':str(OUT.relative_to(ROOT)),'full_suite_rerun':False},
        'native':native,'current_crew_readonly_validation':current,'packages':packages,'upgrade':upgrade,'first_run':first,
        'prior_validation':str((OUT/'previous-release-validation.json').relative_to(ROOT)),
        'compiled_modules_match_current_source':modules,'portable_integrity':'PASS','package_contains_no_business_databases':True,
        'files':{p:{'bytes':(ROOT/p).stat().st_size,'sha256':sha(ROOT/p)} for p in paths},
        'user_data':'Only isolated fictional test data and copied fixtures; no user data replaced',
        'limits':['Unknown, ambiguous or inactive vessel-side endpoints still require review',
                  'Existing manually edited routes are retained; generate a new plan to apply initial return-port defaults',
                  'Current inputs include SELECT-only validation of the existing saved crew list when matching mode is used; no user workbook was modified']}
target=ROOT/'release/release_validation-1.2.1.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'result':'PASS','affected_tests':sum(tests.values()),'manifest':str(target)},indent=2))
