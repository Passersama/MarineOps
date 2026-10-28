"""Small shared boundary for live files and draft recovery generations."""
from __future__ import annotations

import os
import threading
from pathlib import Path


class ProtectedFileError(ValueError):
    pass


class WorkspaceFiles:
    def __init__(self):
        self._paths = set()
        self._generations = {}
        self._lock = threading.RLock()

    def register(self, *paths):
        with self._lock:
            for path in paths:
                path=Path(path).resolve()
                self._paths.add(path)
                self._paths.update(Path(str(path)+suffix) for suffix in ('-journal','-wal','-shm','.recovery-required.json'))

    def register_database(self, path):
        path = Path(path).resolve()
        # Protect the unopened companion database as well as this connection.
        self.register(path, path.parent / "cargo-track.sqlite3", path.parent / "personnel-transfer.sqlite3")

    @staticmethod
    def same_file(first, second):
        if os.path.normcase(str(Path(first).resolve())) == os.path.normcase(str(Path(second).resolve())):
            return True
        try:
            return os.path.samefile(first, second)
        except OSError:
            return False

    def check_output(self, target, *additional):
        with self._lock:
            protected = self._paths | {Path(p).resolve() for p in additional if p}
            if any(self.same_file(target, p) for p in protected):
                raise ProtectedFileError("Choose a separate output file. Cargo and personnel databases are protected.")

    def generation(self, path):
        with self._lock:
            return self._generations.get(os.path.normcase(str(Path(path).resolve())), 0)

    def invalidate(self, path):
        with self._lock:
            name = os.path.normcase(str(Path(path).resolve()))
            self._generations[name] = self._generations.get(name, 0) + 1
            return self._generations[name]


workspace_files = WorkspaceFiles()
