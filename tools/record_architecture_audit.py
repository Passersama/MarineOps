"""Write a bounded architecture report from accepted release evidence."""
from pathlib import Path
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/architecture-audit-1.2.5'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
before=read(OUT/'before.json');after=read(OUT/'after.json')
release=read(ROOT/'release/MarineOps-release-validation-1.2.5.json')
assert release['result']=='PASS' and not after['import_cycles'] and not after['core_qt_imports']
inventory=[]
for name in ('CargoTrack-1.2.4-Windows-x64.zip','MarineOps-1.2.5-Windows-x64.zip'):
    path=ROOT/'release'/name
    with zipfile.ZipFile(path) as archive:
        files=[f for f in archive.infolist() if not f.is_dir()]
        inventory.append({'file':name,'zip_bytes':path.stat().st_size,'files':len(files),
                          'uncompressed_bytes':sum(f.file_size for f in files)})
(OUT/'package-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
rows=[]
for key,label in (('dashboard_read','Dashboard 读取'),('crew_edit_and_saved_sync','人员修改并同步当前计划')):
    first,last=before[key],after[key]
    rows.append(f"| {label} | {first['seconds']:.4f} s | {last['seconds']:.4f} s | "
                f"{first['seconds']/last['seconds']:.1f} 倍 | "
                f"{first['python_peak_bytes']/1048576:.2f} → {last['python_peak_bytes']/1048576:.2f} MiB |")
package_rows='\n'.join(f"| {p['file']} | {p['zip_bytes']/1048576:.2f} MiB | {p['files']} | "
                         f"{p['uncompressed_bytes']/1048576:.2f} MiB |" for p in inventory)
text=f'''# MarineOps 1.2.5 软件架构与数据逻辑审核

日期：2026-10-28。状态：已修复、已验收，安装版和便携版均使用已定稿 Logo。

## 结论与边界

当前单用户离线 Windows 软件采用原生 Qt、业务服务与 SQLite 的结构适合现有需求。没有引入服务器、ORM、Web 前端或新的运行依赖。审核修复了可测量的重复处理和数据一致性问题；没有以大规模重写界面来增加本次回归范围。不能把“对所有未来规模均最优”作为可验证结论；本报告给出实际覆盖、测量与保留的维护风险。

审核覆盖全部 {after['source_modules']} 个源模块的导入关系与体积，以及启动/导航/配置、Cargo 状态与审计、Personnel 导入与人员链、计划生成/自动规划/快照、Dashboard、备份恢复/迁移、Excel 导出和发布流程。代码路径审阅与回归相结合，不等同于逐行形式化证明或穷尽全部组合。

## 架构与依赖

```mermaid
flowchart TD
    UI[Qt 工作区与共享品牌/主题] --> CW[Cargo 串行 Qt worker]
    UI --> PW[Personnel 单线程 executor]
    CW --> CS[Cargo 业务服务 / 仓储]
    PW --> PS[Personnel 业务服务]
    CS --> CD[(Cargo SQLite)]
    PS --> PD[(Personnel SQLite)]
    PS --> PL[计划生成 / 自动规划 / 独立结果校验]
    DB[Dashboard 只读投影] --> CD
    DB --> PD
    PS --> RO[Cargo 只读来源快照]
    RO --> CD
```

- 静态相对导入图无环；{len(after['core_modules_checked'])} 个业务、存储与数据投影模块无直接 Qt 导入。route_layout 属于 Qt 布局层，不属于业务核心。
- SQLite 连接由其工作线程拥有；Dashboard 使用 mode=ro 和 query_only。Cargo/Personnel 两库保持隔离，人员更改与受影响的计划新版本在 Personnel 的同一个事务内完成。
- Cargo 命令保持版本检查、幂等收据、不可变审计。计划族使用单调版本号；历史快照不可变。保留旧持久化名称是升级协议，不是重复实现。
- 依赖仍为 PySide6 6.8.3、openpyxl 3.1.5、tzdata 2026.4；使用已实际通过 Windows 启动验证的固定 Qt 运行时。

## 本次发现与修复

| 问题 | 处理及结果 |
|---|---|
| 每次人员写入前后读取整库版本，重命名等操作也扫描人员 | 连接级临时触发器仅记录受影响名单；事务提交前对这些名单校验并同步。修改 payload 而未递增版本仍可发现；失败回滚不污染下一事务。 |
| Dashboard 与历史选择界面解码所有历史完整计划 | 统一 plan_store：SQL 查询摘要，选择时只解码一个快照；写入同步只解码受影响计划族的当前版本。 |
| 历史版本逐条重复 resolve 同一个来源路径 | 每次读取缓存每个不同来源路径的解析结果。 |
| 名单、历史查询缺少对应索引 | 增加 passengers_plan、personnel_history_task、berth_created 可选索引；不提高备份必需 schema，旧备份恢复后重建。 |
| 人员导入逐行线性匹配现有名单 | 按 ID 和规范化姓名建立一次查找表，保留重复名及显式替换规则。 |
| 编辑器逐人/逐站复制整个路线，校验器逐项查找任务 | 一次构建复用一份路线快照与 ID 映射；验证器预建任务索引。 |
| 排除人员仍可能添加目的船停靠 | 只根据实际纳入或需重新匹配的人员补齐路线，保留明确排除与当前站选择。 |
| Cargo 意外异常只依赖 UI worker 回滚 | 业务命令边界统一回滚并重新抛出，直接调用也不会遗留未提交写入。 |
| Draft 可写入打开时无法读取的畸形快照 | 写入和备份校验共用结构规则，先校验结构再校验运输合同，拒绝无效快照。 |
| 系统时间回拨可能使自动 Dashboard 选择旧版本 | 每个计划族先按版本号取当前快照，历史选择仍完整保留。 |
| 多处品牌资源及不再使用的导入 | 统一 brand 常量、Logo 渲染；移除 23 处无效导入；发布包只包含定稿 PNG/ICO，不含旧 Logo 或设计素材目录。 |

## 业务逻辑复核

- Sign-on 在实际港口接人后送达；Sign-off 在回港前接齐；直接出港、中途回港、同船多次停靠保留真实访问顺序与身份。
- Crew change information 的姓名、职位、From、To、新增、移除和导入自动更新草稿及已保存 Final 的当前版本；旧快照仍是历史。无效分配保留为复核问题，不能静默发布。
- Dashboard 的 Boarding / Leaving 以当前站船舶为准，分别是加入 / 离开；重复船舶访问存在歧义时要求明确选择访问。来源发生变化或恢复换库时拒绝旧结果。
- 人员链保持人员身份、前段及先送达后再次接人的约束；排除前段不能单独规划后段。Cargo 物理货物身份、后续段、作废审计保持独立。
- Auto plan 仅在足够容量、无时间窗等展示模型下证明最少靠船，受限搜索不宣称最优；名单更新使旧证明失效，需重新计算。独立校验与求解器保留分离，是结果可信度要求。
- 备份恢复仍有完整候选校验、安全副本、故障回滚和恢复阻断标记；轻量写入校验没有替代完整打开/备份校验。Excel 原始字段、受保护缩写、用户拼写选择及打印逻辑维持原约定。

## 性能与体积

相同本地隔离虚构数据：501 个含长备注的保存版本；perf_counter 加 tracemalloc。数据为本机单次基准，Python 峰值不含 Qt/C++ 或操作系统全部内存，不能当作任意用户数据的速度保证。原始证据 before.json / after.json，可用 tools/audit_marineops_architecture.py 重现。

| 操作 | 修复前 | 修复后 | 本次速度比 | Python 峰值 |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

审核前 {before['source_modules']} 模块 / {before['source_lines']} 行，审核后 {after['source_modules']} 模块 / {after['source_lines']} 行；新增的是共享品牌与快照存储边界，约 {(after['source_lines']/before['source_lines']-1)*100:.1f}% 行数增长换取重复路径合并。没有新增运行依赖。历史版本随着真实编辑增长是审计数据，不是软件代码膨胀。

| 便携包 | ZIP 大小 | 文件数 | 解压大小 |
|---|---:|---:|---:|
{package_rows}

体积比较包含两个版本实际全部发布内容，并非只比较应用 Python 代码。包内无测试数据、SQLite 库、审核输出、设计素材或仓库历史；Qt/Python 原生运行时占据主要固定成本。没有为了缩小数字而删除必要平台插件或升级兼容逻辑。

## 验证证据

- 全量 {release['full_regression_tests']} 项通过；最后新增系统时间回拨修复后，相关架构及 Dashboard {release['final_architecture_dashboard_regression_tests']} 项再次通过，包含新增回归用例。日志为 artifacts/validation-1.2.5/full-tests-final.log 与 architecture-dashboard-final.log。
- Windows 原生功能链：真实港口顺序 → 修改 From/To 无需 Generate → 新历史版本 → Excel → Dashboard 人数正确；Cargo 哈希不变。三个 About 实际点击验证。
- 三个工作区 × Light/Dark × 1366/1000 宽度共 12 张最终截图；另检 About 两种主题。窄 Cargo 页操作收进 More，导航文字无裁切。此项属于原生 UI 检查，不是图片设计稿。
- 安装和便携实际启动/关闭；1.2.4 升级、旧目录和快捷方式迁移、旧版/新版单实例兼容通过。Personnel 首次增加可选索引会改变文件字节，因此核对所有业务表行；两库业务数据不变，Cargo 文件哈希也不变。
- 发布 ZIP 完整性、嵌入安装载荷一致性、定稿 PNG/ICO 字节一致、固定 Qt DLL 一致，以及 {len(release['compiled_modules_match_source'])} 个打包模块与当前源代码编译结果一致。未使用的 pyi_rth_dll_dirs 历史辅助文件不在活动依赖图或发布包中。
- 所有写入、恢复故障与安装测试使用隔离虚构数据；本次不迁移或清理用户历史数据。

## 保留的维护风险与适用范围

personnel_ui、ui、personnel_service、service 仍是相对较大的模块。已有明确的核心/线程/存储边界，但编辑器与表单还可在后续对应功能变更时按职责拆分；本次不为减少单文件行数引入重复 facade、框架或大规模搬移。PersonnelGateway 的少量同步只读调用仍可能在极大名单或慢盘上等待，需真实延迟证据后再改异步协议。保存历史的摘要查询仍需扫描相关历史 payload 中的元数据；已经避免 Python 全量解码，若达到数万历史版本，应再测量并考虑有版本迁移的独立元数据表，而不是现在增加冗余持久化来源。

自动规划最优性仅指已展示模型下的证明，现实容量、天气与时间窗约束尚不在该证明模型内。

正式安装包：release/MarineOps-Setup-1.2.5.exe；便携包：release/MarineOps-1.2.5-Windows-x64.zip。精确哈希、原生验证与编译一致性见 release/MarineOps-release-validation-1.2.5.json。
'''
(OUT/'软件架构与数据逻辑审核.md').write_text(text,encoding='utf-8')
print(json.dumps({'report':str(OUT/'软件架构与数据逻辑审核.md'),'inventory':inventory},ensure_ascii=False,indent=2))
