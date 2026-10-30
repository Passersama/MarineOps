"""Additive page navigation around the unchanged cargo workbench."""
import os
from pathlib import Path
from PySide6.QtCore import QSettings, Qt, QTimer, QSize
from PySide6.QtWidgets import (QApplication, QStackedWidget, QMessageBox, QMainWindow, QWidget,
                               QFrame, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel,
                               QPushButton, QToolButton, QMenu, QButtonGroup, QSlider, QScrollArea)

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
        self.shell = QWidget(self)
        self.shell.setObjectName('workspaceShell')
        shell_layout = QHBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.sidebar = QFrame(self.shell)
        self.sidebar.setObjectName('workspaceSidebar')
        self.sidebar.setFixedWidth(190)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 18, 14, 16)
        side.setSpacing(8)
        brand = QHBoxLayout()
        from .appearance import brand_pixmap
        self.sidebar_logo = QLabel(self.sidebar)
        self.sidebar_logo.setPixmap(brand_pixmap(64, 32))
        self.sidebar_logo.setAccessibleName('MarineOps logo')
        brand.addWidget(self.sidebar_logo)
        self.sidebar_title = QLabel('MarineOps', self.sidebar)
        self.sidebar_title.setObjectName('sidebarTitle')
        brand.addWidget(self.sidebar_title, 1)
        side.addLayout(brand)
        side.addSpacing(20)
        self.sidebar_group = QButtonGroup(self)
        self.sidebar_buttons = {}
        for key, caption in (('dashboard', 'Dashboard'), ('cargo', 'Cargo'),
                             ('personnel', 'Personnel')):
            item = QPushButton(caption, self.sidebar)
            item.setObjectName('sidebarItem')
            item.setCheckable(True)
            item.setAccessibleName('Open ' + caption + ' workspace')
            self.sidebar_group.addButton(item)
            self.sidebar_buttons[key] = item
            side.addWidget(item)
        side.addStretch(1)
        self.sidebar_settings = QPushButton('Settings', self.sidebar)
        self.sidebar_settings.setObjectName('sidebarItem')
        self.sidebar_settings.setCheckable(True)
        self.sidebar_settings.setAccessibleName('Open Settings workspace')
        self.sidebar_group.addButton(self.sidebar_settings)
        self.sidebar_settings.clicked.connect(self.show_settings)
        self._update_navigation_icons()
        side.addWidget(self.sidebar_settings)
        shell_layout.addWidget(self.sidebar)
        shell_layout.addWidget(self.pages, 1)
        self.setCentralWidget(self.shell)
        self.sidebar_buttons['dashboard'].clicked.connect(self.show_dashboard)
        self.sidebar_buttons['cargo'].clicked.connect(self.show_cargo)
        self.sidebar_buttons['personnel'].clicked.connect(self.open_personnel)
        self._sidebar_mode = True
        self.navigation.hide()
        self.navigation.about_button.hide()
        self.fleet_button.hide()
        self.voyage_button.hide()
        self.settings_button.hide()
        self.personnel_button = self.navigation.personnel_button
        self.personnel_button.clicked.connect(self.open_personnel)
        self.navigation.dashboard_button.clicked.connect(self.show_dashboard)
        self.navigation.cargo_button.clicked.connect(self.show_cargo)
        from .dashboard_ui import DashboardPage
        self.dashboard_page = DashboardPage(self)
        self.dashboard_page.navigation.hide()
        self.dashboard_page.navigation.about_button.hide()
        for child in self.dashboard_page.findChildren(QPushButton):
            if child.text() == 'Settings':
                child.hide()
        self.pages.addWidget(self.dashboard_page)
        self.settings_page = self._build_settings_page()
        self.pages.addWidget(self.settings_page)
        self.pages.setCurrentWidget(self.dashboard_page)
        self._sync_navigation('dashboard')
        for action in self._cargo_actions:action.setEnabled(False)

    def personnel_database_path(self):
        if self.personnel_page is not None:return self.personnel_page.service.path.resolve()
        return (self._personnel_directory / 'personnel-transfer.sqlite3').resolve()

    def _sync_navigation(self, active):
        if hasattr(self, 'sidebar_buttons'):
            (self.sidebar_settings if active == 'settings' else self.sidebar_buttons[active]).setChecked(True)
        for navigation in (self.navigation, getattr(getattr(self,'personnel_page',None),'navigation',None),
                           getattr(getattr(self,'dashboard_page',None),'navigation',None)):
            if navigation and active != 'settings':getattr(navigation, active+'_button').setChecked(True)

    def _build_settings_page(self):
        from .appearance import glass_intensity
        from .about_ui import show_about
        page=QWidget();page.setObjectName('settingsPage')
        root=QVBoxLayout(page);root.setContentsMargins(26,24,26,20);root.setSpacing(12)
        heading=QLabel('Settings');heading.setObjectName('workbenchTitle');root.addWidget(heading)
        subtitle=QLabel('Appearance, workspace and data');subtitle.setObjectName('sectionTitle');root.addWidget(subtitle)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setStyleSheet('QScrollArea {background: transparent; border: 0;}');root.addWidget(scroll,1)
        content=QWidget();content.setStyleSheet('QWidget#settingsContent {background: transparent;}');content.setObjectName('settingsContent');scroll.setWidget(content)
        layout=QGridLayout(content);layout.setContentsMargins(0,0,0,0);layout.setSpacing(12)
        layout.setColumnStretch(0,1);layout.setColumnStretch(1,1)
        def card(title,description,row,column):
            from .frosted import FrostedFrame
            frame=FrostedFrame();frame.setObjectName('settingsCard');box=QVBoxLayout(frame);box.setContentsMargins(18,16,18,16);box.setSpacing(10)
            label=QLabel(title);label.setObjectName('workbenchTitle');box.addWidget(label)
            note=QLabel(description);note.setObjectName('sectionTitle');note.setWordWrap(True);box.addWidget(note)
            layout.addWidget(frame,row,column);return box
        appearance=card('Appearance','Choose your theme and adjust the frosted surface.',0,0)
        self.appearance_card=appearance.parentWidget()
        theme_row=QHBoxLayout();theme_row.addWidget(QLabel('Theme'),1)
        self.theme_group=QButtonGroup(page);self.theme_buttons={}
        for key,title in (('light','Light'),('dark','Dark')):
            button=QPushButton(title);button.setObjectName('workspaceTab');button.setCheckable(True);button.setAccessibleName(title+' theme')
            self.theme_group.addButton(button);self.theme_buttons[key]=button;theme_row.addWidget(button)
            button.clicked.connect(lambda checked=False,value=key:self._set_appearance('theme',value))
        appearance.addLayout(theme_row)
        row=QHBoxLayout();row.addWidget(QLabel('Glass intensity'))
        self.glass_slider=QSlider(Qt.Orientation.Horizontal);self.glass_slider.setRange(0,100);self.glass_slider.setValue(glass_intensity());self.glass_slider.setAccessibleName('Glass intensity');row.addWidget(self.glass_slider,1)
        self.glass_value=QLabel(str(glass_intensity())+'%');row.addWidget(self.glass_value);appearance.addLayout(row)
        self._glass_preview_timer=QTimer(self);self._glass_preview_timer.setSingleShot(True);self._glass_preview_timer.setInterval(100);self._glass_preview_timer.timeout.connect(self._preview_glass)
        self._glass_commit_timer=QTimer(self);self._glass_commit_timer.setSingleShot(True);self._glass_commit_timer.setInterval(220);self._glass_commit_timer.timeout.connect(self._commit_glass)
        self._glass_pending=False
        self.glass_slider.valueChanged.connect(self._glass_changed)
        self.glass_slider.sliderPressed.connect(self._glass_commit_timer.stop)
        self.glass_slider.sliderReleased.connect(self._commit_glass)
        font=QLabel('Font   Manrope');font.setObjectName('sectionTitle');appearance.addWidget(font)
        workspace=card('Workspace','Manage vessel and operating preferences.',0,1)
        for text,handler in (('General preferences',self.open_settings),('Fleet',self.open_fleet),('Personnel and plan settings',self._sidebar_personnel_settings)):
            button=QPushButton(text+'  ›');button.setObjectName('settingsRow');button.setAccessibleName(text);button.clicked.connect(handler);workspace.addWidget(button)
        data=card('Data','Manage cargo backups and recovery. Personnel has separate data settings.',1,0)
        for text,handler in (('Create cargo backup',self.create_backup),('Restore cargo backup',self.restore_backup),('Open backup folder',self.open_backup_folder)):
            button=QPushButton(text+'  ›');button.setObjectName('settingsRow');button.setAccessibleName(text);button.clicked.connect(handler);data.addWidget(button)
        about=card('About','Application information and help.',1,1)
        button=QPushButton('About MarineOps  ›');button.setObjectName('settingsRow');button.clicked.connect(lambda:show_about(self));about.addWidget(button)
        layout.setRowStretch(2,1)
        self._sync_appearance_controls()
        return page

    def _sync_appearance_controls(self):
        from .appearance import is_dark_mode
        self.theme_buttons['dark' if is_dark_mode() else 'light'].setChecked(True)

    def _set_appearance(self,key,value):
        from .appearance import configure_application
        if key=='theme' and self._glass_pending:self._commit_glass()
        QSettings().setValue('appearance/'+key,value)
        if key=='glass_intensity':self.glass_value.setText(str(value)+'%')
        configure_application(QApplication.instance())
        self._update_navigation_icons()
        self._refresh_frosted()
        self._sync_appearance_controls()
        if self.snapshot:self._set_snapshot(self.snapshot)

    def _update_navigation_icons(self):
        from .appearance import navigation_icon,is_dark_mode
        for key,button in list(self.sidebar_buttons.items())+[('settings',self.sidebar_settings)]:
            button.setIcon(navigation_icon(key,is_dark_mode()));button.setIconSize(QSize(19,19))

    def _glass_changed(self,value):
        self.glass_value.setText(str(value)+'%')
        self._glass_pending=True
        if not self._glass_preview_timer.isActive():self._glass_preview_timer.start()
        if not self.glass_slider.isSliderDown():self._glass_commit_timer.start()

    def _preview_glass(self):
        self.appearance_card.refresh_material(self.glass_slider.value())

    def _refresh_frosted(self):
        from .frosted import FrostedFrame
        for frame in self.findChildren(FrostedFrame):frame.refresh_material()

    def _commit_glass(self):
        if not self._glass_pending:return
        self._glass_preview_timer.stop();self._glass_commit_timer.stop()
        QSettings().setValue('appearance/glass_intensity',self.glass_slider.value())
        self._glass_pending=False
        self._refresh_frosted()

    def show_settings(self):
        if self._busy:
            self.statusBar().showMessage('Wait for the current save to finish.',4000);self._sync_current_navigation();return False
        page=self.personnel_page
        if page and self.pages.currentWidget() is page and not page.guard_leave(self.show_settings):
            self._sync_navigation('personnel');return False
        self.pages.setCurrentWidget(self.settings_page);self._sync_navigation('settings');self._sync_appearance_controls()
        for action in self._cargo_actions:action.setEnabled(False)
        return True

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
        self._sync_navigation('settings' if self.pages.currentWidget() is self.settings_page else 'personnel' if self.pages.currentWidget() is self.personnel_page else
                              'dashboard' if self.pages.currentWidget() is self.dashboard_page else 'cargo')

    def open_personnel(self):
        try:
            if self._busy or self.snapshot is None:
                self._sync_current_navigation()
                from .dialogs import prompt
                prompt(self, "Personnel Transfer Track", "Wait for MarineOps to finish its current operation.", buttons=('OK',), default='OK')
                return
            if self.personnel_page is None:
                from .personnel_ui import PersonnelPage
                self.personnel_page = PersonnelPage(self, self.show_cargo)
                self.personnel_page.navigation.hide()
                self.personnel_page.navigation.about_button.hide()
                for child in self.personnel_page.findChildren(QPushButton):
                    if child.text() == 'Settings':
                        child.hide()
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
            from .dialogs import prompt
            prompt(self, "Personnel Transfer Track could not open", str(exc), buttons=('OK',), default='OK')

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

    def _sidebar_open_voyages(self):
        page = self.personnel_page
        if page and self.pages.currentWidget() is page and not page.guard_leave(self._sidebar_open_voyages):
            return
        if not self._busy and self.snapshot is not None:
            self.open_voyages()

    def _sidebar_personnel_settings(self):
        if self.personnel_page is None:
            self.open_personnel()
        if self.personnel_page is not None:
            self.personnel_page.open_settings()

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
        self._commit_glass()
        self.dashboard_page.shutdown()
        super().closeEvent(event)
