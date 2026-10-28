"""Verify and record evidence for the exact final frontend release packages."""
from pathlib import Path
import hashlib,json,re,zipfile
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'output/frontend-update-20261007';V=ROOT/'artifacts/validation-1.1.6';R=ROOT/'release'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def record(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
log=(E/'unit-tests-complete.txt').read_text(encoding='utf-8-sig');assert re.search(r'Ran 115 tests in [\d.]+s\s+OK\s*$',log)
assert 'Built CargoTrack-Setup-1.1.6.exe' in (E/'build-release-final.txt').read_text(encoding='utf-8-sig')
checks={name:read(E/path) for name,path in {'crew_workflow':'ui-final/native-visible.json','restore_and_worker':'runtime-native/checks.json','keyboard_and_close':'keyboard-native/checks.json','shared_port':'shared-port-ui/checks.json','cargo_refresh':'cargo-refresh-ui/checks.json'}.items()}
for name,report in checks.items():
    for key,value in report.items():
        if isinstance(value,bool) and key!='native_visible':assert value,(name,key)
assert checks['keyboard_and_close']['native_visible'] and checks['restore_and_worker']['native_visible']
assert checks['restore_and_worker']['background_backup_gui_timer_ticks']>=5
geometry=[read(E/('scale-'+scale)/'measurements.json') for scale in ('1','1.5','2')]
for report in geometry:
    assert len(report['scenarios'])==18
    assert not report['direct_edit_notice_unchanged'] and report['write_feedback']['page_enabled']
    for scene in report['scenarios']:
        width,height=map(int,scene['name'].split('-')[0].split('x'))
        assert scene['actual_window']==[width,height]
        assert scene['inline']['full_row_capacity'] >= (5 if width==1000 else 6)
package=read(V/'packaged-personnel-validation.json');upgrade=read(V/'upgrade-1.1.5-to-1.1.6.json')
assert package['standalone_installer']==package['shortcut_target']==package['upgrade_data_preservation']=='PASS'
for item in package['packages']:
    assert item['visible'] and item['cargo_hash_unchanged'] and item['file_version']=='1.1.6'
    assert item['launch']==item['single_instance']=='PASS'
assert upgrade['from_version']=='1.1.5' and upgrade['to_version']=='1.1.6'
assert upgrade['installed_upgrade']==upgrade['nested_database_install_guard']=='PASS'
assert upgrade['legacy_cargo_business_rows']==upgrade['legacy_personnel_business_rows']=='UNCHANGED'
exe=ROOT/'dist/CargoTrack/CargoTrack.exe';zip_path=R/'CargoTrack-1.1.6-Windows-x64.zip';setup=R/'CargoTrack-Setup-1.1.6.exe'
with zipfile.ZipFile(zip_path) as z:
    assert z.testzip() is None
    assert hashlib.sha256(z.read('CargoTrack/CargoTrack.exe')).hexdigest()==record(exe)['sha256']
    assert z.read('CargoTrack/_internal/assets/help/user-guide.html')==(ROOT/'assets/help/user-guide.html').read_bytes()
assert record(V/'installed/CargoTrack/CargoTrack.exe')['sha256']==record(Path(upgrade['installed_directory'])/'CargoTrack/CargoTrack.exe')['sha256']==record(exe)['sha256']
files=list((ROOT/'src/cargo_track').glob('*.py'))+[ROOT/'requirements.txt',ROOT/'CargoTrack.spec',ROOT/'tools/CargoTrackInstaller.cs',ROOT/'tools/windows-version.txt',ROOT/'assets/help/user-guide.html']
report={'version':'1.1.6','date':'2026-10-07','result':'PASS',
    'frontend_findings':{'repaired':['UI01','UI02','UI03','UI04','UI05','UI06','UI07','UI08','UI09']},
    'automated_tests':{'total':115,'retained_tests':99,'new_frontend_tests':16,'result':'PASS','log':str(E/'unit-tests-complete.txt')},
    'native_source_checks':checks,'geometry':{'configurations':54,'screenshots':216,'scale_factors':[1,1.5,2],'font_sizes':[10,11,12],'themes':['light','dark'],'reports':[str(E/('scale-'+s)/'measurements.json') for s in ('1','1.5','2')]},
    'component_benchmark':read(E/'benchmark.json'),
    'packaged_native_checks':package,'old_release_upgrade':upgrade,
    'packages':[record(setup),record(zip_path)],'executable':record(exe),'zip_crc_executable_and_help_identity':'PASS',
    'source_manifest':{str(p.relative_to(ROOT)):record(p)['sha256'] for p in sorted(files)},
    'update_report':str(E/'前端改进与验证说明.md'),
    'scope':'Isolated fictional fixtures and workspace test installs; real user databases and installed copy were not replaced.',
    'limits':['Synthetic scale-factor geometry is not a physical three-DPI or multi-monitor certification.',
              'Native keyboard and Qt accessible roles were checked; actual Narrator/NVDA speech remains unverified.',
              'Component timing excludes Excel parsing, database reads and complete plan generation.',
              'No real-vessel usage study or measured user-task efficiency claim.',
              'Localized Windows time-zone descriptions depend on available fonts; IANA identifiers remain visible.']}
content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
for p in (R/'release_validation-1.1.6.json',R/'release_validation.json'):p.write_text(content,encoding='utf-8')
print(json.dumps({'version':report['version'],'result':'PASS','tests':115,'packages':report['packages']},ensure_ascii=False,indent=2))
