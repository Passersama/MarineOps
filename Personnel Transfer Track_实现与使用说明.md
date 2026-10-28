# Personnel Transfer Track 与最终靠船表

版本：Cargo Track 1.1.6 · 2026-10-07

人员模块现在只管理倒班名单。操作流程为 **导入 Excel → 生成最终靠船表 → 导出 Excel**，无需进行人员接载、送达或状态操作。

## 安装和打开

关闭旧版软件，运行 `release/CargoTrack-Setup-1.1.3.exe`，选择现有安装位置升级。也可以完整解压 `release/CargoTrack-1.1.3-Windows-x64.zip`，运行其中的 `CargoTrack/CargoTrack.exe`，保留旁边的 `_internal` 文件夹。

在 Cargo 页顶部选择 **Personnel**。人员及靠船表使用独立数据库；Cargo 原有业务页面、货物状态和 Voyage 顺序保持原样。

## 导入倒班信息

1. 在 Cargo 中选择需要参考的 Voyage，然后进入 Personnel。
2. 点击 **Import Excel**，选择文件、工作表及导入方式。支持示例中的左右 Sign-off / Sign-on 名单，以及 Name / Position / From / To / Date 普通表。
3. 预览人员和船名对应关系。`CHA`、`INN`、`Niger` 等唯一缩写可对应完整 Fleet 船名；不唯一或未识别的名称需要在 Personnel **Settings** 中配置别名。
4. 确认导入。**New crew list** 建立新名单，**Append crew entries** 追加记录，**Replace selected crew list** 替换当前名单。替换时确认移除旧名单中未保留的记录；已保存的靠船表版本仍然保留。

Personnel 表显示姓名、职位、上下船方向、来源、目的地、日期和备注。可使用 **Add entry / Edit crew entry / Remove entry** 修正名单。人员页不显示 Waiting / On Board / Done，也没有人员 Pick up / Drop 执行按钮。

导入姓名和职位统一为每个单词首字母大写，其余字母小写，例如 `ALEX MORGAN` → `Alex Morgan`、`NAV QC` → `Nav Qc`。已有的导入记录在名单及新生成的靠船表中也采用此格式；原 Excel、原始字段记录、船名和备注保持原样。已保存的靠船表版本保留原快照，需要点击 **Edit plan** 生成新草稿后保存新版本。

生成新表时，有可用靠泊路径的人员和物料自动勾选。调整路线后，新获得可用路径的条目也会自动勾选；手动取消及已保存的排除选择继续保留。Waiting 物料的来源船在路线内、目的船不在路线内时，只生成来源船的 **Pick up Materials … to 目的船**，不要求补入目的船，也不生成本次送货动作。物料名称、路径和状态仍由 Cargo 管理；人员草稿中的物料保持只读。

原 Excel 中的离船日期和到船日期按各自列读取，不把左右同一行配成一组。护照、身份号码、公司、电脑和 Mark 列不导入。空缺或错误船名会显示待核对问题，避免人员静默漏出最终表。

## 生成最终靠船表

打开 **Berthing plan**，点击 **Generate final plan**：

- 所有当前倒班记录默认纳入。Sign-on 自动列入目标船的 **Drop passengers**；Sign-off 自动列入来源船的 **Pick up passengers**，并列入最后港口的 **Drop passengers**。
- 倒班日期用于展示和参考，不会因为与表头日期不同就排除人员。表头日期在 Berthing plan 页的 Berthing plan date 选择，仅影响最终表的表头和导出文件名。人员自己的 Crew change date 保留原值。
- 初始靠船顺序参考 Cargo 所选 Voyage。名单中已匹配但未包含的船自动补入新表；可用 **Add stop / Move up / Move down / Remove stop** 或拖动调整。修改只作用于新靠船表，不修改 Cargo Voyage。
- 同一船出现多次时，默认归入第一个可行靠泊点。右侧 **Stop assignment** 可选择具体靠泊次数。
- 勾选要加入的 Cargo 物资记录，核对来源、目的地和靠泊分配。物资状态仍按 Cargo 数据读取；人员名单不受执行状态限制。

点击 **Preview final plan** 查看结果。未解决的船名或不可行的转运路线会显示问题，需要先修正再保存和导出。

每条船和最后的 Port 均含四项：

1. **Drop xx passengers**：每位 `Name(Position)`。
2. **Pick up xx passengers**：每位 `Name(Position)`。
3. **Drop xx Materials**：`Material Name from Vessel Name`，多条物资同一行显示。
4. **Pick up xx Materials**：`Material Name to Vessel Name`，多条物资同一行显示。

物资数量按选中的物资记录条数统计。末尾港口名称在 Personnel **Settings → Port name** 设置。出发港口不列入计划。

## 保存、修改和导出

**Save plan version** 保存当前最终表快照。**Load version** 加载版本。旧 Complete / Remaining 格式会按当前名单和物资重新生成 Final 草稿，消除旧的匹配和日期问题，原版本保留。Final 版本按保存内容加载。

**草稿直接编辑**：生成或加载旧版草稿后，页面直接显示 Edit draft directly。双击人员姓名或职位即可修改，不需要再打开 Edit plan 窗口。**Add crew entry** 添加人员，**Edit selected crew** 修改人员其他信息，**Remove from plan** 从本次表移除选中人员；移除只取消本表的勾选，原名单保留。草稿内仅允许修改人员，物资从 Cargo 读取，不提供物资内容编辑入口。新建或修改人员会保存到当前人员名单；取消靠船表编辑不会撤销这些已保存的名单记录。

物资在首次生成时选择 Cargo 记录；进入草稿后保留该选择。靠泊点仍可补入、移除和调序。重新打开时保留未勾选条目和指定的重复靠泊次数。保存创建新版本，旧版本保持原内容。

Review 按人员或物资记录合并，点击 Plan preview 内的问题后显示所有原因与 From / To；同名但不同记录不会合并为一个人。缺少船舶时提示需要补入的船名。未能找到旧人员记录时会说明原因并提示使用当前名单重新编辑。

已保存版本的靠船表日期不可直接修改；点击 Edit plan 后立即打开页面内草稿，在其中调整 Berthing plan date，再保存新版本。保存及导出会直接读取草稿当前改动，无需先点击 Preview changes。在草稿单元格修改的姓名和职位只作用于本表及其新版本，不覆盖原名单。

点击 **Export Excel** 选择保存位置。未保存且没有问题的预览会先保存为一个版本，再导出两个工作表：**Berthing Plan** 为最终靠船表，**Transfer Details** 为明细。表内不包含人员执行状态。

## 旧版名单升级

1.1.0 中已导入的记录会在新人员页重新按当前 Fleet 名称和别名匹配，不需要先进行接送操作。之前因船名缩写未识别的人员可以直接进入新最终表。

如果旧版把“下船时间 / Date of departure”读成空日期，用 **Import Excel → Replace selected crew list** 重新导入原文件即可恢复日期。缺少该旧日期也不会阻止人员进入最终表。真实用户数据库和原始 Excel 未在开发验证中修改。

Personnel Settings 提供独立备份、恢复和数据目录设置。恢复人员数据时使用人员备份，不要选择 Cargo 备份。

## 验证范围

68 项自动检查通过，包括原 Cargo 的 26 项和人员模块的 42 项。可见原生窗口验证覆盖导入、缩写匹配、双侧日期、去除人员状态操作、自动补船、顺序按钮、最终分组、双工作表导出及 Cargo 数据一致性。

1.1.2 安装包和完整解压的便携版通过可见窗口、安装器生成的快捷方式、重复启动、升级数据保留和 Cargo 数据一致性验证；具体结果见 `release/release_validation-1.1.2.json`。Excel 验证使用本机只读打开和 PDF 打印，不修改导出文件。

本轮快捷方式验证使用工作区测试桌面，未创建真实桌面快捷方式。未重做原 Cargo 的全部 DPI、辅助阅读器和物理多屏测试。证据位于 `artifacts/personnel-load-fix/` 与 `artifacts/validation-1.1.2/`。


## 2026-10-07：统一港口与货物列表

On Shore 与 xx port 是同一个港口地点。Cargo 和 Personnel 的 Settings → Port name 共用一个设置，默认名称为 xx port；修改后，货物地点、人员来源／目的地和新生成的靠船表同步使用该名称。港口仍使用原地点 ID，旧版 Excel 的 On Shore／xxPort 可以正常匹配；已保存的历史计划保留原港口名称。人员独立备份不再决定共用港口名称。

Cargo 的 NO 是当前筛选结果的显示序号，从 1 开始，翻页继续编号；Cargo ID 保持稳定且连续。CSV／Excel 导出的当前筛选范围同样从 1 编号，并保留当前排序。货物页的 Refresh 按钮和 F5 会保留筛选条件并返回第一页。

本次审核发现的其他问题及优先级见 output/audit-20261007/软件审核报告.md；1.1.4 仅包含上述用户指定调整及港口选择修复。


## 1.1.5 审核修复后的当前实现（2026-10-07）

当前业务规则以 PRODUCT.md 的 1.1.5 章节为准。原有两个数据库、稳定 Cargo ID、筛选 NO、Refresh / F5、共享港口和历史计划快照保留。

新增跨模块文件保护；备份及导出不能覆盖已登记的货物或人员数据库，包括另一模块没有打开的情形。人员备份在恢复前核对应用结构和字段类型；恢复保留安全副本，回退失败则阻止继续写入。

恢复、迁移或切换名单后销毁旧编辑器。计划绑定数据库永久身份、恢复代次和完整名单范围，不能从旧缓存发布漏人的计划。来源签名只核对所选 Voyage、相关地点、所选运输段和共享设置；无关历史货物修改不阻断当前计划。

已安排、用户排除、系统无法安排分别记录。系统无法安排的人员列出姓名及原因，正式保存前必须修复或明确从本计划排除；“Remove from plan”可对已未勾选的条目作明确排除。预览和 Excel 都列出排除原因。指定站点失效时保留核对提示，不自动换到另一站；材料也遵守相同规则。

显式修改人员字段时取代该字段旧草稿覆盖，其他草稿字段可继续保留。一个文件的不同工作表或列映射可以追加；同一导入提交由数据库键防重复，完整替换在名单变化后可重做。Excel 按行读取所需列，文件哈希分块计算。

人员写入、备份及恢复由专用串行后台执行器完成，数据库连接不跨线程使用。货物业务设置在同一事务内保存；外观和存储迁移作为后续操作。

当前审核修复说明：output/audit-fixes-20261007/审核修复与更新说明.md；当前发行证据：release/release_validation-1.1.5.json。旧报告和发行证据保留为历史记录，不能用旧版本的测试范围替代本次验证。

## 1.1.6 前端更新后的操作

1. Import Excel 导入人员，在 Crew change information 核对；筛选后的 NO 从 1 开始。
2. Generate final plan 生成草稿，左侧调整独立靠泊顺序，右侧选择人员和停靠分配。双击或按 F2 编辑姓名／职位；分配单元格按 F2 打开选项。Add crew / Edit crew 更新主名单；直接改单元格只影响当前草稿。
3. Save draft 保存未完成版本，允许保留核对问题。Save plan version 通过检查后保存正式版本。历史版本在 Version history 中选择和加载。
4. Export Excel 先选择文件；取消不会新增版本。如果首次导出已保存正式版本但 Excel 写入失败，该版本仍保留，可重新导出。
5. 有修改时切换名单、重新生成、加载版本或关闭窗口，会提供 Save draft / Discard / Cancel。姓名／职位的单元格修改可用 Ctrl+Z 撤销、Ctrl+Shift+Z 重做。
6. 数据恢复或来源变化后，未发布修改保存在人员数据库旁的 draft-recovery 文件夹。Recover draft 按当前来源重新生成，需要再次核对，不能直接发布失效草稿。

窗口在写入期间显示进度并暂时禁止冲突操作，内容保持可读。设置时区始终显示 IANA ID，港口仍在设置中统一管理。更新说明与发行证据见 output/frontend-update-20261007/前端改进与验证说明.md 和 release/release_validation-1.1.6.json。


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
