"""Bind passed source, native, package and upgrade evidence to release hashes."""
from pathlib import Path
import hashlib,json,re,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cargo_track import __version__
from PyInstaller.archive.readers import CArchiveReader
OUT=ROOT/'output/dashboard-release-20261012';VALID=ROOT/f'artifacts/validation-{__version__}'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
log=(OUT/'full-tests-final.log').read_text(encoding='utf-8-sig')
assert log.rstrip().endswith('OK') and 'Ran 172 tests' in log
counts={}
for module in re.findall(r'^test_.*?\((test_[^.]+)\.',log,re.M):counts[module]=counts.get(module,0)+1
assert sum(counts.values())==172
native=read(OUT/'native-checks.json');legacy=read(OUT/'legacy-native/native-checks.json')
packages=read(VALID/'packaged-workspace-validation.json');upgrade=read(VALID/'upgrade-1.2.0-to-1.2.1.json')
first=read(VALID/'first-run-validation.json');focus=read(OUT/'focus-checks.json')
assert native['final']=='PASS' and native['platform']=='windows' and native['delayed_old_read_rejected']
assert legacy['comments_survive_save_edit_export'] and legacy['pickup_command_works']
assert packages['standalone_installer']=='PASS' and packages['shortcut_target']=='PASS' and len(packages['packages'])==2
assert all(p['launch']=='PASS' and p['single_instance']=='PASS' and p['file_version']==__version__ for p in packages['packages'])
assert upgrade['from_version']=='1.2.0' and upgrade['to_version']==__version__ and upgrade['installed_upgrade']=='PASS'
assert upgrade['nested_database_install_guard']=='PASS'
assert first['result']=='PASS' and first['personnel_database_not_created'] and focus['result']=='PASS'
assert read(OUT/'storage-before.json')['existing_roster_visible'] is False
assert read(OUT/'storage-after.json')['existing_roster_visible'] is True
assert read(OUT/'health-before.json')['health']['foreign_keys']=='ok'
assert read(OUT/'health-after.json')['health']['foreign_keys']=='failed'
for name in ('cargo-track.sqlite3','personnel-transfer.sqlite3'):assert upgrade['before'][name]['sha256']==upgrade['after'][name]['sha256']
portable=ROOT/f'release/CargoTrack-{__version__}-Windows-x64.zip'
exe=ROOT/'dist/CargoTrack/CargoTrack.exe'
assert sha(exe)==sha(VALID/'installed/CargoTrack/CargoTrack.exe')
with zipfile.ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert hashlib.sha256(archive.read('CargoTrack/CargoTrack.exe')).hexdigest()==sha(exe)
    help_path='CargoTrack/_internal/assets/help/user-guide.html'
    assert archive.read(help_path)==(ROOT/'assets/help/user-guide.html').read_bytes()
    assert 'Dashboard opens by default' in archive.read('README.txt').decode('utf-8')
    for name in ('Inter-Regular.ttf','Inter-SemiBold.ttf'):assert f'CargoTrack/_internal/assets/fonts/{name}' in archive.namelist()
    assert archive.read('CargoTrack/_internal/assets/branding/maritime-operations-logo-v3-dark.png')==(ROOT/'assets/branding/maritime-operations-logo-v3-dark.png').read_bytes()
container=CArchiveReader(str(exe));embedded=next(name for name in container.toc if name.endswith('.pyz'))
modules=container.open_embedded_archive(embedded).toc
assert 'cargo_track.dashboard_ui' in modules and 'cargo_track.dashboard_data' in modules
assert '1.2.1 Dashboard' in (ROOT/'design-qa.md').read_text(encoding='utf-8-sig')
baseline=OUT/'baseline/src/cargo_track';source=ROOT/'src/cargo_track';changed=[]
for file in source.glob('*.py'):
    old=baseline/file.name
    if not old.exists() or sha(file)!=sha(old):changed.append(file.name)
(OUT/'source-changes.json').write_text(json.dumps({'base':'captured current 1.2.0 checkout','changed_modules':sorted(changed)},indent=2),encoding='utf-8')
paths=[f'release/CargoTrack-Setup-{__version__}.exe',str(portable.relative_to(ROOT)), 'dist/CargoTrack/CargoTrack.exe']
paths += ['src/cargo_track/'+name for name in sorted(changed)]
paths += ['tools/CargoTrackInstaller.cs','tools/windows-version.txt','tools/build_release.py','assets/help/user-guide.html','design-qa.md','output/dashboard-release-20261012/软件审核与发布说明.md']
files={name:{'bytes':(ROOT/name).stat().st_size,'sha256':sha(ROOT/name)} for name in paths}
report={'version':__version__,'base_version':'1.2.0','date':'2026-10-12','result':'PASS',
    'scope':'Native Dashboard, retained Cargo/Personnel workflows, isolated installer/portable and 1.2.0 upgrade',
    'tests':{'complete_suite':172,'modules':counts,'baseline_complete_suite':159},
    'native':native,'legacy_native':legacy,'keyboard':focus,'packages':packages,'upgrade':upgrade,'first_run':first,
    'packaged_assets_and_dashboard_modules':'PASS','files':files,
    'user_data':'Not replaced; isolated fictional fixtures and legacy test copies only',
    'limits':['Cargo summary is all non-deleted transfer legs, not voyage-owned records','Personnel numbers are saved-plan movements, not execution counts','Small windows scroll vertically','Narrator speech and physical multi-monitor DPI transitions not measured','Not an independent penetration test']}
target=ROOT/f'release/release_validation-{__version__}.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'version':__version__,'result':'PASS','tests':172,'manifest':str(target),'source_modules_changed_from_baseline':changed,'packages':paths[:2]},ensure_ascii=False,indent=2))
