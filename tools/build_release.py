"""Build the native application, portable ZIP and standalone Windows setup."""
from pathlib import Path
import os
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from cargo_track import __version__


def main():
    release=ROOT/"release"
    release.mkdir(exist_ok=True)
    logs=ROOT/"artifacts"/f"validation-{__version__}"
    logs.mkdir(parents=True,exist_ok=True)
    with (logs/"build.log").open("w",encoding="utf-8") as log:
        subprocess.run([sys.executable,"-m","PyInstaller","--noconfirm","--clean",str(ROOT/"CargoTrack.spec")],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    portable=release/f"CargoTrack-{__version__}-Windows-x64.zip"
    folder=ROOT/"dist"/"CargoTrack"
    with zipfile.ZipFile(portable,"w",zipfile.ZIP_DEFLATED,compresslevel=8) as archive:
        for file in folder.rglob("*"):
            if file.is_file():archive.write(file,"CargoTrack/"+file.relative_to(folder).as_posix())
        archive.writestr("README.txt",f"Cargo Track {__version__} Windows x64\n\nRun CargoTrack\\CargoTrack.exe. The app keeps the database and backups in the user's LocalAppData Cargo Track folder. CARGO_TRACK_DATA_DIR selects an independent data directory. The first run is empty; design examples are not live cargo data.\n")
    compiler=Path(os.environ["WINDIR"])/"Microsoft.NET"/"Framework64"/"v4.0.30319"/"csc.exe"
    setup=release/f"CargoTrack-Setup-{__version__}.exe"
    subprocess.run([str(compiler),"/nologo","/target:winexe","/platform:x64",f"/out:{setup}",
        "/r:System.IO.Compression.dll","/r:System.IO.Compression.FileSystem.dll","/r:System.Windows.Forms.dll","/r:System.Drawing.dll",
        f"/win32icon:{ROOT/'assets/branding/cargo-track.ico'}",f"/resource:{portable},CargoTrackPayload",
        str(ROOT/"tools/CargoTrackInstaller.cs")],cwd=ROOT,check=True)
    print(f"Built {setup.name} ({setup.stat().st_size} bytes); embedded payload, no companion ZIP required")
    print(f"Built {portable.name} ({portable.stat().st_size} bytes)")


if __name__=="__main__":main()
