"""Check document integrity, internal links and essential readable contrast."""
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[1]


def luminance(value):
    rgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
    return sum(v*w for v,w in zip(linear,[0.2126,0.7152,0.0722]))


def main():
    docs=['货物追踪软件方案.md','货物追踪软件_UI设计方案.md','货物追踪软件_技术审阅.md','架构与UI修订计划.md']
    link_count=0
    local_evidence_references=[]
    for name in docs:
        content=(ROOT/name).read_text(encoding='utf-8-sig')
        assert '\ufffd' not in content and len(content)>100,name
        assert content.count('```')%2==0,name
        for target in re.findall(r'\]\(([^)]+)\)',content):
            if target.startswith(('http:','https:','C:/')):
                continue
            if target.startswith(('./release/','./output/','./artifacts/','./revisions/')):
                local_evidence_references.append(dict(document=name,target=target))
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
    report=dict(documents=docs,valid_local_links=link_count,contrast_ratios=contrast,
                unverified_local_evidence_references=local_evidence_references,
                note='Document/link and palette checks only. Historical UI illustrations are no longer shipped; runtime and full accessibility are not verified here.')
    (ROOT/'tools'/'deliverable_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
