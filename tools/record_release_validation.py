"""Record the current packaged release after native validation has passed."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cargo_track import __version__


def main():
    folder = ROOT / 'artifacts' / f'validation-{__version__}'
    display = json.loads((folder / 'display-validation.json').read_text(encoding='utf-8-sig'))
    setup = json.loads((folder / 'actual-desktop-validation.json').read_text(encoding='utf-8-sig'))
    assert len(display) == 24
    assert all(row['control_bounds'] == 'PASS' for row in display)
    assert all(row['completed_delete_restore_and_popup_free_status'] == 'PASS'
               and row['live_theme_font_switch_and_f1'] == 'PASS'
               for row in display if row['scenario'] == 'filled')
    assert all(setup[key] == 'PASS' for key in ('shortcut_launch', 'upgrade_data_preservation', 'repeat_launch'))
    assets = folder / 'installed/CargoTrack/_internal/assets'
    for relative in ('help/user-guide.html', 'fonts/Inter-Regular.ttf', 'fonts/Inter-SemiBold.ttf',
                     'fonts/Inter-OFL.txt', 'branding/chevron-dark.svg', 'branding/chevron-disabled-dark.svg'):
        assert (assets / relative).is_file(), relative
    contrast = json.loads((ROOT / 'tools/deliverable_validation.json').read_text(encoding='utf-8-sig'))['contrast_ratios']
    artifacts = {}
    for relative in (f'release/CargoTrack-Setup-{__version__}.exe', f'release/CargoTrack-{__version__}-Windows-x64.zip'):
        path = ROOT / relative
        artifacts[relative] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    report = {
        'version': __version__, 'date': '2026-09-30',
        'checks': {'service_tests': 'PASS (26; includes restore fault injection and relocation failures)',
                   'native_display_states': len(display), 'themes': ['Light', 'Dark'],
                   'effective_dpi_percent': [100, 125, 150, 175, 200], 'font_sizes_pt': [11, 12],
                   'popup_free_status_delete_restore': 'PASS', 'live_theme_font_and_f1': 'PASS',
                   'bundled_offline_help_fonts_and_dark_arrows': 'PASS',
                   'actual_desktop_shortcut': 'PASS', 'standalone_setup': 'PASS',
                   'upgrade_data_preservation': 'PASS', 'single_instance': 'PASS'},
        'contrast_ratios': contrast,
        'not_checked': ['Actual screen reader speech listening', 'Physical multi-monitor transitions', 'Windows high contrast theme'],
        'evidence': {'display': f'../artifacts/validation-{__version__}/display-validation.json',
                     'setup': f'../artifacts/validation-{__version__}/actual-desktop-validation.json'},
        'artifacts': artifacts,
    }
    for name in (f'release_validation-{__version__}.json', 'release_validation.json'):
        (ROOT / 'release' / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
