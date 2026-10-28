"""Evidence composites only; product UI is captured from native Qt."""
from pathlib import Path
import json
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'output/dashboard-release-20261012';references=ROOT/'output/dashboard-prototype-20261012/evidence'
evidence=[]
for theme in ('light','dark'):
    reference=Image.open(references/f'reference-{theme}.png').convert('RGB')
    native=Image.open(out/f'dashboard-{theme}-1440.png').convert('RGB')
    evidence.append({'theme':theme,'reference_pixels':reference.size,'native_pixels':native.size,'logical_window':[1440,1024]})
    a=reference.resize((1440,1024),Image.Resampling.LANCZOS);b=native.resize((1440,1024),Image.Resampling.LANCZOS)
    canvas=Image.new('RGB',(2880,1060),'#eeeeee');canvas.paste(a,(0,36));canvas.paste(b,(1440,36))
    draw=ImageDraw.Draw(canvas);draw.text((12,10),'Selected design / normalized 1440 x 1024',fill='black');draw.text((1452,10),'Native Qt / fictional data / 1440 x 1024 logical',fill='black')
    canvas.save(out/f'comparison-{theme}.jpg',quality=95)
    crops=[a.crop((1015,534,1435,989)),b.crop((995,485,1424,984))]
    focus=Image.new('RGB',(960,610),'#eeeeee')
    for i,crop in enumerate(crops):
        crop.thumbnail((460,560),Image.Resampling.LANCZOS);focus.paste(crop,(i*480+10,36))
    ImageDraw.Draw(focus).text((10,10),'Selected personnel panel',fill='black');ImageDraw.Draw(focus).text((490,10),'Native personnel / selected saved version',fill='black')
    focus.save(out/f'comparison-personnel-{theme}.jpg',quality=95)
(out/'comparison-conditions.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence))
