"""Build the native application, portable ZIP and standalone Windows setup."""
from pathlib import Path
import os
import json
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from cargo_track import __version__


def main():
    gate = ROOT / 'output' / f'crew-sync-{__version__}' / 'delivery-status.json'
    if gate.exists() and json.loads(gate.read_text(encoding='utf-8')).get('packaging_allowed') is False:
        raise RuntimeError('Packaging is paused until the user-confirmed final MarineOps logo is recorded in ' + str(gate))
    import PySide6
    if PySide6.__version__ != '6.8.3':
        raise RuntimeError('Release builds require pinned PySide6 6.8.3. Run .venv-package/Scripts/python.exe tools/build_release.py.')
    release=ROOT/"release"
    release.mkdir(exist_ok=True)
    logs=ROOT/"artifacts"/f"validation-{__version__}"
    logs.mkdir(parents=True,exist_ok=True)
    with (logs/"build.log").open("w",encoding="utf-8") as log:
        subprocess.run([sys.executable,"-m","PyInstaller","--noconfirm","--clean",str(ROOT/"CargoTrack.spec")],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    portable=release/f"MarineOps-{__version__}-Windows-x64.zip"
    folder=ROOT/"dist"/"MarineOps"
    with zipfile.ZipFile(portable,"w",zipfile.ZIP_DEFLATED,compresslevel=8) as archive:
        for file in folder.rglob("*"):
            if file.is_file():archive.write(file,"MarineOps/"+file.relative_to(folder).as_posix())
        archive.writestr("README.txt",f"MarineOps {__version__} Windows x64\n\nRun MarineOps\\MarineOps.exe. Dashboard opens by default, with Light/Dark themes, current cargo actions and planned personnel at the exact manually selected visit. All transfers counts unfinished cargo. Cargo summary counts departure backlog and new records in the current voyage. Personnel progress counts each transfer leg once: planned drop calls before the current call are Completed; current and later calls are Pending. This is plan progress, not execution evidence. Drag Cargo sidebar visits to reorder; current visit identity is preserved. Boarding/Leaving refer to the stop vessel. Latest saved Final plans follow crew changes automatically; earlier snapshots retain their history. Other changed sources still require review. View full list searches names and positions. --cargo opens Cargo directly. Select Personnel to open the independent Personnel Transfer Track and Berthing Plan page. Import .xlsx crew plans, review vessel matches, generate a final berthing plan, adjust its independent stop order, and export Excel. No passenger status operations are required. Cargo records remain managed through the original Cargo page. Personnel uses a separate personnel-transfer.sqlite3 file and its own backup/restore settings. Do not restore a Cargo backup into Personnel. --personnel opens the Personnel page directly.\n\nThe app keeps databases and backups in the user's LocalAppData Cargo Track folder unless changed in the relevant settings. CARGO_TRACK_DATA_DIR selects an independent data directory for validation. The first run is empty; design examples are not live cargo data.\n")
        archive.writestr('MarineOps/AUTO-PLANNING.txt', 'MarineOps 1.2.1 automatic planning update\n\nPersonnel > Berthing plan > Auto plan. Select trip materials, retain required calls or assignments, calculate, review, and adopt. Each actual vessel call counts once; return calls count again. Exact search proves minimum vessel calls, then minimum port calls, under the displayed sufficient-capacity/no-time-window model. Limited searches do not claim optimality. Manual additions and drag ordering remain. Planner actions check complete delivery and undo adoption before later edits. Save a version for Dashboard.\n\nDashboard matches exact personnel visit IDs or unique calls to the current vessel. Multiple independent calls require an explicit Plan visit choice. Boarding joins the stop vessel; Leaving leaves it. Stale-source checks remain active.\n')
        archive.writestr('MarineOps/TEXT-CASING.txt', 'MarineOps 1.2.4 text casing\n\nPersonnel Excel imports and manual entries normalize names and positions while preserving known abbreviations. Hover over imported Name / Position cells for original Excel text. Keep Excel spelling / Keep my spelling bypasses automatic casing and survives reopening. Cargo forms preview the saved description, preserving known abbreviations, units, models and mixed-case brands.\n\nExisting data: Cargo > top More > Normalize existing item names, or Personnel > crew-list More > Normalize existing names / positions. Review and select changes. Originals remain in history. Current Final plans follow crew changes automatically; earlier snapshots retain their text. No reimport is needed.\n')
        archive.writestr('MarineOps/CREW-SYNC.txt', 'MarineOps 1.2.5\n\nSign-on boards at an actual port before delivery. Sign-off is collected before port return. Place Port between the vessel visits for a mid-trip crew change. New direct departures include their departure port. Crew edits, additions, removals and Excel updates automatically refresh the open draft and create a new current version for affected saved Final plans. From and To follow the live crew list. Earlier versions stay available. Dashboard defaults to the latest version and shows planned Boarding/Leaving at the selected call; choose the actual plan visit when repeated calls are ambiguous. Review invalid routes before publication.\n')
    compiler=Path(os.environ["WINDIR"])/"Microsoft.NET"/"Framework64"/"v4.0.30319"/"csc.exe"
    setup=release/f"MarineOps-Setup-{__version__}.exe"
    subprocess.run([str(compiler),"/nologo","/target:winexe","/platform:x64",f"/out:{setup}",
        "/r:System.IO.Compression.dll","/r:System.IO.Compression.FileSystem.dll","/r:System.Windows.Forms.dll","/r:System.Drawing.dll",
        f"/win32icon:{ROOT/'assets/branding/marineops.ico'}",f"/resource:{portable},CargoTrackPayload",
        str(ROOT/"tools/CargoTrackInstaller.cs")],cwd=ROOT,check=True)
    print(f"Built {setup.name} ({setup.stat().st_size} bytes); embedded payload, no companion ZIP required")
    print(f"Built {portable.name} ({portable.stat().st_size} bytes)")


if __name__=="__main__":main()
