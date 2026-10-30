# MarineOps 1.2.11

MarineOps is an offline Windows desktop application for cargo transfers, personnel movements, voyage planning and berthing plans. It opens Dashboard by default; Cargo and Personnel retain separate workflows and SQLite databases.

The 1.2.8 UI update adds a charcoal appearance and a shared left navigation for Dashboard, Cargo and Personnel. Voyages is available on Dashboard; Fleet and About are available under Settings. The Cargo route wraps horizontally and preserves individual visits and manual reordering. Existing theme preferences remain in effect; use the appearance controls to choose Dark. Version 1.2.9 includes the latest Live Blur interface and removes unused Inter fonts from its packages.

## Install or run

- Installer: `release/MarineOps-Setup-1.2.11.exe`.
- Portable: extract `release/MarineOps-1.2.11-Windows-x64.zip`, then run `MarineOps/MarineOps.exe`. Keep `_internal` alongside the executable.
- Use `--cargo` or `--personnel` to open a workspace directly.

Installation is per user. Business data stays in `%LOCALAPPDATA%/Cargo Track/Cargo Track` unless changed in Settings. The legacy directory, preferences and activation identity are retained for upgrades. Set `CARGO_TRACK_DATA_DIR` to an independent folder for isolated validation.

## Changes in 1.2.8

Cargo writes a durable recovery record before replacing its database. If restore or rollback is interrupted, reopening blocks until the preserved ledger has been recovered. Recovery copies remain available; the app will not silently create a new empty ledger in that state.

Manual and automatic plans share independent output validation at publication and formal export. Missing, duplicate, misplaced or discontinuous actions are rejected while supported initial loading, collection-only material tasks and reviewed Complete-plan history remain valid. Drafts may retain review issues; saved historical versions remain immutable.

Personnel opens its database and reads lists, import previews and selected versions asynchronously. Forms and editors use detached selected-roster data; source checks run before actions and publication rechecks current sources in the database worker. Previous read results cannot replace a newer selection.

Current package checks no longer require an old release ZIP. Upgrade validation is a separate operation with an explicit previous version. Static package success alone does not imply an installation or upgrade test was performed.

## Run from source

Use Python 3.12 on Windows. Install the pinned application dependencies from `requirements.txt`; `requirements-build.txt` additionally pins the build tools.

```powershell
python -m venv .venv-package
.\.venv-package\Scripts\python.exe -m pip install -r requirements-build.txt
$env:PYTHONPATH = "src"
.\.venv-package\Scripts\python.exe -m cargo_track.main
```

## Verify and build

```powershell
powershell -NoProfile -File tools/check_project.ps1
.\.venv-package\Scripts\python.exe tools/build_release.py
.\.venv-package\Scripts\python.exe tools/verify_workspace_release.py
```

The check entry point verifies pinned dependencies, runs all unit/regression tests, and renders the three native workspace headers with isolated data. `-Jobs 4` runs test modules in independent processes; the default uses one discovery process. `-SkipNative` explicitly omits the native smoke. Test logs and reports are written to versioned output folders.

The package verifier compares every ZIP entry with the clean build, checks the embedded installer payload, and compares frozen Python modules with current source. Its default result explicitly marks upgrade validation `NOT_RUN`.

To test installation, portable startup, single-instance behavior and data-preserving upgrade from an available previous release:

```powershell
powershell -NoProfile -File tools/verify_current_upgrade.ps1 -PreviousVersion 1.2.8
```

This requires both installer and portable artifacts for that previous version. The check creates fictional data, a workspace installation directory and a workspace test-desktop folder. It does not replace the user's installed application or live ledgers. Missing baseline artifacts are reported as an error for this upgrade check.

To attach measured evidence to the current release report, pass `--test-log`, `--native-report` and `--package-report` to `verify_workspace_release.py`. The upgrade report must name the current version and match its executable hash. The final report is `release/MarineOps-release-validation-1.2.11.json`.

## Product rules and history

- [Current requirements](PRODUCT.md)
- [Release history](CHANGELOG.md)
- [Personnel workflow](Personnel%20Transfer%20Track_实现与使用说明.md)

Cargo status represents confirmed physical cargo operations. Personnel counts describe planned movements and route progress. Keep the separate Backup / Restore functions for the two modules; Excel exports are not database backups.
