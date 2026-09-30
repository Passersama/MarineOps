"""Windows desktop entry point for Cargo Track."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

_TRACE_STARTUP = os.environ.get("CARGO_TRACK_TRACE") == "1"
if _TRACE_STARTUP:print("main module: imports starting",flush=True)
from PySide6.QtCore import QLockFile, QStandardPaths, QSettings, Qt
if _TRACE_STARTUP:print("main module: QtCore imported",flush=True)
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox
if _TRACE_STARTUP:print("main module: QtWidgets imported",flush=True)

from . import __version__
from .ui import CargoTrackWindow
if _TRACE_STARTUP:print("main module: UI imported",flush=True)

from .appearance import APP_STYLE, configure_application


def _activate_existing(server_name: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(250):
        socket.write(b"activate")
        socket.flush()
        socket.waitForBytesWritten(250)
        return True
    return False


def main() -> int:
    trace = _TRACE_STARTUP
    if trace:print("Cargo Track main entered",flush=True)
    QApplication.setOrganizationName("Cargo Track")
    QApplication.setApplicationName("Cargo Track")
    QApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv)
    if trace:print("QApplication created",flush=True)
    app.setQuitOnLastWindowClosed(True)
    configure_application(app)
    override = os.environ.get("CARGO_TRACK_DATA_DIR", "").strip()
    default_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    data_dir = Path(override) if override else Path(QSettings().value("storage/database_directory",str(default_dir)))
    data_dir.mkdir(parents=True, exist_ok=True)
    if trace:print(f"Data directory: {data_dir}",flush=True)
    user_key = hashlib.sha256(f"{os.environ.get('USERNAME', 'user')}|{override or default_dir}".encode()).hexdigest()[:20]
    server_name = f"CargoTrack-{user_key}"
    lock_dir = Path(override) if override else default_dir
    lock_dir.mkdir(parents=True,exist_ok=True)
    instance_lock = QLockFile(str(lock_dir / ".cargo-track.instance.lock"))
    if not instance_lock.tryLock(0):
        if _activate_existing(server_name):
            if trace:print("Activated an existing instance",flush=True)
            return 0
        QMessageBox.critical(None, "Cargo Track", "Another Cargo Track window is already running.")
        return 1

    server = QLocalServer()
    if not server.listen(server_name):
        QLocalServer.removeServer(server_name)
        if not server.listen(server_name):
            if trace:print("Local activation server failed",flush=True)
            QMessageBox.critical(None, "Cargo Track", "Another Cargo Track window is already running.")
            instance_lock.unlock()
            return 1

    window = CargoTrackWindow(data_dir / "cargo-track.sqlite3", data_dir)
    if trace:print("Main window and database worker constructed",flush=True)
    window.setWindowTitle(f"Cargo Track {__version__}")
    server.newConnection.connect(lambda: _activate(window, server))
    window.show()
    if trace:print("Entering Qt event loop",flush=True)
    result = app.exec()
    server.close()
    instance_lock.unlock()
    return result


def _activate(window: CargoTrackWindow, server: QLocalServer) -> None:
    while server.hasPendingConnections():
        connection = server.nextPendingConnection()
        connection.readyRead.connect(lambda socket=connection: _raise_window(window, socket))
        if connection.bytesAvailable():
            _raise_window(window, connection)


def _raise_window(window: CargoTrackWindow, socket: QLocalSocket) -> None:
    socket.readAll()
    window.showNormal()
    window.raise_()
    window.activateWindow()


if __name__ == "__main__":
    raise SystemExit(main())
