"""Record immutable 1.2.3 package, source, regression and native print evidence."""
from pathlib import Path
import hashlib
import json
import re
import types
import zipfile
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/audit-fixes-1.2.3'
VALID=ROOT/'artifacts/validation-1.2.3'
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
for name in ('final-full-tests.log','regression-tests.log'):
    value=(OUT/name).read_text(encoding='utf-8-sig')
    assert value.rstrip().endswith('OK'),name
    tests[name]=int(re.findall(r'Ran (\d+) tests',value)[-1])
native=read(OUT/'native-checks.json');assert native['result']=='PASS' and native['platform']=='windows'
assert len(native['scenarios'])==2 and all(s['backup_valid'] and s['reopen_passed'] and s['cargo_unchanged'] for s in native['scenarios'])
excel=read(OUT/'excel-native-checks.json');assert excel['result']=='PASS' and excel['source_workbooks_unchanged']
assert len(excel['outputs'])==8 and all(s['paper_size']==9 and s['zoom']==100 for s in excel['outputs'])
pdf=read(OUT/'pdf-checks.json');assert pdf['result']=='PASS'
assert all(v['physical_A4'] and v['repeated_headers'] for v in pdf['outputs'].values())
assert all(pdf['outputs'][n]['all_120_passengers_present_twice'] for n in ('long-berthing','long-details','long-transfer-print'))
dashboard=read(OUT/'dashboard/native-checks.json');assert dashboard['final']=='PASS'
optimizer=read(OUT/'optimizer/native-checks.json');assert optimizer['result']=='PASS' and optimizer['cargo_database_unchanged']
packages=read(VALID/'print-legs-packaged-validation.json')
assert packages['version']=='1.2.3' and packages['previous_version']=='1.2.2'
assert packages['standalone_installer']==packages['upgrade']=='PASS'
assert packages['fixture']['removed_leg_history_preserved'] and packages['fixture']['legacy_removed_reference_differs_from_current_parent']
exe=ROOT/'dist/CargoTrack/CargoTrack.exe'
assert len(packages['packages'])==2
assert all(p['sha256'].lower()==sha(exe) and p['databases_unchanged'] and p['clean_close']=='PASS' for p in packages['packages'])
portable=ROOT/'release/CargoTrack-1.2.3-Windows-x64.zip'
with zipfile.ZipFile(portable) as archive:
    assert archive.testzip() is None
    assert hashlib.sha256(archive.read('CargoTrack/CargoTrack.exe')).hexdigest()==sha(exe)
    assert archive.read('CargoTrack/_internal/assets/help/user-guide.html')==(ROOT/'assets/help/user-guide.html').read_bytes()
    assert not any(n.lower().endswith(('.sqlite3','.sqlite','.db')) for n in archive.namelist())
container=CArchiveReader(str(exe));pyz=container.open_embedded_archive(next(n for n in container.toc if n.endswith('.pyz')))
modules=['excel_layout','personnel_service','personnel_routes','personnel_ui','berth_plan','service',
    'dashboard_data','dashboard_ui','berth_optimizer','berth_optimization_validation']
for name in modules:
    path=ROOT/'src/cargo_track'/f'{name}.py'
    assert semantic(compile(path.read_text(encoding='utf-8'),'comparison','exec',optimize=0))==semantic(pyz.extract('cargo_track.'+name)),name
previous=read(ROOT/'release/release_validation-1.2.2.json')
for name,metadata in previous['files'].items():
    if name.startswith('release/'):assert sha(ROOT/name)==metadata['sha256'],name
files=['release/CargoTrack-Setup-1.2.3.exe','release/CargoTrack-1.2.3-Windows-x64.zip','dist/CargoTrack/CargoTrack.exe',
    'assets/help/user-guide.html']+['src/cargo_track/'+n+'.py' for n in modules]
report={'version':'1.2.3','date':'2026-10-26','result':'PASS','resolved_audit_findings':['F1','F2','F3','F4'],
    'tests':tests,'native_links':native,'native_excel':excel,'native_pdf':pdf,'dashboard':dashboard,'optimizer':optimizer,
    'packages':packages,'compiled_modules_match_source':modules,'zip_integrity':'PASS',
    'previous_1_2_2_packages_unchanged':True,'no_business_databases_in_package':True,
    'user_data':'Only isolated fictional data was changed; existing user databases and imported workbooks were not modified',
    'limitations':['Physical paper printing and the WPS Office application itself were not tested; native Excel PDF dimensions and text were verified',
        'Transfer Details retains 19 electronic data columns but prints the first 8 business columns; use Transfer Print for the business view with comments',
        'Original Transfers rows retain their data; very long Cargo cells use an additional Cargo Print view for complete continuations',
        'Active chain corruption unrelated to historical removed-leg snapshots still fails validation and needs review'],
    'files':{name:{'bytes':(ROOT/name).stat().st_size,'sha256':sha(ROOT/name)} for name in files}}
(ROOT/'release/release_validation-1.2.3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'更新与验证说明.md').write_text(f'''# Cargo Track 1.2.3 更新与验证说明

完成日期：2026-10-26。结论：审核中的 F1—F4 已修复，并已验证最终安装版和便携版。

## 修复内容

1. 人员链可靠性：已移除的段保留原有历史快照；活动链在提交、打开和备份时统一校验。移除后续段再重接前段后，备份和重新打开均成功，历史载荷及事件不改写。已受旧问题影响、仅取消段历史引用过时的库可直接打开；无效活动链更新会回滚。
2. Link legs：按起终点建议顺序，确认窗口可拖动及 Move up / Move down。名单录入顺序不再限制合法关联。
3. 长名单和备注：完整续行、续页；每页重复表头、站号和地点，人员编号延续，人数只在操作组首行统计。常规小名单仍保留四行格式。保存的计划快照不因导出改变。
4. 打印：主计划保持 C 列 60，使用真实 A4 竖版和 100% 缩放，列宽落在可打印范围内；Cargo 九列使用 A4 横版。完整 19 列 Transfer Details 电子数据保留，新增带备注的 Transfer Print。超长 Cargo 单元格提供 Cargo Print，原始 Transfers 数据保留。

## 最终验证

- 完整回归 {tests['final-full-tests.log']} 项通过；针对本次问题的 {tests['regression-tests.log']} 项回归通过。
- Windows Qt 实际 Link legs 确认窗口：反向录入顺序、移除后重接、备份、关库重开、历史不变、Cargo 不变均通过。
- 本轮重新跑原生 Dashboard 和 Auto plan：Light/Dark、窗口尺寸、240 行名单、24 次到访、旧异步结果失效、重复靠泊选择、采用/撤销、修改后撤销最优证明、源数据哈希等通过。
- Excel 只读导出 8 组 PDF：全部为实际 A4 尺寸（竖版约 595.2×841.8 点，横版反向），重复表头完整，源 XLSX 字节不变。
- 常规靠船计划 1 页 A4 竖版；120 人长名单主计划 {pdf['outputs']['long-berthing']['pages']} 页。核对全部 120 名人员在接人及送人操作中各出现一次，以及长备注末尾标记。
- Cargo 常规测试含两条记录，九列同在 1 页 A4 横版；长备注的 450 组文字与末尾标记完整保留。人员打印视图保持相关业务列同页，按纵向分页。
- 安装版及便携版：1.2.2→1.2.3 隔离升级、人员原生窗口、无人员启动错误弹窗、单实例、正常退出、数据库哈希不变均通过。测试库包括旧版会拒绝的取消段历史关联和有效三段活动链。
- ZIP 完整性通过，不含业务数据库；安装版/便携版 EXE 一致，{len(modules)} 个打包模块与当前源代码一致。1.2.2 的安装包和便携包哈希保持原样。

## 使用

关闭旧版后运行 `release/CargoTrack-Setup-1.2.3.exe`，或完整解压 `release/CargoTrack-1.2.3-Windows-x64.zip` 后运行 CargoTrack/CargoTrack.exe。

更新后刷新人员名单，重新生成、核对并保存计划，再导出 Excel；无需重复导入原名单。历史计划和旧 Excel 不会自动重写。

打印人员业务明细及备注时选 Transfer Print；Transfer Details 保留全部电子字段，其直接打印范围为前八列。Cargo 导出超长内容时默认打开 Cargo Print，完整原始记录仍在 Transfers。

已验证 Microsoft Excel 的原生 PDF 导出，没有进行纸质打印或 WPS Office 应用程序验证。与取消段历史快照无关的活动链损坏仍需复核，程序不会猜测或改写身份关系。

## 证据

- `release/release_validation-1.2.3.json`
- `output/audit-fixes-1.2.3/final-full-tests.log`
- `output/audit-fixes-1.2.3/regression-tests.log`
- `output/audit-fixes-1.2.3/native-checks.json`
- `output/audit-fixes-1.2.3/excel-native-checks.json`
- `output/audit-fixes-1.2.3/pdf-checks.json`
- `output/audit-fixes-1.2.3/dashboard/native-checks.json`
- `output/audit-fixes-1.2.3/optimizer/native-checks.json`
- `artifacts/validation-1.2.3/print-legs-packaged-validation.json`
''',encoding='utf-8')
print(json.dumps({'result':'PASS','version':'1.2.3','tests':tests,'resolved':['F1','F2','F3','F4']},indent=2))
