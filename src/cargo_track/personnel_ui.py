"""Independent native personnel workbench and berth-plan editor."""
from __future__ import annotations

import json
import copy
import html
from datetime import date
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QDate, QObject, QRunnable, QThreadPool, Signal, QSettings, QTimer, QItemSelectionModel, QSize
from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget, QToolButton, QMenu, QProgressBar, QSizePolicy, QStackedWidget, QStyledItemDelegate, QListView, QStyle)

from .appearance import fit_to_screen,is_dark_mode
from .theme_tokens import colors
from .personnel_cargo import read_cargo, dependency_spec, dependency_hash, source_matches
from .personnel_import import PersonnelError, read_personnel_excel, workbook_sheets, key, digest
from .personnel_service import clean_payload, crew_vessel_name
from .coordination import workspace_files
from .plan_state import TaskSelection, DraftOverride
from .crew_plan_sync import complete_crew_route
from .personnel_worker import PersonnelGateway
from .personnel_models import ModelTable, CheckState, ChoiceState, CrewFilter
from .view_state import PlanViewState
from .personnel_routes import transfer_name, transfer_origin, leg_order, suggested_leg_order
from .text_case import personnel_record
from .text_case_ui import CasePreviewDialog, attach_case_preview
from .dialogs import GlassDialog, InputDialog as QInputDialog, FileDialog as QFileDialog, prompt
from .navigation import WorkspaceNavigation,ElidedLabel
from .berth_plan import (cargo_tasks, task_key, route_options, generate_plan, plan_text, export_plan,
                         plan_review_groups, plan_task_selection, plan_assignments, leg_choices)


def message(parent, title, value, error=False):
    prompt(parent,title,str(value),buttons=('OK',),default='OK')


def confirm(parent, title, value):
    return prompt(parent,title,value,buttons=('Cancel','Confirm'))=='Confirm'


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setAccessibleName(text)
    if primary:
        widget.setObjectName("primaryButton")
    widget.clicked.connect(callback)
    return widget


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setAlternatingRowColors(True)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setStretchLastSection(True)
    widget.setWordWrap(False)
    return widget


def fill_table(widget, values):
    if isinstance(widget,ModelTable):
        widget.source_model.replace(values)
        return
    widget.setRowCount(len(values))
    for r, row in enumerate(values):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value if value is not None else ""))
            item.setToolTip(item.text())
            widget.setItem(r, c, item)
    widget.resizeColumnsToContents()
    for c in range(widget.columnCount()):
        widget.setColumnWidth(c, min(300, max(65, widget.columnWidth(c))))


class WorkSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class ReadJob(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkSignals()

    def run(self):
        try:
            self.signals.done.emit(self.function())
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class NativeDialog(GlassDialog):
    def showEvent(self, event):
        fit_to_screen(self)
        super().showEvent(event)


class CrewLegOrderDialog(NativeDialog):
    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Link legs — review transfer order')
        self.resize(700, 430)
        self.tasks = {t['id']: t for t in tasks}
        layout = QVBoxLayout(self)
        note = QLabel('Review the suggested transfer order. Drag rows or use Move up / Move down. Each next leg must start at the preceding destination.')
        note.setWordWrap(True);layout.addWidget(note)
        self.order = QListWidget()
        self.order.setAccessibleName('Personnel transfer leg order')
        self.order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for task in suggested_leg_order(tasks):
            item = QListWidgetItem(f"{task['name']} · {task['from_name']} → {task['to_name']}")
            item.setData(Qt.ItemDataRole.UserRole, task['id']);self.order.addItem(item)
        layout.addWidget(self.order)
        actions = QHBoxLayout()
        actions.addWidget(button('Move up', lambda:self.move(-1)))
        actions.addWidget(button('Move down', lambda:self.move(1)))
        actions.addStretch();layout.addLayout(actions)
        self.notice = QLabel();self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Link in this order')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.order.model().rowsMoved.connect(self.validate_order)
        self.validate_order()

    def ordered_tasks(self):
        return [self.tasks[self.order.item(i).data(Qt.ItemDataRole.UserRole)] for i in range(self.order.count())]

    def move(self, delta):
        row = self.order.currentRow();target = row + delta
        if row >= 0 and 0 <= target < self.order.count():
            item = self.order.takeItem(row);self.order.insertItem(target, item);self.order.setCurrentRow(target)
            self.validate_order()

    def validate_order(self, *_):
        tasks = self.ordered_tasks()
        valid = len(tasks) >= 2 and all(a.get('to_id') and a['to_id'] == b.get('from_id') for a,b in zip(tasks,tasks[1:]))
        self.notice.setText('Consecutive locations match. Confirm that these entries belong to the same person.' if valid else
                            'The route is not continuous. Reorder the legs so each From matches the preceding To.')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)
        return valid

    def accept(self):
        if self.validate_order():super().accept()


class PassengerForm(NativeDialog):
    def __init__(self, service, snapshot, plan_date, initial=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crew change entry")
        self.resize(600, 650)
        self.service, self.snapshot, self.initial = service, snapshot, initial or {}
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(self.initial.get("name", ""))
        self.position = QLineEdit(self.initial.get("position", ""))
        self.nationality = QLineEdit(self.initial.get("nationality", ""))
        self.transfer_date = QDateEdit(QDate.fromString(self.initial.get("date") or plan_date, "yyyy-MM-dd"))
        self.transfer_date.setCalendarPopup(True)
        self.transfer_date.setDisplayFormat("yyyy-MM-dd")
        self.from_location, self.to_location = QComboBox(), QComboBox()
        for location in snapshot["locations"]:
            if location["active"]:
                name = service.port_name(snapshot) if location["kind"] == "SHORE" else location["name"]
                self.from_location.addItem(name, location["id"])
                self.to_location.addItem(name, location["id"])
        vessel = transfer_name(service.planning_source(snapshot))
        if vessel and self.from_location.findText(vessel, Qt.MatchFlag.MatchFixedString) < 0:
            self.from_location.addItem(vessel, None)
        for combo, side in ((self.from_location, "from"), (self.to_location, "to")):
            index = combo.findData(self.initial.get(side + "_id"))
            if self.initial.get(side + '_id') is None:
                index = combo.findText(self.initial.get(side + '_name', ''), Qt.MatchFlag.MatchFixedString)
            combo.setCurrentIndex(index if index >= 0 else -1)
        self.comment = QLineEdit(self.initial.get("comment", ""))
        for label, field in (("Name *", self.name), ("Position *", self.position), ("Nationality", self.nationality),
                             ("Transfer date", self.transfer_date), ("From *", self.from_location), ("To *", self.to_location),
                             ("Comment", self.comment)):
            field.setAccessibleName(label)
            form.addRow(label, field)
        root.addLayout(form)
        keep=self.initial.get('preserve_text_case',False) or any(info.get('preserve') for info in self.initial.get('text_case',{}).values())
        self.preserve_case,self.case_preview=attach_case_preview(form,{'name':self.name,'position':self.position},'personnel',keep)
        self.error = QLabel()
        self.error.setWordWrap(True)
        root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def data(self):
        values = clean_payload(self.initial)
        values.update(name=self.name.text().strip(), position=self.position.text().strip(), nationality=self.nationality.text().strip(),
                      date=self.transfer_date.date().toString("yyyy-MM-dd"), direction="Transfer", issues=[],
                      from_name=self.from_location.currentText(), to_name=self.to_location.currentText(), comment=self.comment.text().strip())
        values=personnel_record(values,preserve=self.preserve_case.isChecked())
        return self.service.bind_record(values, self.snapshot)

    def validate(self):
        try:
            self.service._validate_route(self.data())
            self.accept()
        except PersonnelError as exc:
            self.error.setText(str(exc))


class ColumnMappingDialog(NativeDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manual column mapping")
        self.resize(460, 390)
        root, form = QVBoxLayout(self), QFormLayout()
        root.addWidget(QLabel("Column numbers: A = 1, B = 2. Enter 0 to ignore an optional field."))
        self.header = QLineEdit("1")
        form.addRow("Header row", self.header)
        self.fields = {}
        for field, default in (("name", "1"), ("position", "2"), ("from_name", "3"), ("to_name", "4"),
                               ("date", "5"), ("nationality", "0"), ("comment", "0"), ("task_id", "0")):
            self.fields[field] = QLineEdit(default)
            form.addRow(field, self.fields[field])
        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def mapping(self):
        mapping = {f: int(w.text()) for f, w in self.fields.items()}
        if any(v < 0 or v > 200 for v in mapping.values()) or int(self.header.text()) < 1:
            raise PersonnelError("Use valid positive row and column numbers.")
        return mapping, int(self.header.text())


class ImportDialog(NativeDialog):
    def __init__(self, owner, parsed):
        super().__init__(owner)
        self.owner, self.parsed, self.preview = owner, parsed, None
        self.setWindowTitle("Preview personnel import")
        self._preview_closed=False
        self.finished.connect(lambda _:setattr(self,'_preview_closed',True))
        self.resize(1100, 700)
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.mode = QComboBox()
        for label, code in (("Append crew entries", "append"), ("New crew list", "new"), ("Replace selected crew list", "replace")):
            self.mode.addItem(label, code)
        if not owner.plan_combo.currentData():
            self.mode.setCurrentIndex(1)
        self.plan_name = QLineEdit(Path(parsed["file_name"]).stem)
        parsed_dates = {r["date"] for r in parsed["records"] if r["date"]}
        source_date = next(iter(parsed_dates)) if len(parsed_dates) == 1 else owner.plan_date()
        self.date = QDateEdit(QDate.fromString(source_date, "yyyy-MM-dd"))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.override_dates = QCheckBox("Use this transfer date for all imported rows")
        self.preserve_case = QCheckBox('Keep Excel spelling (skip automatic casing)')
        for widget in (self.mode, self.plan_name, self.date):
            controls.addWidget(widget)
        root.addLayout(controls)
        root.addWidget(self.override_dates)
        root.addWidget(self.preserve_case)
        self.preserve_case.toggled.connect(self.refresh)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.aliases = QWidget()
        self.alias_layout = QFormLayout(self.aliases)
        self.alias_widgets = {}
        labels = set()
        for r in parsed["records"]:
            if r['direction'] in ('Sign-on', 'Sign-off'):
                labels.add(crew_vessel_name(r, 'to' if r['direction'] == 'Sign-on' else 'from'))
            else:
                labels.update([r['from_name'], r['to_name']])
        for label in sorted(labels):
            if label and owner.read_model.resolve_location(owner.source, label) is None:
                combo = QComboBox()
                combo.addItem("Unmatched — save as draft", None)
                for location in owner.source["locations"]:
                    if location["active"]:
                        combo.addItem(location["name"], location["id"])
                vessel_label = QLabel(f"Excel vessel: {label}")
                vessel_label.setTextFormat(Qt.TextFormat.PlainText)
                self.alias_layout.addRow(vessel_label, combo)
                self.alias_widgets[label] = combo
        root.addWidget(self.aliases)
        recognized = []
        for label in sorted(labels):
            location = owner.read_model.resolve_location(owner.source, label)
            if location:
                recognized.append(f"{label} → {location['name']}")
        matched = QLabel("Fleet vessel matches: " + ("; ".join(recognized) or "Choose matches above"))
        matched.setTextFormat(Qt.TextFormat.PlainText)
        matched.setWordWrap(True)
        root.addWidget(matched)
        self.rows = table(["Source row", "Direction", "Name", "Position", "From", "To", "Date", "Issues", "Update existing entry"])
        root.addWidget(self.rows, 1)
        self.cancel_missing = QCheckBox("Confirm removal of entries absent from this replacement crew list")
        root.addWidget(self.cancel_missing)
        self.missing = QLabel()
        self.missing.setTextFormat(Qt.TextFormat.PlainText)
        self.missing.setWordWrap(True)
        root.addWidget(self.missing)
        actions = QHBoxLayout()
        actions.addWidget(button("Apply mapping / refresh preview", self.refresh))
        actions.addStretch(1)
        actions.addWidget(button("Cancel", self.reject))
        self.commit_button = button("Confirm import", self.commit, True)
        actions.addWidget(self.commit_button)
        root.addLayout(actions)
        self.mode.currentIndexChanged.connect(self.refresh)
        for combo in self.alias_widgets.values():combo.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.commit_button.setEnabled(False)
        try:
            source=copy.deepcopy(self.owner.source)
            source['preview_aliases']={key(label):combo.currentData() for label,combo in self.alias_widgets.items() if combo.currentData() is not None}
            parsed=copy.deepcopy(self.parsed)
            for record in parsed['records']:
                for field in ('name','position'):
                    record[field]=record.get('original_values',{}).get(field,record.get(field,''))
                record.pop('text_case',None)
                record.update(personnel_record(record,preserve=self.preserve_case.isChecked()))
            args=(parsed, source, self.owner.plan_combo.currentData(), self.mode.currentData(),
                  self.date.date().toString("yyyy-MM-dd") if self.override_dates.isChecked() else None)
            self.owner.run_service_read('import_preview',args,
                lambda preview:self.render_preview(preview,source),channel='import-preview:'+str(id(self)),
                failed=lambda error:self.summary.setText(str(error)),kwargs={'crew_list':True})
        except Exception as exc:
            self.preview=None;self.summary.setText(str(exc))

    def render_preview(self,preview,source):
        if getattr(self,'_preview_closed',False):return
        try:
            self.preview=preview
            self.preview['aliases']={'source':source,'values':source['preview_aliases']}
            items = self.preview["items"]
            fill_table(self.rows, [[r["data"].get(f, "") if f != "issues" else "; ".join(r["data"]["issues"])
                                  for f in ("source_row", "direction", "name", "position", "from_name", "to_name", "date", "issues")]
                                  for r in items])
            self.matches = []
            for index,item in enumerate(items):
                for column,field in ((2,'name'),(3,'position')):
                    info=item['data'].get('text_case',{}).get(field,{})
                    self.rows.item(index,column).setToolTip('Excel: '+item['data'].get('original_values',{}).get(field,'')+'\nAfter import: '+item['data'].get(field,'')+'\n'+'; '.join(info.get('review',[])))
            previous = self.owner.read_model.passengers(self.preview["plan_id"]) if self.preview["plan_id"] else []
            for index, item in enumerate(items):
                combo = QComboBox()
                combo.addItem("Create a separate entry", None)
                for old in previous:
                    combo.addItem(f"{old['name']} / {old.get('position','')} / {old.get('from_name','')} → {old.get('to_name','')} / {old['id'][:8]}", old["id"])
                combo.setToolTip("Replace reloads the complete crew list. Append requires review of possible duplicates.")
                if item["candidates"]:
                    combo.insertItem(0, "Choose: existing or separate entry", "UNRESOLVED")
                    combo.setCurrentIndex(0)
                combo.currentIndexChanged.connect(self.show_missing)
                self.rows.setCellWidget(index, 8, combo)
                self.matches.append(combo)
            self.rows.setColumnWidth(8, 310)
            off = sum(r["data"]["direction"] == "Sign-off" for r in items)
            on = sum(r["data"]["direction"] == "Sign-on" for r in items)
            self.summary.setText(f"{self.parsed['sheet']} · {len(items)} records · Sign-off {off} / Sign-on {on}" +
                f" · {sum(bool(r['data']['issues']) for r in items)} rows with issues · {sum(bool(r['candidates']) for r in items)} possible matches" +
                (" · Similar content was imported before; review row matches." if self.preview["similar_file"] else ""))
            self.cancel_missing.setEnabled(self.mode.currentData() == "replace")
            self.commit_button.setEnabled(True)
            self.show_missing()
        except Exception as exc:
            self.preview = None
            self.summary.setText(str(exc))

    def show_missing(self):
        if not self.preview or not hasattr(self, "matches"):
            return
        selected = {w.currentData() for w in self.matches if w.currentData()}
        old = self.owner.read_model.passengers(self.preview["plan_id"]) if self.preview["plan_id"] else []
        missing = [r for r in old if r["id"] not in selected]
        self.missing.setText("Not matched in this file: " + (", ".join(r['name'] for r in missing) or "None") +
            (". Append keeps them unchanged." if self.mode.currentData() != "replace" else ". Confirm replacement to remove these old entries."))

    def commit(self):
        if not self.owner._action_prepared:return self.owner.prepare_action(self.commit)
        try:
            if self.preview is None:
                raise PersonnelError("Refresh the preview first.")
            aliases = {key(label): combo.currentData() for label, combo in self.alias_widgets.items() if combo.currentData() is not None}
            if aliases != self.preview.get('aliases', {}).get('values', {}):
                self.refresh()
                raise PersonnelError('Vessel matches changed. Review the refreshed preview before confirming import.')
            if self.owner.source["source_hash"] != self.preview["source_hash"]:
                raise PersonnelError("Cargo sources changed. Close this preview and import again.")
            if self.override_dates.isChecked():
                requested_date = self.date.date().toString("yyyy-MM-dd")
                if any(r["data"]["date"] != requested_date for r in self.preview["items"]):
                    raise PersonnelError("Refresh the preview after changing the transfer date.")
            for item, combo in zip(self.preview["items"], self.matches):
                if combo.currentData() == "UNRESOLVED":
                    raise PersonnelError("Confirm every possible duplicate as an existing entry or a separate person.")
                item["match_id"] = combo.currentData()
            if self.mode.currentData() == "replace" and not self.cancel_missing.isChecked():
                raise PersonnelError("Confirm the complete replacement scope, or use Append list.")
            if not confirm(self, "Confirm crew list import", "Save this reviewed crew change information and update the current berthing plan? Earlier plan versions remain available."):
                return
            def imported(result):
                self.result=result
                self.accept()
            self.owner.run_write('commit_import',(self.preview,self.plan_name.text(),
                self.date.date().toString("yyyy-MM-dd"), self.cancel_missing.isChecked()),imported,self)
        except Exception as exc:
            message(self, "Import needs review", exc, True)


class NumberedStopDelegate(QStyledItemDelegate):
    def __init__(self,parent=None,numbered=True):
        super().__init__(parent);self.numbered=numbered
    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        if self.numbered:option.text=f'{index.row()+1:02d}   '+option.text
    def paint(self,painter,option,index):
        self.initStyleOption(option,index);text=option.text;option.text=''
        option.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem,option,painter,option.widget)
        painter.save();painter.setFont(option.font)
        painter.setPen(option.palette.highlightedText().color() if option.state & QStyle.StateFlag.State_Selected else option.palette.text().color())
        painter.drawText(option.rect.adjusted(6,2,-6,-2),int(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)|int(Qt.TextFlag.TextWordWrap),text)
        painter.restore()
    def sizeHint(self,option,index):
        view=self.parent();count=max(1,index.model().rowCount())
        return QSize(max(80,view.gridSize().width()) if count>12 else 160,46 if count>12 else max(26,min(42,(view.viewport().height()-4)//count)))


class PlanStopList(QListWidget):
    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()
    def reflow(self):
        import math
        count=self.count();long=count>12
        self.setFlow(QListView.Flow.TopToBottom);self.setWrapping(long)
        self.setWordWrap(True);self.setTextElideMode(Qt.TextElideMode.ElideNone)
        if long:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            rows=max(1,(self.viewport().height()-4)//46);columns=max(1,math.ceil(count/rows))
            self.setMinimumWidth(columns*80+4)
            self.setGridSize(QSize(max(80,(self.viewport().width()-4)//columns),46))
        else:
            self.setMinimumWidth(80)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setGridSize(QSize())
        self.doItemsLayout()


class CrewPlanBuilder(NativeDialog):
    """Author a standalone final route from imported crew data and selected cargo."""
    previewRequested = Signal()
    draftChanged = Signal()

    def __init__(self, owner, base_plan=None, inline=False):
        super().__init__(owner)
        self.inline = inline
        self._initializing=True
        self._undoing=False
        self._undo_edits=[]
        self._redo_edits=[]
        self._cell_values={}
        if inline:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.owner = owner
        self.source = owner.read_model.planning_source(copy.deepcopy(owner.source))
        self.source['require_personnel_port_calls'] = not base_plan or base_plan.get('require_personnel_port_calls', False)
        self.personnel_context = owner.read_model.context((base_plan or {}).get('personnel_plan_id') or owner.plan_combo.currentData())
        self.source_generation = workspace_files.generation(owner.host.database_path)
        self.base_plan = base_plan
        self.transport_contract=copy.deepcopy((base_plan or {}).get('transport_contract'))
        self.optimization=copy.deepcopy((base_plan or {}).get('optimization'))
        self.editor_revision=0
        self._applying_optimization=False
        self._optimization_undo=None
        self.optimized_material_assignments={k:copy.deepcopy(v) for k,v in plan_assignments(base_plan).items() if k.startswith('Materials:')} if base_plan and self.transport_contract else {}
        self.stop_comments={s['id']:s.get('comment','') for s in (base_plan or {}).get('stops',[])}
        self.stop_comments.update((base_plan or {}).get('stop_comments',{}))
        self.setWindowTitle("Final berthing plan — crew change information")
        if not inline:
            self.resize(1180, 740)
        self.local_edits = {k: copy.deepcopy(v) for k, v in (base_plan or {}).get("draft_edits", {}).items() if k.startswith("Passengers:")}
        self.override_bases=copy.deepcopy((base_plan or {}).get('override_bases',{}))
        self.master_values={}
        root = QVBoxLayout(self)
        hint = QLabel("Edit this draft's personnel and stop order. Materials are read from Cargo." if inline else
                      "Choose the stops for this plan, including Port if needed. From the Plan transfer vessel needs only a Drop. Add a next leg for a person who transfers again. Cargo Voyage stays unchanged.")
        hint.setWordWrap(True)
        if not inline:root.addWidget(hint)
        self.personnel_plan_id = owner.plan_combo.currentData()
        if base_plan and base_plan.get("personnel_plan_id"):
            self.personnel_plan_id = base_plan["personnel_plan_id"]
        self.crew = owner.read_model.crew_records(self.personnel_plan_id, self.source) if self.personnel_plan_id else []
        self.plan_date = owner.plan_date()
        self.route = PlanStopList()
        self.route.setAccessibleName("Final plan stop order — changes do not affect Cargo")
        self.route.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        initial = copy.deepcopy(self.source["stops"])
        if base_plan:
            base_identity=base_plan.get('source_identity')
            if not base_identity and base_plan['source_path']!=self.source['source_path']:
                try:base_identity=self.source['ledger_identity'] if base_plan['source_path']==self.source['source_path'] else None
                except PersonnelError:pass
            if ((base_identity!=self.source.get('ledger_identity') if base_identity
                 else base_plan['source_path']!=self.source['source_path']) or base_plan['voyage_id']!=self.source['voyage_id']):
                raise PersonnelError("Choose a plan for the current Cargo source and Voyage.")
            initial = [{"id": s["id"], "vessel_id": s["vessel_id"], "vessel_name_snapshot": s["name"], 'optimizer_keep':s.get('optimizer_keep',False)}
                       for s in base_plan.get('recovery_route',base_plan["stops"])]
            if base_plan["mode"] == "Final":
                self.plan_date = base_plan["date"]
        for stop in initial:
            self.append_stop(stop)
        if not base_plan:
            completed = complete_crew_route(self.route_snapshot(), self.crew, departure=True)
            self.route.clear()
            for stop in completed:self.append_stop(stop)
            initial = completed
        vessel_ids = {s["vessel_id"] for s in initial}
        shore = next((r["id"] for r in self.source["locations"] if r["kind"] == "SHORE"), None)
        needed = {r.get(side + "_id") for r in self.crew for side in ("from", "to")
                  if side != 'from' or not transfer_origin(r, self.source)} - {shore, None}
        self.added_names = []
        for location in self.source["locations"]:
            if location["id"] in needed - vessel_ids:
                self.append_stop({"id": "plan:" + str(uuid4()), "vessel_id": location["id"], "vessel_name_snapshot": location["name"]})
                self.added_names.append(location["name"])
        # New crew-change plans return sign-off passengers to the configured
        # port. Existing edited routes and immutable versions keep their order.
        if (not base_plan and shore is not None and shore not in vessel_ids
                and any(r.get('to_id') == shore for r in self.crew)):
            self.append_stop({'id': 'plan:' + str(uuid4()), 'vessel_id': shore,
                              'vessel_name_snapshot': owner.read_model.port_name(self.source)})
            self.added_names.append(owner.read_model.port_name(self.source))
        route_box = QHBoxLayout()
        route_panel = QVBoxLayout()
        route_panel.addWidget(QLabel("Final plan order (drag to reorder)"))
        route_panel.addWidget(self.route, 1)
        route_actions = QHBoxLayout()
        self.vessels = QComboBox()
        for location in self.source["locations"]:
            if location["active"]:
                self.vessels.addItem(location["name"], location["id"])
        route_actions.addWidget(self.vessels, 1)
        route_actions.addWidget(button("Add stop", self.add_stop))
        route_panel.addLayout(route_actions)
        movement = QHBoxLayout()
        movement.addWidget(button("Up" if inline else "Move up", lambda: self.move_stop(-1)))
        movement.addWidget(button("Down" if inline else "Move down", lambda: self.move_stop(1)))
        movement.addWidget(button("Remove" if inline else "Remove stop", self.remove_stop))
        route_panel.addLayout(movement)
        route_note = QLabel('Sign-on boards at Port before delivery; Sign-off is collected before returning to Port. Move or add calls to match the actual trip.');route_note.setWordWrap(True)
        route_panel.addWidget(route_note)
        route_widget=QWidget();route_widget.setLayout(route_panel);self.route_widget=route_widget
        self.rows = ModelTable(["Include", "Type", "Name", "Position", "Stop assignment", 'Leg']+(['Pick up','Drop'] if inline else []))
        self.rows.horizontalHeader().setStretchLastSection(False)
        self.rows.horizontalHeader().setMinimumSectionSize(36)
        self.rows.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.rows.setColumnHidden(1, inline)
        if inline:
            self.rows.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.includes, self.assignments = [], []
        self.selection_overrides = {k:v['state']=='included' for k,v in (base_plan or {}).get('task_selections',{}).items()
                                    if v['state']!='unavailable'}
        if base_plan and not base_plan.get('task_selections'):
            chosen=plan_task_selection(base_plan)
            self.selection_overrides.update({k:False for k in base_plan.get('available_tasks',[]) if k not in chosen})
        self.tasks = []
        task_panel = QVBoxLayout()
        task_panel.addWidget(self.rows, 1)
        task_actions = QHBoxLayout()
        task_actions.addWidget(button("Add crew" if inline else "Add crew entry", self.add_crew_entry))
        edit_crew=button("Edit crew" if inline else "Edit selected crew", self.edit_selected_crew);task_actions.addWidget(edit_crew)
        self.next_leg_button = button('Next leg', self.add_next_crew_leg)
        self.next_leg_button.setToolTip('Continue the selected person from their preceding destination')
        task_actions.addWidget(self.next_leg_button)
        link=button('Link legs', self.link_selected_crew_legs)
        remove=button("Remove from plan", self.remove_from_plan)
        task_actions.addWidget(link);task_actions.addWidget(remove)
        task_panel.addLayout(task_actions)
        task_widget=QWidget();task_widget.setLayout(task_panel)
        self.editor_split=QSplitter();self.editor_split.addWidget(route_widget);self.editor_split.addWidget(task_widget)
        self.editor_split.setStretchFactor(1,4);self.editor_split.setSizes([220,800])
        route_box.addWidget(self.editor_split)
        root.addLayout(route_box, 1)
        notice = QLabel(("Added from crew list: " + ", ".join(self.added_names) + ". ") if self.added_names else "")
        notice.setText(notice.text() + "Double-click a passenger name or position to edit. Check passengers to include them; uncheck to remove. Materials are read only from Cargo." if inline else
                       notice.text() + "Entries with feasible stop assignments are checked automatically; uncheck to remove from this plan. Repeated vessels default to the first feasible stop.")
        notice.setWordWrap(True)
        if not inline:root.addWidget(notice)
        self.rows.setAccessibleName('Draft personnel and stop assignments')
        self.rows.setToolTip('Double-click Name or Position for a draft-only edit. Double-click Stop assignment or press F2 to choose a visit.')
        self.route.model().rowsMoved.connect(self.refresh_assignments)
        self.reload_tasks(initial=True)
        self.rows.itemChanged.connect(self.edit_draft_cell)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Ok).setText("Preview changes" if inline else "Preview final plan")
        if inline:
            actions.button(QDialogButtonBox.StandardButton.Cancel).hide()
            actions.accepted.connect(self.previewRequested.emit)
        else:
            actions.accepted.connect(self.accept)
            actions.rejected.connect(self.reject)
        if not inline:root.addWidget(actions)
        else:
            edits=QToolButton();edits.setText('Edit history');edits.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            edits.setAccessibleName('Cell edit history');menu=QMenu(edits)
            self.undo_button=menu.addAction('Undo cell edit (Ctrl+Z)',self.undo_cell)
            self.redo_button=menu.addAction('Redo cell edit (Ctrl+Shift+Z)',self.redo_cell)
            edits.setMenu(menu);task_actions.addWidget(edits)
            for shortcut,callback in (('Ctrl+Z',self.undo_cell),('Ctrl+Shift+Z',self.redo_cell)):
                action=QAction(self);action.setShortcut(QKeySequence(shortcut));action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);action.triggered.connect(callback);self.addAction(action)
            # The inline view shares the page's route sidebar and right preview.
            # Keep stable source columns for edits and expose endpoints separately.
            self.rows.setColumnHidden(4,True)
            header=self.rows.horizontalHeader();header.setSectionResizeMode(4,QHeaderView.ResizeMode.Interactive)
            header.moveSection(header.visualIndex(5),4)
            header.setSectionResizeMode(2,QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(6,QHeaderView.ResizeMode.Interactive);header.setSectionResizeMode(7,QHeaderView.ResizeMode.Interactive);header.setStretchLastSection(True)
            self.rows.setShowGrid(False);self.rows.setAlternatingRowColors(False)
            root.setContentsMargins(0,0,0,0);task_panel.setContentsMargins(0,0,0,0)
            root.removeItem(route_box);self.editor_split.hide()
            task_widget.setParent(self);root.addWidget(task_widget,1)
            # Move the most common actions above the table; infrequent actions
            # retain their original callbacks in one menu.
            task_panel.removeItem(task_actions)
            root.insertLayout(0,task_actions)
            for widget in (link,remove,edits,edit_crew):task_actions.removeWidget(widget);widget.hide()
            more=QToolButton();more.setText('More');more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu=QMenu(more);menu.addAction('Edit selected crew',self.edit_selected_crew);menu.addAction('Link legs',self.link_selected_crew_legs);menu.addAction('Remove from plan',self.remove_from_plan)
            menu.addSeparator();menu.addAction('Undo cell edit',self.undo_cell);menu.addAction('Redo cell edit',self.redo_cell)
            more.setMenu(menu);task_actions.addWidget(more);task_actions.addStretch()
            self.personnel_title=ElidedLabel();self.personnel_title.setText('Personnel');self.personnel_title.setObjectName('workbenchTitle')
            people=len({t.get('person_id') or t['id'] for t in self.tasks})
            self.personnel_title.setText(f'Personnel · {people} people / {len(self.tasks)} legs')
            self.personnel_title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);task_actions.insertWidget(0,self.personnel_title,1)
            # Compact numbered route controls replace the old explanatory panel.
            route_panel.itemAt(0).widget().hide();route_note.hide();route_panel.setContentsMargins(0,0,0,0)
            self.route.setObjectName('stopList');self.route.setItemDelegate(NumberedStopDelegate(self.route))
            for layout in (route_actions,movement):
                while layout.count():
                    item=layout.takeAt(0)
                    if item.widget():item.widget().hide()
            route_actions.addWidget(button('+ Add vessel',self.choose_add_stop))
            route_more=QToolButton();route_more.setText('Route actions');route_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            route_menu=QMenu(route_more);up=route_menu.addAction('Move earlier',lambda:self.move_stop(-1));down=route_menu.addAction('Move later',lambda:self.move_stop(1));remove_stop=route_menu.addAction('Remove this stop',self.remove_stop)
            def enable_route_actions():
                row=self.route.currentRow();up.setEnabled(row>0);down.setEnabled(0<=row<self.route.count()-1);remove_stop.setEnabled(row>=0)
            route_menu.aboutToShow.connect(enable_route_actions);route_more.setMenu(route_menu);movement.addWidget(route_more)
        self._initializing=False
        self.auto_plan_button=button('Auto plan',self.auto_plan)
        self.auto_plan_button.setToolTip('Find the fewest actual vessel calls to complete all included passengers and selected materials')
        planner_actions=QHBoxLayout();planner_actions.addWidget(self.auto_plan_button,1)
        planner_more=QToolButton();planner_more.setText('…');planner_more.setAccessibleName('Automatic plan actions');planner_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        planner_menu=QMenu(planner_more)
        self.check_route_button=planner_menu.addAction('Check complete route',self.check_complete_route)
        self.undo_optimization_button=planner_menu.addAction('Undo auto plan',self.undo_auto_plan);self.undo_optimization_button.setEnabled(False)
        self.keep_visit_button=planner_menu.addAction('Keep / release selected call',self.toggle_keep_visit)
        planner_more.setMenu(planner_menu);planner_actions.addWidget(planner_more);route_panel.addLayout(planner_actions)
        self.optimization_notice=QLabel('');self.optimization_notice.setWordWrap(True);route_panel.addWidget(self.optimization_notice)
        if self.optimization:
            cost=self.optimization.get('cost',[])
            if len(cost)==2:self.optimization_notice.setText(('Minimum proved' if self.optimization.get('status')=='OPTIMAL' else 'Minimum needs recalculation')+f' / {cost[0]} vessel calls / {cost[1]} port calls')

    def auto_plan(self):
        from .berth_optimization_ui import OptimizationDialog,apply_result
        dialog=OptimizationDialog(self)
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted and dialog.accepted_result:
                apply_result(self,dialog.original,dialog.accepted_result)
        except Exception as exc:message(self,'Automatic planning',exc,True)
        finally:dialog.deleteLater()

    def undo_auto_plan(self):
        from .berth_optimization_ui import restore_editor
        if self._optimization_undo and self.editor_revision==self._optimization_undo_revision:
            restore_editor(self,self._optimization_undo);self._optimization_undo=None;self.undo_optimization_button.setEnabled(False)
            self.optimization_notice.setText('The route and assignments before automatic planning were restored.')

    def toggle_keep_visit(self):
        item=self.route.currentItem()
        if item is None:return
        stop=copy.deepcopy(item.data(Qt.ItemDataRole.UserRole));stop['optimizer_keep']=not stop.get('optimizer_keep',False)
        item.setData(Qt.ItemDataRole.UserRole,stop);item.setToolTip('Retained in automatic planning' if stop['optimizer_keep'] else '')
        self.changed()

    def check_complete_route(self):
        try:
            plan=self.build(check_sources=False)
            if plan['issues']:message(self,'Route needs review','\n'.join(i['message'] for i in plan['issues']),True)
            elif plan.get('transport_contract'):message(self,'Complete route','All required transport legs have valid pickup and delivery assignments.')
            else:message(self,'Manual route','Manual assignments are valid. Use Auto plan to check complete delivery of every included task and find the minimum calls.')
        except Exception as exc:message(self,'Route needs review',exc,True)

    def choose_add_stop(self):
        names=[self.vessels.itemText(i) for i in range(self.vessels.count())]
        name,ok=QInputDialog.getItem(self,'Add plan stop','Vessel or port',names,0,False)
        if ok:self.vessels.setCurrentIndex(self.vessels.findText(name));self.add_stop()

    def changed(self,*_,preserve_optimization=False):
        if self._initializing or self._applying_optimization:return
        self.editor_revision+=1
        if hasattr(self,'undo_optimization_button'):self.undo_optimization_button.setEnabled(False)
        if self.optimization and not preserve_optimization:
            self.optimization['status']='STALE'
            if hasattr(self,'optimization_notice'):self.optimization_notice.setText('Plan changed. Complete delivery will be checked; minimum calls must be recalculated.')
        self.draftChanged.emit()

    def undo_cell(self):
        if self._undo_edits:
            change=self._undo_edits.pop();self._apply_cell_history(change,False);self._redo_edits.append(change)

    def redo_cell(self):
        if self._redo_edits:
            change=self._redo_edits.pop();self._apply_cell_history(change,True);self._undo_edits.append(change)

    def _apply_cell_history(self,change,forward):
        key,column,before,after=change
        index=next((i for i,t in enumerate(self.tasks) if task_key(t)==key),None)
        if index is not None:
            self._undoing=True
            try:self.rows.item(index,column).setText(after if forward else before)
            finally:self._undoing=False

    def showEvent(self, event):
        if self.inline:
            QDialog.showEvent(self, event)
        else:
            super().showEvent(event)

    def edit_draft_cell(self, item):
        if not self.inline or item.column() not in (2, 3) or item.row() >= len(self.tasks):
            return
        task = self.tasks[item.row()]
        old=self._cell_values.get((task_key(task),item.column()),task.get('name' if item.column()==2 else 'position',''))
        if old==item.text().strip():return
        if not self._undoing:
            self._undo_edits.append((task_key(task),item.column(),old,item.text().strip()));self._redo_edits.clear()
        field = "name" if item.column() == 2 else "position"
        task[field] = item.text().strip()
        self.local_edits.setdefault(task_key(task), {})[field] = task[field]
        self.override_bases.setdefault(task_key(task),{})[field]=self.master_values[task_key(task)].get(field,'')
        self._cell_values[task_key(task),item.column()]=task[field]
        self.changed()

    def reload_tasks(self, initial=False):
        previous = {task_key(t): (include.isChecked(), combo.currentData())
                    for t, include, combo in zip(self.tasks, self.includes, self.assignments)}
        links = {task_key(t): (t.get('previous_task_id'), t.get('person_id'), leg_order(t)) for t in self.tasks}
        self.crew = self.owner.read_model.crew_records(self.personnel_plan_id, self.source) if self.personnel_plan_id else []
        self.personnel_context=self.owner.read_model.context(self.personnel_plan_id)
        # Master roster changes invalidate the optimizer's frozen task contract.
        if not initial and self.transport_contract:
            self.transport_contract=None
            if self.optimization:self.optimization['status']='STALE'
        cargo = cargo_tasks(self.source, [r["no"] for r in self.source["cargo"] if not r["is_void"] and r["status"] != "Done"])
        self.all_tasks = self.crew + cargo
        self.tasks = self.crew if self.inline else self.all_tasks
        route_source = self.route_snapshot()
        for task in self.tasks:
            identifier = task_key(task)
            if identifier in previous and links[identifier] != (task.get('previous_task_id'), task.get('person_id'), leg_order(task)):
                # Linking changes when this leg may start. Its old independent
                # assignment must not override the newly calculated chain route.
                previous[identifier] = (previous[identifier][0], None)
            if identifier in previous and previous[identifier][1] not in route_options(route_source, task, 'Final'):
                previous[identifier] = (previous[identifier][0], None)
        material_keys={t['key'] for t in self.transport_contract['tasks'] if t['key'].startswith('Materials:')} if self.transport_contract else (plan_task_selection(self.base_plan) if self.base_plan else set())
        self.materials = [t for t in cargo if task_key(t) in material_keys]
        for task in self.tasks:
            identifier=task_key(task)
            self.master_values[identifier]={field:task.get(field,'') for field in ('name','position')}
            for field,value in list(self.local_edits.get(identifier,{}).items()):
                base=self.override_bases.setdefault(identifier,{}).setdefault(field,task.get(field,''))
                if DraftOverride(value,base).applies_to(task.get(field,'')):
                    task[field]=value
                else:
                    self.local_edits[identifier].pop(field,None)
                    self.override_bases[identifier].pop(field,None)
        selected = plan_task_selection(self.base_plan) if self.base_plan else set()
        available = set(self.base_plan.get("available_tasks", selected)) if self.base_plan else set()
        stored_assignments = plan_assignments(self.base_plan) if self.base_plan else {}
        if self.base_plan:stored_assignments.update(self.base_plan.get('recovery_assignments',{}))
        self.rows.blockSignals(True)
        fill_table(self.rows, [["", r["kind"], r["name"], r.get("position", ""), "", r.get('leg_index', 1) if r['kind']=='Passengers' else '']+(['',''] if self.inline else []) for r in self.tasks])
        for row, task in enumerate(self.tasks):
            self.rows.setRowHidden(row,task['kind']!='Passengers')
            for column in range(self.rows.columnCount()):
                if not self.inline or column not in (2, 3) or task["kind"] != "Passengers":
                    item = self.rows.item(row, column)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.includes, self.assignments = [], []
        self.endpoint_controls=[]
        for index, task in enumerate(self.tasks):
            identifier = task_key(task)
            is_new_crew = task["kind"] == "Passengers" and (not self.base_plan or identifier not in available)
            checked = previous.get(identifier, (identifier in selected or is_new_crew, None))[0]
            include, assignment = CheckState(), ChoiceState()
            include.setAccessibleName('Include '+task['name'])
            assignment.setAccessibleName(task['name']+' stop assignment')
            include.setChecked(checked)
            include.toggled.connect(lambda value, identifier=identifier: self.selection_overrides.__setitem__(identifier, value))
            include.toggled.connect(self.changed)
            assignment.currentIndexChanged.connect(self.assignment_changed)
            include.toggled.connect(self.assignment_changed)
            self.rows.setCellWidget(index, 0, include)
            self.rows.setCellWidget(index, 4, assignment)
            self.rows.item(index, 2).setToolTip(f"{task['name']} · Leg {task.get('leg_index', 1)}\n{task['from_name']} → {task['to_name']}")
            self.includes.append(include)
            self.assignments.append(assignment)
            if self.inline:
                endpoints=[]
                for column,side in ((6,'pick'),(7,'drop')):
                    control=ChoiceState();control.setAccessibleName(task['name']+' '+side+' visit')
                    control.currentIndexChanged.connect(lambda _,i=index,side=side:self.choose_endpoint(i,side))
                    self.rows.setCellWidget(index,column,control);endpoints.append(control)
                self.endpoint_controls.append(endpoints)
            for column,field in ((2,'name'),(3,'position')):self._cell_values[task_key(task),column]=task.get(field,'')
        for column, width in enumerate((64, 90, 160, 110)):
            self.rows.setColumnWidth(column, width)
        self.rows.setColumnWidth(4, 300)
        self.rows.setColumnWidth(5, 48)
        if self.inline:
            for column,width in ((0,70),(2,155),(3,80),(5,45),(6,170),(7,170)):self.rows.setColumnWidth(column,width)
            self.rows.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.rows.verticalHeader().setDefaultSectionSize(42 if self.inline else 34)
        self.rows.blockSignals(False)
        self.refresh_assignments()
        if self.inline:self.route.reflow()
        for task, combo in zip(self.tasks, self.assignments):
            identifier = task_key(task)
            saved = previous.get(identifier, (False, stored_assignments.get(identifier)))[1]
            if saved is not None and (initial or saved in getattr(combo, 'feasible_options', [])):
                self._retain_assignment(combo,saved)
        self.personnel_context=self.owner.read_model.context(self.personnel_plan_id)
        self.sync_endpoints()
        if hasattr(self,'personnel_title'):
            people=len({t.get('person_id') or t['id'] for t in self.tasks})
            self.personnel_title.setText(f'Personnel · {people} people / {len(self.tasks)} legs')

    def choose_endpoint(self,index,side):
        if getattr(self,'_syncing_endpoints',False):return
        control=self.endpoint_controls[index][0 if side=='pick' else 1]
        wanted=control.currentData();combo=self.assignments[index];old=combo.currentData() or {}
        choices=[choice for choice in getattr(combo,'feasible_options',[]) if choice.get(side)==wanted]
        if not choices:return
        other='drop' if side=='pick' else 'pick'
        choice=next((c for c in choices if c.get(other)==old.get(other)),choices[0])
        combo.setCurrentIndex(combo.findData(choice))

    def sync_endpoints(self):
        if not self.inline:return
        self._syncing_endpoints=True
        try:
            names={self.route.item(i).data(Qt.ItemDataRole.UserRole)['id']:f'{i+1:02d} · {self.route.item(i).data(Qt.ItemDataRole.UserRole)["vessel_name_snapshot"]}' for i in range(self.route.count())}
            for task,combo,controls in zip(self.tasks,self.assignments,self.endpoint_controls):
                current=combo.currentData();valid=current is not None and current in getattr(combo,'feasible_options',[])
                for side,control in zip(('pick','drop'),controls):
                    control.clear();seen=set()
                    for choice in getattr(combo,'feasible_options',[]):
                        if choice is None or any(s is not None and s not in names for s in choice.values()):continue
                        visit=choice.get(side)
                        if visit in seen:continue
                        seen.add(visit)
                        label=names.get(visit,('On '+transfer_name(self.source)) if side=='pick' and transfer_origin(task,self.source) else '—')
                        control.addItem(label,visit)
                    if not valid:
                        control.insertItem(0,'Review assignment',None);control.index=0
                    else:control.index=max(0,control.findData(current.get(side)))
                    control.setToolTip(combo.currentText()+' · Changing a visit retains the other visit when feasible.')
            self.rows.viewport().update()
        finally:self._syncing_endpoints=False

    @staticmethod
    def _retain_assignment(combo,saved):
        index=combo.findData(saved)
        if index<0:
            combo.insertItem(0,'Previous assignment is unavailable — choose another stop',saved)
            index=0
        combo.setCurrentIndex(index)
        combo.setToolTip(combo.currentText())

    def ensure_crew_stops(self):
        current = self.route.currentItem()
        current_id = current.data(Qt.ItemDataRole.UserRole)['id'] if current else None
        people = [p for p in self.crew if self.selection_overrides.get(task_key(p)) is not False]
        stops = complete_crew_route(self.route_snapshot(), people, departure=True)
        self.route.clear()
        for stop in stops:self.append_stop(stop)
        route_source = self.route_snapshot()
        for task, combo in zip(self.tasks, self.assignments):
            if combo.currentData() not in route_options(route_source, task, 'Final'):
                combo.clear()
        if current_id is not None:
            for index, stop in enumerate(stops):
                if stop['id'] == current_id:self.route.setCurrentRow(index);break
        self.refresh_assignments()

    def sync_crew(self):
        self.reload_tasks()
        self.ensure_crew_stops()
        # Recalculate after the full master roster and visit choices are loaded.
        self.reload_tasks()

    def add_next_crew_leg(self):
        try:
            row = self.rows.currentRow()
            if row < 0 or self.tasks[row]['kind'] != 'Passengers':
                raise PersonnelError('Select a passenger to add their next transfer leg.')
            old = self.owner.read_model.passenger(self.tasks[row]['id'])
            initial = {k: old.get(k, '') for k in ('name', 'position', 'nationality')}
            initial.update(from_id=old.get('to_id'), from_name=old.get('to_name', ''), to_id=None, to_name='',
                           date=self.plan_date, direction='Transfer')
            form = PassengerForm(self.owner.read_model, self.source, self.plan_date, initial, self)
            form.setWindowTitle('Next transfer leg — ' + old['name']);form.name.setReadOnly(True)
            if form.exec() == QDialog.DialogCode.Accepted:
                def added(_):
                    self.reload_tasks();self.ensure_crew_stops();self.owner.refresh_rows();self.changed()
                self.owner.run_write('add_next_leg', (old['id'], form.data(), self.source, old['version']), added, self)
        except Exception as exc:
            message(self, 'Next leg needs review', exc, True)

    def link_selected_crew_legs(self):
        try:
            rows = sorted({index.row() for index in self.rows.selectedIndexes()})
            tasks = [self.tasks[row] for row in rows]
            if len(tasks) < 2 or any(task['kind'] != 'Passengers' for task in tasks):
                raise PersonnelError('Select two or more passenger rows in transfer order.')
            order = CrewLegOrderDialog(tasks, self)
            if order.exec() != QDialog.DialogCode.Accepted:
                return
            tasks = order.ordered_tasks()
            def linked(_):
                self.reload_tasks();self.owner.refresh_rows();self.changed()
            self.owner.run_write('link_crew_legs', ([task['id'] for task in tasks], {task['id']: task['version'] for task in tasks}), linked, self)
        except Exception as exc:
            message(self, 'Crew legs need review', exc, True)

    def add_crew_entry(self):
        try:
            if not self.personnel_plan_id:
                raise PersonnelError("Create a crew list in the Personnel page first.")
            form = PassengerForm(self.owner.read_model, self.source, self.plan_date, parent=self)
            if form.exec() == QDialog.DialogCode.Accepted:
                def added(value):
                    self.reload_tasks()
                    self.ensure_crew_stops()
                    self.owner.refresh_rows()
                self.owner.run_write('add_passenger',(self.personnel_plan_id,form.data()),added,self)
        except Exception as exc:
            message(self, "Crew entry needs review", exc, True)

    def edit_selected_crew(self):
        try:
            index = self.rows.currentRow()
            if index < 0 or self.tasks[index]["kind"] != "Passengers":
                raise PersonnelError("Select a passenger row to edit. Cargo materials are managed in Cargo.")
            task = self.tasks[index]
            form = PassengerForm(self.owner.read_model, self.source, self.plan_date, task, self)
            if form.exec() == QDialog.DialogCode.Accepted:
                data=form.data()
                # An explicit form submission supersedes draft overlays for the fields it saves.
                def edited(value):
                    for field in ('name','position'):
                        if data.get(field)!=self.master_values[task_key(task)].get(field):
                            self.local_edits.get(task_key(task),{}).pop(field,None)
                    self.reload_tasks()
                    self.ensure_crew_stops()
                    self.owner.refresh_rows()
                self.owner.run_write('edit_crew_entry',(task['id'],data,task['version']),edited,self)
        except Exception as exc:
            message(self, "Crew entry needs review", exc, True)

    def remove_from_plan(self):
        indices = sorted({i.row() for i in self.rows.selectedIndexes()})
        if not indices:
            return message(self, "Select an entry", "Select the passenger or material rows to remove from this plan.")
        for index in indices:
            self.selection_overrides[task_key(self.tasks[index])]=False
            self.includes[index].setChecked(False)

    def append_stop(self, stop):
        item = QListWidgetItem(stop["vessel_name_snapshot"])
        item.setData(Qt.ItemDataRole.UserRole, stop)
        if stop.get('optimizer_keep'):item.setToolTip('Retained in automatic planning')
        self.route.addItem(item)

    def route_snapshot(self):
        source = copy.deepcopy(self.source)
        source['reference_stops']=copy.deepcopy(self.source['stops'])
        source["stops"] = [copy.deepcopy(self.route.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.route.count())]
        if self.transport_contract:source['transport_contract']=copy.deepcopy(self.transport_contract)
        return source

    def add_stop(self):
        if self.vessels.currentData() is None:
            return
        self.append_stop({"id": "plan:" + str(uuid4()), "vessel_id": self.vessels.currentData(), "vessel_name_snapshot": self.vessels.currentText(), 'optimizer_keep':True})
        self.refresh_assignments()

    def move_stop(self, offset):
        row = self.route.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.route.count():
            return
        item = self.route.takeItem(row)
        self.route.insertItem(target, item)
        self.route.setCurrentRow(target)
        self.refresh_assignments()

    def remove_stop(self):
        if self.route.currentRow() >= 0:
            self.route.takeItem(self.route.currentRow())
            self.refresh_assignments()

    def refresh_assignments(self, *args):
        if getattr(self, '_refreshing_assignments', False):
            return
        self._refreshing_assignments = True
        try:
            self._refresh_assignments()
        finally:
            self._refreshing_assignments = False

    def assignment_changed(self, *_):
        self.refresh_assignments()
        self.changed()

    def _refresh_assignments(self):
        source = self.route_snapshot()
        names = {s["id"]: f"{i:02d}. {s['vessel_name_snapshot']}" for i, s in enumerate(source["stops"], 1)} | {"PORT": self.owner.read_model.port_name(source)}
        selected = plan_task_selection(self.base_plan) if self.base_plan else set()
        available = set(self.base_plan.get("available_tasks", selected)) if self.base_plan else set()
        controls = sorted(zip(self.tasks, self.includes, self.assignments), key=lambda entry: leg_order(entry[0]))
        chosen = {task_key(t) for t, include, _ in controls if include.isChecked()}
        resolved = {}
        for task, include, combo in controls:
            old = combo.currentData()
            combo.clear()
            choices = leg_choices(source, task, resolved, chosen)
            combo.feasible_options=choices
            identifier = task_key(task)
            if identifier not in self.selection_overrides and (not self.base_plan or identifier not in available or
                    self.base_plan.get('task_selections',{}).get(identifier,{}).get('state')=='unavailable'):
                include.blockSignals(True)
                include.setChecked(bool(choices))
                include.blockSignals(False)
                if include.isChecked():chosen.add(identifier)
                else:chosen.discard(identifier)
            if not choices:
                combo.addItem("No feasible route — review From / To", None)
            for choice in choices:
                label = "Pick up " + names[choice["pick"]] if choice["pick"] else "Drop at " + names[choice["drop"]]
                if choice["pick"] and choice["drop"]:
                    label += " → Drop " + names[choice["drop"]]
                elif choice["pick"] and task["kind"] == "Materials":
                    label += " → to " + task["to_name"] + " (not called)"
                combo.addItem(label, choice)
            if old is not None:
                self._retain_assignment(combo,old)
            if include.isChecked() and combo.currentData() in choices:
                resolved[identifier] = combo.currentData()
            combo.setToolTip(combo.currentText())
        self.rows.viewport().update()
        self.sync_endpoints()
        self.changed()

    def build(self,check_sources=True):
        self.owner.read_model.assert_context(self.personnel_context)
        if (self.personnel_plan_id!=self.owner.plan_combo.currentData() or self.source_generation!=workspace_files.generation(self.owner.host.database_path)
            or str(Path(self.owner.host.database_path).resolve())!=self.source['source_path']):
            raise PersonnelError("The selected crew list or Cargo database changed. Reopen the plan editor.")
        route_source = self.route_snapshot()
        dependencies=dependency_spec(route_source,self.crew,[int(t['id']) for t in self.materials] if self.inline else
                                    [int(t['id']) for t,include in zip(self.tasks,self.includes) if t['kind']=='Materials' and include.isChecked()])
        # Synchronous source verification remains an explicit diagnostic API.
        # UI actions prepare these inputs asynchronously; publication rechecks in its worker.
        live_source=(read_cargo(self.owner.host.database_path,selected_cargo=dependencies['cargo_ids'])
                     if check_sources else self.owner.source)
        if dependency_hash(live_source,dependencies) != dependency_hash(self.source,dependencies):
            raise PersonnelError("Cargo sources changed. Open the final plan builder again.")
        people, cargo, assignments = list(self.crew), [int(t["id"]) for t in self.materials] if self.inline else [], {}
        selections={}
        if self.inline and self.base_plan:
            material_map = {task_key(t): t for t in self.materials}
            for k, v in plan_assignments(self.base_plan).items():
                if k in material_map:
                    assignments[k] = v
        if self.inline and self.transport_contract:
            assignments.update(copy.deepcopy(self.optimized_material_assignments))
        for task, include, assignment in zip(self.tasks, self.includes, self.assignments):
            identifier=task_key(task)
            selections[identifier]=TaskSelection.decide(include.isChecked(),self.selection_overrides.get(identifier) is False,
                                                        bool(route_options(route_source,task,'Final'))).payload()
            if include.isChecked():
                if task["kind"] != "Passengers":
                    cargo.append(int(task["id"]))
                if assignment.currentData() is not None:
                    assignments[task_key(task)] = assignment.currentData()
        plan = generate_plan(route_source, people, cargo, self.plan_date, self.owner.read_model.port_name(self.source),
                             mode="Final", assignments=assignments, personnel_plan_id=self.personnel_plan_id,selections=selections)
        plan['personnel_context']=copy.deepcopy(self.personnel_context)
        if self.optimization:plan['optimization']=copy.deepcopy(self.optimization)
        plan['personnel_source_path']=str(self.owner.service.path)
        plan["transfer_vessel"] = self.owner.read_model.settings().get("transfer_vessel_name") or plan["transfer_vessel"]
        if self.base_plan:
            if self.base_plan.get("family_id"):
                plan["family_id"] = self.base_plan["family_id"]
            plan["base_version_id"] = self.base_plan.get("id") or self.base_plan.get("base_version_id")
            plan["revision_reviewed"] = True
        plan["available_tasks"] = [task_key(t) for t in self.all_tasks]
        plan["draft_edits"] = copy.deepcopy(self.local_edits)
        plan['override_bases']=copy.deepcopy(self.override_bases)
        original_stops = {s['id']: s for s in route_source['stops']}
        for stop in plan["stops"]:
            stop['comment']=self.stop_comments.get(stop['id'],'')
            original=original_stops.get(stop['id'],{})
            stop['optimizer_keep']=original.get('optimizer_keep',False)
            for group in ("drop_passengers", "pick_passengers", "drop_materials", "pick_materials"):
                for task in stop[group]:
                    task.update(self.local_edits.get(task_key(task), {}))
        plan["plan_route_hash"] = digest(plan["stops"])
        return plan


class PersonnelPage(QWidget):
    def __init__(self, host, back):
        super().__init__(host)
        self.host, self.back = host, back
        self._closed = False
        override = host.data_directory if __import__("os").environ.get("CARGO_TRACK_DATA_DIR") else None
        directory = Path(override or QSettings().value("personnel/database_directory", str(host.data_directory)))
        path = host.personnel_database_path() if hasattr(host,'personnel_database_path') else directory / "personnel-transfer.sqlite3"
        self.service = PersonnelGateway(path,self)
        self._lifecycle_epoch=0
        self._write_pending=False
        self._latest_reads={}
        self._selected_crew_id=None
        self._loading_list=False
        self._version_cache={}
        self._action_prepared=False
        self.view_state=PlanViewState()
        self._crew_source_rows=[]
        self._validation_timer=QTimer(self);self._validation_timer.setSingleShot(True);self._validation_timer.setInterval(220)
        self._validation_timer.timeout.connect(lambda:self.refresh_live_preview(False))
        self.recovery_directory=self.service.path.parent/'draft-recovery'
        self.source, self.draft, self.saved_plan, self.rows_data, self._jobs = None, None, None, [], []
        self.live_builder = None
        self._build()
        self.service.open_failed.connect(self.show_error)
        for shortcut, callback in ((QKeySequence.StandardKey.Find, self.search.setFocus),
                                   (QKeySequence.StandardKey.New, self.add_passenger),
                                   ('F5', self.refresh_source), ('F1', lambda:self.host.open_help('personnel'))):
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
        self.refresh_source()

    @property
    def read_model(self):return self.service.read_model

    def prepare_action(self,callback,plan=None):
        plan=plan or self.draft or self.saved_plan or {}
        plan_id=plan.get('personnel_plan_id') or self.plan_combo.currentData()
        material_ids=plan.get('source_dependencies',{}).get('cargo_ids',[])
        def prepared(value):
            self.source=value['source']
            self._action_prepared=True
            try:callback()
            finally:self._action_prepared=False
        return self.run_service_read('prepare_ui',(str(self.host.database_path),plan_id,material_ids),prepared,channel='action-source')

    def run_service_read(self,method,args,callback,channel=None,failed=None,kwargs=None):
        token=object();self._jobs.append(token)
        epoch=self._lifecycle_epoch;request=str(uuid4())
        if channel:self._latest_reads[channel]=request
        def finished(value,error=False):
            self._jobs.remove(token)
            if self._closed or epoch!=self._lifecycle_epoch or (channel and self._latest_reads.get(channel)!=request):return
            try:
                if error:(failed or self.show_error)(value)
                else:callback(value)
            except Exception as exc:self.show_error(exc)
        try:
            if kwargs is not None:return self.service.submit(method,args,finished,lambda error:finished(error,True),kwargs=kwargs)
            return self.service.submit(method,args,finished,lambda error:finished(error,True))
        except Exception as exc:finished(str(exc),True)

    def run_read(self, function, callback, channel=None,label='Loading',error_context=''):
        self.notice.setText(label+'…')
        job = ReadJob(function)
        self._jobs.append(job)
        epoch=self._lifecycle_epoch
        request=str(uuid4())
        if channel:self._latest_reads[channel]=request
        def done(value):
            self._jobs.remove(job)
            if channel=='export' and not self._closed and self._latest_reads[channel]==request:
                self.view_state.export_state='done';self._update_plan_actions()
            if self._closed or epoch!=self._lifecycle_epoch or (channel and self._latest_reads[channel]!=request):
                return
            try:
                callback(value)
                if not self._write_pending and self.notice.text()==label+'…':self.notice.setText('Ready')
            except Exception as exc:
                self.show_error(exc)
        def failed(value):
            self._jobs.remove(job)
            if channel=='export' and not self._closed and self._latest_reads[channel]==request:
                self.view_state.export_state='error';self._update_plan_actions()
            if self._closed or epoch!=self._lifecycle_epoch or (channel and self._latest_reads[channel]!=request):
                return
            self.show_error(error_context+str(value))
        job.signals.done.connect(done)
        job.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(job)

    def run_write(self,method,args,callback,dialog=None):
        if self._write_pending:
            raise PersonnelError('Wait for the current personnel save to finish.')
        self._write_pending=True
        self.view_state.busy=True
        self.view_state.save_state='saving' if method=='save_berth' else 'writing'
        labels={'save_berth':'Saving plan','commit_import':'Importing crew','backup':'Creating backup','restore':'Restoring personnel','relocate':'Moving data','update_settings':'Saving settings'}
        operation=labels.get(method,'Saving crew changes')+'…'
        self.notice.setText(operation)
        self.progress.show();self.progress.setRange(0,0)
        self.tabs.setEnabled(False);self.plan_combo.setEnabled(False)
        for command in self._write_commands:command.setEnabled(False)
        self._update_plan_actions()
        epoch=self._lifecycle_epoch
        def finished(value,error=False):
            self._write_pending=False
            self.view_state.busy=False;self.progress.hide()
            self.view_state.save_state='error' if error else 'saved'
            if self._closed:return
            if self.service.maintenance:
                self.invalidate_plan('Personnel recovery is required. Writes are blocked; preserve the safety copy.')
                self.setEnabled(False)
            else:self.tabs.setEnabled(True);self.plan_combo.setEnabled(True)
            if not self.service.maintenance:
                for command in self._write_commands:command.setEnabled(True)
            if error:
                if dialog:message(dialog,'Personnel operation failed',value,True)
                else:self.show_error(value)
            elif epoch==self._lifecycle_epoch:
                try:callback(value)
                except Exception as exc:self.show_error(exc)
                else:
                    if self.notice.text()==operation:self.notice.setText('' if method=='save_berth' else 'Changes saved.')
            self._update_plan_actions()
        return self.service.submit(method,args,finished,lambda error:finished(error,True))

    def invalidate_plan(self,reason='The data source changed. Generate a fresh plan.'):
        self._validation_timer.stop()
        self._lifecycle_epoch+=1
        if self.view_state.dirty and not self._preserve_recovery(reason):
            self.view_state.source_invalid=True
            if self.live_builder is not None:self.live_builder.setEnabled(False)
            self.plan_notice.setText(reason+' Unsaved content retained on screen; recovery could not be written.')
            self._update_plan_actions()
            return
        if self.live_builder is not None:
            old=self.live_builder
            self.route_stack.removeWidget(old.route_widget);old.route_widget.setParent(old)
            self.live_builder=None
            self.plan_views.removeTab(self.plan_views.indexOf(old))
            old.setEnabled(False)
            old.deleteLater()
        self.draft=self.saved_plan=None
        self.displayed_plan=None
        self.review_task=None
        self.review_button.hide()
        self.preview.clear()
        self.stops.clear()
        self.snapshot_rows.source_model.replace([]);self.route_stack.setCurrentWidget(self.stops)
        self.stops_title.setText('Stops · 0');self.plan_scope.clear();self._selected_stop_id=None
        self.stop_preview.clear();self.stop_comment.clear();self.stop_comment.setEnabled(False)
        self._adapt_plan()
        self.date.setEnabled(True)
        self.plan_notice.setText(reason)
        self.view_state=PlanViewState(source_invalid=True,busy=self._write_pending,source_epoch=self._lifecycle_epoch,export_state=self.view_state.export_state)
        self._update_plan_actions()

    def _preserve_recovery(self,reason):
        plan=copy.deepcopy(self.draft or getattr(self,'displayed_plan',None) or {})
        builder=self.live_builder
        if builder:
            plan['draft_edits']=copy.deepcopy(builder.local_edits)
            plan['override_bases']=copy.deepcopy(builder.override_bases)
            plan['task_selections']={task_key(t):{'state':'included' if c.isChecked() else 'user_excluded' if builder.selection_overrides.get(task_key(t)) is False else 'unavailable','reason':''} for t,c in zip(builder.tasks,builder.includes)}
            plan['recovery_route']=[{'id':builder.route.item(i).data(Qt.ItemDataRole.UserRole)['id'],'vessel_id':builder.route.item(i).data(Qt.ItemDataRole.UserRole)['vessel_id'],'name':builder.route.item(i).text()} for i in range(builder.route.count())]
            plan['date']=builder.plan_date
            plan['stop_comments']=copy.deepcopy(builder.stop_comments)
            plan['recovery_assignments']={task_key(t):a.currentData() for t,a in zip(builder.tasks,builder.assignments) if a.currentData() is not None}
        if not plan:return
        try:
            self.recovery_directory.mkdir(parents=True,exist_ok=True)
            target=self.recovery_directory/(str(uuid4())+'.json')
            target.write_text(json.dumps({'source_invalid':True,'reason':reason,'plan':plan},ensure_ascii=False,indent=2),encoding='utf-8')
            self.notice.setText('Unpublished edits preserved: '+str(target))
            return True
        except OSError as exc:
            self.notice.setText('Could not preserve a recovery draft: '+str(exc))
            return False

    def recover_draft(self):
        candidates=sorted(self.recovery_directory.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        if not candidates:return message(self,'Recovery draft','No recovery draft is available.')
        if not self.guard_leave(self.recover_draft):return
        try:
            plan=json.loads(candidates[0].read_text(encoding='utf-8'))['plan']
            index=self.plan_combo.findData(plan['personnel_plan_id'])
            if index<0:raise PersonnelError('The original crew list is unavailable. Keep the recovery file for reference.')
            self.plan_combo.setCurrentIndex(index)
            builder=CrewPlanBuilder(self,base_plan=plan)
            try:self.draft=builder.build(check_sources=False)
            finally:builder.deleteLater()
            self.saved_plan=None;self.show_plan(self.draft)
            self.notice.setText('Recovered as a new draft; review current sources before publishing.')
        except Exception as exc:self.show_error(exc)

    def mark_dirty(self):
        self.view_state.dirty=True
        self.plan_notice.setText('Draft · Unsaved changes')
        self._update_plan_actions();self._validation_timer.start()

    def guard_leave(self,continuation):
        if self._write_pending:return False
        if not self.view_state.dirty:return True
        choice=prompt(self,'Unsaved plan changes','Save this draft before leaving?',buttons=('Cancel','Discard','Save draft'))
        if choice=='Discard':
            self.view_state.dirty=False
            self.invalidate_plan('Unsaved draft changes discarded. Generate or load another plan.')
            return True
        if choice=='Save draft':
            if self.view_state.source_invalid:
                if self._preserve_recovery('Source changed; review before reuse'):
                    self.view_state.dirty=False;return True
            else:self.save_version(False,on_saved=continuation)
        return False

    def _update_plan_actions(self):
        if not hasattr(self,'save_draft_button'):return
        self.import_button.setObjectName('')
        self.import_button.style().unpolish(self.import_button);self.import_button.style().polish(self.import_button)
        state=self.view_state
        has_editor=state.editing
        ready=state.has_plan and not state.source_invalid and not state.busy and not self._loading_list
        self.save_draft_button.setEnabled(ready and has_editor)
        self.save_plan_button.setEnabled(ready and has_editor and state.issue_count==0)
        formal=has_editor or (self.saved_plan or {}).get('status')=='Published'
        self.plan_export_button.setEnabled(ready and state.issue_count==0 and formal and state.export_state!='writing')
        self.generate_button.setEnabled(not state.busy and not self._loading_list and bool(self.plan_combo.currentData()))
        self.plan_edit_button.setEnabled(ready)
        if hasattr(self,'plan_tools'):
            for action in self.plan_tools.menu().actions():
                command={'Generate plan':self.generate_button,'Edit plan':self.plan_edit_button,'Save draft':self.save_draft_button}.get(action.text())
                if command:action.setEnabled(command.isEnabled())
        self.plan_export_button.setToolTip('Resolve '+str(state.issue_count)+' review issues before formal export' if state.issue_count else 'Choose an Excel destination; cancelling does not save a version')
        primary=self.save_plan_button if ready and has_editor and state.issue_count==0 else self.plan_export_button if ready and formal else None
        for widget in (self.generate_button,self.save_draft_button,self.save_plan_button,self.plan_export_button,self.plan_edit_button):
            widget.setObjectName('primaryButton' if widget is primary else '')
            widget.style().unpolish(widget);widget.style().polish(widget)

    def show_error(self, value):
        self.notice.setText(str(value))
        message(self, "Personnel Transfer Track", value, True)

    def _build(self):
        root=QVBoxLayout(self);root.setContentsMargins(20,12,20,12);root.setSpacing(10)
        self._write_commands=[]
        nav=QHBoxLayout();self.navigation=WorkspaceNavigation('personnel');self.navigation.cargo_button.clicked.connect(self.back)
        nav.addWidget(self.navigation);self._write_commands.extend((self.navigation.dashboard_button,self.navigation.cargo_button,self.navigation.personnel_button));nav.addStretch()
        self.import_button=button('Import Excel',self.import_excel);nav.addWidget(self.import_button);self._write_commands.append(self.import_button)
        for label,callback in (('Refresh',self.refresh_source),('Settings',self.open_settings)):
            command=button(label,callback);nav.addWidget(command);self._write_commands.append(command)
        self.navigation.layout().removeWidget(self.navigation.about_button);nav.addWidget(self.navigation.about_button)
        root.addLayout(nav)
        controls=QHBoxLayout();controls.addWidget(QLabel('Crew list:'));self.plan_combo=QComboBox();self.plan_combo.setMinimumWidth(240)
        self.plan_combo.setMinimumContentsLength(22);self.plan_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.plan_combo.setAccessibleName('Crew list')
        controls.addWidget(self.plan_combo);self.rename_list_button=button('Rename',self.rename_plan);controls.addWidget(self.rename_list_button);self._write_commands.append(self.rename_list_button)
        self.voyage_label=ElidedLabel();self.voyage_label.setText('Reference Voyage: loading…');self.voyage_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);controls.addWidget(self.voyage_label,1)
        new=button('New crew list',self.new_plan);self._write_commands.append(new)
        list_menu=QToolButton();list_menu.setText('More');list_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(list_menu);menu.addAction('New crew list',new.click);menu.addAction('Normalize existing names / positions…',self.normalize_names);list_menu.setMenu(menu);controls.addWidget(list_menu);root.addLayout(controls)
        date_row=QHBoxLayout();date_row.addWidget(QLabel('Plan date:'));self.date=QDateEdit(QDate.currentDate());self.date.setCalendarPopup(True);self.date.setDisplayFormat('yyyy-MM-dd');self.date.setAccessibleName('Berthing plan date')
        self.date.setToolTip('Date printed in the berthing table and Excel heading; crew change dates stay unchanged.')
        date_row.addWidget(self.date);date_row.addStretch();root.addLayout(date_row)
        from .frosted import FrostedFrame
        self.tabs_surface=FrostedFrame();self.tabs_surface.setObjectName('surface')
        tabs_layout=QVBoxLayout(self.tabs_surface);tabs_layout.setContentsMargins(12,10,12,10)
        self.tabs=QTabWidget();self.tabs.setObjectName('personnelTabs');tabs_layout.addWidget(self.tabs);root.addWidget(self.tabs_surface,1)
        personnel=QWidget();layout=QVBoxLayout(personnel);layout.setContentsMargins(0,12,0,0);layout.setSpacing(10);self.tabs.addTab(personnel,'Crew change information')
        filters=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Search name, position, vessel or comment…');self.search.setAccessibleName('Search personnel entries');self.search.setClearButtonEnabled(True)
        self.view=QComboBox();self.view.addItem('All vessels',None);self.direction=QComboBox();self.direction.addItems(['All directions','Sign-on','Sign-off','Transfer'])
        filters.addWidget(self.search,1);filters.addWidget(self.view);filters.addWidget(self.direction);filters.addWidget(button('Clear filters',self.clear_filters));layout.addLayout(filters)
        actions=QHBoxLayout();self.add_button=button('Add entry',self.add_passenger);self.edit_button=button('Edit crew entry',self.edit_passenger);self.remove_button=button('Remove entry',self.remove_crew_entries)
        for widget in (self.add_button,self.edit_button,self.remove_button):actions.addWidget(widget)
        actions.addStretch();layout.addLayout(actions)
        self.passenger_table=ModelTable(['NO','Name','Position','Sign-on / Sign-off','From','To','Crew change date','Comment']);self.passenger_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.crew_filter=CrewFilter(self);self.crew_filter.setSourceModel(self.passenger_table.source_model);self.passenger_table.setModel(self.crew_filter)
        self.passenger_table.selectionModel().selectionChanged.connect(lambda *_:self.passenger_table.itemSelectionChanged.emit())
        for c,w in enumerate((50,165,105,145,140,140,155,160)):self.passenger_table.setColumnWidth(c,w)
        self.passenger_table.setAccessibleName('Personnel transfer ledger');self.passenger_table.verticalHeader().setDefaultSectionSize(42);self.passenger_table.setShowGrid(False);layout.addWidget(self.passenger_table,1)
        self.detail=QLabel('');self.detail.setWordWrap(True);self.detail.setTextFormat(Qt.TextFormat.PlainText);self.detail.setMaximumHeight(70);layout.addWidget(self.detail)
        berth=QWidget();berth_layout=QVBoxLayout(berth);berth_layout.setContentsMargins(0,12,0,0);berth_layout.setSpacing(10);self.tabs.addTab(berth,'Berthing plan')
        self.generate_button=button('Generate plan',self.generate);self.save_draft_button=button('Save draft',lambda:self.save_version(False));self.save_plan_button=button('Save version',lambda:self.save_version(True));self.plan_export_button=button('Export Excel',self.export)
        self.plan_edit_button=button('Edit plan',self.copy_complete)
        self.versions=QComboBox();self.versions.setAccessibleName('Saved berthing plan versions')
        version_row=QHBoxLayout();version_row.addWidget(self.versions,1);version_row.addWidget(button('Load version',self.load_version))
        self.remove_version_button=button('Remove selected',lambda:self.clear_version_history(False));self.clear_history_button=button('Clear history',lambda:self.clear_version_history(True))
        for command in (self.remove_version_button,self.clear_history_button):version_row.addWidget(command);self._write_commands.append(command)
        self.history_row=QWidget();self.history_row.setLayout(version_row);self.history_row.hide();berth_layout.addWidget(self.history_row)
        self.plan_split=QSplitter();berth_layout.addWidget(self.plan_split,1)
        self.sidebar=QFrame();self.sidebar.setObjectName('routeSidebar');self.sidebar.setMinimumWidth(175);sidebar_layout=QVBoxLayout(self.sidebar);sidebar_layout.setContentsMargins(0,0,12,0)
        self.stops_title=QLabel('Stops · 0');self.stops_title.setObjectName('workbenchTitle');sidebar_layout.addWidget(self.stops_title)
        self.route_stack=QStackedWidget();sidebar_layout.addWidget(self.route_stack,1)
        self.stops=PlanStopList();self.stops.setObjectName('stopList');self.stops.setAccessibleName('Berthing plan stop order');self.stops.itemClicked.connect(self.locate_plan_item)
        self.stops.setItemDelegate(NumberedStopDelegate(self.stops,numbered=False))
        self.route_stack.addWidget(self.stops);self.plan_split.addWidget(self.sidebar)
        self.plan_views=QTabWidget();self.plan_views.setObjectName('planViews');self.plan_views.tabBar().hide();self.plan_views.setMinimumWidth(300)
        self.preview=QTextBrowser();self.preview.setAccessibleName('Full personnel plan preview');self.plan_views.addTab(self.preview,'Personnel preview')
        self.snapshot_rows=ModelTable(['Name','Position','Leg','Pick up','Drop']);self.snapshot_rows.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.snapshot_rows.setShowGrid(False);self.snapshot_rows.verticalHeader().setDefaultSectionSize(42)
        self.plan_views.addTab(self.snapshot_rows,'Saved personnel');self.plan_views.currentChanged.connect(self.plan_view_changed);self.plan_split.addWidget(self.plan_views)
        self.stop_preview_panel=QWidget();self.stop_preview_panel.setMinimumWidth(250);right=QVBoxLayout(self.stop_preview_panel);right.setContentsMargins(14,0,0,0);right.setSpacing(12)
        self.stop_preview_title=QLabel('Stop preview');self.stop_preview_title.setWordWrap(True);self.stop_preview_title.setObjectName('workbenchTitle');right.addWidget(self.stop_preview_title)
        self.stop_preview=QTextBrowser();self.stop_preview.setAccessibleName('Selected stop passengers');self.stop_preview.setMinimumHeight(110);self.stop_preview.setMaximumHeight(220);right.addWidget(self.stop_preview)
        right.addWidget(button('Full personnel preview',self.open_personnel_preview));right.addWidget(QLabel('Comments'))
        self.stop_comment=QTextEdit();self.stop_comment.setPlaceholderText('Add comments about this stop…');self.stop_comment.setAccessibleName('Selected plan stop comment');self.stop_comment.textChanged.connect(self.stop_comment_changed);right.addWidget(self.stop_comment,1)
        self.plan_split.addWidget(self.stop_preview_panel);self.plan_split.setStretchFactor(1,1);self.plan_split.setSizes([220,770,400]);self.plan_split.setChildrenCollapsible(False)
        self.review_button=button('Edit this crew entry',self.edit_review_entry);self.review_button.hide();berth_layout.addWidget(self.review_button)
        footer=QHBoxLayout();self.plan_scope=QLabel('');footer.addWidget(self.plan_scope)
        self.plan_notice=QLabel('Generate or load a plan');self.plan_notice.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);footer.addWidget(self.plan_notice,1)
        history=button('Version history',lambda:self.history_row.setVisible(not self.history_row.isVisible()));footer.addWidget(history)
        self.stop_preview_toggle=button('Stop preview',self.toggle_stop_preview);self.stop_preview_toggle.hide();footer.addWidget(self.stop_preview_toggle)
        self.plan_tools=QToolButton();self.plan_tools.setText('More');self.plan_tools.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);tools_menu=QMenu(self.plan_tools)
        tools_menu.addAction('Generate plan',self.generate_button.click);tools_menu.addAction('Edit plan',self.plan_edit_button.click);tools_menu.addAction('Save draft',self.save_draft_button.click);tools_menu.addAction('Full personnel preview',self.open_personnel_preview);tools_menu.addAction('Recover draft',self.recover_draft);self.plan_tools.setMenu(tools_menu)
        self.generate_button.hide();self.plan_edit_button.hide();self.save_draft_button.hide()
        for widget in (self.plan_tools,self.plan_export_button,self.save_plan_button):footer.addWidget(widget)
        berth_layout.addLayout(footer)
        self.notice=QLabel('');self.notice.setWordWrap(True);self.notice.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        status_row=QHBoxLayout();status_row.addWidget(self.notice,1);self.progress=QProgressBar();self.progress.setMaximumWidth(120);self.progress.setTextVisible(False);self.progress.hide();status_row.addWidget(self.progress);root.addLayout(status_row)
        self._selected_stop_id=None;self._preview_sync=False
        self.plan_combo.currentIndexChanged.connect(self.plan_changed)
        self._crew_search_timer=QTimer(self);self._crew_search_timer.setSingleShot(True);self._crew_search_timer.setInterval(200);self._crew_search_timer.timeout.connect(self._apply_crew_filter)
        self.search.textChanged.connect(lambda *_:self._crew_search_timer.start())
        for signal in (self.view.currentIndexChanged,self.direction.currentIndexChanged):signal.connect(lambda *_:self._apply_crew_filter())
        self.tabs.currentChanged.connect(lambda *_:self._update_plan_actions());self.passenger_table.itemSelectionChanged.connect(self.selection_changed)
        self.date.dateChanged.connect(self.plan_date_changed);self._update_plan_actions()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._adapt_plan()

    def _adapt_plan(self):
        if not hasattr(self,'plan_split'):return
        width=self.width();left=190 if width<1250 else round(width*.15);right=260 if width<1250 else round(width*.31)
        roster_compact=width<1050
        if getattr(self,'_roster_compact',None)!=roster_compact:
            self._roster_compact=roster_compact
            widths=(40,105,75,95,95,95,95,120) if roster_compact else (50,165,105,145,140,140,155,160)
            for column,column_width in enumerate(widths):self.passenger_table.setColumnWidth(column,column_width)
            headers=self.passenger_table.source_model.headers
            headers[3]='Movement' if roster_compact else 'Sign-on / Sign-off'
            headers[6]='Crew date' if roster_compact else 'Crew change date'
            self.passenger_table.source_model.headerDataChanged.emit(Qt.Orientation.Horizontal,3,6)
        compact=width<1250
        count=self.live_builder.route.count() if self.live_builder else self.stops.count()
        if count>12:
            left=min(500,max(330,((count+7)//8)*165));compact=width<1500
        key=(width,count>12,compact)
        if getattr(self,'_plan_layout_key',None)==key:return
        self._plan_layout_key=key
        self.stop_preview_panel.setVisible(not compact);self.stop_preview_toggle.setVisible(compact)
        if compact:right=0
        self.plan_split.setSizes([left,max(300,width-left-right-40),right])
        if self.live_builder:
            self.live_builder.route.reflow()
        self.stops.reflow()

    def toggle_stop_preview(self):
        self.stop_preview_panel.setVisible(not self.stop_preview_panel.isVisible())
        self.plan_split.setSizes([190,max(300,self.width()-510),260])

    def plan_date(self):
        return self.date.date().toString("yyyy-MM-dd")

    def refresh_source(self):
        cargo_path = str(self.host.database_path)
        def received(source):
            if cargo_path != str(self.host.database_path):
                return self.refresh_source()
            self.source = source
            selected_vessel = self.view.currentData()
            self.view.blockSignals(True)
            self.view.clear()
            self.view.addItem("All vessels", None)
            for location in source["locations"]:
                if location["kind"] == "VESSEL" and location["active"]:
                    self.view.addItem(location["name"], location["id"])
            self.view.setCurrentIndex(max(0, self.view.findData(selected_vessel)))
            self.view.blockSignals(False)
            self.voyage_label.setText("Reference Voyage: " + (source["voyage_name"] or "None selected"))
            self.voyage_label.setToolTip(self.voyage_label.text())
            self.notice.setText('')
            if self.saved_plan and not source_matches(self.saved_plan,source):
                self.plan_notice.setText("Cargo source changed. The saved version remains unchanged; generate a new draft for current work.")
            self.refresh_plans(force=True)
        self.run_read(lambda: read_cargo(cargo_path,active_only=True), received,channel='cargo-source')

    def refresh_plans(self, selected=None, force=False):
        selected = selected or self.plan_combo.currentData()
        if self.read_model.state and not any(p['id']==selected for p in self.read_model.plans()):
            selected=self.read_model.state.get('plan_id')
        if force or not self.read_model.state or (selected and selected!=self.read_model.state.get('plan_id')):
            return self.run_service_read('ui_state',(selected,),lambda _:self.refresh_plans(selected),channel='crew-state')
        self._loading_list=False;self.tabs.setEnabled(not self._write_pending)
        self.plan_combo.blockSignals(True)
        self.plan_combo.clear()
        for p in self.read_model.plans():
            self.plan_combo.addItem(p["name"], p["id"])
            self.plan_combo.setItemData(self.plan_combo.count()-1, f"Crew list reference date: {p['date']}", Qt.ItemDataRole.ToolTipRole)
        index = self.plan_combo.findData(selected)
        if index >= 0:
            self.plan_combo.setCurrentIndex(index)
        self.plan_combo.blockSignals(False)
        self.plan_changed()
        self.refresh_versions()

    def plan_changed(self):
        current=self.plan_combo.currentData()
        self.rename_list_button.setEnabled(current is not None and not self._write_pending)
        if current!=self._selected_crew_id and self.view_state.dirty:
            self.plan_combo.blockSignals(True);self.plan_combo.setCurrentIndex(self.plan_combo.findData(self._selected_crew_id));self.plan_combo.blockSignals(False)
            def switched():self.plan_combo.setCurrentIndex(self.plan_combo.findData(current))
            if self.guard_leave(switched):switched()
            return
        if current and current!=self.read_model.state.get('plan_id'):
            self._loading_list=True;self.tabs.setEnabled(False);self._update_plan_actions()
            def loaded(_):
                self._loading_list=False;self.tabs.setEnabled(not self._write_pending)
                if not any(p['id']==current for p in self.read_model.plans()):
                    return self.refresh_plans(self.read_model.state.get('plan_id'))
                self.plan_changed()
            def failed(error):
                self._loading_list=False;self.tabs.setEnabled(not self._write_pending)
                self._update_plan_actions();self.show_error(error)
            return self.run_service_read('ui_state',(current,),loaded,channel='crew-state',failed=failed)
        if current!=self._selected_crew_id:
            self._selected_crew_id=current
            self.invalidate_plan('Crew list changed. Generate a fresh plan for the selected list.')
        selected = next((p for p in self.read_model.plans() if p["id"] == self.plan_combo.currentData()), None)
        if selected and not self.draft and not self.saved_plan:
            dates = {r.get("date") for r in self.read_model.passengers(selected["id"]) if r["status"] != "Cancelled" and r.get("date")}
            self.date.setDate(QDate.fromString(next(iter(dates)) if len(dates) == 1 else selected["date"], "yyyy-MM-dd"))
        self.refresh_rows()
        self._update_plan_actions()

    def plan_date_changed(self):
        if self.draft is not None and not self.draft.get("id"):
            if self.live_builder is not None:
                self.live_builder.plan_date = self.plan_date()
                self.mark_dirty()
                self.refresh_live_preview(False)
                return
            self.draft["date"] = self.plan_date()
            self.show_plan(self.draft)

    def clear_filters(self):
        self.search.clear()
        self.direction.setCurrentIndex(0)
        self.view.setCurrentIndex(0)

    def refresh_rows(self):
        if not self.source:
            return
        if self.plan_combo.currentData()!=self.read_model.state.get('plan_id'):
            return self.plan_changed()
        selected={r['id'] for r in self.selected()} if self.rows_data else set()
        rows = self.read_model.crew_records(self.plan_combo.currentData(), self.source) if self.plan_combo.currentData() else []
        self._crew_source_rows=rows
        for row in rows:
            row["route_issues"] = [p for p in row.get("issues", []) if p != "Missing date"]
        self.passenger_table.source_model.records=rows
        fill_table(self.passenger_table, [[i + 1, *[r.get(f, "") for f in ("name", "position", "direction", "from_name", "to_name", "date", "comment")]]
                                          for i, r in enumerate(rows)])
        self._apply_crew_filter(selected)

    def _apply_crew_filter(self,selected=None):
        if selected is None:selected={r['id'] for r in self.selected()} if self.rows_data else set()
        self.crew_filter.apply(key(self.search.text()),self.view.currentData(),self.direction.currentText() if self.direction.currentIndex() else '')
        self.rows_data=[self._crew_source_rows[self.crew_filter.mapToSource(self.crew_filter.index(i,0)).row()] for i in range(self.crew_filter.rowCount())]
        self.passenger_table.clearSelection()
        for i,row in enumerate(self.rows_data):
            if row['id'] in selected:self.passenger_table.selectionModel().select(self.crew_filter.index(i,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        self.selection_changed()

    def selected(self):
        indices = sorted({i.row() for i in self.passenger_table.selectedIndexes()})
        return [self.rows_data[i] for i in indices if i < len(self.rows_data)]

    def selection_changed(self):
        rows = self.selected()
        self.edit_button.setEnabled(len(rows) == 1)
        self.remove_button.setEnabled(bool(rows))
        if len(rows) == 1:
            r = rows[0]
            self.detail.setText(f"{r['name']} · Nationality: {r.get('nationality') or '—'} · Source: {r.get('source_sheet') or 'Manual'}, row {r.get('source_row') or '—'} · Original date: {r.get('source_date') or '—'}\n" +
                                ("; ".join(r["route_issues"]) or "Vessel matches resolved. Available for plan selection."))
        else:
            self.detail.setText(f"{len(rows)} crew entries selected" if rows else "Select a crew entry to view its source details.")

    def new_plan(self):
        name, ok = QInputDialog.getText(self, "New crew list", "Crew list name")
        if ok:
            try:
                self.run_write('create_plan',(name,self.plan_date()),self.refresh_plans)
            except Exception as exc:
                self.show_error(exc)

    def rename_plan(self):
        identifier=self.plan_combo.currentData()
        if not identifier:return self.show_error('Select a crew list to rename.')
        previous=self.plan_combo.currentText()
        name,ok=QInputDialog.getText(self,'Rename crew list','Crew list name',text=previous)
        if ok:
            try:self.run_write('rename_plan',(identifier,name,previous),lambda _:self.refresh_plans())
            except Exception as exc:self.show_error(exc)

    def clear_version_history(self, all_versions=False):
        if not self.guard_leave(lambda:self.clear_version_history(all_versions)):return
        versions=self.read_model.berth_summaries()
        identifiers=[p['id'] for p in versions] if all_versions else ([self.versions.currentData()] if self.versions.currentData() else [])
        if not identifiers:return self.show_error('There are no saved versions to remove.')
        if not confirm(self,'Clear version history',f'Remove {len(identifiers)} saved version(s) from Version history? Snapshots remain in the database for audit and backup. Crew entries and Cargo are unaffected.'):
            return
        def cleared(_):
            if (self.saved_plan or {}).get('id') in identifiers:
                self.invalidate_plan('Version history cleared. Generate or load another plan.')
            self.refresh_versions()
            self.notice.setText(f'Removed {len(identifiers)} version(s) from history.')
        try:self.run_write('clear_berth_history',(identifiers,),cleared)
        except Exception as exc:self.show_error(exc)

    def import_excel(self):
        if not self._action_prepared:return self.prepare_action(self.import_excel)
        if not self.source:
            return self.show_error("Wait for the Cargo source to load.")
        path, _ = QFileDialog.getOpenFileName(self, "Import personnel Excel", "", "Excel workbook (*.xlsx)")
        if not path:
            return
        def choose(sheets):
            chosen = sheets[0]
            if len(sheets) > 1:
                chosen, ok = QInputDialog.getItem(self, "Choose worksheet", "Worksheet", sheets, 0, False)
                if not ok:
                    return
            def read():
                try:
                    return read_personnel_excel(path, chosen)
                except PersonnelError as exc:
                    return {"mapping_error": str(exc)}
            def preview(parsed):
                if "mapping_error" in parsed:
                    dialog = ColumnMappingDialog(self)
                    if dialog.exec() != QDialog.DialogCode.Accepted:
                        return
                    mapping, header = dialog.mapping()
                    self.run_read(lambda: read_personnel_excel(path, chosen, mapping, header), preview)
                    return
                self.source = copy.deepcopy(self.source)
                self.import_parsed(parsed)
            self.run_read(read, preview)
        self.run_read(lambda: workbook_sheets(path), choose)

    def import_parsed(self, parsed):
        dialog = ImportDialog(self, parsed)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_plans(dialog.result["plan_id"])
            self.crew_changed()
            self.notice.setText(f"Imported: {dialog.result['added']} new, {dialog.result['updated']} updated, {dialog.result['cancelled']} removed. Current berthing plan updated.")

    def normalize_names(self):
        plan_id=self.plan_combo.currentData()
        if not plan_id or not self.guard_leave(self.normalize_names):return
        try:
            proposals=self.read_model.text_case_preview(plan_id)
            if not proposals:return message(self,'Crew names','No spelling changes are suggested.')
            dialog=CasePreviewDialog(proposals,self)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                def applied(count):
                    self.crew_changed();self.notice.setText(f'{count} spelling changes applied. Current plan updated; earlier versions retained.')
                self.run_write('apply_text_case',(plan_id,dialog.selected()),applied)
        except Exception as exc:self.show_error(exc)

    def add_passenger(self):
        if not self._action_prepared:return self.prepare_action(self.add_passenger)
        try:
            if not self.plan_combo.currentData():
                raise PersonnelError("Create a personnel plan first.")
            self.source = copy.deepcopy(self.source)
            dialog = PassengerForm(self.read_model, self.source, self.plan_date(), parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                def added(value):
                    self.crew_changed()
                self.run_write('add_passenger',(self.plan_combo.currentData(),dialog.data()),added)
        except Exception as exc:
            self.show_error(exc)

    def edit_passenger(self):
        if not self._action_prepared:return self.prepare_action(self.edit_passenger)
        try:
            selected = self.selected()
            if len(selected) != 1:
                return
            self.source = copy.deepcopy(self.source)
            row = selected[0]
            dialog = PassengerForm(self.read_model, self.source, self.plan_date(), row, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                def edited(value):
                    self.crew_changed()
                self.run_write('edit_crew_entry',(row['id'],dialog.data(),row['version']),edited)
        except Exception as exc:
            self.show_error(exc)

    def remove_crew_entries(self):
        selected = self.selected()
        if selected and confirm(self, "Remove crew entries", "Remove the selected entries and update the current berthing plan? Earlier versions remain available."):
            try:
                def removed(value):
                    self.crew_changed()
                self.run_write('remove_crew_entries',({r['id']:r['version'] for r in selected},),removed)
            except Exception as exc:
                self.show_error(exc)

    def crew_changed(self):
        self.refresh_rows()
        self.refresh_versions()
        if self.live_builder:
            self.live_builder.sync_crew()
            self.refresh_live_preview()
        elif self.saved_plan and self.saved_plan.get('mode') == 'Final':
            def received(latest):
                if latest and self.saved_plan and latest['id'] != self.saved_plan['id']:
                    self.saved_plan=latest;self.draft=None;self.show_plan(latest)
            self.run_service_read('latest_berth',(self.saved_plan['family_id'],),received,channel='current-family')
        if hasattr(self.host, 'dashboard_page'):self.host.dashboard_page.schedule_refresh()

    def generate(self):
        if not self._action_prepared:return self.prepare_action(self.generate)
        if not self.guard_leave(self.generate):return
        try:
            dialog = CrewPlanBuilder(self)
            try:
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                self.draft = dialog.build(check_sources=False)
                self.saved_plan = None
                self.show_plan(self.draft)
            finally:
                dialog.deleteLater()
        except Exception as exc:
            self.show_error(exc)

    def show_plan(self, plan):
        self.view_state.dirty=not bool(plan.get('id'))
        self.view_state.working_draft_id=str(uuid4()) if not plan.get('id') else None
        if self.live_builder is not None:
            old = self.live_builder
            self.route_stack.removeWidget(old.route_widget);old.route_widget.setParent(old)
            self.live_builder = None
            self.plan_views.removeTab(self.plan_views.indexOf(old))
            old.deleteLater()
        self.update_plan_preview(plan)
        if not plan.get("id"):
            self.live_builder = CrewPlanBuilder(self, base_plan=plan, inline=True)
            self.live_builder.previewRequested.connect(lambda: self.refresh_live_preview(True))
            self.live_builder.draftChanged.connect(self.mark_dirty)
            self.plan_views.insertTab(0, self.live_builder, "Edit draft directly")
            self.plan_views.setCurrentWidget(self.live_builder)
            self.route_stack.addWidget(self.live_builder.route_widget);self.route_stack.setCurrentWidget(self.live_builder.route_widget)
            self.live_builder.route_widget.show()
            self.live_builder.route.currentRowChanged.connect(lambda *_:self.builder_stop_changed())
            initial=next((i for i in range(self.live_builder.route.count()) if self.live_builder.route.item(i).data(Qt.ItemDataRole.UserRole)['id']==self._selected_stop_id),0)
            self.live_builder.route.setCurrentRow(initial)
        else:
            self.plan_views.setCurrentWidget(self.snapshot_rows);self.route_stack.setCurrentWidget(self.stops)
        self.plan_view_changed()
        self._update_plan_actions()

    def update_plan_preview(self, plan):
        self.view_state.has_plan=True;self.view_state.source_invalid=False
        self.view_state.editing=not bool(plan.get('id'));self.view_state.source_epoch=self._lifecycle_epoch
        if self.view_state.editing:
            if not self.view_state.working_draft_id:self.view_state.working_draft_id=str(uuid4())
        else:self.view_state.working_draft_id=None
        self.view_state.snapshot_id=plan.get('id');self.view_state.issue_count=len(plan.get('issues',[]))
        self.displayed_plan = plan
        self.date.blockSignals(True)
        self.date.setDate(QDate.fromString(plan["date"], "yyyy-MM-dd"))
        self.date.blockSignals(False)
        self.date.setEnabled(not plan.get("id"))
        self.review_task = None
        self.review_button.hide()
        self.tabs.setCurrentIndex(1)
        self.stops.clear()
        for stop in plan["stops"]:
            item = QListWidgetItem(f"{stop['number']:02d}   {stop['name']}");item.setSizeHint(QSize(160,42))
            item.setData(Qt.ItemDataRole.UserRole, {"label": f"{stop['number']:02d}. {stop['name']}",'stop_id':stop['id']})
            self.stops.addItem(item)
        reviews = plan_review_groups(plan)
        for problem in reviews:
            if problem.get('task','').startswith('Materials:'):continue
            item = QListWidgetItem("Review: " + problem["name"] + f" · {len(problem['messages'])} checks")
            item.setToolTip("\n".join(problem["messages"]))
            item.setData(Qt.ItemDataRole.UserRole, problem)
            self.stops.addItem(item)
        self.preview.setPlainText(plan_text(plan,compact=True,personnel_only=True))
        self.stops_title.setText(f"Stops · {len(plan['stops'])}")
        crew={task_key(t):t for s in plan['stops'] for group in ('drop_passengers','pick_passengers') for t in s[group]}
        people=len({t.get('person_id') or t['id'] for t in crew.values()})
        self.plan_scope.setText(f"{people} people · {len(crew)} legs · {len(reviews)} review issues")
        self.plan_notice.setText((f"{plan.get('status','Draft')} v{plan['version']}" if plan.get('id') else 'Draft')+(' · Unsaved changes' if self.view_state.dirty else ''))
        self.plan_notice.setToolTip('All export review checks remain enforced. Resolve route prerequisites in Cargo when required.')
        names={s['id']:f"{s['number']:02d} · {s['name']}" for s in plan['stops']};assignments=plan_assignments(plan)
        records=[]
        for identifier,t in sorted(crew.items(),key=lambda pair:leg_order(pair[1])):
            assignment=assignments.get(identifier,{})
            records.append([t['name'],t.get('position',''),leg_order(t),names.get(assignment.get('pick'),'On '+plan['transfer_vessel']),names.get(assignment.get('drop'),'—')])
        fill_table(self.snapshot_rows,records)
        for column,width in enumerate((160,90,50,180,180)):self.snapshot_rows.setColumnWidth(column,width)
        if self._selected_stop_id not in names:self._selected_stop_id=plan['stops'][0]['id'] if plan['stops'] else None
        for i in range(self.stops.count()):
            if (self.stops.item(i).data(Qt.ItemDataRole.UserRole) or {}).get('stop_id')==self._selected_stop_id:self.stops.setCurrentRow(i);break
        self.render_stop_preview()
        if self.live_builder:self.live_builder.route.reflow()
        self._adapt_plan();self.stops.reflow()
        self._update_plan_actions()

    def refresh_live_preview(self, show=False):
        if self.live_builder is None:
            return
        try:
            self.draft = self.live_builder.build(check_sources=False)
            self.saved_plan = None
            self.update_plan_preview(self.draft)
            if show:
                self.plan_views.setCurrentWidget(self.preview)
        except Exception as exc:
            self.view_state.source_invalid=True
            self.plan_notice.setText('Draft needs current source review: '+str(exc))
            self._update_plan_actions()

    def plan_view_changed(self):
        self.stops.setVisible(self.live_builder is None or self.plan_views.currentWidget() is self.preview)
        if self.live_builder is not None and self.plan_views.currentWidget() is self.preview:
            self.refresh_live_preview(False)

    def locate_plan_item(self, item):
        value = item.data(Qt.ItemDataRole.UserRole) or {}
        self.review_button.hide()
        self.review_task = None
        if value.get('stop_id'):
            self._selected_stop_id=value['stop_id'];self.render_stop_preview();return
        if "messages" in value:
            self.plan_views.blockSignals(True)
            self.plan_views.setCurrentWidget(self.preview)
            self.plan_views.blockSignals(False)
            self.review_task = value.get("task", "")
            current = self.draft or self.saved_plan or {}
            route_text = ""
            if self.review_task.startswith("Materials:"):
                source = self.source
                record = next((r for r in source["cargo"] if str(r["no"]) == self.review_task.split(":", 1)[1]), None)
                if record:
                    route_text = f"\nFrom: {record['from_name_snapshot']}\nTo: {record['to_name_snapshot']}\n"
            elif self.review_task.startswith("Passengers:"):
                record = next((r for r in self.read_model.crew_records(current.get("personnel_plan_id"), self.source)
                               if r["id"] == self.review_task.split(":", 1)[1]), None)
                if record:
                    route_text = f"\nFrom: {record['from_name']}\nTo: {record['to_name']}\n"
            self.preview.setPlainText("Review: " + value["name"] + "\n" + route_text + "\n" +
                "\n".join("• " + reason for reason in value["messages"]) +
                "\n\nEdit personnel directly in the draft. For material route problems, add the required vessel stops. "
                "Material content is managed in Cargo.")
            if self.review_task.startswith("Passengers:"):
                self.review_button.show()
            return
        self.preview.setPlainText(plan_text(self.displayed_plan,compact=True,personnel_only=True))
        cursor = self.preview.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.preview.setTextCursor(cursor)
        self.preview.find(value.get("label", ""))

    def builder_stop_changed(self):
        route=self.live_builder.route if self.live_builder else None
        if route and route.currentItem():self._selected_stop_id=route.currentItem().data(Qt.ItemDataRole.UserRole)['id']
        self.render_stop_preview()

    def render_stop_preview(self):
        plan=getattr(self,'displayed_plan',None) or {}
        stop=next((s for s in plan.get('stops',[]) if s['id']==self._selected_stop_id),None)
        self._preview_sync=True
        try:
            if not stop:
                self.stop_preview_title.setText('Stop preview');self.stop_preview.clear();self.stop_comment.clear();self.stop_comment.setEnabled(False);return
            self.stop_preview_title.setText(f"Stop preview · {stop['number']:02d} · {stop['name']}")
            tokens=colors(is_dark_mode());rows=[]
            for label,group in (('Drop passengers','drop_passengers'),('Pick up passengers','pick_passengers')):
                tasks=stop[group];entries='; '.join(f"{t['name']} ({t.get('position','')})" for t in tasks)
                detail=str(len(tasks))+(' · '+entries if tasks else '')
                rows.append('<tr><td><nobr>'+label+'</nobr></td><td>'+html.escape(detail)+'</td></tr>')
            self.stop_preview.setHtml('<style>td {padding:7px; border-bottom:1px solid '+tokens['divider']+';} table {color:'+tokens['text']+';}</style><table width="100%" cellspacing="0"><tr><td>Item</td><td>Details</td></tr>'+''.join(rows)+'</table>')
            comment=self.live_builder.stop_comments.get(stop['id'],'') if self.live_builder else stop.get('comment','')
            self.stop_comment.setPlainText(comment);self.stop_comment.setEnabled(self.live_builder is not None and not self.view_state.busy)
        finally:self._preview_sync=False

    def stop_comment_changed(self):
        if self._preview_sync or not self.live_builder or not self._selected_stop_id:return
        self.live_builder.stop_comments[self._selected_stop_id]=self.stop_comment.toPlainText();self.mark_dirty()

    def open_personnel_preview(self):
        self.refresh_live_preview(False)
        plan=getattr(self,'displayed_plan',None)
        if not plan:return
        dialog=NativeDialog(self);dialog.setWindowTitle('Full personnel preview');dialog.resize(840,680)
        layout=QVBoxLayout(dialog);viewer=QTextBrowser();viewer.setPlainText(plan_text(plan,personnel_only=True));layout.addWidget(viewer)
        layout.addWidget(button('Close',dialog.accept));dialog.exec()

    def edit_review_entry(self):
        if not self._action_prepared:return self.prepare_action(self.edit_review_entry)
        try:
            current = self.draft or self.saved_plan
            source = self.source
            identifier = self.review_task.split(":", 1)[1]
            records = self.read_model.crew_records(current.get("personnel_plan_id"), source)
            record = next((r for r in records if r["id"] == identifier), None)
            if record is None:
                return message(self, "Entry no longer in the crew list", "This version refers to an older crew entry. Choose Edit plan to rebuild it with the current crew list.")
            form = PassengerForm(self.read_model, source, self.plan_date(), record, self)
            if form.exec() == QDialog.DialogCode.Accepted:
                data=form.data()
                def edited(value):
                    revised=copy.deepcopy(current)
                    for field in ('name','position'):
                        if data.get(field)!=record.get(field):
                            revised.get('draft_edits',{}).get('Passengers:'+identifier,{}).pop(field,None)
                    builder = CrewPlanBuilder(self, base_plan=revised)
                    try:self.draft = builder.build(check_sources=False)
                    finally:builder.deleteLater()
                    self.saved_plan = None
                    self.refresh_rows()
                    self.show_plan(self.draft)
                self.run_write('edit_crew_entry',(identifier,data,record['version']),edited)
        except Exception as exc:
            self.show_error(exc)

    def save_version(self, published,on_saved=None):
        if not self._action_prepared:return self.prepare_action(lambda:self.save_version(published,on_saved))
        try:
            if self.live_builder is not None:
                self.draft = self.live_builder.build(check_sources=False)
            if self.draft is None:
                raise PersonnelError("Generate or copy a plan draft first.")
            def saved(value):
                self.saved_plan=value
                self.draft=dict(value)
                self.show_plan(value)
                self.refresh_versions(value['id'])
                self.view_state.dirty=False;self._update_plan_actions()
                if on_saved:on_saved()
            self.run_write('save_berth',(copy.deepcopy(self.draft),published,self.draft.get('family_id')),saved)
        except Exception as exc:
            self.show_error(exc)

    def refresh_versions(self, selected=None):
        self.versions.clear()
        for plan in self.read_model.berth_summaries():
            self.versions.addItem(f"{plan['date']} · {plan['voyage_name']} · {plan['mode']} · {plan['status']} v{plan['version']}", plan["id"])
        if selected:
            self.versions.setCurrentIndex(self.versions.findData(selected))
        for command in (self.remove_version_button,self.clear_history_button):
            command.setEnabled(self.versions.count()>0 and not self._write_pending)

    def selected_version(self):
        identifier = self.versions.currentData()
        return self._version_cache.get(identifier)

    def load_version(self):
        if not self.guard_leave(self.load_version):return
        identifier=self.versions.currentData()
        if not identifier:return self.show_error('Choose a saved version to load.')
        def received(plan):
            if not plan:return self.show_error('This version is no longer available.')
            self._version_cache={identifier:plan}
            def prepared():
                if not any(v['id']==identifier for v in self.read_model.berth_summaries()):
                    return self.show_error('This version was removed while loading. Choose another version.')
                self.refresh_plans(plan.get('personnel_plan_id'))
                self.refresh_versions(identifier)
                self._display_version(plan)
            self.prepare_action(prepared,plan=plan)
        self.run_service_read('berth_version',(identifier,),received,channel='version')

    def _display_version(self,plan):
        try:
            if not plan:
                raise PersonnelError("Choose a saved version to load.")
            if plan.get('personnel_plan_id') and self.plan_combo.findData(plan['personnel_plan_id'])>=0:
                self.plan_combo.setCurrentIndex(self.plan_combo.findData(plan['personnel_plan_id']))
            if plan["mode"] != "Final":
                builder = CrewPlanBuilder(self, base_plan=plan)
                try:
                    self.draft = builder.build(check_sources=False)
                finally:
                    builder.deleteLater()
                self.saved_plan = None
                self.show_plan(self.draft)
                self.plan_notice.setText(f"Loaded old {plan['mode']} v{plan['version']} as a refreshed Final draft. "
                    f"{len(plan_review_groups(self.draft))} entries need review. Edit the draft directly above. Original version retained.")
            else:
                self.saved_plan, self.draft = plan, None
                self.show_plan(plan)
                if not source_matches(plan,self.source):
                    self.plan_notice.setText("Saved snapshot loaded; Cargo sources differ. Choose Edit plan to use current data and save a new version.")
        except Exception as exc:
            self.show_error(exc)

    def copy_complete(self):
        if not self._action_prepared:return self.prepare_action(self.copy_complete)
        try:
            if self.live_builder is not None:
                self.plan_views.setCurrentWidget(self.live_builder)
                return
            plan = self.draft or self.saved_plan or self.selected_version()
            if plan is None:
                return self.load_version()
            builder = CrewPlanBuilder(self, base_plan=plan)
            try:
                self.draft = builder.build(check_sources=False)
            finally:
                builder.deleteLater()
            self.saved_plan = None
            self.show_plan(self.draft)
        except Exception as exc:
            self.show_error(exc)

    def export(self):
        if not self._action_prepared:return self.prepare_action(self.export)
        if self.view_state.export_state=='writing':return
        if self.live_builder is not None:
            try:
                self.draft = self.live_builder.build(check_sources=False)
            except Exception as exc:
                return self.show_error(exc)
        current=self.draft or self.saved_plan
        if current is None:return self.show_error('Generate or load a final berthing plan before exporting.')
        if current.get('issues'):return self.show_error('Resolve review issues for formal export, or use Save draft to keep your work.')
        default=f"{current['date'].replace('-','')}_Fleet Personnel Transfer Plan.xlsx"
        path,_=QFileDialog.getSaveFileName(self,'Export berthing plan',str(self.service.path.parent/default),'Excel workbook (*.xlsx)')
        if not path:return
        try:workspace_files.check_output(Path(path),str(self.service.path),source_references=(current.get('source_path'),))
        except Exception as exc:return self.show_error(exc)
        def output(plan):
            self.view_state.export_state='writing';self._update_plan_actions()
            self.notice.setText('Exporting Excel…')
            self.run_read(lambda:export_plan(copy.deepcopy(plan),path),lambda value:self.notice.setText('Excel exported: '+str(value)),channel='export',label='Exporting Excel',error_context='Plan version remains saved. Excel export failed: ')
        if self.draft is not None and self.draft.get("id") is None:
            try:
                def saved(value):
                    self.saved_plan=value
                    self.draft=dict(value)
                    self.refresh_versions(value['id'])
                    self.show_plan(value)
                    self.view_state.dirty=False;self._update_plan_actions()
                    output(value)
                self.run_write('save_berth',(copy.deepcopy(self.draft),True,self.draft.get('family_id')),saved)
                return
            except Exception as exc:
                return self.show_error(exc)
        if self.saved_plan is None:
            return self.show_error("Generate or load a final berthing plan before exporting.")
        output(self.saved_plan)

    def open_settings(self):
        if not self._action_prepared:return self.prepare_action(self.open_settings)
        dialog = NativeDialog(self)
        dialog.setWindowTitle("Personnel and plan settings")
        dialog.resize(680, 460)
        root, form = QVBoxLayout(dialog), QFormLayout()
        settings = self.read_model.settings()
        shared_source = self.source
        port = QLineEdit(self.read_model.port_name(shared_source))
        port.setMaxLength(120)
        port.setAccessibleName("Shared port name")
        transfer = QLineEdit(settings.get("transfer_vessel_name", ""))
        transfer.setPlaceholderText("Blank uses MarineOps's transfer vessel setting")
        database = QLineEdit(str(self.service.path.parent))
        backup = QLineEdit(settings.get("backup_directory", str(self.service.path.parent / "Personnel Backups")))
        form.addRow("Port name *", port)
        form.addRow("Plan transfer vessel", transfer)
        for label, field in (("Personnel database folder", database), ("Personnel backup folder", backup)):
            field.setReadOnly(True)
            row = QHBoxLayout()
            row.addWidget(field)
            def choose(checked=False, current=field):
                chosen = QFileDialog.getExistingDirectory(dialog, "Choose folder", current.text())
                if chosen:
                    current.setText(chosen)
            row.addWidget(button("Choose…", choose))
            form.addRow(label, row)
        root.addLayout(form)
        note = QLabel("Port name is shared with Cargo Settings and updates the same port in both pages. Personnel backups cover personnel and plans only. Saved plan versions keep their original Port name.")
        note.setWordWrap(True)
        root.addWidget(note)
        actions = QHBoxLayout()
        def backup_now():
            path, _ = QFileDialog.getSaveFileName(dialog, "Backup personnel and plans", str(Path(backup.text()) / f"personnel-{date.today():%Y%m%d}.sqlite3"), "Personnel database (*.sqlite3)")
            if path:
                try:
                    self.run_write('backup',(path,),lambda value:message(dialog,'Personnel backup saved',value),dialog)
                except Exception as exc:
                    message(dialog, "Backup failed", exc, True)
        def restore_now():
            path, _ = QFileDialog.getOpenFileName(dialog, "Restore personnel backup", backup.text(), "Personnel database (*.sqlite3)")
            if path:
                try:
                    def inspected(info):
                        if confirm(dialog,'Restore personnel and plans',f"Personnel backup · {info['crew_entries']} crew entries · {info['plan_versions']} plan versions\n"
                                   f"Backup time: {info['modified']}\nReplace personnel and plans? A safety copy will be retained."):
                            def restored(safety):
                                self.invalidate_plan('Personnel restored. Generate a fresh plan with the restored crew list.')
                                port.setText(self.read_model.port_name(self.source))
                                transfer.setText(self.read_model.settings().get('transfer_vessel_name',''))
                                self.refresh_plans()
                                self.refresh_versions()
                                self.refresh_source()
                                message(dialog,'Personnel restored',f'Safety copy: {safety}')
                            self.run_write('restore',(path,),restored,dialog)
                    self.run_write('inspect_backup',(path,),inspected,dialog)
                except Exception as exc:
                    message(dialog, "Restore failed", exc, True)
        actions.addWidget(button("Backup personnel & plans", backup_now))
        actions.addWidget(button("Restore personnel backup", restore_now))
        root.addLayout(actions)
        def save():
            try:
                if not port.text().strip():
                    raise PersonnelError("Port name is required.")
                target = Path(database.text()) / "personnel-transfer.sqlite3"
                relocating=target.resolve()!=self.service.path.resolve()
                if relocating:
                    workspace_files.check_output(target)
                    if target.exists():raise PersonnelError('Choose a folder without an existing personnel database.')
                if len(transfer.text().strip())>1000 or len(backup.text().strip())>1000:
                    raise PersonnelError('Setting value is too long.')
                def saved(value=None):
                    self.refresh_source()
                    dialog.accept()
                def updated(value):
                    if settings.get('transfer_vessel_name', '').strip() != transfer.text().strip():
                        self.invalidate_plan('Plan transfer vessel changed. Generate a fresh plan using the new From matching rule.')
                    if relocating:
                        def moved(path):
                            self.invalidate_plan('Personnel storage changed. Generate a fresh plan.')
                            if not __import__('os').environ.get('CARGO_TRACK_DATA_DIR'):
                                QSettings().setValue('personnel/database_directory',str(Path(path).parent))
                            self.refresh_plans()
                            self.refresh_versions()
                            saved()
                        self.run_write('relocate',(target,),moved,dialog)
                    else:saved()
                def save_personnel():
                    self.run_write('update_settings',({'transfer_vessel_name':transfer.text(),'backup_directory':backup.text()},),updated,dialog)
                if port.text().strip() != self.read_model.port_name(self.source):
                    if self.host._busy:
                        raise PersonnelError("Wait for Cargo to finish saving before changing the port name.")
                    self.host._submit("set_setting", {"key":"port_name", "value":port.text().strip()}, "Shared port name saved.", on_success=save_personnel)
                else:
                    save_personnel()
            except Exception as exc:
                message(dialog, "Settings not saved", exc, True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)
        dialog.exec()

    def shutdown(self):
        self._closed = True
        QThreadPool.globalInstance().waitForDone(10000)
        self.service.close()
