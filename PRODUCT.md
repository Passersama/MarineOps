# MarineOps

## 2026-10-29：黑灰 UI 适配（1.2.8）

共享左侧导航包含 Dashboard、Cargo、Personnel；Voyages 从 Dashboard 进入。Settings 菜单包含 Preferences、Personnel and plan settings、Fleet、About。Cargo 航次路线改为横向换行并支持滚动和按水平落点拖动排序；Dashboard 汇总去除圆环并保持计划人数语义。Personnel 窄窗口缩短列标题并为完整单元格提供提示。旧数据、计划快照及已保存外观选择不变。旧的 1.2.7 顶栏描述属于历史记录。

## 2026-10-28：顶栏一致性与打包清理（1.2.7）

Cargo 与 Personnel 的 About 与 Dashboard 一样位于顶栏最右侧，窄窗口保留可见入口。安装包与便携包移除已由内置 Help 覆盖的 AUTO-PLANNING.txt、TEXT-CASING.txt、CREW-SYNC.txt 历史版本说明；保留当前 README、Help、字体许可与所需运行库。内部 Cargo Track 存储和单实例身份继续兼容升级。

## 2026-10-28：Dashboard 人员独立校验（1.2.6）

Final 计划保存独立的人员来源指纹，货物 Pick up / Deliver 等执行状态变化不再隐藏当前站人员。旧快照通过完整、连续的命令收据确认期间只有货物或当前站选择变化后可兼容读取，不改写历史。航次、路线、船舶、相关设置、数据库身份或恢复代次改变仍需复核。人员修改同步多个保存计划时按原有先后顺序写新版本，自动 Dashboard 保持跟随最近保存的计划族。Dashboard 的 About 位于右侧 Settings 后面，复核说明位于人数上方。

## 2026-10-28：当前行为与架构（1.2.5，优先于以下历史记录）

正式名称 MarineOps，使用已确认的蓝色／青色飘带 Logo。Dashboard、Cargo、Personnel、About 与 Windows 图标统一使用定稿素材；英文界面，说明与版本集中在 About。为保证升级，内部 Python 包、数据库路径、QSettings 和单实例身份继续兼容 Cargo Track。

Sign-on 必须在实际港口停靠接人后送至目的船；Sign-off 必须先从来源船接齐再回港。直接出港路线包含出发港，中途回港以独立港口站分隔前后的船舶访问，同船多次访问保留各自身份。名单的新增、修改、移除、导入自动更新草稿与受影响的 Final 计划，并保存新的当前版本，包含 From / To；旧版本保持不变。无效分配须复核；明确排除的人员不会自动添加目的船停靠。

Dashboard 是只读投影，自动模式选择每个计划族的当前版本（不依赖系统时间单调前进）；可以显式查看历史。当前站 Boarding 指加入该站船舶，Leaving 指离开；重复船舶访问存在歧义时要求选择真实计划访问。人员变化不能更改 Cargo 账本，Cargo 来源真正变化仍需检查路线。自动同步会使此前的最少靠船证明失效，需要重新 Auto plan 才能证明新最优解。

保留原生 Qt、业务服务、SQLite 两个独立库、串行连接所有权、不可变审计与计划快照的架构。人员变更与新快照同步在同一事务内提交，按受影响名单进行校验；全库和备份打开仍执行完整校验。新增索引属于可重建的查询优化，旧备份仍可恢复；临时变更追踪表／触发器仅属于连接，不写入备份。历史摘要不反序列化完整计划，只有选中和受影响的当前快照才解码。详见 `output/architecture-audit-1.2.5/软件架构与数据逻辑审核.md`。

## 2026-10-25：审核问题修复（1.2.3）

已移除的人员段按历史快照保留原身份与段号；活动链在写入事务提交前以及打开／备份时使用同一套一致性校验。重接前段不会改写已移除段或历史事件；已受旧问题影响且仅取消段历史引用过时的数据库可直接重新打开。

Link legs 增加可拖动和上下调整的顺序确认窗口，按起终点关系给出建议；确认的顺序决定关联，名单行序不再限制合法链路。活动链无效的更新会整体回滚。

长名单和备注导出采用续行／续页，每页保留站号、地点、表头和全局人员编号，不截断内容、不修改保存快照。Berthing Plan 的四个逻辑操作组保留，小名单仍为四行。A4 竖版使用固定 100% 缩放和可打印区域内的实际列宽，避免本机 Excel 缩放时 PDF 物理页面变大的问题。

Cargo 的九列以 A4 横版打印，长单元格提供 Cargo Print 续行视图；原始 Transfers 数据仍保留。Personnel 的 Transfer Details 保留 19 列电子数据，其直接打印范围为前八个业务列；新增 Transfer Print 横版打印视图包含人员、职位、起终点、备注和段号。证据见 `output/audit-fixes-1.2.3/更新与验证说明.md`。

## 2026-10-25：A4 竖版导出与后续接送段（1.2.2）

Berthing Plan 的 C 列由 102 调整为 60，行高按实际列宽、换行、英文单词和中英文内容量计算。默认 A4 竖版，宽度适配一页，高度自然分页；四操作行、合并栏、重复表头与历史快照保留。

后续人员段从港口或接驳船出发时，必须在前段送达后安排真实的再次靠泊接人，不再当作出发前已在船上。前段被排除时不能单独规划后段。Link legs 后，发生关联变化的记录重新计算靠泊分配，其他记录的分配和用户勾选保持原有状态。旧保存版本不会重写；重新生成、核对并保存新版本应用路线修复，重新导出应用打印设置。

复核与限制见 `output/excel-legs-20261025/更新与验证说明.md`；安装包和便携版使用独立 1.2.2 版本。

## 2026-10-21：倒班船名匹配与方向保留（1.2.1）

读取倒班人员时保留原始 Sign-on / Sign-off，不因另一端船名暂未匹配而显示成 Transfer。Fleet 解析先保留明确映射，再兼容船名中的空格、连字符，支持已确认的 BVC → BGP Victor、SPR → BGP Spirit、BGP INV → BGP Innovator 简写。自动匹配仅针对唯一的在用船舶，歧义或停用船舶仍需复核。

导入窗口的船名映射取实际 From / To 或 Vessel；修改映射后立即重新预览，确认导入保存同一份映射快照，不再要求额外点击 Apply mapping。现有倒班名单在读取时重新匹配，不改写原始人员记录、Cargo 数据或历史计划。保留船到船接送段的 Transfer 语义；原表明确的倒班记录不降级为此类型。

## 2026-10-21：倒班表缺省港口与分配（1.2.1）

倒班表 Sign-on 统一从 Settings 配置港口出发，船舶取 To，缺省时取 Vessel；Sign-off 统一送到港口，船舶取 From，缺省时取 Vessel。无需填写港口侧的 From / To。导入支持仅有 Sign-on / Position / To / Date 或 Sign-off / Position / From / Date 的表头。已导入记录若旧绑定丢失船舶端字段，可从保留的原始值在读取时重新匹配，不回写原始记录及历史版本；船舶侧缺失或无法识别、普通 Transfer 缺失端点仍需复核。

新建倒班计划有送回港口的人员时，缺省在末尾补一次港口到访；不修改 Cargo 航程。已有计划及手动调整的路线保持原顺序，港口仍可手动添加、移动和删除。旧名单无需重新导入，重新生成新计划即可使用默认分配。

## 2026-10-12：Dashboard 上下船名单合并（1.2.1）

Current stop personnel 在同一张表中显示 Boarding 和 Leaving 人员，列为 Name、Position、Movement，无需点击方向标签切换。保留两项总人数、保存计划和具体到访选择；长名单独立滚动，完整名单侧栏仍可筛选和搜索。

Cargo Track is a local Windows desktop tool for planning and recording vessel cargo transfers. The user already finds the Cargo module useful and requires its existing behavior and data to remain unchanged while Personnel is extended.

## Personnel user and task

The user imports a crew-change Excel list and produces a final berthing table. They need to see which passengers and materials belong to each vessel, adjust the new table's vessel order, and export Excel. They directly edit personnel in the main-page draft, with material content retained from Cargo. They do not want personnel execution statuses or pickup/drop operation buttons.

## Current scope authority

- Personnel is a separate page and database.
- Import dual Sign-on / Sign-off lists or a flat crew table, retain useful name, position, vessel, date and comment fields, and review vessel matches.
- Sign-on becomes Drop passengers at the target vessel. Sign-off becomes Pick up passengers at the source vessel and Drop passengers at the final configured Port.
- Begin with the selected Cargo Voyage. Automatically add matched crew vessels missing from that Voyage and allow independent additions, removals and order changes in the new plan. These changes never write to Cargo.
- Repeated visits remain distinct. Default to the first feasible visit and allow the user to change the assignment.
- Each vessel and the final Port has four groups: Drop passengers, Pick up passengers, Drop Materials from a source vessel, Pick up Materials to a destination vessel. Count material records and show multiple materials inline.
- Omit the departure port. Save immutable plan versions and export an Excel final table with a details sheet.
- Loading historical Complete / Remaining versions rebuilds a current Final draft while retaining the original. Edit plan works on the displayed draft/version and opens the main-page Edit draft directly tab, preserving chosen exclusions and valid exact repeated-visit assignments; selected materials with route problems remain reviewable.
- Draft editing is personnel-only: double-click Name or Position for snapshot-local changes, use passenger inclusion and assignment controls, or use Add crew entry / Edit selected crew / Remove from plan. Explicit crew forms update the current crew list; direct cell edits affect only the draft and saved snapshot. Material selection belongs to initial generation and remains read-only during inline editing. Save and Export collect current edits without requiring Preview changes; saved versions remain immutable.
- Distinguish Crew change date from Berthing plan date. The latter controls the Excel heading and proposed file name; saved snapshot dates stay fixed until a new draft is created.
- Keep data local. Imported identity numbers, company, laptop and Mark fields are ignored.

## Product and visual constraints

Keep the incumbent native Qt Windows identity: Inter, restrained blue primary actions, light gray and white work areas, existing dark appearance and font settings. Optimize the Personnel surface for clear vessel matching, readable tables and direct import-to-export operation. Cargo's established workflow is outside this change.

Latest user instructions override the V0.2 historical scheme. See Personnel Transfer Track_设计方案.md V0.3 and Personnel Transfer Track_实现与使用说明.md 1.1.2.

## Personnel defaults, 1.1.3

Use title case for imported names and positions, preserving original fields. Automatically select rows with feasible stop assignments in a new plan; select newly feasible rows after route edits, retaining manual and saved exclusions. Final planning allows collection-only Waiting materials when the source is called and the destination is absent. Show their actual destination in Pick up Materials; do not append a destination stop or fabricate a Drop. Cargo remains unchanged.

## Shared port and Cargo view, 1.1.4

The user's 2026-10-07 instructions supersede separate port naming: On Shore is xx port. Keep the existing SHORE location ID and one Cargo-owned port_name setting. Both pages' Settings may submit the shared port rename through Cargo's application command; Personnel otherwise continues to read Cargo. Live labels and new plans follow the setting; saved snapshots retain their original port names. Accept legacy shore labels in imports. Cargo forms must include the port alongside Fleet vessels.

NO is a display sequence starting at 1 after every filter. Pages continue within that filtered sequence. Stable Cargo IDs and internal transfer IDs do not change when filtering, sorting or refreshing. Exports number the filtered scope from 1 and retain the chosen sort. Cargo offers Refresh and F5, retaining the user's filters while returning to the first page.


## Audit repairs and shared coordination, 1.1.5 (retained business rules)

These rules supersede previous implementation notes where they differ. Retain two independent local databases, immutable saved plans, stable Cargo IDs and confirmed cargo status semantics. The shared coordinator protects live file paths (including unopened modules), records recovery generations and invalidates stale editors/results. Backups and all exports reject live database destinations before writing and again before replacement. A registered original database remains protected after storage migration.

Personnel saves, import commits, settings, backups, restore and relocation use a dedicated serial executor; its SQLite connection is created, used and closed in that thread. Cargo shared settings save in one application transaction. Appearance and storage migration are separate subsequent steps; migration failure retains the original file.

A draft binds Cargo ledger identity/recovery generation, selected Voyage and relevant source dependencies, plus personnel module identity/recovery generation and the complete crew-list scope. Restore, storage changes and list switching invalidate old editors. Publication rejects changed roster scope, not just changes to selected people. Unrelated historical transfers do not invalidate a draft.

Plan input retains all active crew entries and distinguishes included, user-excluded and automatically unavailable records. Unavailable records have named reasons in Review and block publication. Remove from plan is an explicit exclusion even for an already unchecked row. Exclusions persist through editing and are printed in preview and Excel. A removed or reordered visit never silently substitutes another stop for a previous assignment. Inline material assignments obey the same rule.

Draft name/position edits store a base value per field. Explicitly changing that field in the crew list supersedes its draft override; unrelated route edits preserve other overrides. Old saved snapshots stay unchanged.

Import idempotency covers file hash, sheet, mapping/parser, target list and operation. Different worksheets/mappings can be appended with explicit duplicate review; repeat submission is rejected by a database key. Complete replacement remains repeatable after its roster scope changes. Import scans a bounded header preview and streams required columns, with 20,000-row/200-column limits and chunked file hashing.

Personnel restore validates supported tables, columns, immutable triggers, constraints, settings and JSON types before replacing data. Legacy 1.1.4 backups migrate the import-key table without rewriting business history. Restore keeps a validated safety copy; failed rollback blocks further writes and identifies the recovery file.

Current evidence: output/audit-fixes-20261007/审核修复与更新说明.md and release/release_validation-1.1.5.json. Current UI commands: tools/verify_crew_final_runtime.py --plan-load-regression and tools/verify_audit_fixes_runtime.py. tools/verify_personnel_runtime.py is a compatibility alias for the current crew workflow.

## Frontend workflow, 1.1.6 (retained)

The business rules above continue to apply. Save draft persists status Draft and permits review issues. Publish persists a new immutable Published version after current-source validation. Formal export is enabled for a reviewed editable draft or a Published snapshot; saved Draft snapshots first return to editing. The file picker precedes publication; cancelling it does not persist a version.

Unsaved edits are protected on list switching, regeneration, version loading and window close. Save failures retain the editable draft. When sources invalidate a dirty editor, a separate JSON recovery copy preserves route, assignments, selections and field edits; reuse requires current-source regeneration and normal publishing checks.

Personnel tables use QAbstractTableModel / QSortFilterProxyModel, 200 ms debounced search and on-demand assignment delegates. Filtered NO starts at 1; UUID selection survives refresh. Native checkbox and assignment cells expose row context. Ctrl+Z / Ctrl+Shift+Z apply to local name/position cell edits; crew-list forms retain their distinct business effect.

Reference viewport targets are at least 5 complete editor rows at 1000×700 and 6 at 1366×768. Keep the route and manual current-stop controls visible. History and infrequent commands are compacted, with one primary task action per workspace. Shared light/dark semantic tokens drive QSS, QPalette and status delegates. Writes provide progress and protect conflicting controls. IANA time-zone IDs remain visible alongside Windows descriptions.

Current update record: output/frontend-update-20261007/前端改进与验证说明.md. Release evidence: release/release_validation-1.1.6.json. Earlier evidence describes its original version only.

## Full voyage overview, 1.1.7 (current)

The user's full-plan visibility requirement takes priority over the former single-row route density. Show every voyage visit in reading order, wrapping to new rows as the window narrows. Do not place the route in a horizontal scroll area or collapse visits behind an expansion control. Long ship names wrap within their stop button. Keep stable stop identities, manual current-stop selection, repeated visits and each stop's move/remove menu. The route grows vertically before the Cargo table receives the remaining space.

Current evidence: output/route-overview-20261007/全航程展开与验证说明.md and release/release_validation-1.1.7.json. Native 13-visit and 24-visit fixtures each passed 12 width/font/theme configurations; the smallest tested window is 1000×700. These measured configurations do not assert unlimited visits fit a finite screen.


## 2026-10-11 更新：1.1.8 人员分段接送

本节替代早期关于 Final 计划自动追加港口的规则。Final 路线中的港口是可选停靠点，可添加、移动、删除，保存版本不被回溯改写。

人员每一段保持独立任务 ID；通过 Next leg 或显式 Link legs 关联 person_id、leg_index、previous_task_id，按段验证路线连续性。后段接人必须发生在前段送达后的再次靠泊，不能沿用同一次到访。同名人员不自动合并。编辑路线后失效的已选到访仍保留并提示复核，禁止静默替换。

From 匹配 Settings 的 Plan transfer vessel 时，人员仅按 To 分配 Drop；空 From 不推断为传送船。物料原规则不变。配置变动使草稿来源失效，需要重新核对。

Excel 主表为四列，每停靠点四行，人数及编号列表写在同一个操作单元格中，橙色表头、黑色边框、纵向合并序号／目的船／备注。另保留 Transfer Details 明细和人员段关联字段。超出 Excel 单元格／行高能力的内容明确报错，不截断，不覆盖已有文件。

更新后的 maritime-operations-logo-v3-dark.png 原稿作为界面标志，Windows 图标使用同一稿件。真实用户数据库与已安装程序不在测试中替换。


## 2026-10-11：1.1.9 页面管理与本轮审核

两个工作区使用同一个 WorkspaceNavigation：Logo、Cargo Track 标题、Cargo／Personnel 按钮的顺序、尺寸和选中样式一致。人员页切回 Cargo 经过未保存草稿检查，取消保留编辑，放弃清除未保存草稿，保存完成后继续切换。人员页提供 F1 帮助及 F5 刷新。

Crew list 通过 Rename 改名，只改列表名称，保留列表 ID、人员及段关联、日期和历史快照；比较旧名称以拒绝并发覆盖，并留下不可改写的管理记录。

当前靠泊按钮再次点击取消 Current，只清空当前站选择，不删除到访、不改变物料状态。检查 expected_stop_id 以阻止过期清除请求取消另一个当前站。

Version history 提供 Remove selected 和 Clear history，清理可见列表，历史快照仍不可修改／删除。列表清理状态及管理记录包含在人员备份中；原版本序号继续递增。新增管理表以兼容旧数据库及旧备份，不改变已有业务行。

数据库打开失败时关闭 PersonnelGateway executor，避免重复打开错误数据库积累后台线程。

## 2026-10-12：1.2.0 用户已确定两页 UI

最新 UI 指令优先于早期 Cargo 页面不变和四组屏幕预览的说明；货物业务规则及两库权限边界继续保持。Cargo 使用靠船侧栏和表格上方操作，合并 Status 筛选，按需显示 Completed Date 和分页。Personnel 只显示人员信息，分开 Pick up / Drop 到访，提供人员站点预览及版本化 Comments。初次生成中的 Cargo 关联保留，四组 Excel 格式不变；页面和生成对话框不显示货物行。

重复到访继续使用独立身份；人物关联仍需明确操作。长路线自动分列，测试中的 24 站在 1000×700 可完整显示；不宣称任意长度路线都可放进有限屏幕。用户现有主题和字号设置保留。最终实施与原生验收记录见 `design-qa.md`。

## 2026-10-12：1.2.1 Dashboard 与软件审核

在现有 1.2.0 原生软件中增加 Dashboard，默认启动进入此页，保留 Cargo／Personnel 业务页及品牌。三页共享 Dashboard／Cargo／Personnel 导航；Personnel 未保存草稿离开时继续执行 Save draft／Discard／Cancel。

当前站仍由用户手动选择，重复到访按 stop ID 区分。Dashboard 的 Boarding／Leaving 是加入／离开当前站船舶，对应保存计划中的 Drop passengers／Pick up passengers。显示日期、名单及 Draft／Published 版本，可选择保存版本；只显示来源、名单范围与当前到访匹配的计划。来源失效、计划不存在或未选择站点时清空人数及名单并说明下一步。Dashboard 只读两库，未创建 Personnel 时不自动建库。

Cargo 的 All transfers 标签数字仅计未删除的 Waiting 和 On Board，不计 Done，历史记录仍通过 Status 筛选查看。Cargo ledger summary 只统计本航程开始时未完成的物料和此后新增的物料，按各段当前实际状态分类；利用不可变操作记录重建航程开始时的待办，同秒事件按记录 ID 区分，旧航程已完成记录不混入。无当前航程时三项为 0。当前站物料动作保留原 Cargo 业务定义，只在明示的前 200 条预览中截取，完整结果从 Cargo 查看。

Personnel plan progress 与物料饼图并排，统计当前航程所选有效保存计划中的人次：每个人员转运段计一次，Pick up 与 Drop 不重复计次，同一人多段分别计次。送达计划到访严格早于当前到访才计 Completed，当前及后续送达、未分配送达的已选段均为 Pending。随手动当前站、保存计划版本和人员计划具体到访变化重新计算；退回早站会相应回退进度。这是用户确认的计划进度，不写实际接送状态。未选择站点、无法匹配具体到访或来源失效时显示不可用。

Cargo 左侧靠船列表支持拖动船名到目标站的上半部或下半部，分别插入目标之前或之后；显示插入线，保留独立 stop ID、重复到访及当前站身份。菜单移动和移除继续可用。旧界面或另一航程的拖拽内容不能修改当前路线。

### 1.2.1 增补：自动靠船规划与独立到访匹配

Personnel 的 Auto plan 按当前未显式排除的人员段和用户选定的物料，规划全部接取与送达。一次实际船舶靠泊计一次，同船重复两次计两次；先最少船舶靠泊、再最少港口停靠。首版为单传送船、运力足够、无时间窗的全程计划。港口来源主段作为出发前计划装载，关联后段不能沿用该条件。精确 A* 搜索证明最优，限时或状态限制结果不能称最少或无解。现有手动添加、删除、拖拽不被替换，手动新停靠默认保留；具体到访和接送分配可保留。采用前预览，采用后在继续编辑前可完整撤销。严格传送合同继续约束手动修改、服务发布和导出，源变化使旧结果失效。两库权限和旧版本兼容规则保持。

Dashboard 以到访身份优先匹配人员。Personnel 使用独立 ID 时，同船只有一次计划到访可唯一匹配；同船多次且无精确 ID 匹配时，要求选择具体计划到访。不得按船名合并多次上下船人数。该规则替代早期只接受 Cargo stop ID 的显示限制。

固定主面板人数、上下船标签及约 6 行内部滚动名单。View full list 打开侧栏，可按上下船筛选、姓名和职位搜索、排序；人数总计不随搜索变化。全路线按窗口换行，超出有限窗口高度时使用 Dashboard 页面纵向滚动。

两库路径独立：第一次显示 Dashboard 即固定原 Personnel 路径，之后单独迁移 Cargo 不改变 Personnel 路径。数据库健康报告执行真实结构、外键和业务完整性检查。所有审核与发布验收使用隔离虚构数据及旧版本数据副本，不替换用户现有数据。

## 2026-10-29：1.2.8 审查修复

Cargo 在替换数据库前持久化恢复记录；恢复／回滚中断后，跨进程重新启动仍须先恢复原账本，禁止静默创建空库。只有验证并重新打开有效账本后才移除恢复记录。

手工和自动计划发布、正式导出、Published 备份校验共用输出完整性检查。保留合法的初始在船、仅收取物资、显式排除、连续人员段，以及 Complete 修订中的历史接人动作和更正后的未来目的地。所有新发布均在工作线程重新验证当前来源。

Personnel 数据库异步打开，名单／设置／历史元数据以分离的只读内存模型提供界面显示，导入预览和选中版本按需异步读取。动作前的来源检查在串行后台线程执行；过期响应不覆盖新选择，旧快照不被改写。

当前包静态验证不依赖旧包或本地历史日志。升级验收使用显式上一版本和独立虚构数据，验证报告须绑定当前可执行文件哈希。源码／Windows 元数据／README 的当前版本统一为 1.2.8；历史发布说明归档至 CHANGELOG。
