"""Register bundled Qt and Shiboken DLL directories on Windows."""

import os
import sys
import ctypes
from pathlib import Path

if sys.platform == "win32" and hasattr(sys, "_MEIPASS"):
    _directories = []
    for _relative in ("PySide6", "shiboken6", "."):
        _directory = Path(sys._MEIPASS, _relative)
        if _directory.is_dir():
            _directories.append(str(_directory))
    sys._cargo_track_dll_handles = [os.add_dll_directory(directory) for directory in _directories]
    os.environ["PATH"] = os.pathsep.join(_directories + [os.environ.get("PATH", "")])
    sys._cargo_track_shiboken = ctypes.WinDLL(str(Path(sys._MEIPASS, "shiboken6", "shiboken6.abi3.dll")))
