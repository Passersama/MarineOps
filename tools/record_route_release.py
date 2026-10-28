"""Record evidence against the exact 1.1.7 route-overview packages."""
from pathlib import Path
import hashlib
import json
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cargo_track import __version__

E = ROOT / 'output/route-overview-20261007'
V = ROOT / 'artifacts/validation-1.1.7'
R = ROOT / 'release'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def record(path):
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

assert __version__ == '1.1.7'
log = (E / 'unit-tests-complete.txt').read_text(encoding='utf-8-sig')
assert re.search(r'Ran 120 tests in [\d.]+s\s+OK\s*$', log)
assert 'Built CargoTrack-Setup-1.1.7.exe' in (E / 'build-release-final.txt').read_text(encoding='utf-8-sig')
routes = [read(E / name) for name in ('checks.json', 'checks-24.json')]
assert [report['stops'] for report in routes] == [13, 24]
for report in routes:
    assert report['native_visible'] and len(report['scenarios']) == 12
    assert all(scene['all_stops_visible'] for scene in report['scenarios'])
    assert report['last_stop_click_uses_original_identity']
    assert report['current_stop_remains_manual'] and report['stop_menus_retained']
package = read(V / 'packaged-route-validation.json')
upgrade = read(V / 'upgrade-1.1.6-to-1.1.7.json')
assert package['standalone_installer'] == package['shortcut_target'] == package['upgrade_data_preservation'] == 'PASS'
assert {item['edition'] for item in package['packages']} == {'installed', 'portable'}
for item in package['packages']:
    assert item['visible'] and item['cargo_hash_unchanged']
    assert item['file_version'] == '1.1.7' and item['native_window'] == 'Cargo Track 1.1.7'
    assert item['launch'] == item['single_instance'] == 'PASS'
assert upgrade['from_version'] == '1.1.6' and upgrade['to_version'] == '1.1.7'
assert upgrade['installed_upgrade'] == upgrade['nested_database_install_guard'] == 'PASS'
assert upgrade['legacy_cargo_business_rows'] == upgrade['legacy_personnel_business_rows'] == 'UNCHANGED'
exe = ROOT / 'dist/CargoTrack/CargoTrack.exe'
archive = R / 'CargoTrack-1.1.7-Windows-x64.zip'
setup = R / 'CargoTrack-Setup-1.1.7.exe'
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    assert hashlib.sha256(bundle.read('CargoTrack/CargoTrack.exe')).hexdigest() == record(exe)['sha256']
    assert bundle.read('CargoTrack/_internal/assets/help/user-guide.html') == (ROOT / 'assets/help/user-guide.html').read_bytes()
assert record(V / 'installed/CargoTrack/CargoTrack.exe')['sha256'] == record(exe)['sha256']
assert record(Path(upgrade['installed_directory']) / 'CargoTrack/CargoTrack.exe')['sha256'] == record(exe)['sha256']
files = list((ROOT / 'src/cargo_track').glob('*.py')) + [
    ROOT / name for name in ('requirements.txt', 'CargoTrack.spec', 'tools/CargoTrackInstaller.cs',
                            'tools/windows-version.txt', 'assets/help/user-guide.html')]
report = {
    'version': '1.1.7', 'date': '2026-10-07', 'result': 'PASS',
    'change': 'All voyage stops expand in reading order and wrap to the available window width; no horizontal route scrolling.',
    'automated_tests': {'total': 120, 'retained_tests': 115, 'new_route_tests': 5,
                        'result': 'PASS', 'log': str(E / 'unit-tests-complete.txt')},
    'native_route_checks': routes,
    'packaged_native_checks': package, 'old_release_upgrade': upgrade,
    'packages': [record(setup), record(archive)], 'executable': record(exe),
    'zip_crc_executable_and_help_identity': 'PASS',
    'source_manifest': {str(path.relative_to(ROOT)): record(path)['sha256'] for path in sorted(files)},
    'update_report': str(E / '全航程展开与验证说明.md'),
    'scope': 'Isolated fictional fixtures and workspace test installs; real user databases and installed copy were not replaced.',
    'limits': ['Visibility verified for 13 and 24 visits across the recorded windows, fonts and themes; arbitrary route length is not certified.',
               '1920x1080 requests are constrained by the native monitor work area to 1920x1047; actual dimensions are recorded.',
               'These checks do not certify multiple physical Windows DPI settings or screen-reader speech.']}
content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
for path in (R / 'release_validation-1.1.7.json', R / 'release_validation.json'):
    path.write_text(content, encoding='utf-8')
print(json.dumps({'version': report['version'], 'result': 'PASS', 'tests': 120,
                  'packages': report['packages']}, ensure_ascii=False, indent=2))
