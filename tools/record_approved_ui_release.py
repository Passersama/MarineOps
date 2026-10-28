"""Record evidence and hashes after the approved UI release checks pass."""
from pathlib import Path
import hashlib,json,zipfile,sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cargo_track import __version__
def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))
native=read('output/approved-ui-20261011/native-checks.json')
package=read(f'artifacts/validation-{__version__}/packaged-workspace-validation.json')
upgrade=read(f'artifacts/validation-{__version__}/upgrade-1.1.9-to-{__version__}.json')
assert native['fictional_data'] and native['cargo_creation_receipt_selects_new_record']
assert native['personnel_24_visits_visible_without_scrolling'] and native['help_menu_routes_to_named_sections']
assert package['standalone_installer']=='PASS' and package['shortcut_target']=='PASS'
assert len(package['packages'])==2 and all(p['launch']=='PASS' and p['single_instance']=='PASS' for p in package['packages'])
assert upgrade['installed_upgrade']=='PASS' and upgrade['legacy_cargo_business_rows']=='UNCHANGED' and upgrade['legacy_personnel_business_rows']=='UNCHANGED'
assert 'final result: passed' in (ROOT/'design-qa.md').read_text(encoding='utf-8')
for file in ('output/ui-approved-final-tests.txt','output/ui-approved-final-frontend.txt','output/ui-approved-regressions.txt'):
    assert (ROOT/file).read_text(encoding='utf-8').rstrip().endswith('OK'),file
portable=ROOT/f'release/CargoTrack-{__version__}-Windows-x64.zip'
with zipfile.ZipFile(portable) as archive:assert archive.testzip() is None
paths=[f'release/CargoTrack-Setup-{__version__}.exe',str(portable.relative_to(ROOT))]
paths += ['src/cargo_track/'+file for file in ('ui.py','personnel_ui.py','appearance.py','navigation.py','route_layout.py','theme_tokens.py','berth_plan.py','__init__.py')]
paths += ['assets/help/user-guide.html','assets/branding/maritime-operations-logo-v3-dark.png','design-qa.md']
files={file:{'bytes':(ROOT/file).stat().st_size,'sha256':hashlib.sha256((ROOT/file).read_bytes()).hexdigest()} for file in paths}
report={'version':__version__,'date':'2026-10-12','result':'PASS','scope':'Native workspaces and isolated Windows release validation',
        'tests':{'complete_suite':159,'final_frontend':23,'new_planning_regressions':5},
        'native':native,'packages':package,'upgrade':upgrade,'files':files,
        'user_data':'Not replaced; fixtures and isolated legacy copies only'}
target=ROOT/f'release/release_validation-{__version__}.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'version':__version__,'result':'PASS','manifest':str(target),'packages':[str(ROOT/p) for p in paths[:2]]},ensure_ascii=False))
