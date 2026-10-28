"""Bind the 1.1.9 delivery to tests, native Excel and exact package bytes."""
from pathlib import Path
import hashlib
import json
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cargo_track import __version__

E = ROOT / 'output/workspace-audit-20261011'
V = ROOT / 'artifacts/validation-1.1.9'
R = ROOT / 'release'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def record(path):
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

assert __version__ == '1.1.9'
assert re.search(r'Ran 154 tests in [\d.]+s\s+OK\s*$', (E / 'unit-tests-complete.txt').read_text(encoding='utf-8-sig'))
assert re.search(r'Ran 28 tests in [\d.]+s\s+OK\s*$', (E / 'final-ui-tests.txt').read_text(encoding='utf-8-sig'))
assert 'Built CargoTrack-Setup-1.1.9.exe' in (E / 'build-release-final.txt').read_text(encoding='utf-8-sig')
native = read(E / 'native-checks.json')
assert all(value is True for value in native.values() if isinstance(value, bool))
assert len(native['scenarios']) == 8 and all(scene['navigation_consistent'] for scene in native['scenarios'])
excel = [read(ROOT / 'output/personnel-routes-20261011/excel-native' / name) for name in ('excel-native-validation.json', 'long-excel-native-validation.json')]
for item in excel:
    assert item['readonly_open'] == item['native_pdf_export'] == 'PASS' and item['source_unchanged']
package = read(V / 'packaged-workspace-validation.json')
upgrade = read(V / 'upgrade-1.1.8-to-1.1.9.json')
assert package['standalone_installer'] == package['shortcut_target'] == package['upgrade_data_preservation'] == 'PASS'
assert {item['edition'] for item in package['packages']} == {'installed', 'portable'}
for item in package['packages']:
    assert item['visible'] and item['cargo_hash_unchanged']
    assert item['file_version'] == '1.1.9' and item['native_window'] == 'Cargo Track 1.1.9'
    assert item['launch'] == item['single_instance'] == 'PASS'
assert upgrade['from_version'] == '1.1.8' and upgrade['to_version'] == '1.1.9'
assert upgrade['installed_upgrade'] == upgrade['nested_database_install_guard'] == 'PASS'
assert upgrade['legacy_cargo_business_rows'] == upgrade['legacy_personnel_business_rows'] == 'UNCHANGED'
exe = ROOT / 'dist/CargoTrack/CargoTrack.exe'
archive = R / 'CargoTrack-1.1.9-Windows-x64.zip'
setup = R / 'CargoTrack-Setup-1.1.9.exe'
assets = ('assets/help/user-guide.html', 'assets/branding/maritime-operations-logo-v3-dark.png', 'assets/branding/cargo-track.ico')
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    assert hashlib.sha256(bundle.read('CargoTrack/CargoTrack.exe')).hexdigest() == record(exe)['sha256']
    for name in assets:
        expected = (ROOT / name).read_bytes()
        assert bundle.read('CargoTrack/_internal/' + name) == expected
        for folder in (ROOT / 'dist/CargoTrack', V / 'installed/CargoTrack', Path(upgrade['installed_directory']) / 'CargoTrack'):
            assert (folder / '_internal' / name).read_bytes() == expected
for folder in (V / 'installed/CargoTrack', Path(upgrade['installed_directory']) / 'CargoTrack'):
    assert record(folder / 'CargoTrack.exe')['sha256'] == record(exe)['sha256']
files = list((ROOT / 'src/cargo_track').glob('*.py')) + [ROOT / name for name in
    ('requirements.txt', 'CargoTrack.spec', 'tools/CargoTrackInstaller.cs', 'tools/windows-version.txt', *assets)]
report = {
    'version': '1.1.9', 'date': '2026-10-11', 'result': 'PASS',
    'changes': ['Shared workspace navigation', 'Crew-list rename', 'Current-stop deselection', 'History-list clearing with immutable snapshots', 'Unsaved navigation guard', 'Personnel F1/F5', 'Failed-open executor cleanup'],
    'automated_tests': {'total': 154, 'result': 'PASS', 'log': str(E / 'unit-tests-complete.txt'),
                        'frontend_after_final_logo_and_column_changes': {'total': 28, 'result': 'PASS', 'log': str(E / 'final-ui-tests.txt')}},
    'native_workflow': native, 'excel_native': excel,
    'packaged_native_checks': package, 'old_release_upgrade': upgrade,
    'packages': [record(setup), record(archive)], 'executable': record(exe),
    'zip_crc_executable_help_and_brand_identity': 'PASS',
    'source_manifest': {str(path.relative_to(ROOT)): record(path)['sha256'] for path in sorted(files)},
    'roster_performance': read(E / 'roster-performance.json'),
    'update_report': str(E / '软件审核与修复报告.md'),
    'scope': 'Fictional fixtures and isolated workspace test installs; no replacement of real user databases or installed copy.',
    'limits': ['History clearing removes list entries while retaining immutable snapshots.',
               'Large-roster refresh remains synchronous; 3002-row timing is recorded.',
               'Physical multi-monitor DPI transitions and screen-reader speech were not tested.']}
content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
for path in (R / 'release_validation-1.1.9.json', R / 'release_validation.json'):
    path.write_text(content, encoding='utf-8')
print(json.dumps({'version': report['version'], 'result': 'PASS', 'tests': 154, 'packages': report['packages']}, ensure_ascii=False, indent=2))
