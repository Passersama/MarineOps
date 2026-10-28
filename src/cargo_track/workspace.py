"""Additive page navigation around the unchanged cargo workbench."""
import os
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QStackedWidget, QMessageBox, QMainWindow

from .ui import CargoTrackWindow


class WorkspaceWindow(CargoTrackWindow):
    def __init__(self, database_path, data_directory):
        super().__init__(database_path, data_directory)
        self.personnel_page = None
        self._personnel_directory = Path(data_directory) if os.environ.get('CARGO_TRACK_DATA_DIR') else Path(QSettings().value('personnel/database_directory', str(data_directory)))
        # Pin the independent companion before Cargo can move to another folder.
        if not os.environ.get('CARGO_TRACK_DATA_DIR') and not QSettings().contains('personnel/database_directory'):
            QSettings().setValue('personnel/database_directory', str(self._personnel_directory))
        self._cargo_actions = list(self.actions())
        self.cargo_page = self.takeCentralWidget()
        self.pages = QStackedWidget()
        self.pages.addWidget(self.cargo_page)
        self.setCentralWidget(self.pages)
        self.personnel_button = self.navigation.personnel_button
        self.personnel_button.clicked.connect(self.open_personnel)
        self.navigation.dashboard_button.clicked.connect(self.show_dashboard)
        self.navigation.cargo_button.clicked.connect(self.show_cargo)
        from .dashboard_ui import DashboardPage
        self.dashboard_page = DashboardPage(self)
        self.pages.addWidget(self.dashboard_page)
        self.pages.setCurrentWidget(self.dashboard_page)
        self._sync_navigation('dashboard')
        for action in self._cargo_actions:action.setEnabled(False)

    def personnel_database_path(self):
        if self.personnel_page is not None:return self.personnel_page.service.path.resolve()
        return (self._personnel_directory / 'personnel-transfer.sqlite3').resolve()

    def _sync_navigation(self, active):
        for navigation in (self.navigation, getattr(getattr(self,'personnel_page',None),'navigation',None),
                           getattr(getattr(self,'dashboard_page',None),'navigation',None)):
            if navigation:getattr(navigation, active+'_button').setChecked(True)

    def show_dashboard(self):
        if self._busy:
            self.statusBar().showMessage('Wait for the current save to finish.',4000);self._sync_current_navigation();return False
        page=self.personnel_page
        if page and self.pages.currentWidget() is page and not page.guard_leave(self.show_dashboard):
            self._sync_navigation('personnel');return False
        self.pages.setCurrentWidget(self.dashboard_page);self._sync_navigation('dashboard')
        for action in self._cargo_actions:action.setEnabled(False)
        self.dashboard_page.schedule_refresh()
        return True

    def _sync_current_navigation(self):
        self._sync_navigation('personnel' if self.pages.currentWidget() is self.personnel_page else
                              'dashboard' if self.pages.currentWidget() is self.dashboard_page else 'cargo')

    def open_personnel(self):
        try:
            if self._busy or self.snapshot is None:
                self._sync_current_navigation()
                QMessageBox.information(self, "Personnel Transfer Track", "Wait for MarineOps to finish its current operation.")
                return
            if self.personnel_page is None:
                from .personnel_ui import PersonnelPage
                self.personnel_page = PersonnelPage(self, self.show_cargo)
                self.pages.addWidget(self.personnel_page)
                self.personnel_page.navigation.dashboard_button.clicked.connect(self.show_dashboard)
            else:
                if self.pages.currentWidget() is self.personnel_page:
                    self._sync_navigation('personnel');return
                self.personnel_page.refresh_source()
            self.pages.setCurrentWidget(self.personnel_page)
            self._sync_navigation('personnel')
            for action in self._cargo_actions:
                action.setEnabled(False)
        except Exception as exc:
            self._sync_current_navigation()
            QMessageBox.warning(self, "Personnel Transfer Track could not open", str(exc))

    def show_cargo(self):
        page=self.personnel_page
        if page and self.pages.currentWidget() is page and not page.guard_leave(self.show_cargo):
            self._sync_navigation('personnel')
            return False
        self._sync_navigation('cargo')
        self.pages.setCurrentWidget(self.cargo_page)
        for action in self._cargo_actions:
            action.setEnabled(True)
        return True

    def _set_snapshot(self,snapshot):
        previous=self.snapshot
        super()._set_snapshot(snapshot)
        if self.snapshot is not snapshot:return
        page=getattr(self,'personnel_page',None)
        if page and previous and snapshot and (previous['dataset_epoch']!=snapshot['dataset_epoch'] or
                                               previous['current_voyage_id']!=snapshot['current_voyage_id']):
            page.invalidate_plan('Cargo database or Voyage changed. Generate a fresh plan.')
            page.refresh_source()
        dashboard=getattr(self,'dashboard_page',None)
        if dashboard:
            if previous is snapshot:dashboard.apply_theme()
            else:dashboard.schedule_refresh()

    def keyPressEvent(self, event):
        if self.pages.currentWidget() is not self.cargo_page:
            QMainWindow.keyPressEvent(self, event)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.personnel_page is not None and not self.personnel_page._closed and not self.personnel_page.guard_leave(self.close):
            event.ignore();return
        if self.personnel_page is not None:
            self.personnel_page.shutdown()
        self.dashboard_page.shutdown()
        super().closeEvent(event)
