"""Record current source, test, native Excel and packaged release evidence."""
from pathlib import Path
import hashlib
import json
import re
import types
import zipfile
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/excel-legs-20261025'
VALID=ROOT/'artifacts/validation-1.2.2'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def semantic(code):
    def constant(value):
        if isinstance(value,types.CodeType):return semantic(value)
        if isinstance(value,tuple):return [constant(v) for v in value]
        if isinstance(value,frozenset):return sorted((constant(v) for v in value),key=repr)
        if isinstance(value,bytes):return {'bytes':value.hex()}
        if value is Ellipsis:return {'ellipsis':True}
        return value
    return {'code':code.co_code.hex(),'consts':[constant(c) for c in code.co_consts],
        'names':code.co_names,'vars':code.co_varnames,'free':code.co_freevars,'cells':code.co_cellvars,
        'args':code.co_argcount,'pos':code.co_posonlyargcount,'kw':code.co_kwonlyargcount,
        'flags':code.co_flags,'exceptions':code.co_exceptiontable.hex()}

tests={}
for name in ('related-tests.log','full-tests.log','native-qt-leg-tests.log'):
    log=(OUT/name).read_text(encoding='utf-8-sig')
    assert log.rstrip().endswith('OK'),name
    tests[name]=int(re.findall(r'Ran (\d+) tests',log)[-1])
assert 'Qt platform: windows' in (OUT/'native-qt-leg-tests.log').read_text(encoding='utf-8-sig')
native=read(OUT/'portrait-excel-native-validation.json')
assert native['native_pdf_export']=='PASS' and native['source_unchanged']
assert native['paper_size']==9 and native['orientation']==1
packages=read(VALID/'print-legs-packaged-validation.json')
assert packages['standalone_installer']==packages['upgrade_from_1_2_1']=='PASS'
exe=ROOT/'dist/CargoTrack/CargoTrack.exe'
assert len(packages['packages'])==2
assert all(p['sha256'].lower()==sha(exe) and p['databases_unchanged'] for p in packages['packages'])
portable=ROOT/'release/CargoTrack-1.2.2-Windows-x64.zip'
with zipfile.ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert hashlib.sha256(archive.read('CargoTrack/CargoTrack.exe')).hexdigest()==sha(exe)
    assert archive.read('CargoTrack/_internal/assets/help/user-guide.html')==(ROOT/'assets/help/user-guide.html').read_bytes()
    assert not any(n.lower().endswith(('.sqlite3','.sqlite','.db')) for n in archive.namelist())
container=CArchiveReader(str(exe))
pyz=container.open_embedded_archive(next(n for n in container.toc if n.endswith('.pyz')))
modules=['berth_plan','personnel_ui','personnel_service','personnel_routes','berth_optimizer','berth_optimization_validation']
for name in modules:
    source=ROOT/'src/cargo_track'/f'{name}.py'
    assert semantic(compile(source.read_text(encoding='utf-8'),'comparison','exec',optimize=0))==semantic(pyz.extract('cargo_track.'+name)),name
paths=['release/CargoTrack-Setup-1.2.2.exe','release/CargoTrack-1.2.2-Windows-x64.zip','dist/CargoTrack/CargoTrack.exe']
report={'version':'1.2.2','date':'2026-10-25','result':'PASS','tests':tests,'excel':native,
    'packages':packages,'compiled_modules_match_source':modules,'zip_integrity':'PASS',
    'scope':'A4 portrait Berthing Plan exports and linked personnel generation',
    'fixes':['C column width 60 and content-aware wrapped row heights',
        'Linked port and transfer-vessel origins require an actual later pickup',
        'Excluded preceding legs cannot be detached silently',
        'Link legs recalculates assignments when linkage changes'],
    'user_data':'All verification uses fictional isolated data; existing user stores and workbooks were not opened or changed',
    'limitations':['Native Excel reports A4 portrait, but the configured WPS PDF printer exports media boxes of 692.09 x 978.84 points rather than physical A4; preview layout was reviewed, physical printer output was not tested',
        'Qt Next leg and Link legs actions passed on both offscreen and Windows backends with hidden test widgets; packaged checks validate Personnel startup, single instance, clean close and unchanged fictional databases',
        'Saved historical plans are immutable; regenerate and save a new version for route fixes, re-export for print layout',
        'Excel rows above the existing 409-point/32767-character limit still require a smaller voyage'],
    'files':{p:{'bytes':(ROOT/p).stat().st_size,'sha256':sha(ROOT/p)} for p in paths}}
(ROOT/'release/release_validation-1.2.2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'更新与验证说明.md').write_text(f'''# Cargo Track 1.2.2 — 2026-10-25

## 本次修改

- Berthing Plan 默认 A4 竖版，宽度适配一页，纵向自然分页；C 列由 102 调整为 60。
- 导出时根据实际列宽、换行、单词换行和中英文内容量计算每行高度；四行操作格式、合并栏、重复表头和日期保留。
- Next leg / Link legs 的后续段从港口或接驳船出发时，需要在前段送达后再次靠泊接人，不再视为出发前已上船。
- 取消前段勾选后，后段不能绕过依赖继续安排；需包含前段，或明确排除整条后续链。
- Link legs 关联已有记录后，发生关联变化的航段重新计算分配，避免保留关联前失效的靠泊点。其他分配和用户勾选保留。

## 验证结果

- 相关回归 {tests['related-tests.log']} 项通过；完整测试集 {tests['full-tests.log']} 项通过。
- Windows Qt 后端另行验证 Next leg 和 Link legs 按钮流程，{tests['native-qt-leg-tests.log']} 项通过。
- 港口后续段、接驳船后续段、重复到访、排除前段、链路身份与顺序、保存及导出均覆盖。
- 虚构的 11 站打印样例包含 19 人长英文单元格、中英文物料和多行备注；Excel 只读打开并导出打印预览，逐页视觉检查无截断。
- Excel 读取 PaperSize=9（A4）、Orientation=1（竖版），源 XLSX 文件字节未变。
- 安装版及便携版的人员原生窗口、单实例、正常退出通过；隔离目录内从 1.2.1 升级到 1.2.2 通过，虚构数据库哈希不变。
- 两个包的 EXE 一致，ZIP 完整性通过，不含业务数据库；主要业务模块的打包代码与当前源代码一致。

## 使用方式与限制

安装 `release/CargoTrack-Setup-1.2.2.exe`，或完整解压 `release/CargoTrack-1.2.2-Windows-x64.zip` 后运行 CargoTrack/CargoTrack.exe。

打印布局：重新导出 Excel 即可应用。分段路线：重新生成、核对靠泊顺序并保存新版本，再导出。若后一段从某船或港口再次出发，必须在前段送达之后添加该地点的再次到访；也可用 Auto plan 生成完整候选。历史保存版本不会被重写，旧 Excel 不会自动改变。

本机默认“导出为 WPS PDF”驱动虽然让 Excel 读取到 A4 竖版，实际 PDF MediaBox 为 692.09 × 978.84 点，而标准 A4 约为 595.28 × 841.89 点。已确认预览中内容完整，但不能据此宣称物理 A4 打印验收通过。实机打印时须在打印机属性中确认 A4；本轮没有进行纸质打印。

测试使用隔离的虚构数据。Windows Qt 控件流程通过程序调用测试，未在安装版中逐项手工操作；安装版验证范围为窗口启动、单实例、正常退出与数据保留。单个 Excel 行超过既有 409 点高度／32767 字符上限时，仍需拆分为较小航程。

## 证据

- `release/release_validation-1.2.2.json`
- `output/excel-legs-20261025/full-tests.log`
- `output/excel-legs-20261025/related-tests.log`
- `output/excel-legs-20261025/native-qt-leg-tests.log`
- `output/excel-legs-20261025/portrait-excel-native-validation.json`
- `output/excel-legs-20261025/portrait-multileg-example.xlsx`
- `output/excel-legs-20261025/portrait-berthing-excel-print.pdf`
- `artifacts/validation-1.2.2/print-legs-packaged-validation.json`
''',encoding='utf-8')
print(json.dumps({'result':'PASS','tests':tests,'version':'1.2.2'},indent=2))
