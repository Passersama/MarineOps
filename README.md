# Cargo Track 1.0.5 source and UI review

Cargo Track is a single-user Windows desktop ledger for cargo hand-offs between vessels and shore. It keeps each physical cargo identity stable across transfer legs, records the latest confirmed location, and preserves corrections and voids in an audit history.

The Python source, design documents, static UI figures, service tests, and native Qt runtime preview are available in this workspace. A tested Windows 64-bit installer bundle and portable ZIP are available in `release/`. Run release/CargoTrack-Setup-1.0.5.exe directly. Its payload is embedded; installation is per-user and does not require administrator access.

## Run from source

Use Python 3.12 on Windows with the pinned dependencies from `requirements.txt`:

```powershell
$env:PYTHONPATH = "src"
python -m cargo_track.main
```

The application stores its database and backup folder in the current Windows user's local application data directory (`%LOCALAPPDATA%\Cargo Track\Cargo Track`). For an isolated test run, set `CARGO_TRACK_DATA_DIR` to a writable folder. Use **Backup** in the application to create or restore a verified backup. Restore makes a safety copy of the current ledger before replacing it.

## Main workflows

- Add a new cargo record or append the next transfer to a delivered cargo item.
- Pick up and deliver transfers; the application records the completion date in the configured business time zone.
- Review transfer details, confirmed cargo location, prior legs, and audit history.
- Correct or void records with a reason. Historical voyages are read-only; copy one to start a new working route.
- Filter, search, and export the current view to CSV or Excel (`.xlsx`). No Excel import is included.

The first run starts with an empty ledger. Example rows in the design preview are fictional and are not loaded into the application.

## Windows packaging status

The release build uses PyInstaller onedir with PySide6 Essentials 6.8.3. The user-level setup and portable ZIP were tested from a clean directory; the setup embeds the ZIP payload, and the installed app created its SQLite database under an isolated data directory. A second launch activated the first process and exited successfully. The earlier 6.11.2 candidate failed at QtCore import; the pinned 6.8.3 runtime passed both a minimal Qt import check and the full application launch check. See `release/release_validation.json` for the recorded checks and exact package hashes.

## Verify

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python tools/verify_architecture.py
python tools/verify_ui_runtime.py
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


## 1.0.4 current release

Help provides an offline Chinese guide for every main workflow; F1 and contextual Help buttons open the relevant chapter. Settings now switches Light/Dark appearance and 10/11/12 pt fonts immediately, with 11 pt as default. Completed transfers have a visible Delete… action; Deleted records offers Restore…. Status dropdown changes submit directly with no confirmation or correction popup, retaining audit history and service constraints. These rules supersede the 1.0.3 status interaction described above.

26 service tests and 24 native display states passed. The release report records standalone setup, actual desktop shortcut, upgrade preservation and single-instance checks: [1.0.4 validation](./release/release_validation-1.0.4.json). See [light UI](./artifacts/validation-1.0.4/light/main-filled-1.5x.png), [dark UI](./artifacts/validation-1.0.4/dark/main-filled-1.5x.png) and [help](./artifacts/validation-1.0.4/dark/help-filled-1.5x.png).


## 1.0.5 distribution

The setup offers an installation folder field and Browse picker, desktop shortcut and launch options. Choose a dedicated empty folder or the existing Cargo Track installation folder. Cancel makes no installation changes. The portable ZIP requires no installation: extract the entire archive, then run CargoTrack/CargoTrack.exe. Keep _internal alongside the executable. Both editions keep business data in the user data directory by default; Settings can change database and backup folders.
