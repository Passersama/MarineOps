import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name == 'nt', 'Windows installer test')
class InstallerFailureTests(unittest.TestCase):
    def test_shortcut_failure_reports_installed_and_invalid_target_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / 'payload.zip'
            with zipfile.ZipFile(payload, 'w') as archive:
                archive.writestr('MarineOps/MarineOps.exe', b'fixture executable')
            harness = root / 'harness.cs'
            harness.write_text(r'''using System;
using System.IO;
class Harness {
 static int Main(string[] args) {
  string root = args[0], target = Path.Combine(root, "installed"), warning;
  string exe = Installer.Install(target, root, "bad:name", true, delegate {}, out warning);
  if (!File.Exists(exe) || !warning.Contains("shortcut could not be created")) return 1;
  string invalid = Path.Combine(root, "other"); Directory.CreateDirectory(invalid);
  string marker = Path.Combine(invalid, "user-file.txt"); File.WriteAllText(marker, "keep");
  try { Installer.Install(invalid, root, "MarineOps", false, delegate {}, out warning); return 2; }
  catch (ArgumentException) { return File.ReadAllText(marker) == "keep" ? 0 : 3; }
 }
}''', encoding='utf-8')
            compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
            exe = root / 'harness.exe'
            subprocess.run([str(compiler), '/nologo', '/target:exe', '/main:Harness', f'/out:{exe}',
                '/r:System.IO.Compression.dll', '/r:System.IO.Compression.FileSystem.dll',
                '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', f'/resource:{payload},CargoTrackPayload',
                str(ROOT / 'tools/CargoTrackInstaller.cs'), str(harness)], check=True, capture_output=True)
            subprocess.run([str(exe), str(root)], check=True, timeout=30)
