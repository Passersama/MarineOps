"""Normalize native DPI captures and place each beside its selected reference."""
from pathlib import Path
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QImage,QPainter

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output/approved-ui-20261011'
import sys
if len(sys.argv) != 2:raise SystemExit('Usage: compare_approved_ui.py REFERENCE_DIRECTORY')
REFERENCES=Path(sys.argv[1]).resolve()
for name,file in (('cargo','exec-1c6aadff-f707-4435-93ae-d3750be6a40b.png'),('personnel','exec-3c781ef7-d7d1-4603-8854-07636bcd96b7.png')):
    source=QImage(str(REFERENCES/file));native=QImage(str(OUTPUT/f'{name}-dark-1672.png'))
    assert not source.isNull() and not native.isNull()
    images=[image.scaled(1672,940,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation) for image in (source,native)]
    for image in images:image.setDevicePixelRatio(1)
    canvas=QImage(3344,940,QImage.Format.Format_RGB32);canvas.fill(Qt.GlobalColor.black)
    painter=QPainter(canvas)
    for i,image in enumerate(images):painter.drawImage(QRect(i*1672,0,1672,940),image,image.rect())
    painter.end();assert canvas.save(str(OUTPUT/f'{name}-comparison.png'))
    focus=QImage(2000,330,QImage.Format.Format_RGB32);focus.fill(Qt.GlobalColor.black)
    painter=QPainter(focus)
    regions=[QRect(280,170,1000,330),QRect(280,140,1000,330)]
    for i,(image,region) in enumerate(zip(images,regions)):painter.drawImage(QRect(i*1000,0,1000,330),image,region)
    painter.end();assert focus.save(str(OUTPUT/f'{name}-focused-comparison.png'))
