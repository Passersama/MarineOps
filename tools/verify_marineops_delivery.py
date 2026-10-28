"""Read-only verification of the delivered PNGs and embedded ICO frames."""
from pathlib import Path
import hashlib
import json
import struct
import sys

from PySide6.QtGui import QImage


def verify(root: Path) -> dict:
    checks = []
    for path in [root / 'marineops-symbol-master.png',
                 *sorted((root / 'png').glob('*.png')),
                 *sorted((root / 'icons').glob('*.png'))]:
        image = QImage(str(path))
        assert not image.isNull(), path
        assert image.hasAlphaChannel(), path
        corners = [(0, 0), (image.width()-1, 0),
                   (0, image.height()-1), (image.width()-1, image.height()-1)]
        assert all(image.pixelColor(x, y).alpha() == 0 for x, y in corners), path
        if path.parent.name == 'icons':
            size = int(path.stem.split('-')[-1])
            assert (image.width(), image.height()) == (size, size)
        checks.append({'file': path.relative_to(root).as_posix(),
                       'size': [image.width(), image.height()],
                       'decoded': True, 'alpha_channel': True,
                       'transparent_corners': True})
    master = QImage(str(root / 'marineops-symbol-master.png'))
    hole_alpha = master.pixelColor(int(master.width()*.76), int(master.height()*.60)).alpha()
    assert hole_alpha == 0, hole_alpha
    ico = (root / 'marineops.ico').read_bytes()
    assert struct.unpack_from('<HHH', ico) == (0, 1, 8)
    frames = []
    for index in range(8):
        w, h, _, _, planes, depth, length, offset = struct.unpack_from('<BBBBHHII', ico, 6+index*16)
        w, h = w or 256, h or 256
        assert (planes, depth) == (1, 32)
        png = ico[offset:offset+length]
        assert png.startswith(b'\x89PNG\r\n\x1a\n')
        assert struct.unpack_from('>II', png, 16) == (w, h)
        assert png == (root / 'icons' / f'marineops-{w}.png').read_bytes()
        image = QImage.fromData(png, 'PNG')
        assert not image.isNull() and image.hasAlphaChannel()
        assert (image.width(), image.height()) == (w, h)
        frames.append([w, h])
    assert [size[0] for size in frames] == [16, 20, 24, 32, 48, 64, 128, 256]
    native_ico = QImage(str(root / 'marineops.ico'))
    assert not native_ico.isNull(), 'Native Qt ICO decoder failed'
    return {'status': 'passed', 'png_files_checked': len(checks),
            'png_checks': checks, 'loop_interior_alpha': hole_alpha,
            'ico_frames': frames, 'ico_frames_decoded': True,
            'native_qt_ico_decode': True}


if __name__ == '__main__':
    folder = Path(sys.argv[1])
    report = verify(folder)
    (folder / 'file-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    files = sorted(p for p in folder.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
    (folder / 'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(folder).as_posix() + '\n'
        for p in files), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'png_files': report['png_files_checked'],
                      'ico_sizes': [size[0] for size in report['ico_frames']],
                      'loop_alpha': report['loop_interior_alpha'],
                      'native_qt_ico_decode': True, 'package_files': len(files)+1}))
