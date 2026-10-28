# MarineOps 1.2.6

This repository contains the 1.2.6 source and a subsequent pre-publication security hardening patch. The patch rejects unsupported SQL triggers/views in backups, blocks network/device paths in plan-source reads, renders imported labels as literal text, and checks both current/legacy program directories during upgrades. Diagnostic scripts require explicit private inputs. Generated validation output, business databases, backups and installers are excluded from Git. Existing 1.2.6 packages do not include this source patch and must be rebuilt before distribution.

1.2.6 fixes Current stop personnel becoming blank after Cargo pickup/delivery in a saved combined plan. Final plans track crew-source dependencies separately from material execution; legacy snapshots are accepted only when complete command receipts establish that intervening changes affected Cargo execution rather than the route, fleet or settings. Current roster edits continue to refresh the view, and shared-list automatic saves retain the most recently saved plan family. Actual route changes and explicit stale historical selections still require review. Dashboard About is now at the far right, after Settings, with review messages above the counts. Install `release/MarineOps-Setup-1.2.6.exe` or use the portable ZIP; evidence is in `output/dashboard-fix-1.2.6/更新与验证说明.md` and `release/MarineOps-release-validation-1.2.6.json`.

The approved blue/turquoise ribbon logo is integrated in all three workspaces, About, Windows application icons and the installer. Small-window Cargo commands move into More so the logo and workspace navigation remain visible. Final verification and artifact hashes are recorded in `release/MarineOps-release-validation-1.2.6.json` after successful release acceptance.

The 1.2.5 architecture audit removes whole-roster scans from unrelated writes, limits plan payload decoding to selected/current snapshots, shares snapshot validation, adds optional query indexes and closes an unexpected-error transaction rollback gap. No runtime dependencies were added. Scope, measurements and remaining maintenance limits are in `output/architecture-audit-1.2.5/软件架构与数据逻辑审核.md`.

MarineOps replaces the public Cargo Track name while keeping its data, settings and activation identity compatible. The interface and offline Help are English. About is accessible from Dashboard, Cargo and Personnel and includes the product description and version.

1.2.5 schedules Sign-on at an actual port pickup before vessel delivery, and Sign-off at vessel pickup before port return. New direct departures include their departure port; intermediate port calls separate the two groups, including repeated visits to the same vessel. Auto plan uses the same real port-pickup rule. Crew edits, additions, removals and imports update the open draft and save a new current version for each affected saved Final plan automatically, including From / To. Earlier versions remain available. Dashboard follows the latest current plan; automatic mode can also refresh older roster snapshots read-only. Invalid routes remain visible for review. Install `release/MarineOps-Setup-1.2.5.exe`; verification details are in `output/crew-sync-1.2.5/更新与验证说明.md`.

1.2.4 adds field-specific automatic casing for personnel Excel imports, manual crew entries and Cargo descriptions. Names retain apostrophes and hyphens; positions preserve NAV / QC / HSE and other known abbreviations; Cargo protects known abbreviations, units, model identifiers and mixed-case brands. Import cells retain original text in tooltips, and manual forms preview the saved value. **Keep my spelling** / **Keep Excel spelling** bypasses automatic casing and survives refresh and reopening. Existing data can be reviewed under **Cargo → top More → Normalize existing item names** or **Personnel → crew-list More → Normalize existing names / positions**. Select changes before applying; original text remains in audit history, identities and routes remain stable, and saved plan versions retain their historical text. Regenerate and save a plan after changing names. Install `release/CargoTrack-Setup-1.2.4.exe` or extract the matching portable ZIP. See `output/text-case-1.2.4/更新与验证说明.md` and `release/release_validation-1.2.4.json`.

1.2.3 fixes the audit findings: removed crew legs retain historical chain snapshots while active-chain consistency is checked before writes commit; Link legs now offers a suggested order with drag / Move up / Move down review. Long personnel groups and comments export as complete continuation rows/pages. Berthing Plan uses physical A4 portrait at 100% with bounded column widths. Cargo exports keep all nine columns on A4 landscape; very long cells get a separate Cargo Print view. Personnel exports retain the full 19-column Transfer Details data and add a Transfer Print view containing business fields and comments. See `output/audit-fixes-1.2.3/更新与验证说明.md` and `release/release_validation-1.2.3.json`.

1.2.2 adjusts Berthing Plan Excel exports for A4 portrait: column C is 60 characters wide, wrapped row heights follow the actual column widths, and page breaks retain complete stop blocks where possible. Next leg / Link legs require a later actual pickup call, including port and transfer-vessel origins; excluding the preceding leg blocks the continuation. Linking existing rows recalculates changed leg assignments. Re-export a saved plan to apply the print layout; regenerate and save to apply route fixes. Validation evidence: `output/excel-legs-20261025/`.

The updated 1.2.1 includes **Personnel → Berthing plan → Auto plan**. Select this trip's materials, retain required visits or existing assignments, calculate and review a complete route, then adopt it. Every actual vessel call counts once; returning to the same vessel counts again. Exact search proves minimum calls under the displayed sufficient-capacity/no-time-window model, while limited searches identify candidates without claiming a minimum. Manual additions and drag ordering remain available. Planner actions offer full-delivery checks and immediate undo before further edits. Save a plan version for Dashboard and Excel.

Dashboard personnel now supports independent Personnel visit IDs: it matches the exact visit first, a unique same-vessel call second, and asks for a specific plan visit when repeated calls are ambiguous. Boarding joins the stop vessel; Leaving leaves it. Stale sources still clear counts. Update evidence is in `output/berth-optimizer-release-20261012/更新与验证说明.md` and the regenerated `release/release_validation-1.2.1.json`.

The Dashboard defaults to **Latest saved plan (automatic)** and follows newly saved plans. Explicit historical version selections are retained and report changed sources when stale, instead of silently displaying outdated personnel.

The 1.2.1 legacy-roster hotfix normalizes missing or blank passenger leg numbers at read time and writes integer leg numbers in new snapshots. Older lists mixed with newly linked legs can again preview, edit, save and export without the `int`/`str` comparison error. Existing roster payloads and saved history are retained. See `output/personnel-leg-hotfix-20261012/旧人员段编号兼容修复说明.md`.

Cargo Track is a single-user Windows desktop ledger for cargo hand-offs between vessels and shore. It keeps each physical cargo identity stable across transfer legs, records the latest confirmed location, and preserves corrections and voids in an audit history.

The Python source, design documents, static UI figures, service tests, and native Qt runtime preview are available in this workspace. Windows 64-bit installer and portable ZIP are available in `release/`. Run release/MarineOps-Setup-1.2.6.exe directly. Its payload is embedded; installation is per-user and does not require administrator access.

1.2.1 builds on 1.2.0 and opens the native Dashboard by default. It shows the manually selected visit, current cargo actions and saved personnel plan, with Light/Dark themes and a searchable full roster drawer. Boarding/Leaving refer to joining/leaving the stop vessel, and repeated visits retain distinct identities. Cargo ledger totals cover all non-deleted transfers because cargo records have no voyage ownership field. Personnel numbers are planned movements from the selected saved version; changed sources clear the old numbers. Use `--cargo` or `--personnel` for direct startup. See `output/dashboard-release-20261012/软件审核与发布说明.md` for scope and evidence.

The 1.1.8 update adds explicitly linked personnel legs, later-visit pickup, optional port calls, transfer-vessel origin matching by destination only, and the four-row Excel plan layout. It includes the updated maritime logo in the header and Windows icons. See `output/personnel-routes-20261011/人员分段接送与导出更新说明.md` and `release/release_validation-1.1.8.json`.

The 1.1.9 workspace update unifies Cargo/Personnel navigation, adds crew-list rename and history-list clearing, supports clearing the current stop with a second click, and protects unsaved drafts on workspace switches. See `output/workspace-audit-20261011/软件审核与修复报告.md` and `release/release_validation-1.1.9.json`.

Current requirements are in `PRODUCT.md`. The current verification entry points below supersede historical release notes. The full route update record is `output/route-overview-20261007/全航程展开与验证说明.md`; measured release evidence is `release/release_validation-1.1.7.json`. Earlier audit and release records remain available.

The 1.1.7 route shows all voyage visits directly, wrapping to multiple rows without horizontal scrolling. Long names also wrap, while manual current-stop selection and visit menus remain available. 120 tests and isolated native installer, portable and 1.1.6 upgrade checks passed. See the current update record above for measured 13/24-visit visibility and scope.

## Run from source

Use Python 3.12 on Windows with the pinned dependencies from `requirements.txt`:

```powershell
$env:PYTHONPATH = "src"
python -m cargo_track.main
```

The application stores its database and backup folder in the current Windows user's local application data directory (`%LOCALAPPDATA%\Cargo Track\Cargo Track`). For an isolated test run, set `CARGO_TRACK_DATA_DIR` to a writable folder; the packaged entry point also isolates UI preferences there. Use **Backup** in the application to create or restore a verified backup. Restore makes a safety copy of the current ledger before replacing it.

## Main workflows

- Add a new cargo record or append the next transfer to a delivered cargo item.
- Pick up and deliver transfers; the application records the completion date in the configured business time zone.
- Review transfer details, confirmed cargo location, prior legs, and audit history.
- Correct or void records with a reason. Historical voyages are read-only; copy one to start a new working route.
- Filter, search, and export the current Cargo view to CSV or Excel (`.xlsx`). Personnel Excel import is available on the separate Personnel page.

The first run starts with an empty ledger. Example rows in the design preview are fictional and are not loaded into the application.

## Windows packaging status

The release build uses PyInstaller onedir with PySide6 Essentials 6.8.3. The user-level setup and portable ZIP were tested from a clean directory; the setup embeds the ZIP payload. Native launch, legacy data preservation, shortcut migration and old/new single-instance activation passed. The earlier 6.11.2 candidate failed at QtCore import; the pinned 6.8.3 runtime passed the application launch check. See `release/MarineOps-release-validation-1.2.6.json` for the recorded checks and exact package hashes.

## Verify

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python tools/verify_architecture.py
python tools/verify_ui_runtime.py
python tools/verify_crew_final_runtime.py --plan-load-regression
python tools/verify_audit_fixes_runtime.py
```

The service tests use temporary on-disk SQLite files. The UI smoke check starts the native Qt window offscreen, checks the worker and a real transfer action, and saves a preview image. Static design validation and detailed scope notes are recorded in `tools/` and the two Chinese design documents.

## Project documents

- [Software and architecture plan](./货物追踪软件方案.md)
- [UI design plan](./货物追踪软件_UI设计方案.md)
- [Technical review and validation](./货物追踪软件_技术审阅.md)
- [Runtime UI preview](./CargoTrack-UI-runtime.png)

## 1.0.1 validation and display repair

The route area, Fleet list and unused table header now use an explicit light Fusion palette, including when Windows prefers a dark theme. The approved Logo appears in the app header, executable, setup and desktop shortcut. Search and filters use separate rows; window and dialog sizes fit the available screen. Ctrl+F and Ctrl+N are implemented.

Validation passed: 19 service tests (10 restore fault scenarios), 13 reference architecture checks, native display checks at effective 100%, 125%, 150%, 175% and 200% DPI in empty and filled states, a real Windows Desktop shortcut launch, standalone setup, upgrade data preservation and single-instance launch. Windows accessibility exposes names, table headers, record identities and statuses, including the Fleet list. Actual Narrator/NVDA speech has not been listened to; high contrast and physical multi-monitor transitions remain device checks.

See release/release_validation-1.0.1.json and artifacts/validation-1.0.1/ for detailed evidence. Tests use isolated fictional data.

## 1.0.2 appearance

macOS-inspired native controls: thin borderless chevron areas, rounded inputs and panels, segmented tabs, blue primary actions, quieter table backgrounds and slim scrollbars. The original Logo and business flows are retained. Effective DPI and menu checks passed at 100–200%. See artifacts/validation-1.0.2 and release/release_validation-1.0.2.json.

## 1.0.3 settings and record management

Settings offers Windows-style time zone choices and independent database/backup folder pickers. A database folder change copies and validates the ledger before switching, retains the original and refuses an existing target database. Paths persist locally; CARGO_TRACK_DATA_DIR remains the test override. Select a transfer to use the bottom status dropdown; backwards/jump changes require a correction reason. Fleet and Voyages now support deletion with retained history and protection for active vessel references. Inter Regular/SemiBold and its OFL licence are bundled.

26 service tests and five effective DPI scales passed, including real Qt settings, status, relocation and deletion workflows. See artifacts/validation-1.0.3 and release/release_validation-1.0.3.json.


## 1.0.4 historical release

Help provides an offline Chinese guide for every main workflow; F1 and contextual Help buttons open the relevant chapter. Settings now switches Light/Dark appearance and 10/11/12 pt fonts immediately, with 11 pt as default. Completed transfers have a visible Delete… action; Deleted records offers Restore…. Status dropdown changes submit directly with no confirmation or correction popup, retaining audit history and service constraints. These rules supersede the 1.0.3 status interaction described above.

26 service tests and 24 native display states passed. The release report records standalone setup, actual desktop shortcut, upgrade preservation and single-instance checks: [1.0.4 validation](./release/release_validation-1.0.4.json). See [light UI](./artifacts/validation-1.0.4/light/main-filled-1.5x.png), [dark UI](./artifacts/validation-1.0.4/dark/main-filled-1.5x.png) and [help](./artifacts/validation-1.0.4/dark/help-filled-1.5x.png).


## 1.0.5 distribution

The setup offers an installation folder field and Browse picker, desktop shortcut and launch options. Choose a dedicated empty folder or the existing installation folder. Cancel makes no installation changes. For the current MarineOps portable ZIP, extract the entire archive, then run MarineOps/MarineOps.exe. Keep _internal alongside the executable. Both editions keep business data in the user data directory by default; Settings can change database and backup folders.

## 1.1.1 Crew change information and final Berthing Plan

Select **Personnel** in the Cargo header. Import a dual Sign-off/Sign-on workbook or a standard Name/Position/From/To/Date table. Review vessel matches before saving. Unambiguous abbreviations such as CHA, INN and Niger resolve to fleet vessel names; ambiguous names need an explicit alias in Personnel Settings. Chinese departure-date headers are recognized as dates. Ignored identity, company, laptop and Mark columns never enter personnel payloads.

The personnel page is a crew list with add, edit and remove actions. It has no passenger status or pickup/drop execution controls. Append preserves entries absent from the file. **Replace selected crew list** permits reimporting the same file, archives superseded entries after confirmation, and retains saved plan versions. Personnel and plan data use a separate database with independent backup, restore and relocation settings.

**Generate final plan** includes imported crew directly: Sign-on is dropped at its vessel; Sign-off is picked up at its vessel and dropped at the configured final Port. Crew dates do not silently exclude records. The route starts from Cargo's selected Voyage. Missing matched crew vessels are added to the new plan, where stops can be added, removed or reordered independently. Repeated vessels default to the first feasible visit and offer a stop-assignment choice. Select cargo explicitly to include materials. Every vessel and final Port has four groups; material counts use records and entries share a line. Departure port is excluded.

Preview, save an immutable version, then export the **Berthing Plan** and **Transfer Details** Excel sheets. Revising creates a new version with the current crew list and independent route; previous snapshots remain available. Cargo business files and data remain unchanged.

See [Chinese usage notes](./Personnel%20Transfer%20Track_实现与使用说明.md), [updated scope](./Personnel%20Transfer%20Track_设计方案.md), and [1.1.1 validation](./release/release_validation-1.1.1.json). Tests and native checks use isolated fictional data. The supplied workbook is read only. Package shortcut verification uses a workspace test-desktop folder.

## 1.1.2 Saved plan loading and editing

**Load version** refreshes historical Complete/Remaining versions into an editable Final draft using current crew and Cargo data, retaining the original snapshot. Reviews appear once per record; clicking a row shows the reasons and From/To. Missing vessel messages identify the stop to add. **Edit plan** edits the displayed plan and offers Add crew entry, Edit selected crew and Remove from plan. Uncheck/recheck personnel rows to exclude or include people; the draft retains material selection and content as read only. Explicit exclusions and exact repeated-visit assignments persist when reopening. Cargo is read only throughout.

Crew list selection now shows the list name. **Reference Voyage** names the Cargo route. **Berthing plan date** lives on the Berthing plan tab with its Excel heading/file-name purpose stated. It is separate from each person's Crew change date. A saved snapshot's date is read only; change the editable draft's date before saving a new version.

68 automated checks and real native button regressions cover the repair. [1.1.2 validation](./release/release_validation-1.1.2.json) records the package checks and unchanged Cargo comparison. Historical 1.1.1 behavior above is superseded where it conflicts with this section.

The final 1.1.2 repair also embeds **Edit draft directly** on the main plan page. Double-click passenger names or positions; add or remove passengers there. Saving and export collect the current edits even without a preview step. Only personnel is editable in the draft: Cargo material content is read only and its original selection is retained. Saved versions remain immutable; Edit plan opens a new inline draft. This supersedes the earlier modal-edit description.

### Personnel defaults in 1.1.3

Imported names and positions use title case (ALEX MORGAN / NAV QC becomes Alex Morgan / Nav Qc), including existing imported crew when displayed or used in new plans. Records with feasible stop assignments are checked automatically in a new plan, and newly feasible records are checked after route changes; manual exclusions and saved selections persist. Waiting materials can be collected at a called source vessel even when the destination is outside this plan: show Pick up Materials to the actual destination, without inventing a delivery or adding that destination. Material content remains read only from Cargo.

### Shared port, display numbering and Refresh in 1.1.4

On Shore and xx port identify the same port. Cargo Settings and Personnel Settings now edit one shared **Port name** stored in Cargo; the default is `xx port`. Existing SHORE IDs and transfer references are retained. Cargo locations, personnel routes and new berthing plans use that name; saved plan snapshots and original transfer evidence stay fixed. Legacy Excel labels `On Shore` and `xxPort` still resolve to the same port. The Cargo add/edit form now correctly includes the port location.

**NO** is the current filtered list's display sequence starting at 1; subsequent pages continue the sequence. **Cargo ID** keeps its stable continuous identity. CSV and Excel exports number their filtered rows from 1 and respect the chosen sort order. Cargo has a **Refresh** button beside Clear filters and an **F5** shortcut; refreshing retains filters and returns to the first page.

The original 2026-10-07 audit confirmed eight boundary findings; 1.1.4 repaired the missing-port selector. The other seven findings were repaired in 1.1.5. The original reproduction evidence remains in `output/audit-20261007/`.

### Audit repairs and coordinated workflows in 1.1.5

Both live databases and their configured paths are protected from backups and exports, including paths to an unopened companion module. Personnel backup restore validates the complete supported schema and application payloads before replacing data; a safety copy is retained. If rollback also fails, writes are blocked and the recovery copy is identified.

Restoring a database, changing storage or switching crew lists invalidates old editors and pending read results. Drafts record database identity, recovery generation and the complete roster scope. A changed or restored roster cannot publish an old partial draft. Cargo has a permanent ledger identity; plan dependencies cover relevant voyage, locations, selected transfers and shared settings, so unrelated historical cargo changes do not invalidate a plan.

The plan records selected entries, explicit user exclusions and automatically unavailable entries separately. Unavailable crew have named review reasons and prevent publication until resolved or explicitly excluded. Exclusions are visible in preview and Excel. Previously chosen visits remain marked unavailable when removed; no silent reassignment occurs, including material assignments in an inline draft. Explicit crew edits supersede draft overlays field by field; unrelated draft edits survive route changes.

Import identity includes worksheet, column mapping, parser version, target list and operation; different worksheets can be appended while identical submissions are rejected. Reviewed complete replacement remains repeatable after the roster changes. Import streams rows and hashes files in chunks. Personnel writes, settings, backup and restore run on one dedicated executor owning its SQLite connection. Cargo business settings save in one transaction; appearance and storage relocation are subsequent operations. Historical plan snapshots and Cargo IDs remain unchanged.

### Frontend workflow update in 1.1.6

Cargo and Personnel retain the same branding, font settings and explicit light/dark semantic colors. The route remains visible; infrequent route administration and plan history are compacted. Personnel uses model-backed tables, native checks and on-demand assignment editors. Search is debounced and keeps row identities across refreshes. Long routes, vessel names and cell content have complete tooltips.

**Save draft** keeps an unfinished plan, including review issues. **Save plan version** publishes only after checks pass. **Export Excel** chooses the destination before publishing an unsaved draft; cancelling does not create a version. If file output fails after publication, the saved version remains available and the error explains this. Saved drafts must be edited and reviewed before formal export.

Unsaved list switches, generation, version loading and window closing offer Save draft / Discard / Cancel. Cell name/position edits have Ctrl+Z and Ctrl+Shift+Z. Source invalidation preserves local edits in `draft-recovery/*.json`; Recover draft rebuilds against current sources, without bypassing publication checks. Writes show progress and disable conflicting controls while leaving the page readable.

Verification: `tests/test_frontend.py`, the complete test suite, the two native workflow tools above, and `output/frontend-update-20261007/`. Source geometry uses synthetic scale factors; physical multi-monitor transitions and actual Narrator speech remain unverified.

## Approved workspaces, 1.2.0

Cargo and Personnel implement the selected graphite workbenches. Cargo uses a compact stop sidebar, a single status filter, actions above the ledger, optional Completed Date and pagination only for multiple pages. Long voyages use additional sidebar columns. Current stop remains a reversible manual selection.

Personnel shows passenger information, separate Pick up / Drop visit selectors, a selected-stop preview and versioned stop comments. The generation dialog hides Cargo rows; existing Cargo associations remain in the four-group Excel contract. At narrow widths, Stop preview opens the side panel on demand. More contains Generate plan, Edit plan, Save draft, Full personnel preview and Recover draft. Save version publishes after review; unfinished plans use More → Save draft.

Source and native visual checks: output/approved-ui-20261011/更新与验证说明.md and design-qa.md. Installer and portable package: release/CargoTrack-Setup-1.2.0.exe and release/CargoTrack-1.2.0-Windows-x64.zip.

## Current verification, 1.2.3

The 1.2.3 evidence is `release/release_validation-1.2.3.json`. Reproduce targeted checks with `tools/verify_audit_fixes_runtime.py`, `tools/verify_audit_fixes_excel.ps1`, `tools/verify_audit_fixes_pdf.py`, and `tools/verify_print_legs_release.ps1`. The Excel checks open fictional workbooks read-only; the PDF checks inspect real physical A4 dimensions, repeated headers and complete 120-person / long-comment stress outputs.

## Historical verification, 1.2.2

The print and multi-leg update is recorded in `release/release_validation-1.2.2.json` and `output/excel-legs-20261025/更新与验证说明.md`. It includes source regressions, fictional Excel exports, native Excel print checks, and isolated installer/portable checks. Run `tools/verify_excel_portrait_legs.py` and `tools/verify_print_legs_release.ps1` to reproduce the targeted fixtures and package checks.

## Historical verification, 1.2.1

The previous release evidence is `release/release_validation-1.2.1.json`, with the audit report in `output/dashboard-release-20261012/软件审核与发布说明.md`. Run `tools/verify_dashboard_runtime.py` for the real native Dashboard, `tools/verify_dashboard_legacy_ui.py` for retained Cargo/Personnel workflows, and the Dashboard release/upgrade/first-run PowerShell helpers for isolated packaged checks. That historical release reported 172 test cases. Use a writable TEMP/TMP and PYTHONPATH=src. Historical evidence remains under its original version and date.
