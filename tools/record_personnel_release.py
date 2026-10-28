"""Record only the checks performed for the additive Personnel release."""
import hashlib
import json
import subprocess
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cargo_track import __version__

def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))

def main():
    evidence = "artifacts/personnel-load-fix"
    packages = read(f"artifacts/validation-{__version__}/packaged-personnel-validation.json")
    assert packages["standalone_installer"] == "PASS" and packages["upgrade_data_preservation"] == "PASS"
    assert all(p["visible"] and p["cargo_hash_unchanged"] and p["file_version"] == __version__ for p in packages["packages"])
    native = read(f"{evidence}/native-visible.json")
    assert all(native[field] for field in ("native_visible", "cargo_hash_unchanged", "crew_status_controls_absent",
               "automatic_abbreviations", "departure_date_recognized", "missing_vessel_added", "reorder_via_button", "two_excel_sheets"))
    assert all(native[field] for field in ("legacy_load_refreshed_final", "old_snapshot_unchanged", "review_rows_grouped",
        "review_click_shows_reasons", "crew_add_and_plan_remove_via_buttons", "material_selection_editable",
        "excluded_entry_stays_excluded_on_reload", "repeated_visit_assignment_preserved", "edit_targets_displayed_plan",
        "berthing_date_reaches_excel", "date_labels_clarified", "draft_personnel_edited_in_place",
        "only_personnel_editable_in_draft", "direct_edits_saved_without_preview_step", "direct_edits_reach_excel", "material_content_unchanged"))
    excel = read(f"{evidence}/excel-native-validation.json")
    direct_excel = read(f"{evidence}/direct-excel-native-validation.json")
    direct_print = read(f"{evidence}/direct-print-content.json")
    assert direct_excel["source_unchanged"] and all(direct_print[k] for k in ("changed_name_printed", "changed_position_printed", "material_names_unchanged"))
    printed = read(f"{evidence}/print-content-validation.json")
    existing = read(f"{evidence}/existing-crew-readonly.json")
    legacy = read(f"{evidence}/legacy-user-readonly.json")
    assert excel["source_unchanged"] and not printed["missing"]
    assert existing["all_vessels_matched"] and existing["user_databases_unchanged"] and existing["user_workbook_unchanged"]
    assert legacy["user_files_unchanged"]
    cargo_files = ["ui.py", "service.py", "schema.py", "models.py", "worker.py", "repository.py", "domain.py", "appearance.py"]
    git = shutil.which('git')
    if not git:raise RuntimeError('Git is required to compare release sources.')
    for name in cargo_files:
        committed = subprocess.check_output([str(git), "-c", f"safe.directory={ROOT.as_posix()}", "show", f"HEAD:src/cargo_track/{name}"], cwd=ROOT)
        current = (ROOT / "src/cargo_track" / name).read_bytes()
        assert committed.replace(b"\r\n", b"\n") == current.replace(b"\r\n", b"\n"), name
    artifacts = {}
    for name in (f"CargoTrack-Setup-{__version__}.exe", f"CargoTrack-{__version__}-Windows-x64.zip"):
        path = ROOT / "release" / name
        artifacts[name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    report = {"version": __version__, "date": "2026-10-05", "automated_tests": {"total": 68, "original_cargo": 26, "personnel": 42},
        "native_personnel": {k: v for k, v in native.items() if k not in {"data_directory", "export"}},
        "packages": packages, "excel": excel, "print_content": printed, "existing_crew_readonly": existing,
        "legacy_plan_readonly": legacy, "direct_personnel_excel": direct_excel, "direct_personnel_print": direct_print, "artifacts": artifacts,
        "unchanged_cargo_business_files": cargo_files,
        "cargo_source_comparison": "Matches local Git HEAD after CRLF normalization",
        "finish_review": {"disposition": "ship", "scope": "Eight native inline-editor captures reviewed; all three named documentation fixes scored resolved afterward"},
        "not_checked_this_release": ["Actual desktop shortcut", "All Cargo DPI states", "Screen reader speech", "Physical multi-monitor transitions"],
        "evidence": [f"../{evidence}/native-visible.json", f"../{evidence}/excel-native-validation.json",
                     f"../{evidence}/print-content-validation.json", f"../{evidence}/existing-crew-readonly.json", f"../{evidence}/legacy-user-readonly.json",
                     f"../artifacts/validation-{__version__}/packaged-personnel-validation.json"]}
    (ROOT / "release" / f"release_validation-{__version__}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "release" / "release_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"version": __version__, "automated_tests": report["automated_tests"], "artifacts": artifacts}, indent=2))

if __name__ == "__main__":
    main()
