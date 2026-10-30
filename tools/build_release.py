"""Build the native application, portable ZIP and standalone Windows setup."""
from pathlib import Path
import os
import json
import subprocess
import sys
import zipfile
import hashlib
import importlib.metadata

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
    pins={}
    for filename in ('requirements.txt','requirements-build.txt'):
        for line in (ROOT/filename).read_text().splitlines():
            if '==' in line:
                name,version=line.strip().split('==');pins[name]=version
    for name,version in pins.items():
        if importlib.metadata.version(name)!=version:raise RuntimeError('Build dependency differs from its pin: '+name)
    metadata=(ROOT/'tools/windows-version.txt').read_text()
    installer_source=(ROOT/'tools/CargoTrackInstaller.cs').read_text(encoding='utf-8')
    if (f"'FileVersion', '{__version__}'" not in metadata or f"'ProductVersion', '{__version__}'" not in metadata
            or f'AssemblyVersion("{__version__}.0")' not in installer_source
            or f'AssemblyFileVersion("{__version__}.0")' not in installer_source):
        raise RuntimeError('Windows version metadata must match cargo_track.__version__.')
    release=ROOT/"release"
    release.mkdir(exist_ok=True)
    logs=ROOT/"artifacts"/f"validation-{__version__}"
    logs.mkdir(parents=True,exist_ok=True)
    inputs=list((ROOT/'src').rglob('*.py'))+list((ROOT/'assets').rglob('*'))
    inputs=[p for p in inputs if p.is_file() and '__pycache__' not in p.parts]
    inputs.extend(ROOT/p for p in ('CargoTrack.spec','tools/windows-version.txt','tools/CargoTrackInstaller.cs',
                                   'requirements.txt','requirements-build.txt'))
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    (logs/'build-input.json').write_text(json.dumps({'version':__version__,'dependencies':pins,
        'source_manifest':hashes},indent=2),encoding='utf-8')
    with (logs/"build.log").open("w",encoding="utf-8") as log:
        subprocess.run([sys.executable,"-m","PyInstaller","--noconfirm","--clean",str(ROOT/"CargoTrack.spec")],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected for name,expected in hashes.items()):
        raise RuntimeError('Build inputs changed while compiling. Rebuild a stable candidate.')
    portable=release/f"MarineOps-{__version__}-Windows-x64.zip"
    folder=ROOT/"dist"/"MarineOps"
    with zipfile.ZipFile(portable,"w",zipfile.ZIP_DEFLATED,compresslevel=8) as archive:
        for file in folder.rglob("*"):
            if file.is_file():archive.write(file,"MarineOps/"+file.relative_to(folder).as_posix())
        archive.writestr("README.txt",f"MarineOps {__version__} Windows x64\n\nRun MarineOps\\MarineOps.exe. Dashboard opens by default, with Light/Dark themes, current cargo actions and planned personnel at the exact manually selected visit. All transfers counts unfinished cargo. Cargo summary counts departure backlog and new records in the current voyage. Personnel progress counts each transfer leg once: planned drop calls before the current call are Completed; current and later calls are Pending. This is plan progress, not execution evidence. Drag Cargo sidebar visits to reorder; current visit identity is preserved. Boarding/Leaving refer to the stop vessel. Latest saved Final plans follow crew changes automatically; earlier snapshots retain their history. Other changed sources still require review. View full list searches names and positions. --cargo opens Cargo directly. Select Personnel to open the independent Personnel Transfer Track and Berthing Plan page. Import .xlsx crew plans, review vessel matches, generate a final berthing plan, adjust its independent stop order, and export Excel. No passenger status operations are required. Cargo records remain managed through the original Cargo page. Personnel uses a separate personnel-transfer.sqlite3 file and its own backup/restore settings. Do not restore a Cargo backup into Personnel. --personnel opens the Personnel page directly.\n\nThe app keeps databases and backups in the user's LocalAppData Cargo Track folder unless changed in the relevant settings. CARGO_TRACK_DATA_DIR selects an independent data directory for validation. The first run is empty; design examples are not live cargo data.\n")
    compiler=Path(os.environ["WINDIR"])/"Microsoft.NET"/"Framework64"/"v4.0.30319"/"csc.exe"
    setup=release/f"MarineOps-Setup-{__version__}.exe"
    subprocess.run([str(compiler),"/nologo","/target:winexe","/platform:x64",f"/out:{setup}",
        "/r:System.IO.Compression.dll","/r:System.IO.Compression.FileSystem.dll","/r:System.Windows.Forms.dll","/r:System.Drawing.dll",
        f"/win32icon:{ROOT/'assets/branding/marineops.ico'}",f"/resource:{portable},CargoTrackPayload",
        str(ROOT/"tools/CargoTrackInstaller.cs")],cwd=ROOT,check=True)
    print(f"Built {setup.name} ({setup.stat().st_size} bytes); embedded payload, no companion ZIP required")
    print(f"Built {portable.name} ({portable.stat().st_size} bytes)")


if __name__=="__main__":main()
