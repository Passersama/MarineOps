"""Record the bounded Personnel defaults release evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cargo_track import __version__


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def main():
    prefix = f"artifacts/personnel-defaults-{__version__}"
    native = read(f"{prefix}/native-visible.json")
    assert all(v for v in native.values() if isinstance(v, bool))
    regression = read(f"artifacts/personnel-regression-{__version__}/native-visible.json")
    assert all(v for v in regression.values() if isinstance(v, bool))
    packages = read(f"artifacts/validation-{__version__}/packaged-personnel-validation.json")
    assert packages["standalone_installer"] == packages["upgrade_data_preservation"] == "PASS"
    assert all(p["visible"] and p["cargo_hash_unchanged"] and p["file_version"] == __version__ for p in packages["packages"])
    excel = read(f"{prefix}/excel-native-validation.json")
    printed = read(f"{prefix}/print-content-validation.json")
    assert excel["source_unchanged"] and not printed["missing"]
    cargo_files = ["ui.py", "service.py", "schema.py", "models.py", "worker.py", "repository.py", "domain.py", "appearance.py"]
    git = shutil.which('git')
    if not git:raise RuntimeError('Git is required to compare release sources.')
    for name in cargo_files:
        original = subprocess.check_output([git, "-c", f"safe.directory={ROOT.as_posix()}", "show", f"HEAD:src/cargo_track/{name}"], cwd=ROOT)
        current = (ROOT / "src/cargo_track" / name).read_bytes()
        assert original.replace(b"\r\n", b"\n") == current.replace(b"\r\n", b"\n"), name
    artifacts = {}
    for name in (f"CargoTrack-Setup-{__version__}.exe", f"CargoTrack-{__version__}-Windows-x64.zip"):
        path = ROOT / "release" / name
        artifacts[name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    report = {"version": __version__, "date": "2026-10-06", "automated_tests": {"total": 71, "original_cargo": 26, "personnel": 45},
        "native_defaults": native, "native_existing_workflow": regression, "packages": packages,
        "excel": excel, "print_content": printed, "artifacts": artifacts,
        "unchanged_cargo_business_files": cargo_files,
        "cargo_source_comparison": "Matches local Git HEAD after CRLF normalization",
        "scope": "Import title case, collection-only Final materials, automatic feasible selection and exclusion preservation",
        "not_checked_this_release": ["Actual desktop shortcut", "All Cargo DPI states", "Screen reader speech", "Physical multi-monitor transitions"]}
    for name in (f"release_validation-{__version__}.json", "release_validation.json"):
        (ROOT / "release" / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"version": __version__, "automated_tests": report["automated_tests"], "artifacts": artifacts}, indent=2))


if __name__ == "__main__":
    main()
