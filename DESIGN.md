---
name: Cargo Track Native Workspaces
description: Shared native Windows visual system for Cargo Track and the independent Personnel Transfer Track workbench.
colors:
  primary: "#0066D6"
  primary-hover: "#006BE0"
  primary-text: "#FFFFFF"
  focus: "#007AFF"
  window: "#F5F5F7"
  workspace: "#FFFFFF"
  text: "#24262B"
  muted-text: "#666970"
  surface-border: "#E5E5EA"
  control-border: "#DCDDE2"
  control-hover: "#F0F3F8"
  control-pressed: "#E7EDF5"
  disabled-text: "#8D9098"
  selection: "#EAF3FF"
  alternate-row: "#FAFAFC"
  tab-track: "#E9EAEE"
  tab-text: "#62656D"
  header-text: "#6D7078"
  dark-window: "#191B20"
  dark-workspace: "#25272E"
  dark-text: "#E6E8ED"
  dark-muted-text: "#ADB4C1"
  dark-surface-border: "#373A43"
  dark-control-border: "#414650"
  dark-control-hover: "#303744"
  dark-control-pressed: "#38475D"
  dark-disabled-text: "#9299A6"
  dark-selection: "#183D61"
  dark-alternate-row: "#202329"
  dark-focus: "#4199FF"
  dark-tab-track: "#262931"
  dark-tab-text: "#B6BDCA"
typography:
  body:
    fontFamily: "Inter, Segoe UI, Microsoft YaHei UI"
    fontSize: "11pt"
    fontWeight: 400
  title:
    fontFamily: "Inter, Segoe UI, Microsoft YaHei UI"
    fontSize: "11pt"
    fontWeight: 600
  label:
    fontFamily: "Inter, Segoe UI, Microsoft YaHei UI"
    fontSize: "11pt"
    fontWeight: 600
rounded:
  scrollbar: "3px"
  tab: "6px"
  control: "7px"
  field: "8px"
  surface: "12px"
spacing:
  control-block: "5px"
  control-inline: "12px"
  field-inline: "10px"
  header-block: "7px"
  header-inline: "8px"
  page-inline: "16px"
  page-block: "10px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-text}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "5px 12px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.primary-text}"
    rounded: "{rounded.control}"
  button-secondary:
    backgroundColor: "{colors.workspace}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "5px 12px"
  field:
    backgroundColor: "{colors.workspace}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
    padding: "5px 10px"
  tab-selected:
    backgroundColor: "{colors.workspace}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.tab}"
    padding: "7px 13px"
  ledger:
    backgroundColor: "{colors.workspace}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
  cargo-surface:
    backgroundColor: "{colors.workspace}"
    rounded: "{rounded.surface}"
---

# Design System: Cargo Track Native Workspaces

## Overview

**Creative North Star: "The Native Workbench"**

This descriptive name records the incumbent application rather than introducing a new brand. The interface is a practical Windows workbench: readable ledgers, clearly labelled native controls, restrained blue actions, and a quiet gray frame around white work areas. Personnel Transfer Track inherits this visual system and has its own page and dialogs.

The established user direction is Inter Regular/SemiBold, light gray backgrounds, white workspaces, blue primary actions, and the existing dark theme and font-size settings. Density comes from table columns and compact control rows. Selection, transfer direction, vessel matches, route problems and saved-version state remain explicit in words.

**Key Characteristics:**

- Native PySide6 widgets using Qt's Fusion style.
- One shared typographic family and configurable reading size.
- Flat surfaces separated by tone and thin borders.
- Text-led tables, source details and ordered plan previews.

This scan records the current 1.1.2 native implementation, using `appearance.py`, `personnel_ui.py`, `berth_plan.py`, `workspace.py` and the reviewed repair captures in `artifacts/personnel-load-fix/`, including `inline-draft.png` and `inline-small.png`. It documents implemented appearance and UI presentation, including the main-page personnel-only draft editor, legacy-version recovery, actionable review entries and the clarified date controls. `PRODUCT.md` is the current scope authority; page-specific implementation and evidence limits are in `.impeccable/personnel-surface.md`. Historical V0.2 personnel lifecycle concepts do not describe the current surface. No detector was run in this documentation pass.

## Colors

The palette pairs a clear action blue with low-chroma neutrals. The frontmatter is the token reference; Qt styling in `src/cargo_track/appearance.py` is the implementation authority.

### Primary

- **Action Blue:** Import Excel, Confirm import and Generate final plan use `primary`, white `primary-text`, and `primary-hover` on hover. Primary color and white text persist in dark mode.
- **Focus Blue:** `focus` marks focused buttons, fields and table items; `dark-focus` is its theme counterpart.
- **Selection Wash:** `selection` highlights selected ledger rows and checked tool buttons; `dark-selection` preserves that distinction on a dark surface.

### Neutral

- **Window Gray / Dark Window:** `window` and `dark-window` provide the outer frame.
- **Workspace White / Dark Workspace:** `workspace` and `dark-workspace` provide controls and data views.
- **Reading Ink / Dark Reading Ink:** `text` and `dark-text` carry body content. Muted text identifies section headings and auxiliary information.
- **Quiet Borders:** surface and control border tokens separate views and establish editable fields.
- **Alternating Rows:** alternate-row tokens support scanning without encoding business status.
- **Tab Track:** tab-track and tab-text tokens distinguish navigation from the selected workspace.
- **Disabled Ink:** disabled-text tokens communicate unavailable actions alongside the control's native disabled state.

**The Text Meaning Rule.** Direction, match issues, route assignments and saved-version state use written labels. Color must not be their only explanation.

## Typography

**Body Font:** bundled Inter Regular, with Segoe UI and Microsoft YaHei UI as the existing fallback stack. **Title and Label Font:** bundled Inter SemiBold.

All roles inherit the application size: the default is (11pt), with user settings for (10pt) and (12pt). Qt point sizes are retained; do not convert them into a fixed screenshot-pixel scale. There is no separate display or promotional headline scale.

### Hierarchy

- **Title:** semibold section title at the selected application size.
- **Body:** regular table values, form content, details and plain-text plan preview.
- **Label:** semibold primary actions, selected tabs and table headers; secondary button labels remain regular.

Native layout and text metrics determine line height. No explicit custom line-height or letter-spacing token is established. Dates use the visible `yyyy-MM-dd` format. Table cells do not wrap; selected-record details and notice labels do.

**The Shared Reading Size Rule.** New native screens inherit the existing font setting and bundled fonts rather than creating a separate scale.

## Layout

The Personnel page uses a vertical native layout with (16px) horizontal and (10px) vertical contents margins in Qt logical units. Its top row holds the return-to-Cargo action, title and import/refresh/settings controls. The second row holds a labelled, name-only Crew list selector, read-only Reference Voyage label and New crew list. Two tabs fill the remaining work area. Berthing plan date belongs inside the Berthing plan tab, beside its explanation that the date is used in the Excel heading and file name; crew change dates remain separately labelled in the ledger.

Crew change information places a horizontal vessel/search/direction filter row above a ledger. The ledger takes available height; wrapping source details and Add entry / Edit crew entry / Remove entry sit below it. Berthing plan places its date row and Generate final plan / Save plan version / Export Excel above the saved-version row, then shows Edit draft directly and Preview tabs. The active draft tab embeds the personnel editor and route controls in the main page; Preview uses an adjustable horizontal splitter with stop order on the left and a larger scrollable text view on the right. A selected passenger review exposes Edit this crew entry below the splitter.

Native table and text-view scrollbars handle long content. Table columns are fitted to content, then capped between (65px) and (300px); the final column stretches. The initial generation dialog and the embedded draft editor place their editable stop list beside a wider inclusion/assignment table; the embedded editor contains personnel rows only. Its stop-assignment column starts at (280px), and the import entry-match column at (310px). These are observed logical dimensions, subject to desktop scaling, rather than new reusable spacing tokens.

On a smaller desktop window the same control rows remain, fields contract, detail text wraps and views keep their scroll behavior. There is no CSS breakpoint system or mobile layout. Dialogs shrink to available screen geometry with horizontal and vertical screen allowances of (24px) and (48px). Current Personnel implementation uses a wrapping detail label capped at (100px) height; this cap is an implementation limit, not a universal rule for future detail views. The small screenshot establishes only its depicted desktop size, not arbitrary-width fit.

## Elevation & Depth

The application is flat. Workspace tone, alternating rows, selected-tab backgrounds, one-pixel borders and blue focus strokes provide separation. No custom widget shadow or animated elevation token is defined. Native menus, calendars, dialogs and message boxes retain their Qt behavior; do not invent a shadow or motion scale from them.

## Shapes

Controls have gently curved corners: buttons and combo boxes use the control radius; text fields and data views use the field radius; selected tabs use the tab radius. The incumbent Cargo surface frame uses the larger surface radius. Personnel tabs are native tab pages, not a new collection of decorative cards. Borders are thin and functional. Standard Qt date/calendar, checkbox and splitter geometry is retained.

## Components

### Buttons

Compact, explicitly named actions use the existing control padding and minimum content height of (22px). Primary actions use Action Blue and semibold white labels; secondary actions use workspace backgrounds and control borders. Hover changes tone and border; press changes tone; focus changes border to Focus Blue. Native disabled state and muted text indicate unavailable operations. Preserve accessible action names.

### Inputs / Fields

Text fields use workspace backgrounds, field corners, a control border and compact padding. Focus changes the border to Focus Blue. Combo boxes add right-side space for the bundled chevron and use native popup lists. Dates use `QDateEdit` with a calendar popup. Validation appears as form text or a warning message box; no red error-field variant is currently established.

### Navigation

An additive Personnel button opens an independent stacked page. Cargo Track returns to the existing cargo page. Inside Personnel, a native two-tab bar switches Crew change information and Berthing plan. Selected tabs have workspace fill and semibold text; unselected tabs have muted text on the tab track. Cargo actions are disabled while the Personnel page is active.

### Ledger and crew details

The read-only `QTableWidget` selects complete rows, supports multiple selections and alternates row tone. Columns are NO, Name, Position, Sign-on / Sign-off, From, To, Crew change date and Comment. Tooltips expose full cell text. Nationality, source sheet/row, original date and vessel-match feedback appear in the selected-record detail label. An empty selection displays guidance.

Add entry and Edit crew entry use a native core-field form. Edit requires one selected entry; Remove entry requires a selection and a confirmation dialog. The current Personnel ledger has no status column, status filter or passenger pickup/drop/history/correction control row. These are crew information actions; their planning behavior belongs in the surface brief.

### Import review

Native workbook/worksheet selection leads to a preview dialog. Append crew entries, New crew list and Replace selected crew list are explicit modes. A summary shows direction counts, row issues and possible matches; the Fleet vessel matches line explains recognized abbreviations. Unmatched Excel vessel names show an alias combo beginning with “Unmatched — save as draft”. The preview table shows source row, direction, core fields, issues and an existing-entry/separate-entry choice. Possible duplicates require a choice. Replacement shows absent entries and an explicit removal confirmation checkbox. A transfer-date checkbox makes a date override visible. Manual column mapping uses a form when automatic mapping needs review.

### Final plan builder, preview and revision

Initial Generate final plan uses a native dialog to choose crew, optional Cargo materials and the independent route. The generated draft opens Edit draft directly in the main Berthing plan page. Its embedded editor uses a native drag-reorder stop list with Add stop, Move up, Move down and Remove stop controls, and a separate Final Port line. The neighboring table contains personnel rows only: Include checkboxes, editable Name and Position cells, and native stop-assignment combos. Double-clicking a name or position changes that draft snapshot only. Add crew entry and Edit selected crew use explicit forms that update the current crew list; Remove from plan excludes selected personnel without deleting source records. Materials chosen during initial generation remain read-only in the inline editor and visible in Preview. Editing retains exclusions and valid exact repeated-visit assignments. Repeated stops use numbered assignment labels; an infeasible selected material remains included and visibly reviewable.

The plan tab shows ordered stop labels with action counts and a plain-text four-group preview for each vessel and the final Port: Drop passengers, Pick up passengers, Drop Materials and Pick up Materials. Empty groups explicitly show None. Passenger names and positions use numbered lines; multiple material records use numbered inline text separated by semicolons, with source/destination vessel names. Review entries are grouped once per task, show a count of distinct checks, and expose the reasons and available From/To context when selected. Passenger reviews offer Edit this crew entry; an entry absent from the current crew list gets an explicit rebuild message. Notices distinguish unsaved draft, saved version, unresolved issues, changed Cargo source and refreshed legacy plans. Saved-version labels expose date, voyage, mode, publication state and version number.

Edit plan selects the embedded editor for the displayed draft, or creates a new inline draft from the loaded immutable version. Loading an old Complete / Remaining version rebuilds a Final draft with current crew and cargo while retaining the original immutable version. The current surface does not expose Complete / Remaining mode selection or a lifecycle-revision dialog. Berthing plan date is editable for drafts and disabled for saved snapshots. Preview changes refreshes the text view; Save plan version and Export Excel collect current inline edits directly without that intermediate step. Export Excel can first save an unsaved final draft, then opens a native `.xlsx` save-file dialog. Page-specific route, date and export rules remain in the surface brief.

### Loading, notices and settings

A bottom notice displays Loading, source or error feedback. Reference Voyage text explicitly says read only, including None selected. Native settings contain Port name, an optional transfer-vessel override, personnel database/backup folders and personnel-only backup/restore actions. Folder fields are read-only with Choose actions. The original Cargo settings and data operations remain part of the existing workspace.

## Do's and Don'ts

### Do:

- **Do** inherit Inter, the existing 10/11/12pt setting and both theme mappings.
- **Do** retain explicit direction, route, source and version-state words.
- **Do** use native row selection, keyboard focus, dialogs and scrollable data views.
- **Do** keep page-specific task rules in the personnel surface brief and source implementation.
- **Do** treat the sidecar's HTML/CSS as preview translations of Qt primitives.

### Don't:

- **Don't** introduce a new visual identity into the additive Personnel page.
- **Don't** replace operational tables with decorative cards or imagery.
- **Don't** claim a responsive drawer, mobile breakpoint, custom animation or shadow that the source does not implement.
- **Don't** turn a screenshot or sidecar preview into a claim of complete runtime or release validation.
- **Don't** expose ignored Excel fields such as identity documents, company, laptop details or Mark in the personnel UI.

## Personnel default-selection update, 1.1.3

The generation dialog starts feasible rows checked and explains that default. Manual checkbox changes override automatic selection during subsequent route edits, and saved exclusions remain intact. Waiting Cargo materials with a called source and an absent destination receive a pickup-only stop assignment; its label includes the destination and not called. The four-group preview and Excel retain the true destination without a delivery group or invented stop. Imported names and positions use title case, preserving original source values. Material content remains read only.

## Native frontend update, 1.1.6

`src/cargo_track/theme_tokens.py` is the explicit light/dark semantic color source. `appearance.STYLE_TEMPLATE` names roles; QPalette and status delegates consume the same roles. Hex-value replacement no longer generates the dark stylesheet. Primary text stays white in both themes; checked and focus boundaries use the focus role, preserving the existing visual identity.

Both module headers use the existing brand. Crew Import is the primary ledger action; editable berth drafts emphasize Save draft, while saved formal snapshots emphasize Export Excel. History remains accessible in Version history. The berth editor splits a compact route list from the table. Cell editors appear on demand, and full text remains available through tooltips. Empty preview groups occupy one line; exported Excel keeps its fixed four-section structure.

Use source geometry and native workflows to verify density, rather than a design image alone. Synthetic 100/150/200% scale-factor evidence does not certify physical Windows scaling, screen-reader speech or user task efficiency.

## Expanded voyage route, 1.1.7

Cargo's route uses a height-for-width native layout. Buttons appear left to right in voyage order and wrap into subsequent rows; each button keeps its full ship name, visit number and current marker. Route controls stay in the toolbar above the visits. The route has no scrollbar and takes the height its rows require. Remaining vertical space belongs to the Cargo table. Stop menus and the manual current-stop workflow retain their original identities and commands.

Implementation: src/cargo_track/route_layout.py and ui.py. Native fixture, packaged window and upgrade evidence: output/route-overview-20261007/全航程展开与验证说明.md and release/release_validation-1.1.7.json.


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

## 2026-10-12：1.2.0 已确定的工作区

本节替代早期页面布局说明。两页采用已选定的石墨色界面，同时兼容用户现有 Light / Dark 和字号设置。Cargo 左侧完整显示靠船顺序，台账操作位于表格上方；Status 合并状态与范围，Current stop 仅开放待办筛选，On my vessel 固定 On Board。Completed Date 通过 More 显示，单页不显示分页控件。用户删除的提示、所选货物摘要和 Local ledger ready 不恢复。

Personnel 采用路线、人员、站点预览三栏。页面和生成对话框不显示货物行；原有 Cargo 关联仍保留在计划与四操作行 Excel 中。Pick up / Drop 分别选择到访，完整组合仍由原有路线规则验证；失效组合不被静默替换。站点 Comments 保存在版本、恢复副本及 Excel 中。小窗口按需展开站点预览，长路线分列显示，船名完整换行。

不以同名推断同一人员，不改变两库数据权限和不可变版本。真实 Qt 截图、交互及打包证据见 `design-qa.md`、`output/approved-ui-20261011/更新与验证说明.md` 与 `release/release_validation-1.2.0.json`。

## 2026-10-12：Dashboard 原生实现（1.2.1）

采用用户选定的 Silver precision：银白底、白色区块、细边线和蓝色当前状态；深色使用现有石墨色语义主题。当前船名小于 Overview 标题，沿用 Inter、10／11／12 pt 设置和现有品牌。上方显示当前站、待收／待交数量及全台账状态，下方为 Cargo 动作表和当前站人员。人数相对当前站船舶，保留明确 Boarding／Leaving 文案、姓名与职位。

人员表固定高度，页签与人数保持可见；完整名单为原生右侧侧栏，包含范围、固定总数、筛选、搜索、排序、关闭及空结果状态。较窄窗口堆叠下方两块并纵向滚动，维持必要列宽；不会以缩小文字来塞入全部名单。原生实现遵循 Qt 字体、主题和控件行为，不承诺生成图逐像素复制。源设计、实际截图及联合对比保存在 `output/dashboard-release-20261012/`，验收见 `design-qa.md`。
