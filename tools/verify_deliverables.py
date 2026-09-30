"""Check artifact integrity, internal links and essential readable contrast."""
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def luminance(value):
    rgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
    return sum(v*w for v,w in zip(linear,[0.2126,0.7152,0.0722]))


def main():
    docs=['货物追踪软件方案.md','货物追踪软件_UI设计方案.md','货物追踪软件_技术审阅.md','架构与UI修订计划.md']
    link_count=0
    for name in docs:
        content=(ROOT/name).read_text(encoding='utf-8-sig')
        assert '\ufffd' not in content and len(content)>100,name
        assert content.count('```')%2==0,name
        for target in re.findall(r'\]\(([^)]+)\)',content):
            if target.startswith(('http:','https:','C:/')):
                continue
            assert (ROOT/target).exists(),(name,target)
            link_count+=1
    contrast={}
    pairs={'body':('#17243A','#FFFFFF'),'secondary':('#59677D','#FFFFFF'),
           'primary button':('#FFFFFF','#0066D6'),'current-stop on selected row':('#0066CC','#EAF3FF'),
           'Waiting':('#7A4B00','#FFF2D6'),'On Board':('#174B87','#DFEDFF'),'Done':('#17603A','#E2F3E7'),
           'dark body':('#E6E8ED','#25272E'),'dark secondary':('#ADB4C1','#202329'),
           'dark placeholder':('#A4ABB7','#25272E'),'dark selected':('#A6D0FF','#183D61'),
           'dark menu selected':('#081827','#4199FF'),'dark help link':('#A6D0FF','#25272E'),
           'dark Waiting':('#FFD58A','#49381C'),'dark On Board':('#A9D0FF','#193957'),
           'dark Done':('#A1E3BC','#1E4030')}
    for label,(fg,bg) in pairs.items():
        values=sorted([luminance(fg),luminance(bg)])
        ratio=(values[1]+0.05)/(values[0]+0.05)
        assert ratio>=4.5,(label,ratio)
        contrast[label]=round(ratio,2)
    images=[]
    for stem,size in [('货物追踪软件_UI主界面示意',(1366,768)),('货物追踪软件_UI宽屏详情示意',(1920,1080)),('货物追踪软件_UI空航程示意',(1366,768))]:
        svg=ET.parse(ROOT/(stem+'.svg')).getroot()
        assert svg.attrib['viewBox']==f'0 0 {size[0]} {size[1]}'
        with Image.open(ROOT/(stem+'.png')) as im:
            assert im.size==size
            im.verify()
        images.append(dict(file=stem+'.png',size=size,bytes=(ROOT/(stem+'.png')).stat().st_size))
    report=dict(date='2026-09-30',documents=docs,valid_local_links=link_count,contrast_ratios=contrast,images=images,
                note='Static artifact checks only, not runtime or full accessibility verification.')
    (ROOT/'tools'/'deliverable_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
