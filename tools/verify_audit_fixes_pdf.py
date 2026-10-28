"""Inspect native Excel PDFs, physical paper sizes and complete stress-fixture text."""
from pathlib import Path
import json
import re
from pypdf import PdfReader
import pypdfium2 as pdfium

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/audit-fixes-1.2.3'
result={'outputs':{},'result':'PASS'}
texts={}
for name in ('normal-berthing','normal-details','normal-transfer-print','long-berthing','long-details','long-transfer-print','cargo-normal','cargo-long'):
    path=OUT/(name+'.pdf');book=PdfReader(path)
    expected=(595.28,841.89) if name.endswith('berthing') else (841.89,595.28)
    pages=[]
    for page in book.pages:
        width,height=float(page.mediabox.width),float(page.mediabox.height)
        assert abs(width-expected[0])<1 and abs(height-expected[1])<1,(name,width,height)
        text=' '.join((page.extract_text() or '').split());pages.append(text)
        if name.startswith('cargo'):assert 'Physical ID' in text and 'Description' in text,(name,text[:160])
        elif not name.endswith('berthing'):assert 'Position' in text and 'From' in text and 'To' in text,(name,text[:160])
        else:assert 'Comments' in text,(name,text[:160])
    texts[name]=' '.join(pages)
    result['outputs'][name]={'pages':len(pages),'physical_A4':True,'repeated_headers':True,'orientation':'portrait' if name.endswith('berthing') else 'landscape'}
    document=pdfium.PdfDocument(path)
    selected=range(len(document)) if name.endswith('berthing') else sorted({0,len(document)-1})
    for i in selected:document[i].render(scale=1.3).to_pil().save(str(OUT/(name+f'-page-{i+1}.png')))
for name in ('long-berthing','long-details','long-transfer-print'):
    text=texts[name]
    for i in range(1,121):
        person=f'Fictional Passenger {i:03d} Long English Full Name'
        assert text.count(person)==2,(name,person,text.count(person))
    result['outputs'][name]['all_120_passengers_present_twice']=True
for name in ('normal-berthing','long-berthing'):
    compact=re.sub(r'\s+','',texts[name]);assert 'COMMENT-END' in compact
    result['outputs'][name]['comment_tail_present']=True
assert 'CARGO-NOTE-END' in re.sub(r'\s+','',texts['cargo-long'])
assert texts['cargo-long'].count('Cargo note')==450,texts['cargo-long'].count('Cargo note')
assert result['outputs']['cargo-normal']['pages']==1
result['outputs']['cargo-long']['all_450_comment_phrases_present']=True
(OUT/'pdf-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
