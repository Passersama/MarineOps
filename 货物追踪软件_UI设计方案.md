# 货物追踪软件 UI 设计方案

日期：2026-09-30；版本 R2，架构适配与界面优化稿。  
依据：[软件方案](./货物追踪软件方案.md)，尤其第 9–11 节；[审阅与验证](./货物追踪软件_技术审阅.md)。

本稿是 Cargo Track 的目标 UI 设计稿，示例数据均为虚构，界面首版沿用原表英文；中文说明不改变字段含义。它与 1.0.0 可运行界面并非逐控件一致：宽屏并列详情、快捷键和更持久的操作反馈仍是后续目标，真实控件状态以[运行截图](./CargoTrack-UI-runtime.png)和源码为准。旧稿保存在 `revisions/20260930-before/`。实现范围和验证证据见[软件方案](./货物追踪软件方案.md)与[交付说明](./README.md)。

## 1. 使用目标与本次优化

用户操作一艘转运船，沿航程访问 Fleet 船舶。打开软件后需要判断：当前在哪次停靠、现在能收取或交付哪些货、自己船上还剩什么。主界面围绕这条任务路径组织，不使用营销页面或大面积统计卡片。

本次按已安装 **Impeccable** 的 Operate 原生工具界面原则优化：保留浅色桌面作业台，减少重复列表和卡片，统一状态文字与颜色，明确保存、冲突、恢复维护和空航程反馈。实际尝试 context 与 detector，但本机缺少 Impeccable 引擎，自动检查不可用；因此用原生 SVG 渲染、人工视觉检查和架构契约核对补充，不能宣称通过自动检测。design-taste-frontend 明确排除密集数据表和工具界面，本任务不套用它的营销页面规则。

主要调整：

- 航程列表常驻主页面，独立站点按 ID 选择；重复船舶标明序号，可添加、移除，并通过站点菜单前后移动。历史航次只读，可复制为新的工作航次。
- 当前站作业区压缩为摘要、操作入口和最多两条预览，把主要空间留给表格。
- `All transfers / Current stop / On my vessel` 共用一个表格，避免上方任务卡片与下方台账大面积重复。
- 本段状态与整件货物的最后确认位置分别展示，旧历史段不冒充当前位置。
- 1366 宽默认关闭详情，1920 宽可并列查看；表格不会为了抽屉而挤成窄列。

## 2. 视觉与组件规范

视觉方向为安静、便于长时间核对的 Windows 船队作业台。主色海军蓝，紫色只表达当前站关联；Waiting/On Board/Done 分别使用琥珀/蓝/绿。完成记录不涂整行红色。

| Token | 值/应用 |
| --- | --- |
| background / surface | `#F4F6FA` / `#FFFFFF` |
| text / secondary | `#17243A` / `#59677D`；重要说明不用浅灰 |
| primary | `#173A63`，主要保存、新增和任务动作 |
| current-stop | `#6F4CC3`，当前站序号、关联标记和轻底色；沿用原方案语义 |
| border / selected | `#DCE3ED` / `#E8F0FA`；选中行独立于状态色 |
| Waiting | `#FFF2D6` / `#7A4B00` |
| On Board | `#DFEDFF` / `#174B87` |
| Done | `#E2F3E7` / `#17603A` |
| error | `#A32323`；只用于真实错误或破坏性操作 |
| typography | Segoe UI，中文回退微软雅黑；正文 14、次要标签 12–13、区标题 16、当前站船名 24 px |
| spacing / radius | 4/8/12/16/24 px；按钮 6、面板 8 px；无嵌套卡片、装饰阴影或大面积渐变 |
| targets | 常规按钮高 32–36 px；站点按钮和菜单操作可通过鼠标与键盘触发 |
| table | 单行 44 px，最多两行时 56 px；表头 36 px；数值用等宽数字 |

按钮、输入框和选择器覆盖默认、悬停、2 px 键盘焦点、按下、禁用、保存中、错误状态。成功保存才显示结果，不提前改变台账。状态标签始终有文字；当前关联使用细线/符号及可读名称，高对比模式由系统色替代装饰色。原生组件自带滚动条和键盘行为，不绘制自定义桌面窗口控件。

## 3. 主窗口布局

### 3.1 标准窗口 1366×768

```text
Cargo Track                         Fleet  Voyages  Export  Backup  Settings
Voyage 2 [Choose] [New] [Copy previous]
[1 BVC] [2 CHA] [3 BVC: current]                         [+ Add vessel]
Current stop: BVC · 3 of 3                [Previous] [Next: disabled] [Choose]
2 ready to pick up · 1 ready to deliver · 1 other related
预览：当前可收取/交付任务（最多两条，直接办理）        [View all 4]
[All transfers] [Current stop 4] [On my vessel 3]                  [+ Add cargo]
[Search NO, ID, description, comment…] [Status] [Vessel] [History] [Clear]
NO | Cargo ID | Description | From | To | Status | Comment | Completed Date
共享表格，保持至少 5 行可见；当前选择下方显示 Details 和允许动作
状态栏：保存反馈、已显示段数/范围、业务时区
```

主导航高约 52 px；航程区约 110 px；当前站及预览约 140 px；表格页签和筛选约 92 px。其余空间优先分配表格，状态栏高 24–28 px。当前站预览可折叠，折叠状态记在本机 UI 设置中，不改变数据库业务状态。

主窗口不常驻左侧导航，不放大统计数字。保留原字段的相对顺序，仅在 NO 后增加 Cargo ID；行尾不增加一排按钮，单击选中后显示底部操作栏，完整编辑使用 Details/Enter/双击。

### 3.2 宽屏 1920×1080 目标布局与缩放

宽屏目标布局可使用 `QSplitter`：表格最小舒适宽约 1100 px，右侧详情 400–480 px。当前 1.0.0 在所有尺寸都使用独立详情对话框，尚未实现并排详情；因此本节和宽屏图属于后续目标，不是现版本行为。对话框宽 520–600 px，高度不超过可用屏幕的 85%，正文可滚动，固定底部 Cancel/Save。若宽屏并列布局实际操作收益不明显，保留对话框即可，不为使用屏幕空间而强制加分栏。

1100×700 为建议最小逻辑窗口，不等同于物理像素。在高 DPI 或屏幕可用宽度不足时使用实际可用大小，工具栏换行、预览折叠、表格横向滚动，详情改独立窗口。200% 缩放的验收看可用逻辑空间，不将图稿缩小后声称通过。

建议列宽：NO 54、Cargo ID 100、Description 260、From 80、To 90、Status 110、Comment 230、Completed Date 130 px，总计约 1154 px，余宽优先给描述和备注。允许用户调宽列并保存偏好；Description/Comment 不能被永久压成几十像素。

## 4. 航程与当前站

### 4.1 航程区

航程名称与 Choose/New/Copy previous 同一行。站点在下一行显示序号和船名，当前站标注 Current；每个站点按钮可选择该站，菜单提供 Move earlier、Move later、Remove。示例 `1 BVC → 2 CHA → 3 BVC` 中两次 BVC 是两个 stop_id。

`Add vessel` 固定在路线右侧，打开可搜索 Fleet 有效船舶选择器；不自由输入船名，不显示 On Shore。长路线只在站点带内部横向滚动，添加入口固定。提供站点菜单 Move earlier/Move later/Remove 及可见快捷键说明。

前后移动菜单提交后刷新路线；提交失败保留原顺序并说明原因。当前站按 stop_id 跟随，不按旧序号跟随。移除当前站与清空选择原子保存，显示 `Current stop removed. Choose another stop.`，不自动跳站。

### 4.2 当前站作业区

当前站名称、序号、Previous/Next/Choose stop 同行。首站 Previous、末站 Next 禁用，禁用原因可读。新航程、复制航程和加入第一站均不自动选站；用户显式指定。

三个计数来自完整未完成集，不受下面搜索和筛选影响：

| 分组 | 条件 | 动作 |
| --- | --- | --- |
| Ready to pick up | Waiting 且 From ID=当前船 ID | Pick up |
| Ready to deliver | On Board 且 To ID=当前船 ID | Deliver |
| Other related | 未完成且 From/To 匹配，排除前两组 | Details；说明需先装船或等到目的地 |

From=To 只出现一次，并显示 `Check route`。Done/作废不进入当前站集。预览最多两条，优先可收取与可交付；计数按钮切入 Current stop 并选择相应动作分组。`View all N` 选择完整 Current stop 视图并清除该视图的搜索、状态、船舶及动作分组条件，保证显示全部 N 条；这一行为有明确反馈。预览行和表格都是同一 DTO，不重新计算动作。

## 5. 三个共享表格视图

| 视图 | 数据范围与筛选行为 |
| --- | --- |
| All transfers | 默认未作废的所有段，初始 NO 升序；历史按需加载，显示已载入/结果总数。范围可切换 Open only、Include completed、Voided only |
| Current stop N | 完整相关未完成集，可按动作分组及文字进一步筛选；无当前站时禁用并说明 Choose a stop；顶部 N 是完整集，表格另显示筛选结果数 |
| On my vessel N | 所有未作废 On Board，独立于当前站；搜索/Vessel 可筛选，Status 固定 On Board，History 控件不适用。数量 N 始终是完整本船集 |

每个视图的搜索和可用筛选分别记忆，切换时显示条件，不悄悄沿用另一视图的筛选。Vessel 按 From 或 To ID 匹配；搜索覆盖 NO、Cargo ID、实物识别号、Description、Comment。全部历史搜索在数据库全量执行，不能只搜索已加载页。CSV/Excel 的当前结果导出也采用同一全量条件。

表格描述、备注最多两行，超出省略；完整值通过详情/键盘可访问的展开或提示查看。Completed Date 显示 YYYYMMDD，未完成显示短横线，排序时空值最后。当前关联行标记与选中背景独立，状态标签不消失。

保存或状态变化后按 transfer_leg_id 定位。排序和滚动保留；若当前段因完成或作废退出视图，清空选择并反馈 `Transfer #108 delivered; removed from this view.`。不能自动选中下一行，避免用户紧接着把另一件货误交付。

## 6. 详情与新增表单

### 6.1 货物详情

顶部显示 Cargo ID、实物识别号、本段 NO 和状态。两个独立位置块：

- **Cargo location now**：由该 cargo 最新有效段推导的最后确认位置及时间；新 Waiting 无确认时显示 Not confirmed。
- **Selected transfer**：选中段 From → To、预计收取地点、状态与只读完成日期。选择旧 Done 段时注明 Historical transfer，不以它的目的地代替 Cargo location now。

下方为本段 Comment、完整 Description、多段路线和 Audit history。事件显示动作、前后值、时间（带时区）与原因。船名快照与 Fleet 现名不一致时显示 Recorded name/Current Fleet name，不改变按 ID 匹配。

正常动作采用 **Pick up / Deliver**，以使用者实际动作命名，状态标签仍是 Waiting/On Board/Done。当前站匹配时可直接提交；在无站点、其他视图或岸上操作时，先确认实物已装上本船/已交到指定 To。单次提交期间按钮禁用；保存成功才显示新状态和日期。

普通字段编辑与 Correction 分开。More 菜单包含 Correct record、Void record、Restore record（按权限和状态显示），禁用时给出原因与受阻段 NO。On Board 不提供可执行 Void；提示先更正确认位置，不能让货物无交代地离开本船清单。

### 6.2 新增/下一段/编辑

1. New cargo / Next transfer 两种入口。下一段通过 Cargo ID、描述、识别号找现有货物，只有有效末段 Done 才可创建。
2. Description 必填多行，实物识别号可选。描述属于本段，修改不会批量改写历史；识别号属于货物，修改时明确提示影响范围。
3. From/To 从有效 Fleet 或 On Shore 选择；下一段 From 默认前段 To。前段 To 已停用时不给新段悄悄使用停用地点，显示 Reactivate vessel or correct pickup location。
4. 初始 Status 固定 Waiting，用只读标签展示；普通编辑不出现可任意跳级的状态下拉框。
5. Comment 多行可空；Completed Date 只读，完成时按业务时区写入，普通编辑不改变日期。
6. 表单底部固定 Cancel/Save，校验错误靠近字段；失败保留输入。Esc/关闭遇到未保存修改时提示 Discard changes/Keep editing。

From=To 提示 `From and To are the same. Check this route.`，允许保存但保留警示。识别号重复提示可能为同一实物，提供查看现有货物，不自动合并。下一段 From 不等于前段 To 时必须说明原因，保存事件记录差异。

Waiting 路线可编辑；On Board 修改 To 需要重定向原因，修改 From 须 Correction；Done 改路线/状态须 Correction，存在有效后续段时阻止。更正页展示前后位置、完成日期和受影响后续段。离开 Done 清空当前完成字段；再次完成按本次操作时间计算，不提供回填历史日期。

### 6.3 作废与恢复

作废原因必填，显示 NO、Cargo ID、描述和位置影响。仅 Waiting/Done 的有效末段允许作废；On Board 或存在有效后段时阻止并说明解决路径。作废记录在 Voided only 中查看，不能计入本船或当前站数量。

恢复保持 NO/Cargo ID，校验唯一活跃段和链路。若已有替代段，显示冲突段编号，即使替代段已完成也不能恢复旧分支。没有越过约束的 Continue anyway。保存后的误建记录也使用作废；未保存草稿直接取消。

## 7. Fleet、Voyages、设置及文件操作

Fleet 仅管理船舶目录；Voyages 管理航程，不在 Fleet 中维护“全局作业顺序”。Fleet 的新增、重命名、停用、重新启用均有清晰标签。名称忽略大小写及首尾空白后不得重复。On Shore 不属于 Fleet。停用前检查当前航程和未完成转运引用，显示阻塞记录，历史引用保持。

Voyages 支持空白新建、复制上一航程、选择当前航程与只读回看历史。复制不复制 current_stop_id；站点编辑在主页面进行。业务时区默认 Asia/Riyadh，首次使用确认；Settings 展示数据目录、备份目录和本船可选显示名。更改时区不重写历史日期。

Export 对话框明确全部/当前视图结果、是否含已完成/作废、文件格式与路径；成功显示段数和文件位置，失败不报告成功。导出不等于完整备份，不能显示“货物数”代替段数。

Backup 分 Create backup/Restore backup。恢复先预检备份，再显示文件时间、记录数、覆盖目标与自动安全副本位置，最后确认。确认后出现维护遮罩及阶段反馈：Saving safety copy → Replacing data → Reloading。期间录入禁用；失败回到原数据并给出具体原因。恢复成功关闭旧详情和表单，重新加载当前航程/站点，不沿用旧选中行。

## 8. 边界状态与反馈

| 场景 | 展示/可操作行为 |
| --- | --- |
| 初次无货物 | 保留表头，No transfers yet/Add cargo；无 Fleet 引导 Manage Fleet，岸上到岸上的录入仍可用 |
| 无当前航程 | 顶部 No active voyage/Create voyage；无当前站集，本船及 All transfers 可用 |
| 空航程 | 常驻空路线 No vessels in this voyage/Add vessel；Choose stop/Previous/Next 禁用；本船和完整表仍可用 |
| 有站点未选择 | Choose current stop；不自动指定第一站 |
| 当前站无任务 | No open transfers for BVC，计数为 0，不隐藏航程或其他视图 |
| 无筛选结果 | No transfers match these filters/Clear filters，显示条件与范围 |
| 保存中/失败 | Saving… 禁用重复提交；失败保留表单、原表行和计数，显示具体字段/目录/冲突问题 |
| 过时版本 | Record changed. Reload to review. 保留输入供比较，不自动覆盖新数据 |
| 已保存但后续读取失败 | 显示 Saved; refresh failed. Retry refresh. 禁止重做业务动作，不误报保存失败 |
| 长历史查询 | Loading history…；显示已载入/总计，旧数据标记更新中，丢弃过时查询结果 |
| 读取或初始化失败 | 不把失败包装成空台账；显示数据目录、重试/查看错误入口 |
| 备份/导出失败 | 不覆盖旧目标文件，不将临时文件计为成功 |

## 9. 无障碍、键盘与状态同步契约

目标键盘操作为 Ctrl+N 新增、Ctrl+F 搜索、Enter 打开详情、Ctrl+S 保存表单、Esc 关闭；表格筛选与站点菜单排序都能键盘完成，焦点回到触发控件。**1.0.0 尚未绑定这些快捷键**；实现前不把它们描述为现有功能。更正、作废和恢复对话框使用有名称的明确按钮，不使用仅图标动作。

界面只发送应用命令，状态权限、位置、当前站分类、计数来自软件方案定义的 WorkspaceSnapshot/行 DTO。不得直接写 SQLite、从表格当前行数计算本船数量、从船名匹配当前船，或自己计算 Completed Date。数据提交成功后在 GUI 线程更新模型；工作线程不操作 QWidget/QAbstractTableModel。查询返回同时验证 dataset_epoch、request_id 与 data_revision，恢复数据库时重置 epoch，确保恢复前的迟到结果不会覆盖新数据。

标签和读屏名称包含 NO、Cargo ID、描述、From、To、状态及关联原因。计数/保存反馈短暂宣布一次，不连续弹窗；颜色之外保留文字与焦点。实际程序需测试 Windows 高对比与屏幕阅读器，图稿本身无法验证真实控件的读屏表现。

## 10. 图稿、示例与验收

静态方案图用于评审视觉方向；已实现的桌面程序另提供[运行截图](./CargoTrack-UI-runtime.png)，由 Qt 窗口加载六条示例转运与双站航程后直接抓取。截图验证了真实控件间距、路由栏、状态标签、表格和操作区；按钮交互由 `tools/verify_ui_runtime.py` 实际执行收货流程验证。截图与方案图用途不同，运行截图路径显示测试数据目录。

- [1366×768 主界面 PNG](./货物追踪软件_UI主界面示意.png) · [可编辑 SVG](./货物追踪软件_UI主界面示意.svg)
- [1920×1080 宽屏详情 PNG](./货物追踪软件_UI宽屏详情示意.png) · [SVG](./货物追踪软件_UI宽屏详情示意.svg)
- [1366×768 空航程 PNG](./货物追踪软件_UI空航程示意.png) · [SVG](./货物追踪软件_UI空航程示意.svg)

图稿统一示例：Voyage 2 的站点为 1 BVC、2 CHA、3 BVC，当前站为 3；有效段 8 条，可收取 #104/#112、可交付 #108、其他相关 #114，共 4 条；本船 #108/#114/#116，共 3 条。#105 已完成，#110/#118 等待且与当前站无关。末站 Next 禁用。空航程图沿用这份台账，只清空站点与当前站；本船数量仍为 3。

验收必须覆盖：

1. 标准尺寸不需要整页滚动就能看到航程添加、当前站、全部页签、搜索、至少五行表格；宽屏详情不遮挡表格；长路线只在局部滚动。
2. 任意搜索下摘要保持完整集数量，表格单独显示结果数；View all 清除相关视图条件；From=To 去重。
3. 单击仅选择，Details/双击/Enter 打开详情；选中态保留状态标签与当前关联；动作后退出视图不自动换选。
4. Cargo location now 与 Selected transfer 分离；Waiting 显示预计而非确认，旧 Done 不冒充当前位置。
5. 空航程、无航程、未选站、无任务、无结果、加载失败各有不同文案；零站点仍能添加和管理货物。
6. 所有写入都遵循事务、保存失败保留输入、过时快照丢弃；备份恢复有明确维护模式。
7. 在真实程序中另行验证 100%/125%/150%/200% DPI、键盘、读屏、高对比、长多行文本与 10,000 条历史；不得以静态图稿替代运行验收。

## 11. 1.0.0 现状与后续目标

| 优先级 | 现状 | UI 方案调整 |
| --- | --- | --- |
| P1 | 主图和宽屏图是目标设计；实际程序的模块入口、路线控件和详情对话框存在布局差异 | 图稿 footer 明确标为 Design target；运行截图单独标为真实窗口。先完成实际窗口与主图的关键层级对齐，再评估是否实现宽屏 `QSplitter` |
| P1 | 方案写有 Ctrl+N/Ctrl+F/Ctrl+S 等快捷键，1.0.0 尚未实现 | 保留为待开发目标，开发后逐项做键盘焦点与对话框作用域测试 |
| P2 | 保存反馈在状态栏短暂显示；底部同时显示本地数据完整路径 | 目标方案将数据路径放入 Settings；把状态区域留给最近操作结果，并在行状态/计数更新时提供就地确认 |
| P2 | 首次使用提示较轻，Fleet、Voyage、stop 与 transfer 对新用户是多个概念 | 空数据库增加一步式引导：管理船队 → 创建航程 → 可选添加站点 → 新增货物；仍允许不建航程直接录入岸上转运 |
| P2 | 当前站匹配的 Pick up/Deliver 适合快速操作，但误点后需要通过更正恢复 | 保留直接办理；让选中货物、From/To 与成功结果明确关联，不增加逐条确认弹窗，除非实测误操作率偏高 |

尚待产品决定的只有最终是否增加中文 UI 与可选交接人字段，二者不阻塞当前架构和图稿评审，图稿不擅自加入未确认功能。


## 1.0.1 修订与验证（2026-09-30，替代上文 1.0.0 对应现状）

截图中的黑色区域来自未统一的系统调色板。程序现统一使用 Fusion 浅色调色板，并明确覆盖滚动区、列表、表格空白表头、菜单和禁用控件。已采用原设计 Logo；原图保留，应用抬头使用裁切后的组合标识，程序、安装程序和桌面快捷方式使用其符号图标。搜索与筛选拆分为两行，选中货物信息独立置于操作按钮上方；窗口和对话框根据可用屏幕尺寸收缩。Ctrl+F 搜索、Ctrl+N 新增已实现，其余快捷键仍需逐项确认。

验证结果：19 项服务测试通过，其中 10 项覆盖恢复故障；13 项参考架构检查通过。真实 Windows Qt 窗口在实际有效 100%、125%、150%、175%、200% DPI 下分别验证空数据和有数据状态，检查背景、控件边界、分页区、搜索焦点和无障碍名称；10 个组合均通过。Windows 无障碍树已读取安装版的航站、筛选、表头、货物身份和状态，以及 Fleet 船名、启用状态和引用数量。尚未人工听检 Narrator/NVDA 的实际语音；高对比主题、物理多显示器切换和突然断电仍未验证。

桌面快捷方式已在真实 Windows 桌面创建并成功启动，目标、工作目录及 Logo 图标正确。验证使用独立名称与虚构数据，升级前后数据库校验值一致，重复启动只保留一个应用实例。安装程序现为单文件内嵌载荷，无需同目录配套 ZIP；另提供便携版。

恢复保护覆盖安全备份失败、磁盘写入中断、准备文件校验失败、两阶段替换失败、恢复库打开失败、回滚失败和旧文件清理失败。可回滚时重新打开原台账；替换和回滚同时失败时保留原始回滚文件、安全备份及相关路径，并维持维护模式阻止继续写入。安全备份以逻辑数据一致性校验，保留的原文件另做字节校验；不把模拟文件错误描述为真实断电测试。初始化内置岸上地点时不再推进未使用的自增序号，避免重新打开改变序列。

- 1.0.1 单文件安装程序（历史文件，当前目录未保留）
- 1.0.1 便携版（历史文件，当前目录未保留）
- [完整验证记录](./release/release_validation-1.0.1.json)
- [实际主窗口：150% DPI](./artifacts/validation-1.0.1/main-filled-1.5x.png)
- [实际 Fleet：150% DPI](./artifacts/validation-1.0.1/fleet-empty-1.5x.png)

本次按用户要求未执行 Impeccable 审核。静态方案图已同步 Logo，仍是目标设计，实际布局以运行截图为准。


## 1.0.2 macOS 风格修订（2026-09-30）

根据用户对粗重下拉控件的反馈，实际原生窗口改用更轻的桌面视觉：中性浅灰背景、白色圆角面板、细灰边框、蓝色主操作和分段页签。全部 QComboBox 的箭头区域明确无边框、无独立灰色按钮底，使用随包分发的细线 SVG 箭头；停靠点的分体菜单按钮采用相同箭头和透明菜单区，保留点击选择站点与菜单排序/移除的原有行为。当前站用深色标题和淡蓝选中态，滚动条取消两端按钮，表格关联行降低紫色底的强度。原设计 Logo 保留。NO 列按字符串展示阿拉伯数字，避免平台整数显示产生符号样式。

五档有效 DPI（100/125/150/175/200%）各覆盖空/有数据状态，含筛选弹窗与站点菜单打开检查，全部通过；19 项服务回归和真实 Qt 收货操作通过。窗口仍是 Windows 原生 PySide6 程序，数据、命令与恢复保护边界沿用 1.0.1。实际语音播报、物理多屏切换与高对比主题的未验证范围沿用前版。

- [1.0.2 实际界面](./artifacts/validation-1.0.2/main-filled-1.5x.png)
- [筛选弹窗](./artifacts/validation-1.0.2/filter-menu-filled-1.5x.png)
- 1.0.2 安装程序（历史文件，当前目录未保留）
- [1.0.2 便携版](./release/CargoTrack-1.0.2-Windows-x64.zip)

视觉方向参照 [Apple 弹出按钮设计主题](https://developer.apple.com/design/human-interface-guidelines/pop-up-buttons)，具体尺寸与配色是本应用的实现选择。本次未执行 Impeccable 审核。

1.0.2 最终安装验证：真实桌面快捷方式启动、升级数据保留与重复启动均通过；安装目录包含 Logo 与两款细线箭头资源。完整证据见 [1.0.2 发行验证](./release/release_validation-1.0.2.json)。


## 1.0.3 设置与管理修订（2026-09-30）

设置页的 Business time zone 改为下拉菜单，从本机 Windows 时区注册表读取 UTC 偏移与城市显示名称，并通过 Qt 的 Windows/IANA 映射保存业务时区。原有 IANA 设置保持选中，即使不是 Windows 主映射也不会丢失。修改业务时区只影响之后的业务确认，既有完成日期和审计时区快照不重算。

Database folder 与 Backup folder 提供 Choose 按钮及系统目录选择器，保存前检查可写性。数据库目录变更时在工作线程进入维护模式，SQLite Backup API 生成完整一致副本，独占创建目标文件、校验并打开后才切换服务；旧库保留，已有目标库不覆盖，失败时原库继续使用。备份目录独立保存。两个路径均在本机 QSettings 持久化；正常启动读取保存的数据库目录，CARGO_TRACK_DATA_DIR 保持隔离测试优先。单实例锁使用稳定的用户配置目录，避免改变数据库目录产生第二实例。

Voyages 与 Fleet 增加 Delete 按钮。删除航程会从航程列表移除，删除当前航程同时清空当前站；路线及审计保留。删除船舶会从 Fleet 与正常选船列表移除，被未完成段或当前站点引用时阻止删除并提示先处理关联。历史货物船名及船舶 ID 保留，同名船舶可作为新身份重新添加。删除均写入不可修改的审计事件，不物理删除历史记录。

主窗口选中货物后，底部状态下拉可选择 Waiting / On Board / Done。正常前进复用收货、交付命令和实物位置确认；1.0.3 的回退/跳步需要更正对话框；1.0.4 按本文最新章节改为直接提交并自动记录原因，日期、版本及唯一活跃段仍由业务层校验。修复当前站任务预览误投递到主表的问题，删除当前航程后“全部货物”仍显示完整台账。

按用户最终选择，字体改为 [Inter](https://github.com/rsms/inter)，使用官方 4.1 的 Regular 和 SemiBold 文件，并随安装包附带 SIL Open Font License。采用清晰的系统界面字号、正常正文和半粗标题，延续 macOS 视觉方向。Calibre 不再作为本版交付要求。

验证：26 项服务测试通过；100/125/150/175/200% 有效 DPI 下空/有数据窗口、设置时区、目录显示、菜单、状态下拉、实时迁移和 Fleet/Voyage 删除实际窗口流程通过。迁移覆盖已有目标拒绝、打开失败、备份失败；删除覆盖当前/历史航程、在用船阻止、历史完成转运保留、同名新身份与重新打开数据库。

- [1.0.3 设置页运行图](./artifacts/validation-1.0.3/settings-filled-1.5x.png)
- [1.0.3 主界面运行图](./artifacts/validation-1.0.3/main-filled-1.5x.png)
- 1.0.3 安装程序（历史文件，当前目录未保留）
- [1.0.3 便携版](./release/CargoTrack-1.0.3-Windows-x64.zip)

之前未验证的实际读屏语音、高对比主题和物理多屏切换范围沿用，不将控件接口检查替代人工听检。本次未执行 Impeccable 审核。


## 1.0.4 当前交付：帮助、主题与记录操作（2026-09-30）

本节为当前实现；下述状态下拉规则取代旧版需要确认或填写更正原因的交互。选中货物后，状态下拉直接提交 Waiting / On Board / Done，不显示确认弹窗。正常前进复用收取、交付命令；回退或跳步仍由业务层校验，自动记录变更原因、前后状态与时间。已有有效后续段、重复活跃段及陈旧版本仍会被拒绝；操作失败恢复当前显示。更正字段的独立对话框保留。

底部提供明确的 Delete… 按钮，Waiting 和 Done 的有效末段都可删除。删除填写原因后逻辑作废，保留编号及审计；正常清单隐藏该行。在范围下拉选择 Deleted records，选中行后按钮变为 Restore…，填写原因并重新校验后恢复。On Board 必须先修改状态；已有后续段须先处理后续段。

默认 Inter 正文字号由 9 pt 提高为 11 pt。Settings 的 Font size 可选 Compact 10 / Standard 11 / Large 12 pt。Appearance 提供 Light / Dark，两项保存后立即生效并在重启后保留。主题与字体为本机界面偏好，保存在 QSettings，不修改业务数据库。UI 调色板、样式表、模型背景、状态标签和当前站提示统一读取主题；菜单、下拉列表、输入、禁用控件、滚动条、对话框、帮助链接分别采用对应颜色。原 Logo 在深色模式中置于浅色底板，保证原标识可辨。

主窗口 Help 菜单按功能打开离线中文帮助：快速开始、货物与状态、删除与恢复、船队、航程、搜索与导出、备份与故障恢复、设置与外观、快捷键。F1 打开帮助；Fleet、Voyages、Settings 的 Help 按钮和 F1 定位对应章节。帮助 HTML 随安装包分发，不依赖网络，使用应用字体及当前主题。

验证：26 项服务测试通过；两种主题在 100/125/150/175/200% 有效缩放下检查空/有数据窗口，另检查两种主题的 12 pt、200% 场景，共 24 个状态。实际 Qt 流程覆盖 Done 删除/恢复、状态前进/回退无弹窗、主题及字号即时切换、F1 帮助、设置和船队/航程删除。正文、次要文本、选择态、帮助链接与状态标签的浅/深色对比均不低于 4.5:1。实际桌面快捷方式启动、独立安装程序、升级数据保留和单实例检查的最终结果见发行报告。

- [浅色主界面](./artifacts/validation-1.0.4/light/main-filled-1.5x.png)
- [深色主界面](./artifacts/validation-1.0.4/dark/main-filled-1.5x.png)
- [深色设置页](./artifacts/validation-1.0.4/dark/settings-filled-1.5x.png)
- [帮助窗口](./artifacts/validation-1.0.4/dark/help-filled-1.5x.png)
- [最终安装包 1.0.4](./release/CargoTrack-Setup-1.0.4.exe)
- [便携版 1.0.4](./release/CargoTrack-1.0.4-Windows-x64.zip)
- [发行验证报告](./release/release_validation-1.0.4.json)

实际读屏语音听检、物理多屏切换与 Windows 高对比主题尚未完成；已检查的可访问名称与控件接口不替代这些检查。本次未执行 Impeccable 审核。


## 1.0.5 安装路径与免安装版（2026-09-30）

安装程序先显示 Installation folder，支持手动输入及 Browse 目录选择；Create desktop shortcut 与 Launch Cargo Track after installation 可独立勾选。点击 Install 后才写入文件，Cancel 退出。安装位置是专用父目录，程序位于其 CargoTrack 子目录。已有非空目录只允许识别为 Cargo Track 安装目录；含其他文件的目录、磁盘根目录会被拒绝，避免覆盖无关文件。程序继续支持升级并保留独立数据目录。

免安装版解压整个 ZIP，运行 CargoTrack/CargoTrack.exe 即可；不要单独移动 EXE 或删除 _internal。无需安装 Python。默认业务数据仍保存于用户数据目录，Settings 可以选择数据库及备份路径；免安装是指程序无需安装，并不默认将台账写入程序目录。

验证：安装窗口实际选择与提交、自定义带空格路径安装、取消与选项保留、无关目录和盘符保护通过；独立安装包、实际桌面快捷方式启动、升级保留数据及重复启动通过；免安装 ZIP 已完整解压，实际启动并创建隔离数据库，帮助资源完整。业务与主题功能沿用 1.0.4 实现，未重新声明全套业务测试。

- [安装包 1.0.5](./release/CargoTrack-Setup-1.0.5.exe)
- [免安装版 1.0.5](./release/CargoTrack-1.0.5-Windows-x64.zip)
- [安装路径选择窗口](./artifacts/validation-1.0.5/installer-options.png)
- [发行验证](./release/release_validation-1.0.5.json)
