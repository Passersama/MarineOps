"""Bind the 1.1.8 delivery to tests, native Excel and exact package bytes."""
from pathlib import Path
import hashlib
import json
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cargo_track import __version__

E = ROOT / 'output/personnel-routes-20261011'
V = ROOT / 'artifacts/validation-1.1.8'
R = ROOT / 'release'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def record(path):
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

assert __version__ == '1.1.8'
assert re.search(r'Ran 141 tests in [\d.]+s\s+OK\s*$', (E / 'unit-tests-complete.txt').read_text(encoding='utf-8-sig'))
assert re.search(r'Ran 19 tests in [\d.]+s\s+OK\s*$', (E / 'frontend-after-logo.txt').read_text(encoding='utf-8-sig'))
assert 'Built CargoTrack-Setup-1.1.8.exe' in (E / 'build-release-final.txt').read_text(encoding='utf-8-sig')
native = read(E / 'native-checks.json')
assert all(value is True for value in native.values() if isinstance(value, bool))
excel = [read(E / 'excel-native' / name) for name in ('excel-native-validation.json', 'long-excel-native-validation.json')]
for item in excel:
    assert item['readonly_open'] == item['native_pdf_export'] == 'PASS' and item['source_unchanged']
package = read(V / 'packaged-personnel-validation.json')
upgrade = read(V / 'upgrade-1.1.7-to-1.1.8.json')
assert package['standalone_installer'] == package['shortcut_target'] == package['upgrade_data_preservation'] == 'PASS'
assert {item['edition'] for item in package['packages']} == {'installed', 'portable'}
for item in package['packages']:
    assert item['visible'] and item['cargo_hash_unchanged']
    assert item['file_version'] == '1.1.8' and item['native_window'] == 'Cargo Track 1.1.8'
    assert item['launch'] == item['single_instance'] == 'PASS'
assert upgrade['from_version'] == '1.1.7' and upgrade['to_version'] == '1.1.8'
assert upgrade['installed_upgrade'] == upgrade['nested_database_install_guard'] == 'PASS'
assert upgrade['legacy_cargo_business_rows'] == upgrade['legacy_personnel_business_rows'] == 'UNCHANGED'
exe = ROOT / 'dist/CargoTrack/CargoTrack.exe'
archive = R / 'CargoTrack-1.1.8-Windows-x64.zip'
setup = R / 'CargoTrack-Setup-1.1.8.exe'
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
    'version': '1.1.8', 'date': '2026-10-11', 'result': 'PASS',
    'changes': ['Optional port in Final plan', 'Explicit personnel transfer legs and later-visit pickup',
                'Configured transfer-vessel origin matches To only', 'Inline four-row Excel stop table', 'Updated maritime logo'],
    'automated_tests': {'total': 141, 'result': 'PASS', 'log': str(E / 'unit-tests-complete.txt'),
                        'frontend_after_final_logo_and_column_changes': {'total': 19, 'result': 'PASS', 'log': str(E / 'frontend-after-logo.txt')}},
    'native_workflow': native, 'excel_native': excel,
    'packaged_native_checks': package, 'old_release_upgrade': upgrade,
    'packages': [record(setup), record(archive)], 'executable': record(exe),
    'zip_crc_executable_help_and_brand_identity': 'PASS',
    'source_manifest': {str(path.relative_to(ROOT)): record(path)['sha256'] for path in sorted(files)},
    'sample_workbook': record(E / 'Niger-plan-example.xlsx'),
    'update_report': str(E / '人员分段接送与导出更新说明.md'),
    'scope': 'Fictional fixtures and isolated workspace test installs; no replacement of real user databases or installed copy.',
    'limits': ['Excel verified with seven visits and an additional 45-passenger, six-long-CJK-material fixture.',
               'Excel hard cell and row-height limits produce explicit errors; arbitrary unbounded content is not certified.',
               'Physical multi-monitor DPI transitions and screen-reader speech were not tested.']}
content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
for path in (R / 'release_validation-1.1.8.json', R / 'release_validation.json'):
    path.write_text(content, encoding='utf-8')
print(json.dumps({'version': report['version'], 'result': 'PASS', 'tests': 141, 'packages': report['packages']}, ensure_ascii=False, indent=2))
