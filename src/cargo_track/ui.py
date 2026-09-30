"""Native PySide6 workbench, record dialogs and file operations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt,QTimer,QThread,Signal,QSettings,QSortFilterProxyModel,QUrl,QMetaObject
from PySide6.QtGui import QAction,QDesktopServices,QKeySequence,QIcon,QPixmap
from PySide6.QtWidgets import (QApplication,QComboBox,QDialog,QDialogButtonBox,QFileDialog,QFormLayout,QFrame,
    QHBoxLayout,QInputDialog,QLabel,QLineEdit,QMainWindow,QMenu,QMessageBox,QProgressBar,QPushButton,
    QScrollArea,QSizePolicy,QTabBar,QTableView,QTextEdit,QToolButton,QVBoxLayout,QWidget,
    QAbstractItemView,QCheckBox,QListWidget,QListWidgetItem,QTableWidget,QTableWidgetItem,QTextBrowser)

from .domain import AppError
from .models import HEADERS,StatusDelegate,TransferTableModel
from .worker import DatabaseWorker
from .appearance import asset_path,fit_to_screen,application_font_family,application_font_size,configure_application,is_dark_mode,themed_color
from .preferences import time_zone_choices

PAGE_SIZE=200
OPEN_FILTER={"range":"open","query":"","status":"","vessel_id":""}
EMPTY_FILTER={"range":"all","query":"","status":"","vessel_id":""}


class AppDialog(QDialog):
    def showEvent(self,event):
        fit_to_screen(self)
        super().showEvent(event)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_F1 and hasattr(self.parent(),"open_help"):
            self.parent().open_help("settings" if isinstance(self,SettingsDialog) else "fleet" if isinstance(self,FleetDialog) else "voyages" if isinstance(self,VoyagesDialog) else "cargo");event.accept();return
        super().keyPressEvent(event)


class DatabaseClient(QWidget):
    """Owns the worker thread and request/result boundary."""
    send_request=Signal(str,str,dict)
    shutdown_requested=Signal()
    received=Signal(str,dict)
    rejected=Signal(str,dict)
    opened=Signal(dict)
    startup_failed=Signal(str,dict)
    maintenance_changed=Signal(bool)

    def __init__(self,path,parent=None):
        super().__init__(parent);self.setVisible(False);self.pending={}
        self.thread=QThread(self);self.worker=DatabaseWorker(path);self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.open)
        self.send_request.connect(self.worker.request)
        self.shutdown_requested.connect(self.worker.shutdown)
        self.worker.ready.connect(self.opened);self.worker.failed.connect(self.startup_failed)
        self.worker.result.connect(self.received);self.worker.request_failed.connect(self.rejected)
        self.worker.maintenance.connect(self.maintenance_changed)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    def request(self,operation,payload=None,meta=None):
        request_id=str(uuid4());self.pending[request_id]=meta or {}
        self.send_request.emit(request_id,operation,payload or {})
        return request_id

    def take(self,request_id):return self.pending.pop(request_id,{})

    def close(self):
        if self.thread.isRunning():
            QMetaObject.invokeMethod(self.worker,"shutdown",Qt.ConnectionType.BlockingQueuedConnection)
            self.thread.quit()
            if not self.thread.wait(5000):self.thread.requestInterruption();self.thread.quit();self.thread.wait(2000)


def info_box(parent,title,message,details=""):
    box=QMessageBox(parent);box.setIcon(QMessageBox.Icon.Information);box.setWindowTitle(title);box.setText(message)
    if details:box.setDetailedText(str(details))
    box.exec()


def confirm(parent,title,message,details=""):
    box=QMessageBox(parent);box.setIcon(QMessageBox.Icon.Warning);box.setWindowTitle(title);box.setText(message)
    if details:box.setInformativeText(details)
    box.setStandardButtons(QMessageBox.StandardButton.Cancel|QMessageBox.StandardButton.Yes)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    return box.exec()==QMessageBox.StandardButton.Yes


class TransferForm(AppDialog):
    def __init__(self,*,vessels,cargo_choices,initial=None,edit=False,next_for=None,parent=None):
        super().__init__(parent);self.setWindowTitle("Edit transfer" if edit else "Next transfer" if next_for else "Add cargo")
        self.resize(560,570);self.initial=initial or {};self.edit=edit;self.next_for=next_for
        layout=QVBoxLayout(self);form=QFormLayout();form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        if not edit and not next_for:
            self.record_mode=QComboBox();self.record_mode.addItem("New cargo",None)
            for item in cargo_choices:self.record_mode.addItem(f"{item['cargo_tag']}  ·  {item['default_description'][:56]}",item)
            form.addRow("Record",self.record_mode)
            self.record_mode.currentIndexChanged.connect(self._existing_changed)
        else:self.record_mode=None
        self.description=QTextEdit();self.description.setMaximumHeight(92);self.description.setPlaceholderText("Describe the physical cargo")
        self.identifier=QLineEdit();self.identifier.setPlaceholderText("Serial number, box number or sticker ID")
        self.from_location=QComboBox();self.to_location=QComboBox()
        for vessel in vessels:
            if vessel["active"] and vessel.get("kind","VESSEL")=="VESSEL":self.from_location.addItem(vessel["name"],vessel["id"]);self.to_location.addItem(vessel["name"],vessel["id"])
        # The fixed shore location is supplied by the parent snapshot.
        self.shore_id=0
        if hasattr(parent,"shore_id"):self.shore_id=parent.shore_id
        if self.shore_id:
            self.from_location.addItem("On Shore",self.shore_id);self.to_location.addItem("On Shore",self.shore_id)
        self.status=QComboBox();self.status.addItem(self.initial.get("status","Waiting"));self.status.setEnabled(edit and self.initial.get("status")=="Done")
        if edit:self.status.setEnabled(False)
        else:self.status.setEnabled(False)
        self.comment=QTextEdit();self.comment.setMaximumHeight(86);self.comment.setPlaceholderText("Optional notes")
        self.completed=QLabel(self.initial.get("completed_date") or "Set automatically when delivered")
        form.addRow("Description *",self.description);form.addRow("Physical ID",self.identifier)
        form.addRow("From *",self.from_location);form.addRow("To *",self.to_location)
        form.addRow("Status",self.status);form.addRow("Comment",self.comment);form.addRow("Completed Date",self.completed)
        if not edit and not next_for:
            self.route_reason=QLineEdit();self.route_reason.setPlaceholderText("Required only if the next pickup differs from the last delivery")
            self.route_reason.hide();form.addRow("Route reason",self.route_reason)
            self.record_mode.currentIndexChanged.connect(lambda *_:self.route_reason.setVisible(self.record_mode.currentData() is not None))
        else:self.route_reason=None
        layout.addLayout(form)
        self.route_warning=QLabel("From and To are the same. Check this route.");self.route_warning.setStyleSheet("color:"+themed_color("#7A4B00","#FFD58A")+";background:"+themed_color("#FFF2D6","#49381C")+";padding:7px;border-radius:5px;");self.route_warning.hide();layout.addWidget(self.route_warning)
        self.from_location.currentIndexChanged.connect(self._route_changed);self.to_location.currentIndexChanged.connect(self._route_changed)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save);buttons.accepted.connect(self._validate);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        if edit:
            for combo,key,name_key in ((self.from_location,"from_location_id","from_name"),(self.to_location,"to_location_id","to_name")):
                if combo.findData(self.initial.get(key))<0 and self.initial.get(key) is not None:
                    combo.addItem(f"Recorded: {self.initial.get(name_key,'location')} (Inactive)",self.initial[key])
            self.description.setPlainText(self.initial.get("description",""));self.identifier.setText(self.initial.get("physical_id", ""));self.comment.setPlainText(self.initial.get("comment",""))
            self._select(self.from_location,self.initial.get("from_location_id"));self._select(self.to_location,self.initial.get("to_location_id"))
            if self.initial.get("is_void"):self.setWindowTitle(f"Voided transfer #{self.initial['no']}")
        elif next_for:
            self.description.setPlainText(next_for.get("default_description", ""));self.identifier.setText(next_for.get("physical_id") or "")
            self._select(self.from_location,next_for.get("to_location_id"));self._select(self.to_location,self._default_to())
            self._cargo_id=next_for["cargo_id"]
        self._route_changed()

    @staticmethod
    def _all_locations(vessels):return vessels

    @staticmethod
    def _select(combo,value):
        index=combo.findData(value)
        if index>=0:combo.setCurrentIndex(index)

    def _default_to(self):
        for index in range(self.to_location.count()):
            if self.to_location.itemData(index)!=self.from_location.currentData():return self.to_location.itemData(index)
        return self.to_location.currentData()

    def _existing_changed(self,index):
        item=self.record_mode.itemData(index)
        if not item:
            self._cargo_id=None
            return
        self._cargo_id=item["cargo_id"];self.description.setPlainText(item["default_description"] or "");self.identifier.setText(item["physical_id"] or "")
        self._select(self.from_location,item["to_location_id"])

    def _route_changed(self,*_):
        self.route_warning.setVisible(self.from_location.currentData() is not None and self.from_location.currentData()==self.to_location.currentData())

    def _validate(self):
        if not self.description.toPlainText().strip():self.description.setFocus();info_box(self,"Description required","Enter a description for this transfer.");return
        if self.from_location.currentData() is None or self.to_location.currentData() is None:info_box(self,"Locations required","Add a vessel in Fleet or select On Shore.");return
        self.accept()

    def payload(self):
        value={"description":self.description.toPlainText().strip(),"physical_id":self.identifier.text().strip(),
               "from_location_id":self.from_location.currentData(),"to_location_id":self.to_location.currentData(),"comment":self.comment.toPlainText().strip()}
        if self.edit:value.update(no=self.initial["no"],expected_version=self.initial["version"])
        elif self.next_for:value["cargo_id"]=self._cargo_id
        elif self.record_mode.currentData() is not None:
            item=self.record_mode.currentData();value["cargo_id"]=item["cargo_id"]
            prior=item["to_location_id"]
            if prior!=value["from_location_id"]:value["route_reason"]=self.route_reason.text().strip()
        return value


class CorrectionDialog(AppDialog):
    def __init__(self,row,vessels,parent=None):
        super().__init__(parent);self.setWindowTitle(f"Correct transfer #{row['no']}");self.row=row;self.resize(520,450)
        layout=QVBoxLayout(self);form=QFormLayout();self.source=QComboBox();self.destination=QComboBox()
        for item in vessels:
            label=item["name"]+(" (Inactive)" if not item["active"] else "")
            self.source.addItem(label,item["id"]);self.destination.addItem(label,item["id"])
        for combo,key in ((self.source,"from_location_id"),(self.destination,"to_location_id")):
            pos=combo.findData(row[key]);
            if pos>=0:combo.setCurrentIndex(pos)
        self.status=QComboBox()
        for value in ("Waiting","On Board","Done"):self.status.addItem(value)
        self.status.setCurrentText(row["status"])
        self.description=QLineEdit(row["description"]);self.comment=QTextEdit();self.comment.setMaximumHeight(74);self.comment.setPlainText(row["comment"])
        self.reason=QTextEdit();self.reason.setMaximumHeight(86);self.reason.setPlaceholderText("Explain what was wrong and what the cargo's actual status/location should be")
        form.addRow("From",self.source);form.addRow("To",self.destination);form.addRow("Status",self.status);form.addRow("Description",self.description);form.addRow("Comment",self.comment);form.addRow("Reason *",self.reason);layout.addLayout(form)
        warning=QLabel("Correction is recorded in the audit history. Completed Date is cleared or recalculated when the status changes.");warning.setWordWrap(True);layout.addWidget(warning)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save);buttons.accepted.connect(self._accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def _accept(self):
        if not self.reason.toPlainText().strip():info_box(self,"Reason required","Explain why this record needs correction.");return
        self.accept()

    def payload(self):return {"no":self.row["no"],"expected_version":self.row["version"],"from_location_id":self.source.currentData(),"to_location_id":self.destination.currentData(),"status":self.status.currentText(),"description":self.description.text(),"comment":self.comment.toPlainText(),"reason":self.reason.toPlainText().strip()}


class FleetDialog(AppDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.host=parent;self.setWindowTitle("Fleet");self.resize(560,440)
        layout=QVBoxLayout(self);self.list=QListWidget();self.list.setAccessibleName("Fleet vessels");self.list.setAccessibleDescription("Vessel name, active state, unfinished transfers and current stops");layout.addWidget(self.list)
        buttons=QHBoxLayout();self.add=QPushButton("Add vessel");self.rename=QPushButton("Rename");self.activate=QPushButton("Deactivate");self.delete=QPushButton("Delete…");self.delete.clicked.connect(self.delete_vessel)
        self.add.clicked.connect(self.add_vessel);self.rename.clicked.connect(self.rename_vessel);self.activate.clicked.connect(self.toggle)
        for button in (self.add,self.rename,self.activate,self.delete):buttons.addWidget(button)
        help_button=QPushButton("Help");help_button.clicked.connect(lambda:self.host.open_help("fleet"));buttons.addWidget(help_button)
        layout.addLayout(buttons);self.list.currentRowChanged.connect(self.update_actions);self.rows=[];self.reload()

    def reload(self):self.host._send("_fleet_details",{},meta={"kind":"fleet_details","dialog":self})

    def set_rows(self,rows):
        self.rows=rows;self.list.clear()
        for row in rows:
            state="Active" if row["active"] else "Inactive"
            note=f"{row['open_transfers']} unfinished · {row['current_stops']} current stops"
            item=QListWidgetItem(f"{row['name']}     {state}     {note}");item.setData(Qt.ItemDataRole.UserRole,row);self.list.addItem(item)
        self.update_actions()

    def current(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None

    def update_actions(self,*_):
        row=self.current();self.delete.setEnabled(bool(row));self.rename.setEnabled(bool(row and row["active"]));self.activate.setEnabled(bool(row));self.activate.setText("Deactivate" if row and row["active"] else "Reactivate")

    def delete_vessel(self):
        row=self.current()
        if row and confirm(self,"Delete vessel?",f"Delete {row['name']} from Fleet?","Historical cargo records keep their vessel names. Resolve unfinished transfers and remove current voyage stops first."):
            self.host._submit("delete_vessel",{"id":row["id"]},"Vessel deleted.",on_success=self.reload)

    def add_vessel(self):
        name,ok=QInputDialog.getText(self,"Add vessel","Vessel name")
        if ok and name.strip():self.host._submit("create_vessel",{"name":name.strip()},"Vessel added.",on_success=self.reload)

    def rename_vessel(self):
        row=self.current()
        if not row:return
        name,ok=QInputDialog.getText(self,"Rename vessel","New vessel name",text=row["name"])
        if ok and name.strip():self.host._submit("rename_vessel",{"id":row["id"],"name":name.strip()},"Vessel renamed.",on_success=self.reload)

    def toggle(self):
        row=self.current()
        if not row:return
        active=not row["active"]
        if not active and (row["open_transfers"] or row["current_stops"]):
            info_box(self,"Vessel is in use",f"Resolve {row['open_transfers']} unfinished transfer(s) and remove {row['current_stops']} active stop(s) first.");return
        if not active and not confirm(self,"Deactivate vessel?",f"Deactivate {row['name']}?","The vessel stays in history. New transfers and voyage stops cannot use it."):return
        self.host._submit("set_vessel_active",{"id":row["id"],"active":active,"reason":"Fleet management"},"Vessel status updated.",on_success=self.reload)


class DetailDialog(AppDialog):
    def __init__(self,host,number):
        super().__init__(host);self.host=host;self.number=number;self.detail=None;self.setWindowTitle(f"Transfer #{number}");self.resize(600,720)
        root=QVBoxLayout(self);self.heading=QLabel("Loading transfer…");self.heading.setStyleSheet("font-size:18px;font-weight:600;");root.addWidget(self.heading)
        self.body=QTextEdit();self.body.setReadOnly(True);self.body.setAccessibleName("Transfer, current cargo location, route and audit history");root.addWidget(self.body,1)
        buttons=QHBoxLayout();self.pickup=QPushButton("Pick up");self.deliver=QPushButton("Deliver");self.next=QPushButton("Next transfer");self.edit=QPushButton("Edit fields");self.more=QToolButton();self.more.setText("More  ⌄");self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.menu=QMenu(self.more);self.more.setMenu(self.menu)
        for button in (self.pickup,self.deliver,self.next,self.edit,self.more):buttons.addWidget(button)
        root.addLayout(buttons);self.pickup.clicked.connect(lambda:self.transition("pick_up"));self.deliver.clicked.connect(lambda:self.transition("deliver"));self.next.clicked.connect(self.new_leg);self.edit.clicked.connect(self.edit_fields)
        self.load()

    def load(self):self.host._send("_detail",{"no":self.number,"include_void":True},meta={"kind":"detail","dialog":self})

    def set_detail(self,detail):
        self.detail=detail;row=detail["row"];cargo=detail["cargo"];self.heading.setText(f"Cargo {cargo['cargo_tag']}  ·  transfer #{row['no']}  ·  {row['status']}")
        location=detail["location"]
        where=location["label"] if location["confirmed"] else "Not confirmed"
        at=f"\nLast confirmed {location['at_utc']}" if location["at_utc"] else ""
        route=f"{row['from_name']}  →  {row['to_name']}"
        history="\n".join(f"#{leg['no']}  {leg['from']} → {leg['to']}  ·  {leg['status']}"+("  ·  VOIDED" if leg["is_void"] else "")+(f"  ·  {leg['completed_date']}" if leg['completed_date'] else "") for leg in detail["legs"])
        events="\n".join(f"{event['occurred_utc']}  {event['type']}"+(f"\n  Reason: {event['reason']}" if event['reason'] else "") for event in detail["events"])
        self.body.setPlainText(f"Physical ID: {cargo['physical_id'] or 'Not provided'}\n\nCargo location now\n{where}{at}\n\nSelected transfer\n{route}\nStatus: {row['status']}\nCompleted Date: {row['completed_date'] or '—'}\n\nDescription\n{row['description']}\n\nComment\n{row['comment'] or '—'}\n\nTransfer history\n{history or 'No transfer history'}\n\nAudit history\n{events or 'No history'}")
        current=row.get("current_relation");actions=not row["is_void"]
        self.pickup.setVisible(actions and row["status"]=="Waiting");self.deliver.setVisible(actions and row["status"]=="On Board")
        self.pickup.setText("Pick up" if current in ("from","both") else f"Confirm pickup at {row['from_name']}")
        self.deliver.setText("Deliver" if current in ("to","both") else f"Confirm delivery to {row['to_name']}")
        self.next.setVisible(actions and row["status"]=="Done" and not detail["descendants"])
        self.edit.setVisible(actions)
        self.menu.clear()
        if row["is_void"]:
            restore=self.menu.addAction("Restore transfer…");restore.triggered.connect(self.restore)
        else:
            correct=self.menu.addAction("Correct record…");correct.triggered.connect(self.correct)
            void=self.menu.addAction("Void transfer…");void.setEnabled(row["status"]!="On Board" and not detail["descendants"]);void.setToolTip("Confirm actual location first" if row["status"]=="On Board" else "Resolve later transfers first" if detail["descendants"] else "")
            void.triggered.connect(self.void)
        if row["is_void"]:self.edit.setVisible(False)

    def transition(self,operation):
        if not self.detail:return
        row=self.detail["row"];current=row.get("current_relation");payload={"no":row["no"],"expected_version":row["version"]}
        if operation=="pick_up" and current not in ("from","both") or operation=="deliver" and current not in ("to","both"):
            question="Confirm that this cargo was picked up" if operation=="pick_up" else "Confirm that this cargo was delivered"
            endpoint=row["from_name"] if operation=="pick_up" else row["to_name"]
            if not confirm(self,"Confirm physical location?",f"{question} at {endpoint}?","This confirmation changes the recorded cargo location."):return
            payload["confirmed_location"]=True
        self.host._submit(operation,payload,"Transfer updated.",on_success=lambda:self.host._refresh_then(lambda:self.load()))

    def edit_fields(self):
        if not self.detail:return
        row=self.detail["row"]
        form=TransferForm(vessels=self.host.snapshot.get("locations",[]),cargo_choices=[],initial=row,edit=True,parent=self.host)
        if form.exec()==QDialog.DialogCode.Accepted:self.host._submit("edit_transfer",form.payload(),"Transfer saved.",on_success=lambda:self.host._refresh_then(lambda:self.load()))

    def new_leg(self):
        choices=[item for item in self.host.cargo_choices if item["cargo_id"]==self.detail["cargo"]["id"]]
        if not choices:info_box(self,"Next transfer unavailable","The latest transfer must be delivered before creating its next segment.");return
        form=TransferForm(vessels=self.host.snapshot.get("locations",[]),cargo_choices=choices,next_for=choices[0],parent=self.host)
        if form.exec()==QDialog.DialogCode.Accepted:self.host._submit("create_transfer",form.payload(),"Next transfer created.",on_success=lambda:self.host._refresh_then(lambda:self.load()))

    def correct(self):
        if not self.detail:return
        row=self.detail["row"];dialog=CorrectionDialog(row,self.host.snapshot.get("locations",[]),self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.host._submit("correct_transfer",dialog.payload(),"Correction saved.",on_success=lambda:self.host._refresh_then(lambda:self.load()))

    def void(self):
        row=self.detail["row"]
        reason,ok=QInputDialog.getText(self,"Void transfer",f"Reason for voiding transfer #{row['no']}")
        if ok and reason.strip():self.host._submit("void_transfer",{"no":row["no"],"expected_version":row["version"],"reason":reason.strip()},"Transfer voided.",on_success=self.accept)

    def restore(self):
        row=self.detail["row"];reason,ok=QInputDialog.getText(self,"Restore transfer",f"Reason for restoring transfer #{row['no']}")
        if ok and reason.strip():self.host._submit("restore_transfer",{"no":row["no"],"expected_version":row["version"],"reason":reason.strip()},"Transfer restored.",on_success=lambda:self.host._refresh_then(lambda:self.load()))


class CargoTrackWindow(QMainWindow):
    def __init__(self,database_path,data_directory):
        super().__init__();self.setWindowTitle("Cargo Track");self.setMinimumSize(960,600);self.resize(1366,768)
        self.setWindowIcon(QIcon(str(asset_path("cargo-track.ico"))));self.setAccessibleName("Cargo Track cargo transfer ledger")
        self.database_path=Path(database_path);self.data_directory=Path(data_directory);self.backup_directory=Path(QSettings().value("storage/backup_directory",str(self.data_directory/"Backups")))
        self.client=DatabaseClient(database_path,self);self.client.opened.connect(self._opened);self.client.startup_failed.connect(self._startup_failed)
        self.client.received.connect(self._received);self.client.rejected.connect(self._rejected);self.client.maintenance_changed.connect(self._maintenance)
        self.snapshot=None;self.view="all";self.filters={"all":dict(OPEN_FILTER),"current_stop":dict(OPEN_FILTER),"on_my_vessel":dict(OPEN_FILTER)}
        self.order_column=0;self.descending=False;self.page=0;self.page_total=0;self.selected_no=None;self._busy=False;self._updating=False
        self._latest={};self._refresh_callbacks={};self._refresh_wait={};self._detail_dialog=None;self.cargo_choices=[];self.pending_restore_path=None
        self.settings=QSettings("CargoTrack","CargoTrack")
        self._build();self._apply_saved_layout();fit_to_screen(self)
        names=((self.voyage_combo,"Current voyage"),(self.choose_stop_combo,"Choose current stop"),
               (self.route_scroll,"Voyage stops"),(self.tabs,"Transfer views"),(self.search,"Search transfers"),
               (self.status_filter,"Transfer status filter"),(self.vessel_filter,"Vessel filter"),
               (self.range_filter,"Completed and voided filter"),(self.table,"Cargo transfer ledger"))
        for widget,name in names:widget.setAccessibleName(name)
        self.search.setAccessibleDescription("Search number, cargo ID, description, physical ID or comment. Control F focuses search.")
        self.table.setAccessibleDescription("Use arrow keys to select a transfer. Press Enter for details. Each cell exposes its column and record identity.")
        for shortcut,callback in ((QKeySequence.StandardKey.Find,lambda:(self.search.setFocus(),self.search.selectAll())),
                                  (QKeySequence.StandardKey.New,self.add_transfer)):
            action=QAction(self);action.setShortcut(QKeySequence(shortcut));action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);action.triggered.connect(callback);self.addAction(action)

    def _build(self):
        central=QWidget();self.setCentralWidget(central);root=QVBoxLayout(central);root.setContentsMargins(16,10,16,10);root.setSpacing(8)
        nav=QHBoxLayout();self.brand=QLabel();self.brand.setObjectName("brand");self.brand.setAccessibleName("Cargo Track")
        logo=QPixmap(str(asset_path("cargo-track-lockup.png"))).scaled(660,132,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation);logo.setDevicePixelRatio(3)
        self.brand.setPixmap(logo);self.brand.setFixedSize(220,44);nav.addWidget(self.brand);nav.addStretch(1)
        self.fleet_button=QPushButton("Fleet");self.voyage_button=QPushButton("Voyages");self.export_button=QPushButton("Export");self.backup_button=QPushButton("Backup");self.settings_button=QPushButton("Settings")
        for button in (self.fleet_button,self.voyage_button,self.export_button,self.backup_button,self.settings_button):nav.addWidget(button)
        self.help_button=QPushButton("Help");self.help_button.setAccessibleName("Help menu");help_menu=QMenu(self.help_button)
        for label,section in (("Quick start","start"),("Cargo and status","cargo"),("Delete and restore","delete"),("Fleet and voyages","fleet"),("Search and export","search"),("Backup and recovery","backup"),("Settings and appearance","settings"),("Keyboard shortcuts","keys")):
            action=help_menu.addAction(label);action.triggered.connect(lambda _,section=section:self.open_help(section))
        self.help_button.setMenu(help_menu);nav.addWidget(self.help_button)
        help_action=QAction("Help",self);help_action.setShortcut(QKeySequence("F1"));help_action.triggered.connect(lambda:self.open_help());self.addAction(help_action)
        root.addLayout(nav)
        self.fleet_button.clicked.connect(self.open_fleet);self.voyage_button.clicked.connect(self.open_voyages);self.export_button.clicked.connect(self.export_file);self.backup_button.clicked.connect(self.backup_menu);self.settings_button.clicked.connect(self.open_settings)

        self.route_panel=QFrame();self.route_panel.setObjectName("surface");route_root=QVBoxLayout(self.route_panel);route_root.setContentsMargins(14,8,14,8);route_root.setSpacing(7)
        first=QHBoxLayout();self.voyage_combo=QComboBox();self.voyage_combo.setMinimumWidth(170);self.voyage_combo.activated.connect(self.choose_voyage)
        first.addWidget(self.voyage_combo);self.new_voyage_button=QPushButton("New voyage");self.copy_voyage_button=QPushButton("Copy previous")
        first.addWidget(self.new_voyage_button);first.addWidget(self.copy_voyage_button);first.addStretch(1)
        self.route_add_button=QPushButton("+ Add vessel");first.addWidget(self.route_add_button);route_root.addLayout(first)
        second=QHBoxLayout();self.route_scroll=QScrollArea();self.route_scroll.setWidgetResizable(True);self.route_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded);self.route_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.route_scroll.setFixedHeight(58)
        self.route_content=QWidget();self.route_items=QHBoxLayout(self.route_content);self.route_items.setContentsMargins(0,1,0,1);self.route_items.setSpacing(8);self.route_items.addStretch(1);self.route_scroll.setWidget(self.route_content);second.addWidget(self.route_scroll,1)
        self.route_hint=QLabel("");self.route_hint.setMinimumWidth(190);self.route_hint.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);second.addWidget(self.route_hint);route_root.addLayout(second);root.addWidget(self.route_panel)
        self.new_voyage_button.clicked.connect(self.new_voyage);self.copy_voyage_button.clicked.connect(self.copy_voyage);self.route_add_button.clicked.connect(self.add_vessel_stop)

        self.stop_panel=QFrame();self.stop_panel.setObjectName("surface");stop_root=QVBoxLayout(self.stop_panel);stop_root.setContentsMargins(14,8,14,8);stop_root.setSpacing(3)
        top=QHBoxLayout();self.stop_title=QLabel("Current stop");self.stop_title.setObjectName("sectionTitle");self.stop_name=QLabel("");self.stop_name.setObjectName("stopName");top.addWidget(self.stop_title);top.addWidget(self.stop_name);top.addStretch(1)
        self.previous_button=QPushButton("Previous");self.next_button=QPushButton("Next");self.choose_stop_combo=QComboBox();self.choose_stop_combo.setMinimumWidth(220);self.choose_stop_combo.activated.connect(self.choose_stop)
        for widget in (self.previous_button,self.next_button,self.choose_stop_combo):top.addWidget(widget)
        stop_root.addLayout(top)
        counts=QHBoxLayout();self.pickup_count=QPushButton("0 ready to pick up");self.delivery_count=QPushButton("0 ready to deliver");self.other_count=QPushButton("0 other related");self.vessel_count=QPushButton("On my vessel 0")
        for button in (self.pickup_count,self.delivery_count,self.other_count):button.setFlat(True);counts.addWidget(button)
        counts.addStretch(1);counts.addWidget(self.vessel_count);self.view_all_button=QPushButton("View all");counts.addWidget(self.view_all_button);stop_root.addLayout(counts)
        self.preview_buttons=[];preview=QHBoxLayout()
        for _ in range(2):
            button=QPushButton("");button.setVisible(False);button.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.preview_buttons.append(button);preview.addWidget(button)
        stop_root.addLayout(preview);root.addWidget(self.stop_panel)
        self.previous_button.clicked.connect(lambda:self.move_current_stop(-1));self.next_button.clicked.connect(lambda:self.move_current_stop(1))
        self.pickup_count.clicked.connect(lambda:self.show_current_group("pick_up"));self.delivery_count.clicked.connect(lambda:self.show_current_group("deliver"));self.other_count.clicked.connect(lambda:self.show_current_group("other"))
        self.view_all_button.clicked.connect(self.view_current_all);self.vessel_count.clicked.connect(self.open_on_my_vessel)

        tabs=QHBoxLayout();self.tabs=QTabBar();self.tabs.setDrawBase(False);self.tabs.setExpanding(False);self.tabs.setMinimumWidth(365);self.tabs.addTab("All transfers");self.tabs.addTab("Current stop");self.tabs.addTab("On my vessel");self.tabs.currentChanged.connect(self._tab_changed);tabs.addWidget(self.tabs);tabs.addStretch(1)
        self.add_button=QPushButton("+ Add cargo");self.add_button.setObjectName("primaryButton");tabs.addWidget(self.add_button);root.addLayout(tabs);self.add_button.clicked.connect(self.add_transfer)
        search_row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText("Search NO, Cargo ID, description, physical ID or comment…");self.search.setClearButtonEnabled(True);self.search.setMinimumWidth(180);search_row.addWidget(self.search,1)
        self.clear_button=QPushButton("Clear filters");search_row.addWidget(self.clear_button);root.addLayout(search_row)
        filters=QHBoxLayout()
        self.status_filter=QComboBox();self.status_filter.addItems(["All statuses","Waiting","On Board","Done"]);filters.addWidget(self.status_filter)
        self.vessel_filter=QComboBox();self.vessel_filter.addItem("All vessels","");filters.addWidget(self.vessel_filter)
        self.range_filter=QComboBox();self.range_filter.addItem("Open only","open");self.range_filter.addItem("Include completed","all");self.range_filter.addItem("Completed only","completed");self.range_filter.addItem("Deleted records","voided");filters.addWidget(self.range_filter)
        filters.addStretch(1);self.result_label=QLabel("Loading local ledger…");filters.addWidget(self.result_label);root.addLayout(filters)
        self._search_timer=QTimer(self);self._search_timer.setSingleShot(True);self._search_timer.setInterval(240);self._search_timer.timeout.connect(self._apply_search)
        self.search.textChanged.connect(lambda *_:self._search_timer.start());self.clear_button.clicked.connect(self.clear_filters)
        self.status_filter.currentIndexChanged.connect(self._filters_changed);self.vessel_filter.currentIndexChanged.connect(self._filters_changed);self.range_filter.currentIndexChanged.connect(self._filters_changed)

        self.model=TransferTableModel(self);self.proxy=QSortFilterProxyModel(self);self.proxy.setSourceModel(self.model);self.proxy.setSortRole(Qt.ItemDataRole.DisplayRole)
        self.table=QTableView();self.table.setModel(self.proxy);self.table.setItemDelegateForColumn(5,StatusDelegate(self.table));self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(False);self.table.setWordWrap(False);self.table.setSortingEnabled(False);self.table.setShowGrid(False);self.table.verticalHeader().setVisible(False);self.table.verticalHeader().setDefaultSectionSize(44);self.table.horizontalHeader().setSectionsClickable(True);self.table.horizontalHeader().setStretchLastSection(False)
        root.addWidget(self.table,1);self.table.doubleClicked.connect(self.open_selected_detail);self.table.selectionModel().currentChanged.connect(self._selection_changed);self.table.horizontalHeader().sectionClicked.connect(self._sort_clicked)
        self.selected_label=QLabel("Select a transfer to see available actions");self.selected_label.setWordWrap(True);root.addWidget(self.selected_label)
        actions=QHBoxLayout();self.details_button=QPushButton("Details");self.pickup_button=QPushButton("Pick up");self.deliver_button=QPushButton("Deliver");self.edit_button=QPushButton("Edit fields");self.more_button=QToolButton();self.more_button.setText("More  ⌄");self.more_button.setAccessibleName("More transfer actions");self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.more_menu=QMenu(self.more_button);self.more_button.setMenu(self.more_menu)
        for button in (self.details_button,self.pickup_button,self.deliver_button,self.edit_button,self.more_button):actions.addWidget(button)
        self.status_choice=QComboBox();self.status_choice.setAccessibleName("Change selected transfer status");self.status_choice.addItems(["Waiting","On Board","Done"]);self.status_choice.setEnabled(False);self.status_choice.activated.connect(self.change_selected_status);actions.insertWidget(0,self.status_choice)
        self.delete_button=QPushButton("Delete…");self.delete_button.setAccessibleName("Delete selected transfer");self.delete_button.clicked.connect(self.delete_selected_transfer);actions.addWidget(self.delete_button)
        root.addLayout(actions);self.details_button.clicked.connect(self.open_selected_detail);self.pickup_button.clicked.connect(lambda:self.run_selected_action("pick_up"));self.deliver_button.clicked.connect(lambda:self.run_selected_action("deliver"));self.edit_button.clicked.connect(self.edit_selected)
        self.more_button.setEnabled(False)

        footer=QHBoxLayout();self.status_text=QLabel("Local data  ·  "+self.database_path.parent.name);self.status_text.setToolTip(str(self.database_path.parent));self.status_text.setAccessibleDescription(str(self.database_path.parent));self.status_text.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);footer.addWidget(self.status_text,1)
        self.previous_page=QPushButton("Previous page");self.page_label=QLabel("");self.next_page=QPushButton("Next page")
        footer.addWidget(self.previous_page);footer.addWidget(self.page_label);footer.addWidget(self.next_page);root.addLayout(footer)
        self.previous_page.clicked.connect(lambda:self.change_page(-1));self.next_page.clicked.connect(lambda:self.change_page(1))
        self.statusBar().showMessage("Opening local ledger…")

    def _apply_saved_layout(self):
        size=self.settings.value("window/size")
        if size:self.resize(size)
        widths=self.settings.value("table/widths")
        if widths:
            try:
                for column,value in enumerate(json.loads(widths)):
                    if column<self.model.columnCount():self.table.setColumnWidth(column,int(value))
                return
            except (ValueError,TypeError,json.JSONDecodeError):pass
        for column,width in enumerate((58,112,330,96,112,118,340,150)):self.table.setColumnWidth(column,width)

    def _send(self,operation,payload=None,meta=None):
        key=(meta or {}).get("latest_key")
        request_id=self.client.request(operation,payload,meta)
        if key:self._latest[key]=request_id
        return request_id

    def _submit(self,operation,payload,message,on_success=None):
        if self._busy:return
        self._busy=True;self.statusBar().showMessage("Saving…")
        self._send("_command",{"command_id":str(uuid4()),"operation":operation,"payload":payload},meta={"kind":"action","message":message,"on_success":on_success})

    def _opened(self,snapshot):
        self._set_snapshot(snapshot);self._fill_filters();self._refresh_table();self.statusBar().showMessage("Local ledger ready",4000)
        if snapshot["counts"]["all"]==0 and not snapshot["vessels"]:self.statusBar().showMessage("Start by adding a vessel in Fleet, or add a shore-to-shore transfer.",12000)

    def _startup_failed(self,message,details):
        self.status_text.setText(f"Could not open local ledger: {message}")
        info_box(self,"Cargo Track could not open its data",message,json.dumps(details,ensure_ascii=False,indent=2) if details else "")

    def _received(self,request_id,envelope):
        meta=self.client.take(request_id);key=meta.get("latest_key")
        if key and self._latest.get(key)!=request_id:
            self._finish_refresh(meta)
            return
        kind=envelope.get("kind");data=envelope.get("data")
        if kind=="receipt":
            self._busy=False;self.statusBar().showMessage(meta.get("message","Saved."),7000)
            self._refresh_then(meta.get("on_success"))
        elif kind=="workspace":self._set_snapshot(data)
        elif kind=="query" and meta.get("kind")=="preview":self._show_preview(data)
        elif kind=="query":self._show_query(data)
        elif kind=="preview":self._show_preview(data)
        elif kind=="detail":
            dialog=meta.get("dialog")
            if dialog and dialog.isVisible():dialog.set_detail(data)
        elif kind in ("vessels","fleet_details"):
            dialog=meta.get("dialog")
            if dialog and dialog.isVisible():dialog.set_rows(data)
        elif kind=="voyage_history":
            dialog=meta.get("dialog")
            if dialog and dialog.isVisible():dialog.set_rows(data)
        elif kind=="cargo_choices":
            self.cargo_choices=data or []
            callback=meta.get("callback")
            if callback:callback(self.cargo_choices)
        elif kind=="backup_preview":self._confirm_restore(data)
        elif kind=="restore":
            self.pending_restore_path=None;self.statusBar().showMessage("Restore complete. The previous ledger was kept as a safety copy.",10000)
            info_box(self,"Backup restored",f"Restored {data['counts']['transfer_legs']} transfers.",f"Safety copy: {data['safety_copy']}")
            self._refresh_then()
        elif kind=="relocated":
            self.database_path=Path(data["path"]);self.data_directory=self.database_path.parent
            QSettings().setValue("storage/database_directory",str(self.data_directory))
            self.status_text.setText("Local data  ·  "+self.data_directory.name);self.status_text.setToolTip(str(self.data_directory));self.status_text.setAccessibleDescription(str(self.data_directory))
            self._save_backup_directory(meta["backup_directory"])
            self._refresh_table();self.statusBar().showMessage("Database location changed. The original file was retained as a safety copy.",12000)
        elif kind=="backup":info_box(self,"Backup created",f"Saved {data['transfers']} transfers.",data["path"])
        elif kind=="export":info_box(self,"Export complete",f"Exported {data['transfers']} transfers.",data["path"])
        self._finish_refresh(meta)

    def _finish_refresh(self,meta):
        refresh_id=meta.get("refresh_id")
        if refresh_id in self._refresh_wait:
            self._refresh_wait[refresh_id]-=1
            if self._refresh_wait[refresh_id]<=0:
                callback=self._refresh_callbacks.pop(refresh_id,None);self._refresh_wait.pop(refresh_id,None)
                if callback:callback()

    def _rejected(self,request_id,error):
        meta=self.client.take(request_id)
        if meta.get("kind")=="action":self._busy=False
        if meta.get("refresh_id") in self._refresh_wait:
            refresh_id=meta["refresh_id"];self._refresh_wait[refresh_id]-=1
            if self._refresh_wait[refresh_id]<=0:self._refresh_wait.pop(refresh_id,None);callback=self._refresh_callbacks.pop(refresh_id,None);callback and callback()
        self._update_selected_actions()
        message=error.get("message","The request failed.");self.statusBar().showMessage(message,12000)
        if error.get("code")=="RESTORE_RECOVERY_REQUIRED":
            self.centralWidget().setEnabled(False);self.statusBar().showMessage(message,0)
        dialog=meta.get("dialog")
        if dialog and hasattr(dialog,"setEnabled"):dialog.setEnabled(True)
        info_box(self,"Cargo Track",message,json.dumps(error.get("details",{}),ensure_ascii=False,indent=2) if error.get("details") else "")

    def _maintenance(self,active):
        self.centralWidget().setEnabled(not active)
        self.statusBar().showMessage("Updating ledger…",0) if active else self.statusBar().showMessage("Ledger ready",5000)

    def _refresh_then(self,callback=None):
        identifier=str(uuid4());self._refresh_wait[identifier]=2;self._refresh_callbacks[identifier]=callback
        self._send("_workspace",{},meta={"kind":"workspace","refresh_id":identifier,"latest_key":"workspace"})
        self._request_table(refresh_id=identifier)

    def _set_snapshot(self,snapshot):
        if snapshot is None:return
        if self.snapshot and snapshot["dataset_epoch"]==self.snapshot["dataset_epoch"] and snapshot["revision"]<self.snapshot["revision"]:return
        epoch_changed=bool(self.snapshot and snapshot["dataset_epoch"]!=self.snapshot["dataset_epoch"])
        self.snapshot=snapshot
        if epoch_changed:self.page=0;self.selected_no=None;self.model.replace([])
        self._updating=True
        self.voyage_combo.blockSignals(True);self.voyage_combo.clear()
        current_voyage=next((voyage for voyage in snapshot["voyages"] if voyage["id"]==snapshot["current_voyage_id"]),None)
        self.voyage_combo.addItem(current_voyage["name"] if current_voyage else "No active voyage",current_voyage["id"] if current_voyage else None)
        self.voyage_combo.setToolTip("Open Voyages to review history or create/copy a working voyage.")
        self.voyage_combo.setEnabled(False)
        self.voyage_combo.blockSignals(False)
        self._render_stops();self._render_current_stop();self._fill_filters(update_values=True)
        counts=snapshot["counts"]
        self.tabs.setTabText(0,f"All transfers  {counts['all']}")
        self.tabs.setTabText(1,f"Current stop  {counts['pickup']+counts['delivery']+counts['other']}")
        self.tabs.setTabText(2,f"On my vessel  {counts['onboard']}")
        self._updating=False
        if epoch_changed:self._refresh_table()

    def _render_stops(self):
        while self.route_items.count():
            item=self.route_items.takeAt(0);widget=item.widget()
            if widget:widget.deleteLater()
        stops=self.snapshot["stops"];current=self.snapshot["current_stop_id"]
        for index,stop in enumerate(stops):
            label=f"{index+1}  ·  {stop['vessel_name_snapshot']}"
            if stop["id"]==current:label+="  ·  Current"
            button=QToolButton();button.setText(label);button.setCheckable(True);button.setChecked(stop["id"]==current);button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setAccessibleName(f"Stop {index+1}, {stop['vessel_name_snapshot']}"+(", current stop" if stop["id"]==current else ""))
            button.setStyleSheet("QToolButton { padding-right: 30px; }");button.setMinimumHeight(28);button.clicked.connect(lambda checked=False,identifier=stop["id"]:self._choose_stop_id(identifier))
            menu=QMenu(button);earlier=menu.addAction("Move earlier");later=menu.addAction("Move later");menu.addSeparator();remove=menu.addAction("Remove this stop")
            earlier.setEnabled(index>0);later.setEnabled(index<len(stops)-1)
            earlier.triggered.connect(lambda _,i=index:self._move_stop(i,-1));later.triggered.connect(lambda _,i=index:self._move_stop(i,1));remove.triggered.connect(lambda _,identifier=stop["id"]:self.remove_stop(identifier))
            button.setMenu(menu);button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup);self.route_items.addWidget(button)
        self.route_items.addStretch(1)
        no_voyage=self.snapshot["current_voyage_id"] is None
        self.route_hint.setText("Create a voyage to add stops" if no_voyage else "No vessels in this voyage" if not stops else "Open a stop menu to move or remove")
        self.route_add_button.setEnabled(not no_voyage)

    def _render_current_stop(self):
        s=self.snapshot;stop_id=s["current_stop_id"];stops=s["stops"]
        self.choose_stop_combo.blockSignals(True);self.choose_stop_combo.clear()
        for i,stop in enumerate(stops,1):self.choose_stop_combo.addItem(f"Choose: {i}  ·  {stop['vessel_name_snapshot']}",stop["id"])
        self.choose_stop_combo.setEnabled(bool(stops));index=self.choose_stop_combo.findData(stop_id)
        if index>=0:self.choose_stop_combo.setCurrentIndex(index)
        self.choose_stop_combo.blockSignals(False)
        enabled=stop_id is not None and bool(stops)
        if enabled:
            position=next((i for i,item in enumerate(stops) if item["id"]==stop_id),-1)
            stop=stops[position] if position>=0 else None
            vessel=(stop.get("current_name") or stop["vessel_name_snapshot"]) if stop else ""
            self.stop_name.setText(f"{vessel}  ·  {position+1} of {len(stops)}")
            self.stop_name.setStyleSheet("color:"+themed_color("#24262B","#E6E8ED")+";font-size:20px;font-weight:600;")
            self.previous_button.setEnabled(position>0);self.next_button.setEnabled(0<=position<len(stops)-1)
        else:
            self.stop_name.setText("No voyage selected" if s["current_voyage_id"] is None else "Add a vessel to choose your current stop." if not stops else "Choose the current stop")
            self.stop_name.setStyleSheet("color:"+themed_color("#59677D","#ADB4C1")+";font-size:16px;")
            self.previous_button.setEnabled(False);self.next_button.setEnabled(False)
        self.pickup_count.setText(f"{len(s['ready_pickup'])} ready to pick up")
        self.delivery_count.setText(f"{len(s['ready_delivery'])} ready to deliver")
        self.other_count.setText(f"{len(s['other_related'])} other related")
        self.vessel_count.setText(f"On my vessel  {len(s['onboard_ids'])}")
        self.pickup_count.setStyleSheet("color:"+themed_color("#7A4B00","#FFD58A")+";");self.delivery_count.setStyleSheet("color:"+themed_color("#174B87","#A9D0FF")+";");self.other_count.setStyleSheet("color:"+themed_color("#59677D","#ADB4C1")+";")
        total=len(s["ready_pickup"])+len(s["ready_delivery"])+len(s["other_related"])
        self.view_all_button.setText(f"View all {total}")
        self.view_all_button.setEnabled(enabled and total>0)
        self.stop_panel.setVisible(True)
        self._send("_query",{"view":"current_stop","filters":{"range":"open"},"limit":200,"offset":0},meta={"kind":"preview","latest_key":"preview"})

    def _fill_filters(self,update_values=False):
        if self.snapshot is None:return
        vessels=self.snapshot["vessels"]
        selected=self.vessel_filter.currentData() if self.vessel_filter.count() else ""
        self.vessel_filter.blockSignals(True);self.vessel_filter.clear();self.vessel_filter.addItem("All vessels","")
        for vessel in vessels:self.vessel_filter.addItem(vessel["name"]+(" (Inactive)" if not vessel["active"] else ""),vessel["id"])
        if selected:
            idx=self.vessel_filter.findData(selected)
            if idx>=0:self.vessel_filter.setCurrentIndex(idx)
        self.vessel_filter.blockSignals(False)
        if update_values:
            filters=self.filters.get(self.view,OPEN_FILTER)
            self.search.blockSignals(True);self.search.setText(filters.get("query",""));self.search.blockSignals(False)
            self.status_filter.blockSignals(True);self.status_filter.setCurrentIndex(max(0,self.status_filter.findText(filters.get("status","") or "All statuses")));self.status_filter.blockSignals(False)
            self.range_filter.blockSignals(True);self.range_filter.setCurrentIndex(max(0,self.range_filter.findData(filters.get("range","open"))));self.range_filter.blockSignals(False)
            idx=self.vessel_filter.findData(filters.get("vessel_id","") or "")
            if idx>=0:self.vessel_filter.setCurrentIndex(idx)

    def _filters_changed(self,*_):
        if self._updating:return
        self.filters[self.view]={"range":self.range_filter.currentData() or "open","query":self.search.text().strip(),
            "status":"" if self.status_filter.currentIndex()==0 else self.status_filter.currentText(),"vessel_id":self.vessel_filter.currentData() or ""}
        self.page=0;self._request_table()

    def _apply_search(self):
        if self.snapshot is None:return
        self.filters[self.view]["query"]=self.search.text().strip();self.page=0;self._request_table()

    def clear_filters(self):
        self.filters[self.view]=dict(OPEN_FILTER if self.view!="all" else OPEN_FILTER)
        self._updating=True;self.search.clear();self.status_filter.setCurrentIndex(0);self.vessel_filter.setCurrentIndex(0);self.range_filter.setCurrentIndex(0);self._updating=False
        self.page=0;self._request_table()

    def _tab_changed(self,index):
        if self._updating or self.snapshot is None:return
        self.view={0:"all",1:"current_stop",2:"on_my_vessel"}.get(index,"all")
        self.page=0;self.selected_no=None;self._fill_filters(update_values=True)
        self.status_filter.setEnabled(self.view!="on_my_vessel");self.range_filter.setEnabled(self.view=="all")
        self._request_table()

    def _request_table(self,refresh_id=None):
        if self.snapshot is None:return
        selected=self.filters.get(self.view,OPEN_FILTER)
        payload={"view":self.view,"filters":dict(selected),"order_column":self.order_column,"descending":self.descending,"limit":PAGE_SIZE,"offset":self.page*PAGE_SIZE}
        meta={"kind":"query","latest_key":"query","refresh_id":refresh_id}
        self._send("_query",payload,meta)

    def _show_query(self,data):
        if not self.snapshot or data.get("epoch")!=self.snapshot.get("dataset_epoch"):return
        if data.get("revision",0)<self.snapshot.get("revision",0):return
        preserve=self.selected_no;self._selection_reset=True;self.model.replace(data["rows"]);self._selection_reset=False;self.page_total=data["total"]
        start=data["offset"]+1 if data["total"] else 0;end=data["offset"]+len(data["rows"])
        self.result_label.setText(f"Showing {start}–{end} of {data['total']} transfers" if data["total"]>PAGE_SIZE else f"{data['total']} transfers  ·  {data['total']} loaded")
        pages=max(1,(data["total"]+PAGE_SIZE-1)//PAGE_SIZE);self.page_label.setText(f"Page {self.page+1} of {pages}")
        self.previous_page.setEnabled(self.page>0);self.next_page.setEnabled((self.page+1)*PAGE_SIZE<data["total"])
        self.selected_no=preserve
        if self.selected_no:
            for index,row in enumerate(self.model.rows):
                if row["no"]==self.selected_no:
                    proxy=self.proxy.mapFromSource(self.model.index(index,0));self.table.selectRow(proxy.row());break
            else:self.selected_no=None;self.table.clearSelection()
        self._update_selected_actions()

    def change_page(self,delta):self.page=max(0,self.page+delta);self.selected_no=None;self._request_table()

    def _sort_clicked(self,column):
        if self.order_column==column:self.descending=not self.descending
        else:self.order_column=column;self.descending=False
        self.page=0;self.table.horizontalHeader().setSortIndicator(column,Qt.SortOrder.DescendingOrder if self.descending else Qt.SortOrder.AscendingOrder);self._request_table()

    def _selection_changed(self,current,*_):
        if getattr(self,"_selection_reset",False):return
        if not current.isValid():self.selected_no=None;self._update_selected_actions();return
        mapped=self.proxy.mapToSource(current);row=self.model.row_at(mapped.row());self.selected_no=row["no"] if row else None;self._update_selected_actions()

    def _selected_row(self):
        index=self.table.currentIndex()
        if not index.isValid():return None
        mapped=self.proxy.mapToSource(index);return self.model.row_at(mapped.row())

    def _update_selected_actions(self):
        row=self._selected_row()
        self.delete_button.setEnabled(bool(row));self.delete_button.setText("Restore…" if row and row["is_void"] else "Delete…");self.delete_button.setToolTip("Restore this deleted record" if row and row["is_void"] else "Remove this record from normal lists; keep history and allow restore")
        self.status_choice.blockSignals(True);self.status_choice.setEnabled(bool(row and not row["is_void"]));self.status_choice.setCurrentText(row["status"] if row else "Waiting");self.status_choice.blockSignals(False)
        for button in (self.details_button,self.edit_button,self.pickup_button,self.deliver_button,self.more_button):button.setEnabled(row is not None)
        if not row:self.selected_label.setText("Select a transfer to see available actions");return
        self.selected_label.setText(f"Selected: #{row['no']}  ·  {row['cargo_tag']}  ·  {row['status']}")
        self.pickup_button.setVisible(not row["is_void"] and row["status"]=="Waiting")
        self.deliver_button.setVisible(not row["is_void"] and row["status"]=="On Board")
        self.edit_button.setVisible(not row["is_void"])
        self.more_menu.clear()
        if row["is_void"]:
            restore=self.more_menu.addAction("Restore transfer…");restore.triggered.connect(lambda:self.restore_selected(row))
        else:
            correction=self.more_menu.addAction("Correct record…");correction.triggered.connect(lambda:self.correct_selected(row))
            void=self.more_menu.addAction("Delete record…");void.setEnabled(row["status"]!="On Board");void.triggered.connect(self.delete_selected_transfer)

    def _refresh_table(self):
        self.page=0;self._refresh_then()

    def _move_stop(self,position,direction):
        stops=self.snapshot["stops"];new=position+direction
        if new<0 or new>=len(stops):return
        identifiers=[row["id"] for row in stops];identifiers[position],identifiers[new]=identifiers[new],identifiers[position]
        self._submit("reorder_stops",{"stop_ids":identifiers},"Voyage order saved.")

    def remove_stop(self,stop_id):
        stop=next((item for item in self.snapshot["stops"] if item["id"]==stop_id),None)
        if stop and confirm(self,"Remove this stop?",f"Remove {stop['vessel_name_snapshot']} from this voyage?","The Fleet vessel and cargo records will stay unchanged."):
            self._submit("remove_stop",{"stop_id":stop_id},"Stop removed from this voyage.")

    def _choose_stop_id(self,identifier):self._submit("choose_stop",{"stop_id":identifier},"Current stop saved.")

    def choose_stop(self,index):
        identifier=self.choose_stop_combo.itemData(index)
        if identifier is not None and identifier!=self.snapshot["current_stop_id"]:self._choose_stop_id(identifier)

    def choose_voyage(self,index):
        identifier=self.voyage_combo.itemData(index)
        if identifier is not None and identifier!=self.snapshot["current_voyage_id"]:
            if confirm(self,"Change active voyage?",f"Switch to {self.voyage_combo.currentText()}?","The current stop will be cleared. Choose one on the selected voyage."):
                self._submit("set_current_voyage",{"voyage_id":identifier},"Active voyage changed.")
            else:self._set_snapshot(self.snapshot)

    def move_current_stop(self,delta):
        stops=self.snapshot["stops"];position=next((i for i,row in enumerate(stops) if row["id"]==self.snapshot["current_stop_id"]),-1);target=position+delta
        if position<0 or not 0<=target<len(stops):return
        self._submit("choose_stop",{"stop_id":stops[target]["id"]},"Current stop saved.")

    def add_vessel_stop(self):
        if not self.snapshot or not self.snapshot["vessels"]:
            info_box(self,"Fleet is empty","Add a vessel to Fleet first. The voyage can remain empty while you manage transfers.");return
        names=[row["name"] for row in self.snapshot["vessels"] if row["active"]]
        if not names:info_box(self,"No active vessels","Reactivate or add a vessel in Fleet first.");return
        name,ok=QInputDialog.getItem(self,"Add vessel to voyage","Choose a Fleet vessel",names,0,False)
        if ok:
            vessel=next(row for row in self.snapshot["vessels"] if row["name"]==name)
            self._submit("add_stop",{"vessel_id":vessel["id"]},f"Added {name} as a new stop.")

    def new_voyage(self):
        name,ok=QInputDialog.getText(self,"New voyage","Voyage name")
        if ok and name.strip():
            if confirm(self,"Create an empty voyage?",f"Start {name.strip()} with no stops?","You can add or copy stops later. No current stop will be selected automatically."):
                self._submit("create_voyage",{"name":name.strip()},"New empty voyage created.")

    def copy_voyage(self):
        name,ok=QInputDialog.getText(self,"Copy voyage","Name for the copied route",text="New voyage")
        if ok and name.strip():self._submit("copy_voyage",{"name":name.strip()},"Voyage copied. Choose a current stop to begin.")

    def show_current_group(self,action):
        if not self.snapshot or self.snapshot["current_stop_id"] is None:return
        self._updating=True;self.tabs.setCurrentIndex(1);self._updating=False;self.view="current_stop"
        self.filters["current_stop"].update({"range":"open","query":"","status":"","vessel_id":"","action":action})
        self._fill_filters(update_values=True);self.page=0;self._request_table()

    def view_current_all(self):
        self.filters["current_stop"]={"range":"open","query":"","status":"","vessel_id":"","action":""}
        self._updating=True;self.tabs.setCurrentIndex(1);self._updating=False;self.view="current_stop";self._fill_filters(update_values=True);self.page=0;self._request_table()

    def open_on_my_vessel(self):
        self._updating=True;self.tabs.setCurrentIndex(2);self._updating=False;self.view="on_my_vessel";self._fill_filters(update_values=True);self.page=0;self._request_table()

    def _show_preview(self,data):
        if not self.snapshot or data.get("epoch")!=self.snapshot["dataset_epoch"]:return
        candidates=data.get("rows",[]);selected=[]
        for desired in ("pick_up","deliver"):
            row=next((item for item in candidates if desired in item["allowed_actions"] and ((desired=="pick_up" and item["no"] in self.snapshot["ready_pickup"]) or (desired=="deliver" and item["no"] in self.snapshot["ready_delivery"]))),None)
            if row and row not in selected:selected.append(row)
        for button in self.preview_buttons:button.setVisible(False)
        for button,row in zip(self.preview_buttons,selected[:2]):
            verb="Pick up" if "pick_up" in row["allowed_actions"] and row["no"] in self.snapshot["ready_pickup"] else "Deliver"
            route=f"{row['from_name']} to {row['to_name']}";button.setText(f"{verb}  ·  #{row['no']}  ·  {row['description']}  ·  {route}")
            button.setToolTip(f"{row['status']}  ·  Cargo {row['cargo_tag']}")
            try:button.clicked.disconnect()
            except RuntimeError:pass
            button.clicked.connect(lambda checked=False,record=row,action=verb.lower().replace(" ","_"):self._preview_action(record,action))
            button.setVisible(True)

    def _preview_action(self,row,action):
        self.selected_no=row["no"]
        self._submit(action,{"no":row["no"],"expected_version":row["version"]},"Transfer updated.")

    def _sort_clicked(self,column):
        if self.order_column==column:self.descending=not self.descending
        else:self.order_column=column;self.descending=False
        self.page=0;self.selected_no=None
        self.table.horizontalHeader().setSortIndicator(column,Qt.SortOrder.DescendingOrder if self.descending else Qt.SortOrder.AscendingOrder)
        self._request_table()

    def open_selected_detail(self,*_):
        row=self._selected_row()
        if row:self.open_detail(row["no"])

    def open_detail(self,number):
        dialog=DetailDialog(self,number);self._detail_dialog=dialog;dialog.exec();
        if self._detail_dialog is dialog:self._detail_dialog=None

    def add_transfer(self):
        self._send("_cargo_choices",{},meta={"kind":"cargo_choices","callback":self._show_new_transfer})

    def _show_new_transfer(self,choices):
        form=TransferForm(vessels=self.snapshot.get("locations",[]),cargo_choices=choices,parent=self)
        if form.exec()==QDialog.DialogCode.Accepted:self._submit("create_transfer",form.payload(),"Transfer created.",on_success=lambda result:self._select_after_refresh(result.get("no")))

    def _select_after_refresh(self,number):
        self.selected_no=number;self.page=0;self._refresh_then()

    def edit_selected(self):
        row=self._selected_row()
        if not row or row["is_void"]:return
        form=TransferForm(vessels=self.snapshot.get("locations",[]),cargo_choices=[],initial=row,edit=True,parent=self)
        if form.exec()==QDialog.DialogCode.Accepted:self._submit("edit_transfer",form.payload(),"Transfer saved.")

    def change_selected_status(self,index):
        row=self._selected_row()
        if not row or row["is_void"] or self._busy:return
        target=self.status_choice.itemText(index)
        if target==row["status"]:return
        payload={"no":row["no"],"expected_version":row["version"]}
        if row["status"]=="Waiting" and target=="On Board":
            payload["confirmed_location"]=True;operation="pick_up"
        elif row["status"]=="On Board" and target=="Done":
            payload["confirmed_location"]=True;operation="deliver"
        else:
            payload.update(status=target,reason=f"Status dropdown: {row['status']} to {target}");operation="correct_transfer"
        self._submit(operation,payload,"Status saved.");self.status_choice.setEnabled(False)

    def delete_selected_transfer(self):
        row=self._selected_row()
        if not row:return
        if row["is_void"]:self.restore_selected(row);return
        if row["status"]=="On Board":
            info_box(self,"Resolve cargo location first","Change this cargo to Waiting or Done before deleting it.");return
        reason,ok=QInputDialog.getText(self,"Delete transfer?",f"Delete #{row['no']} · {row['cargo_tag']} · {row['description']}?\nThe record leaves normal lists. Restore it from Deleted records if needed.\nReason:",text="Deleted by user")
        if ok and reason.strip():self._submit("void_transfer",{"no":row["no"],"expected_version":row["version"],"reason":reason.strip()},"Record deleted. Restore it from Deleted records if needed.")

    def run_selected_action(self,operation):
        row=self._selected_row()
        if not row or row["is_void"]:return
        action_is_current=(operation=="pick_up" and row.get("current_relation") in ("from","both")) or (operation=="deliver" and row.get("current_relation") in ("to","both"))
        payload={"no":row["no"],"expected_version":row["version"]}
        if not action_is_current:
            endpoint=row["from_name"] if operation=="pick_up" else row["to_name"]
            noun="picked up" if operation=="pick_up" else "delivered"
            if not confirm(self,"Confirm physical location?",f"Confirm that this cargo was {noun} at {endpoint}?","This updates the recorded cargo location."):return
            payload["confirmed_location"]=True
        self._submit(operation,payload,"Transfer updated.")

    def correct_selected(self,row=None):
        row=row or self._selected_row()
        if not row or row["is_void"]:return
        dialog=CorrectionDialog(row,self.snapshot.get("locations",[]),self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self._submit("correct_transfer",dialog.payload(),"Correction saved.")

    def void_selected(self,row=None):
        row=row or self._selected_row()
        if not row:return
        reason,ok=QInputDialog.getText(self,"Void transfer",f"Reason for voiding transfer #{row['no']}")
        if ok and reason.strip():self._submit("void_transfer",{"no":row["no"],"expected_version":row["version"],"reason":reason.strip()},"Transfer voided.")

    def restore_selected(self,row=None):
        row=row or self._selected_row()
        if not row:return
        reason,ok=QInputDialog.getText(self,"Restore transfer",f"Reason for restoring transfer #{row['no']}")
        if ok and reason.strip():self._submit("restore_transfer",{"no":row["no"],"expected_version":row["version"],"reason":reason.strip()},"Transfer restored.")

    def open_help(self,section="start"):
        dialog=HelpDialog(self,section);dialog.exec()

    def open_fleet(self):
        dialog=FleetDialog(self);dialog.exec();self._refresh_then()

    def open_voyages(self):
        dialog=VoyagesDialog(self);self._send("_voyage_history",{},meta={"kind":"voyage_history","dialog":dialog});dialog.exec()

    def open_settings(self):
        if not self.snapshot:return
        dialog=SettingsDialog(self,self.snapshot.get("settings",{}),self.database_path,self.backup_directory)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            values=dialog.values();self._submit("set_setting",{"key":"business_timezone","value":values["business_timezone"]},"Settings saved.",on_success=lambda:self._save_transfer_vessel_name(values))

    def _save_transfer_vessel_name(self,values):
        self._submit("set_setting",{"key":"transfer_vessel_name","value":values["transfer_vessel_name"]},"Settings saved.",on_success=lambda:self._save_storage(values))

    def _save_backup_directory(self,path):
        self.backup_directory=Path(path)
        QSettings().setValue("storage/backup_directory",str(self.backup_directory))

    def _save_storage(self,values):
        QSettings().setValue("appearance/font_size",values["font_size"]);QSettings().setValue("appearance/theme",values["theme"]);configure_application(QApplication.instance());self._set_snapshot(self.snapshot);self.model.dataChanged.emit(self.model.index(0,0),self.model.index(max(0,len(self.model.rows)-1),7));fit_to_screen(self)
        target=Path(values["database_directory"])/"cargo-track.sqlite3"
        if target.resolve()!=self.database_path.resolve():
            self._send("_relocate",{"path":str(target)},meta={"backup_directory":values["backup_directory"]})
        else:self._save_backup_directory(values["backup_directory"])


    def backup_menu(self):
        menu=QMenu(self);create=menu.addAction("Create backup…");restore=menu.addAction("Restore backup…");menu.addSeparator();folder=menu.addAction("Open backup folder")
        choice=menu.exec(self.backup_button.mapToGlobal(self.backup_button.rect().bottomLeft()))
        if choice==create:self.create_backup()
        elif choice==restore:self.restore_backup()
        elif choice==folder:self.backup_directory.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.backup_directory)))

    def create_backup(self):
        self.backup_directory.mkdir(parents=True,exist_ok=True)
        default=self.backup_directory/f"CargoTrack-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
        path,_=QFileDialog.getSaveFileName(self,"Create database backup",str(default),"Cargo Track database (*.sqlite3 *.db)")
        if path:self._send("_backup",{"path":path},meta={"kind":"backup"})

    def restore_backup(self):
        path,_=QFileDialog.getOpenFileName(self,"Choose a Cargo Track backup",str(self.backup_directory),"Cargo Track database (*.sqlite3 *.db);;All files (*)")
        if path:self.pending_restore_path=path;self._send("_backup_preview",{"path":path},meta={"kind":"backup_preview"})

    def _confirm_restore(self,preview):
        if not confirm(self,"Restore this backup?",f"Restore {preview['counts']['transfer_legs']} transfers from this file?",
            f"Modified: {preview['modified_utc']}\nThe current database will be replaced. A safety copy will be saved automatically in:\n{self.database_path.parent}"):
            self.pending_restore_path=None;return
        self._send("_restore",{"path":preview["path"]},meta={"kind":"restore"})

    def export_file(self):
        mode=QMessageBox.question(self,"Export transfers",f"Export the full set matching this view and its filters?\n\n{self.result_label.text()}",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)
        if mode!=QMessageBox.StandardButton.Yes:return
        file_type,ok=QInputDialog.getItem(self,"Export format","File format",["Excel workbook (.xlsx)","CSV (.csv)"],0,False)
        if not ok:return
        fmt="xlsx" if file_type.startswith("Excel") else "csv";extension="xlsx" if fmt=="xlsx" else "csv"
        path,_=QFileDialog.getSaveFileName(self,"Export transfers",str(self.data_directory/f"CargoTrack-transfers.{extension}"),"Excel workbook (*.xlsx)" if fmt=="xlsx" else "CSV (*.csv)")
        if path:
            if Path(path).suffix.lower()!=f".{extension}":path+=f".{extension}"
            view=self.view if self.view!="voided" else "voided"
            self._send("_export",{"path":path,"view":view,"filters":dict(self.filters.get(self.view,OPEN_FILTER)),"format":fmt,"include_completed":True},meta={"kind":"export"})

    def keyPressEvent(self,event):
        if event.matches(QKeySequence.StandardKey.Find):self.search.setFocus();self.search.selectAll();event.accept();return
        if event.matches(QKeySequence.StandardKey.New):self.add_transfer();event.accept();return
        if event.key()==Qt.Key.Key_Return and self._selected_row():self.open_selected_detail();event.accept();return
        super().keyPressEvent(event)

    def closeEvent(self,event):
        widths=[self.table.columnWidth(i) for i in range(self.model.columnCount())];self.settings.setValue("table/widths",json.dumps(widths));self.settings.setValue("window/size",self.size())
        self.client.close();super().closeEvent(event)


class VoyagesDialog(AppDialog):
    def __init__(self,host):
        super().__init__(host);self.host=host;self.rows=[];self.setWindowTitle("Voyages");self.resize(620,500)
        root=QVBoxLayout(self);self.list=QListWidget();self.list.setAccessibleName("Voyage history");root.addWidget(self.list)
        self.details=QLabel("Voyage stops are read-only after a new voyage replaces the active route.");self.details.setWordWrap(True);root.addWidget(self.details)
        actions=QHBoxLayout();self.new_button=QPushButton("New empty voyage");self.copy_button=QPushButton("Copy selected route");self.close_button=QPushButton("Close");self.delete_button=QPushButton("Delete…");self.delete_button.clicked.connect(self.delete_selected)
        for button in (self.new_button,self.copy_button,self.delete_button,self.close_button):actions.addWidget(button)
        help_button=QPushButton("Help");help_button.clicked.connect(lambda:self.host.open_help("voyages"));actions.addWidget(help_button)
        root.addLayout(actions);self.list.currentRowChanged.connect(self.show_selected);self.new_button.clicked.connect(self.new);self.copy_button.clicked.connect(self.copy_selected);self.close_button.clicked.connect(self.accept)

    def set_rows(self,rows):
        self.rows=rows;self.list.clear()
        for row in rows:
            state="Current · editable" if row["is_current"] else "History · read-only" if row["archived"] else "Available"
            item=QListWidgetItem(f"{row['name']}     {state}");item.setData(Qt.ItemDataRole.UserRole,row);self.list.addItem(item)
        self.list.setCurrentRow(0 if rows else -1);self.show_selected()

    def show_selected(self,*_):
        item=self.list.currentItem();row=item.data(Qt.ItemDataRole.UserRole) if item else None
        stops=[stop["vessel_name_snapshot"] for stop in row["stops"] if not stop["removed"]] if row else []
        self.details.setText(("Route: "+"  →  ".join(stops) if stops else "This voyage has no active stops.")+"\nA historical voyage is read-only. Copy its route to create a new working voyage.")
        self.copy_button.setEnabled(bool(row));self.delete_button.setEnabled(bool(row));self._selected=row

    def new(self):
        name,ok=QInputDialog.getText(self,"New voyage","Voyage name")
        if ok and name.strip() and confirm(self,"Create a new voyage?",f"Create {name.strip()} with no stops?","The active route will become read-only. You can add stops later."):
            self.host._submit("create_voyage",{"name":name.strip()},"New voyage created.",on_success=lambda *_:self.host._refresh_then())

    def delete_selected(self):
        row=self._selected
        if row and confirm(self,"Delete voyage?",f"Delete {row['name']}?","The route leaves the voyage list. Cargo and audit history are retained. Deleting the current voyage clears the current stop."):
            self.host._submit("delete_voyage",{"voyage_id":row["id"]},"Voyage deleted.",on_success=lambda:self.host._send("_voyage_history",meta={"dialog":self}))

    def copy_selected(self):
        if not self._selected:return
        source=self._selected
        name,ok=QInputDialog.getText(self,"Copy route",f"Name for a copy of {source['name']}",text=source["name"]+" (copy)")
        if ok and name.strip():self.host._submit("copy_voyage",{"name":name.strip(),"voyage_id":source["id"]},"Route copied into a new working voyage.",on_success=lambda *_:self.host._refresh_then())


class SettingsDialog(AppDialog):
    def __init__(self,host,settings,database_path,backup_directory):
        super().__init__(host);self.setWindowTitle("Settings");self.resize(690,380)
        root=QVBoxLayout(self);root.setSpacing(14);form=QFormLayout();form.setSpacing(12)
        self.timezone=QComboBox();self.timezone.setAccessibleName("Business time zone")
        current=settings.get("business_timezone","Asia/Riyadh")
        for label,zone in time_zone_choices(current):self.timezone.addItem(label,zone)
        self.timezone.setCurrentIndex(self.timezone.findData(current));self.timezone.setMaxVisibleItems(12)
        self.transfer_vessel=QLineEdit(settings.get("transfer_vessel_name",""));self.transfer_vessel.setPlaceholderText("Optional name for the transfer vessel")
        form.addRow("Business time zone",self.timezone);form.addRow("Transfer vessel name",self.transfer_vessel)
        self.database_directory=QLineEdit(str(Path(database_path).parent));self.backup_directory=QLineEdit(str(backup_directory))
        for label,field in (("Database folder",self.database_directory),("Backup folder",self.backup_directory)):
            field.setReadOnly(True);field.setCursorPosition(0);field.setToolTip(field.text());field.setAccessibleName(label);row=QHBoxLayout();row.addWidget(field,1);choose=QPushButton("Choose…");choose.setAccessibleName("Choose "+label.lower());choose.clicked.connect(lambda _,f=field,l=label:self.choose_directory(f,l));row.addWidget(choose);form.addRow(label,row)
        root.addLayout(form)
        note=QLabel("Changing the database folder copies the current ledger safely. The original file stays as a safety copy. Existing databases are never overwritten.");note.setWordWrap(True);root.addWidget(note)
        self.theme=QComboBox();self.theme.setAccessibleName("Appearance mode");self.theme.addItem("Light","light");self.theme.addItem("Dark","dark");self.theme.setCurrentIndex(self.theme.findData("dark" if is_dark_mode() else "light"));form.addRow("Appearance",self.theme)
        self.font_size=QComboBox();self.font_size.setAccessibleName("Interface font size")
        for size,label in ((10,"Compact · 10 pt"),(11,"Standard · 11 pt"),(12,"Large · 12 pt")):self.font_size.addItem(label,size)
        self.font_size.setCurrentIndex(self.font_size.findData(application_font_size()));form.addRow("Font size",self.font_size)
        self.font_label=QLabel("Font: Inter · bundled with Cargo Track");root.addWidget(self.font_label)
        root.addStretch(1);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Save);buttons.addButton("Help",QDialogButtonBox.ButtonRole.HelpRole).clicked.connect(lambda:host.open_help("settings"));buttons.accepted.connect(self.validate_and_accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
    def choose_directory(self,field,label):
        path=QFileDialog.getExistingDirectory(self,"Choose "+label.lower(),field.text())
        if path:field.setText(path);field.setCursorPosition(0);field.setToolTip(path)
    def validate_and_accept(self):
        import tempfile
        try:
            for field in (self.database_directory,self.backup_directory):
                path=Path(field.text());path.mkdir(parents=True,exist_ok=True)
                with tempfile.TemporaryFile(dir=path):pass
            target=Path(self.database_directory.text())/"cargo-track.sqlite3"
            if target.resolve()!=self.parent().database_path.resolve() and target.exists():
                info_box(self,"Database already exists","Choose an empty database folder. Use Backup → Restore to load an existing ledger.");return
        except OSError as error:
            info_box(self,"Folder unavailable","Choose writable folders.",str(error));return
        self.accept()
    def values(self):return {"theme":self.theme.currentData(),"font_size":self.font_size.currentData(),"business_timezone":self.timezone.currentData(),"transfer_vessel_name":self.transfer_vessel.text().strip(),"database_directory":self.database_directory.text(),"backup_directory":self.backup_directory.text()}


class HelpDialog(AppDialog):
    def __init__(self,parent=None,section="start"):
        super().__init__(parent);self.setWindowTitle("Cargo Track Help");self.resize(760,650)
        root=QVBoxLayout(self);self.browser=QTextBrowser();self.browser.setAccessibleName("Cargo Track user guide");self.browser.setOpenExternalLinks(False)
        self.browser.document().setDefaultStyleSheet("a { color: " + themed_color("#0066CC", "#A6D0FF") + "; }")
        self.browser.setHtml((asset_path("cargo-track.ico").parent.parent/"help/user-guide.html").read_text(encoding="utf-8"));self.browser.document().setDefaultFont(QApplication.font());root.addWidget(self.browser)
        close=QPushButton("Close");close.clicked.connect(self.accept);root.addWidget(close);QTimer.singleShot(0,lambda:self.browser.scrollToAnchor(section))
