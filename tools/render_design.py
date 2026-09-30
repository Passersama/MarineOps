"""Render the editable design drawings with the same Windows font as the native UI.

These are design artifacts, not screenshots of an implemented Cargo Track app.
"""
from pathlib import Path
from html import escape
import json
import base64
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QFont, QFontMetricsF, QFontDatabase
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication([])
for filename in ('segoeui.ttf', 'segoeuib.ttf'):
    if QFontDatabase.addApplicationFont(f'C:/Windows/Fonts/{filename}') < 0:
        raise RuntimeError(f'Required font not found: {filename}')
C = dict(bg='#F5F5F7', white='#FFFFFF', text='#17243A', sub='#59677D',
         navy='#0066D6', border='#E5E5EA', purple='#0066CC', related='#FAFBFE',
         select='#EAF3FF', amber='#FFF2D6', ambertext='#7A4B00',
         blue='#DFEDFF', bluetext='#174B87', green='#E2F3E7', greentext='#17603A')
DATA = [
    dict(no=104, cargo='C-0001', desc='Hydraulic hose assembly, 12 m', src='BVC', dst='DF2', status='Waiting', comment='Check connector size', date=''),
    dict(no=105, cargo='C-0002', desc='Deck lifting slings, set of four', src='DF2', dst='CHA', status='Done', comment='Delivered to deck crew', date='20260929'),
    dict(no=108, cargo='C-0003', desc='Pump seal kit, cargo box 03', src='CHA', dst='BVC', status='On Board', comment='Keep dry during transfer', date=''),
    dict(no=110, cargo='C-0004', desc='Fuel sample container', src='HB6', dst='On Shore', status='Waiting', comment='Lab pickup required', date=''),
    dict(no=112, cargo='C-0005', desc='Electrical junction box, type J4', src='BVC', dst='On Shore', status='Waiting', comment='Return to shore workshop', date=''),
    dict(no=114, cargo='C-0006', desc='Hard Disk', src='BVC', dst='CHA', status='On Board', comment='SN: HD-441; deliver at CHA', date=''),
    dict(no=116, cargo='C-0007', desc='Hard Disk', src='CHA', dst='On Shore', status='On Board', comment='SN: HD-442; shore delivery', date=''),
    dict(no=118, cargo='C-0008', desc='Spare seals, box 02', src='DF2', dst='INN', status='Waiting', comment='Collect at DF2', date=''),
]


class Drawing:
    def __init__(self, w, h, title):
        self.w, self.h = w, h
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
                      f'<title>{escape(title)}</title>', '<desc>Illustrative native desktop UI design, 30 September 2026. Not an implemented application.</desc>']
        self.failures = []
        self.rect(0, 0, w, h, C['bg'])

    def rect(self, x, y, w, h, fill, radius=0, stroke=None):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"' + (f' stroke="{stroke}"' if stroke else '') + '/>')

    def line(self, x, y, xx, yy, color=None, width=1):
        self.parts.append(f'<line x1="{x}" y1="{y}" x2="{xx}" y2="{yy}" stroke="{color or C["border"]}" stroke-width="{width}"/>')

    def text(self, x, y, value, size=14, color=None, weight=400, maxw=None):
        font = QFont('Segoe UI')
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.Bold if weight >= 600 else QFont.Weight.Normal)
        metrics = QFontMetricsF(font)
        if maxw is not None and metrics.horizontalAdvance(str(value)) > maxw:
            self.failures.append(dict(text=value, width=round(metrics.horizontalAdvance(str(value)), 1), available=maxw))
        self.parts.append(f'<text x="{x}" y="{y}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{weight}" fill="{color or C["text"]}">{escape(str(value))}</text>')

    def button(self, x, y, w, label, primary=False, disabled=False, h=32):
        fill = C['navy'] if primary else (C['bg'] if disabled else C['white'])
        self.rect(x, y, w, h, fill, 6, None if primary else C['border'])
        self.text(x+12, y+h/2+5, label, 13, C['white'] if primary else C['sub'] if disabled else C['text'], 600, w-24)

    def status(self, x, y, status):
        fill, text = {'Waiting': ('amber','ambertext'), 'On Board': ('blue','bluetext'), 'Done': ('green','greentext')}[status]
        w = {'Waiting': 82, 'On Board': 94, 'Done': 65}[status]
        self.rect(x, y, w, 24, C[fill], 5)
        self.text(x+10, y+17, status, 12, C[text], 600, w-20)

    def save(self, name):
        if self.failures:
            raise ValueError(json.dumps(self.failures, ensure_ascii=False))
        self.parts.append('</svg>')
        source = ROOT / f'{name}.svg'
        source.write_text('\n'.join(self.parts), encoding='utf-8')
        renderer = QSvgRenderer(str(source))
        if not renderer.isValid():
            raise ValueError(f'Invalid SVG: {source.name}')
        output = QImage(self.w, self.h, QImage.Format.Format_ARGB32)
        output.fill(Qt.GlobalColor.transparent)
        painter = QPainter(output)
        renderer.render(painter)
        painter.end()
        if not output.save(str(ROOT / f'{name}.png')):
            raise ValueError('PNG save failed')
        return dict(name=name, width=self.w, height=self.h, svg_valid=True, text_overflow=0)


def header(d):
    d.rect(0, 0, d.w, 52, C['white'])
    d.line(0, 52, d.w, 52)
    logo = base64.b64encode((ROOT/'assets/branding/cargo-track-lockup.png').read_bytes()).decode('ascii')
    d.parts.append(f'<image x="24" y="6" width="200" height="40" href="data:image/png;base64,{logo}"/>')
    x = d.w-475
    for label, w in [('Fleet', 66), ('Voyages', 90), ('Export', 80), ('Backup', 85), ('Settings', 90)]:
        d.text(x, 32, label, 14, C['navy'], 600)
        x += w


def voyage(d, w, empty=False):
    d.rect(24, 68, w, 96, C['white'], 8)
    d.text(40, 93, 'Voyage 3' if empty else 'Voyage 2', 16, weight=600)
    d.button(166, 77, 86, 'Choose')
    d.button(260, 77, 60, 'New')
    d.button(328, 77, 132, 'Copy previous')
    d.button(24+w-154, 120, 138, '+ Add vessel')
    if empty:
        d.text(40, 143, 'No vessels in this voyage', 14, C['sub'])
        d.text(490, 97, 'No stop selected', 13, C['sub'])
        return
    for i, name in enumerate(['BVC', 'CHA', 'BVC']):
        x, active = 40+i*198, i == 2
        d.rect(x, 120, 182, 32, '#EEE7FA' if active else C['bg'], 6)
        # Geometry-only drag handle, deliberately not a Unicode icon.
        for yy in [130, 135, 140]:
            d.line(x+10, yy, x+18, yy, C['sub'])
        d.text(x+28, 141, f'{i+1}  {name}', 14, C['purple'] if active else C['text'], 600)
        if active:
            d.text(x+92, 141, 'Current', 12, C['purple'], 600)
        d.line(x+162, 133, x+170, 141, C['sub'])
        d.line(x+162, 141, x+170, 133, C['sub'])
    d.text(668, 142, 'Stop menu: Move earlier / later / Remove', 12, C['sub'], maxw=w-860)


def current(d, w, empty=False):
    d.rect(24, 178, w, 140, C['white'], 8)
    d.text(40, 208, 'Current stop', 16, weight=600)
    if empty:
        d.text(40, 243, 'Add a vessel to choose your current stop.', 20, weight=600)
        d.text(40, 274, 'Your transfer ledger and on-board list are still available.', 14, C['sub'])
        d.button(24+w-312, 190, 92, 'Previous', disabled=True)
        d.button(24+w-212, 190, 62, 'Next', disabled=True)
        d.button(24+w-142, 190, 126, 'Choose stop', disabled=True)
        return
    d.text(162, 209, 'BVC', 24, C['purple'], 600)
    d.text(222, 208, '3 of 3  ·  Manual selection', 13, C['sub'])
    d.button(24+w-312, 190, 92, 'Previous')
    d.button(24+w-212, 190, 62, 'Next', disabled=True)
    d.button(24+w-142, 190, 126, 'Choose stop')
    d.text(40, 239, '2 ready to pick up', 14, C['ambertext'], 600)
    d.text(217, 239, '1 ready to deliver', 14, C['bluetext'], 600)
    d.text(394, 239, '1 other related', 14, C['sub'])
    d.text(24+w-113, 238, 'View all 4', 13, C['purple'], 600)
    for y, no, label, route, action in [(250,104,'Hydraulic hose assembly, 12 m','BVC to DF2','Pick up'),(282,108,'Pump seal kit, cargo box 03','CHA to BVC','Deliver')]:
        d.line(40, y, 24+w-16, y)
        d.text(40, y+21, f'#{no}', 13, C['sub'])
        d.text(104, y+21, label, 14, weight=600)
        d.text(570, y+21, route, 13, C['sub'])
        d.status(24+w-256, y+4, 'Waiting' if no == 104 else 'On Board')
        d.button(24+w-126, y+3, 110, action, h=26)


def views(d, w, empty=False):
    d.text(40, 355, 'All transfers', 15, C['navy'], 600)
    d.line(40, 367, 151, 367, C['navy'], 2)
    d.text(185, 355, 'Current stop  0' if empty else 'Current stop  4', 15, C['sub'])
    d.text(363, 355, 'On my vessel  3', 15, C['sub'])
    d.button(24+w-142, 336, 126, '+ Add cargo', primary=True)
    d.rect(24, 382, 410, 34, C['white'], 6, C['border'])
    d.text(38, 404, 'Search NO, Cargo ID, description, comment...', 13, C['sub'])
    d.button(446, 383, 136, 'All statuses')
    d.button(594, 383, 136, 'All vessels')
    d.button(742, 383, 178, 'Include completed')
    d.text(940, 404, 'Clear', 13, C['navy'])
    d.text(24+w-217, 404, '8 transfers  ·  8 loaded', 12, C['sub'], maxw=201)


def table(d, w, wide=False, empty=False):
    x, y = 24, 432
    header_h, row_h = 34, 44
    # A viewport can display five rows; all eight are loaded in the example model.
    rows = DATA if wide else DATA[:5]
    widths = [54,110,w-1002,88,98,112,352,156]
    columns = ['NO','Cargo ID','Description','From','To','Status','Comment','Completed Date']
    positions = [40]
    for width in widths[:-1]:
        positions.append(positions[-1]+width)
    total_h = header_h+row_h*len(rows)
    d.rect(x, y, w, total_h, C['white'])
    d.rect(x, y, w, header_h, '#EAF0F6')
    for pos, label, width in zip(positions, columns, widths):
        d.text(pos, y+22, label, 12, C['sub'], 600, width-12)
    for idx, row in enumerate(rows):
        ry = y+header_h+idx*row_h
        related = not empty and row['status'] != 'Done' and 'BVC' in (row['src'],row['dst'])
        selected = row['no'] == 108
        if related:
            d.rect(x, ry, w, row_h, C['related'])
            d.line(x+1, ry+8, x+1, ry+row_h-8, C['purple'])
        if selected:
            d.rect(x+2, ry, w-2, row_h, C['select'])
        values = [row['no'],row['cargo'],row['desc'],row['src'],row['dst'],row['status'],row['comment'],row['date'] or '-']
        for n, (pos, val, width) in enumerate(zip(positions, values, widths)):
            if n == 5:
                d.status(pos, ry+10, val)
            else:
                d.text(pos, ry+27, val, 14, C['sub'] if n in [1,6] else C['text'], 600 if n==0 else 400, width-12)
        d.line(x, ry+row_h, x+w, ry+row_h)
    if not wide:
        d.rect(x+w-8, y+header_h+4, 4, total_h-header_h-8, C['bg'], 2)
        d.rect(x+w-8, y+header_h+4, 4, 108, C['border'], 2)
    by = y+total_h+10
    d.text(40, by+21, 'Selected: #108  ·  C-0003', 13, C['sub'])
    d.button(290, by, 94, 'Details', h=30)
    d.button(394, by, 160 if empty else 110, 'Confirm delivery' if empty else 'Deliver', h=30, primary=True)
    d.text(575, by+21, 'To BVC  ·  On Board', 13, C['sub'])


def detail(d):
    x, y, w = 1432, 178, 464
    d.rect(x, y, w, 850, C['white'], 8)
    d.text(x+24,y+32,'Cargo C-0003',20,weight=600)
    d.button(x+w-92,y+15,68,'Close',h=28)
    d.text(x+24,y+59,'Transfer #108  ·  Pump seal kit, cargo box 03',14,C['sub'],maxw=w-48)
    d.text(x+24,y+98,'CHA to BVC',22,weight=600)
    d.status(x+w-118,y+77,'On Board')
    d.line(x+24,y+122,x+w-24,y+122)
    d.text(x+24,y+154,'Cargo location now',16,weight=600)
    d.text(x+24,y+184,'Confirmed on my vessel',18,C['bluetext'],600)
    d.text(x+24,y+209,'30 Sep 2026, 09:14 (UTC+03:00)',13,C['sub'])
    d.text(x+24,y+248,'Selected transfer',16,weight=600)
    d.text(x+24,y+278,'From  CHA      To  BVC',14)
    d.text(x+24,y+304,'Completed Date  -',14,C['sub'])
    d.text(x+24,y+344,'Physical ID (optional)',14,weight=600)
    d.rect(x+24,y+357,w-48,36,C['bg'],6)
    d.text(x+36,y+381,'BOX-03',14)
    d.text(x+24,y+428,'Comment',14,weight=600)
    d.rect(x+24,y+441,w-48,70,C['bg'],6)
    d.text(x+36,y+468,'Keep dry during transfer',14)
    d.text(x+24,y+550,'Transfer history',16,weight=600)
    d.text(x+24,y+578,'#108  CHA to BVC  ·  On Board',14)
    d.text(x+24,y+620,'Audit history',16,weight=600)
    d.text(x+24,y+651,'09:14  Picked up: Waiting to On Board',14)
    d.text(x+24,y+678,'08:52  Transfer created: Waiting',14,C['sub'])
    d.line(x+24,y+718,x+w-24,y+718)
    d.button(x+24,y+740,150,'Deliver to BVC',primary=True,h=36)
    d.button(x+186,y+740,108,'Edit fields',h=36)
    d.button(x+306,y+740,110,'More',h=36)
    d.text(x+24,y+816,'Delivery is saved before the status changes.',13,C['sub'],maxw=w-48)


def render(name, wide=False, empty=False):
    w,h = (1920,1080) if wide else (1366,768)
    d = Drawing(w,h,'Cargo Track: empty voyage' if empty else 'Cargo Track: wide-screen cargo detail' if wide else 'Cargo Track: main workbench')
    area = 1392 if wide else 1318
    header(d)
    voyage(d,area,empty)
    current(d,area,empty)
    views(d,area,empty)
    table(d,area,wide,empty)
    if wide:
        detail(d)
    d.line(24,h-28,w-24,h-28)
    d.text(24,h-10,'Design target  ·  Illustrative data  ·  30 Sep 2026',12,C['sub'])
    d.text(w-278,h-10,'Local data  ·  Asia/Riyadh',12,C['sub'])
    return d.save(name)


def main():
    ready_pickup = [r['no'] for r in DATA if r['status']=='Waiting' and r['src']=='BVC']
    ready_delivery = [r['no'] for r in DATA if r['status']=='On Board' and r['dst']=='BVC']
    related = [r['no'] for r in DATA if r['status']!='Done' and 'BVC' in (r['src'],r['dst'])]
    manifest = [r['no'] for r in DATA if r['status']=='On Board']
    assert ready_pickup==[104,112] and ready_delivery==[108]
    assert related==[104,108,112,114] and manifest==[108,114,116]
    outputs = [render('货物追踪软件_UI主界面示意'),render('货物追踪软件_UI宽屏详情示意',wide=True),render('货物追踪软件_UI空航程示意',empty=True)]
    report = dict(outputs=outputs, example=dict(total_legs=len(DATA),pickup=ready_pickup,delivery=ready_delivery,related=related,on_board=manifest), limitations='Design renders only; not runtime or accessibility verification.')
    (ROOT/'tools'/'design_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
