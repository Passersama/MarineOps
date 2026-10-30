"""Reviewable background planning and atomic adoption in the existing crew editor."""
from __future__ import annotations

import copy
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QCheckBox, QListWidget,
                              QListWidgetItem, QDialogButtonBox, QPushButton, QTextBrowser)

from .berth_optimizer import make_problem, solve, materialize
from .berth_optimization_validation import validate_route
from .berth_plan import task_key, plan_assignments
from .personnel_cargo import read_cargo, dependency_spec, dependency_hash
from .personnel_import import PersonnelError, digest
from .dialogs import GlassDialog


class PlanningSignals(QObject):
    done = Signal(object)
    progress = Signal(object)


class PlanningJob(QRunnable):
    def __init__(self, problem):
        super().__init__();self.problem = problem;self.cancelled = Event();self.signals = PlanningSignals()

    def run(self):
        try:
            result = solve(self.problem, cancelled=self.cancelled.is_set, progress=self.signals.progress.emit)
        except Exception as exc:
            result = {'status': 'INPUT_INVALID', 'errors': [str(exc)]}
        self.signals.done.emit(result)


def editor_snapshot(builder):
    return {'route': copy.deepcopy(builder.route_snapshot()['stops']),
            'selections': copy.deepcopy(builder.selection_overrides),
            'controls': {task_key(t): {'checked': c.isChecked(), 'assignment': copy.deepcopy(a.currentData())}
                         for t, c, a in zip(builder.tasks, builder.includes, builder.assignments)},
            'materials': copy.deepcopy(builder.materials), 'comments': copy.deepcopy(builder.stop_comments),
            'local_edits': copy.deepcopy(builder.local_edits), 'override_bases': copy.deepcopy(builder.override_bases),
            'material_assignments': copy.deepcopy(builder.optimized_material_assignments),
            'contract': copy.deepcopy(builder.transport_contract), 'optimization': copy.deepcopy(builder.optimization)}


def restore_editor(builder, state):
    builder._applying_optimization = True
    try:
        builder.transport_contract = copy.deepcopy(state['contract']);builder.optimization = copy.deepcopy(state['optimization'])
        builder.selection_overrides = copy.deepcopy(state['selections']);builder.materials = copy.deepcopy(state['materials'])
        builder.stop_comments = copy.deepcopy(state['comments']);builder.local_edits = copy.deepcopy(state['local_edits'])
        builder.override_bases = copy.deepcopy(state['override_bases'])
        builder.optimized_material_assignments=copy.deepcopy(state['material_assignments'])
        builder.route.clear()
        for stop in state['route']:builder.append_stop(copy.deepcopy(stop))
        builder.refresh_assignments()
        for task, control, assignment in zip(builder.tasks, builder.includes, builder.assignments):
            value = state['controls'].get(task_key(task))
            if value:
                control.blockSignals(True);control.setChecked(value['checked']);control.blockSignals(False)
                assignment.blockSignals(True)
                if value['assignment'] is not None:builder._retain_assignment(assignment, value['assignment'])
                assignment.blockSignals(False)
        builder.sync_endpoints();builder.route.reflow()
    finally:builder._applying_optimization = False
    builder.changed(preserve_optimization=True)


class OptimizationDialog(GlassDialog):
    def __init__(self, builder):
        super().__init__(builder);self.builder = builder;self.job = None;self.result = None;self.problem = None
        self.accepted_result = None;self.revision = builder.editor_revision
        self.source = copy.deepcopy(builder.source);self.context = copy.deepcopy(builder.personnel_context)
        self.original = editor_snapshot(builder)
        self.setWindowTitle('Automatic berthing plan');self.resize(780, 650)
        layout = QVBoxLayout(self)
        info = QLabel('Complete every included passenger leg and selected material transfer. Each actual vessel call counts once, including return visits. Port calls break ties.');info.setWordWrap(True);layout.addWidget(info)
        self.keep = QCheckBox('Keep manually added / retained calls in their current relative order');self.keep.setChecked(True);layout.addWidget(self.keep)
        self.lock = QCheckBox('Keep current passenger and material pickup / drop assignments');layout.addWidget(self.lock)
        excluded = {k for k, v in builder.selection_overrides.items() if v is False}
        people = [t for t in builder.crew if task_key(t) not in excluded]
        layout.addWidget(QLabel(f'{len(people)} passenger legs included / {len(builder.crew) - len(people)} explicitly excluded. Unavailable entries are included for repair.'))
        layout.addWidget(QLabel('Materials for this trip (read only from Cargo):'))
        self.materials = QListWidget();self.materials.setMaximumHeight(140);layout.addWidget(self.materials)
        chosen = {task_key(t) for t in builder.materials}
        if not builder.inline:
            chosen.update(task_key(t) for t, c in zip(builder.tasks, builder.includes) if t['kind'] == 'Materials' and c.isChecked())
        for task in builder.all_tasks:
            if task['kind'] != 'Materials':continue
            item = QListWidgetItem(f"{task['name']} / {task['from_name']} → {task['to_name']} / {task['status']}")
            item.setData(Qt.ItemDataRole.UserRole, copy.deepcopy(task));item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if task_key(task) in chosen else Qt.CheckState.Unchecked);self.materials.addItem(item)
        self.calculate = QPushButton('Calculate complete route');self.calculate.clicked.connect(self.start);layout.addWidget(self.calculate)
        self.notice = QLabel('Model: one transfer vessel, sufficient capacity, no time windows. Sign-on boards at a real Port call; Sign-off reaches Port after vessel pickup.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.preview = QTextBrowser();layout.addWidget(self.preview, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Use this route');self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.use_result);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.keep.toggled.connect(self.invalidate);self.lock.toggled.connect(self.invalidate);self.materials.itemChanged.connect(self.invalidate)
        self.finished.connect(self.cancel)

    def cancel(self, *_):
        if self.job:self.job.cancelled.set()

    def invalidate(self, *_):
        self.cancel();self.result = None;self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.preview.clear();self.notice.setText('Options changed. Calculate again to review the route.')

    def start(self):
        if not self.builder.owner._action_prepared:return self.builder.owner.prepare_action(self.start)
        if self.job:return
        builder = self.builder
        try:
            builder.owner.read_model.assert_context(self.context)
            if builder.editor_revision != self.revision:raise PersonnelError('The editor changed. Reopen automatic planning.')
            materials = [self.materials.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.materials.count())
                         if self.materials.item(i).checkState() == Qt.CheckState.Checked]
            self.dependencies = dependency_spec(self.source, builder.crew, [int(t['id']) for t in materials])
            live = builder.owner.source
            if dependency_hash(live, self.dependencies) != dependency_hash(self.source, self.dependencies):
                raise PersonnelError('Cargo changed. Refresh the plan editor before calculating.')
            excluded = {k for k, v in builder.selection_overrides.items() if v is False}
            locked = {}
            if self.lock.isChecked():
                locked.update({task_key(t): copy.deepcopy(a.currentData()) for t, c, a in zip(builder.tasks, builder.includes, builder.assignments)
                               if c.isChecked() and a.currentData() is not None and task_key(t) not in excluded})
                if builder.inline and builder.base_plan:
                    mat_keys = {task_key(t) for t in materials}
                    locked.update({k: v for k, v in plan_assignments(builder.base_plan).items() if k in mat_keys})
            needed_pins = {visit for a in locked.values() for visit in a.values() if visit is not None}
            route = self.original['route']
            pins = [s for s in route if s['id'] in needed_pins or (self.keep.isChecked() and s.get('optimizer_keep'))]
            self.problem = make_problem(self.source, builder.crew, materials, excluded=excluded, pins=pins, locked=locked,
                                        reference_order=[s['vessel_id'] for s in route])
            self.chosen_materials = materials
            self.calculate.setEnabled(False);self.keep.setEnabled(False);self.lock.setEnabled(False);self.materials.setEnabled(False)
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False);self.notice.setText('Calculating… Cancel keeps the existing draft.')
            self.job = PlanningJob(self.problem);self.job.signals.done.connect(self.finished_calculation)
            self.job.signals.progress.connect(self.show_progress);QThreadPool.globalInstance().start(self.job)
        except Exception as exc:self.notice.setText(str(exc))

    def show_progress(self, value):
        self.notice.setText(f"Calculating… {value['expanded_states']} states checked / {value['elapsed_ms'] / 1000:.1f}s")

    def finished_calculation(self, result):
        self.job = None;self.calculate.setEnabled(True);self.keep.setEnabled(True);self.lock.setEnabled(True);self.materials.setEnabled(True)
        if not self.isVisible():return
        self.result = result
        if result['status'] not in {'OPTIMAL', 'FEASIBLE'}:
            descriptions={'INPUT_INVALID':'Inputs need review','NO_SOLUTION_YET':'Calculation limit reached',
                          'INFEASIBLE_PROVEN':'Retained conditions cannot complete all transfers','CANCELLED':'Calculation cancelled'}
            self.notice.setText(descriptions.get(result['status'],'Planning needs review') + ': ' + '; '.join(result.get('errors', [])));return
        stops, assignments = materialize(result, self.source, self.original['route'])
        check = validate_route(self.problem, stops, assignments)
        if not check['valid']:
            self.notice.setText('The candidate failed independent validation: ' + '; '.join(check['errors']));return
        self.applied_stops, self.applied_assignments = stops, assignments
        old = self.original['route'];shore = self.problem['shore_id']
        before = (sum(s['vessel_id'] != shore for s in old), sum(s['vessel_id'] == shore for s in old))
        names = {r['id']: r['name'] for r in self.source['locations']}
        lines = [f"Current: {before[0]} vessel calls / {before[1]} port calls",
                 f"Recommended: {check['cost'][0]} vessel calls / {check['cost'][1]} port calls",
                 f"All {check['required']} selected transport legs have pickup / delivery assignments.",
                 'Proven minimum under the displayed model and retained conditions.' if result['status'] == 'OPTIMAL' else
                 f"Complete candidate; minimum not proven. Lower bound: {result['lower_bound']}.", '', 'Recommended calls:']
        for i, stop in enumerate(stops):
            picks = sum(a['pick'] == stop['id'] for a in assignments.values());drops = sum(a['drop'] == stop['id'] for a in assignments.values())
            repeat = ' / leave and return for a separate call' if i and stops[i - 1]['vessel_id'] == stop['vessel_id'] else ''
            lines.append(f"{i + 1}. {names[stop['vessel_id']]} / pick up {picks}, drop {drops}{repeat}")
        removed = [s['vessel_name_snapshot'] + (' / comment: ' + self.original['comments'][s['id']] if self.original['comments'].get(s['id']) else '')
                   for s in old if s['id'] not in {v['id'] for v in stops}]
        lines += ['', 'Removed calls: ' + (', '.join(removed) or 'None'),
                  'Changed assignments: ' + str(sum(self.original['controls'].get(k, {}).get('assignment') != a for k, a in assignments.items()))]
        self.preview.setPlainText('\n'.join(lines));self.notice.setText('Minimum calls proved' if result['status']=='OPTIMAL' else 'Complete candidate / minimum not proved');self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def use_result(self):
        if not self.builder.owner._action_prepared:return self.builder.owner.prepare_action(self.use_result)
        try:
            builder = self.builder;builder.owner.read_model.assert_context(self.context)
            if builder.editor_revision != self.revision:raise PersonnelError('The editor changed. Recalculate.')
            live = builder.owner.source
            if dependency_hash(live, self.dependencies) != dependency_hash(self.source, self.dependencies):
                raise PersonnelError('Cargo changed. Refresh and recalculate.')
            check = validate_route(self.problem, self.applied_stops, self.applied_assignments)
            if not check['valid']:raise PersonnelError('; '.join(check['errors']))
            self.accepted_result = (self.problem, self.result, self.applied_stops, self.applied_assignments, self.chosen_materials)
            self.accept()
        except Exception as exc:
            self.notice.setText(str(exc));self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)


def apply_result(builder, original, accepted):
    problem, result, stops, assignments, materials = accepted
    state = copy.deepcopy(original);state['route'] = stops;state['materials'] = materials;state['contract'] = problem
    chosen={task_key(t) for t in materials}
    for task in builder.all_tasks:
        key=task_key(task)
        if task['kind']=='Materials' and key not in chosen:
            state['selections'][key]=False
            state['controls'][key]={'checked':False,'assignment':None}
    state['material_assignments']={k:copy.deepcopy(a) for k,a in assignments.items() if k.startswith('Materials:')}
    for task in problem['tasks']:
        state['selections'][task['key']] = True
        state['controls'][task['key']] = {'checked': True, 'assignment': assignments[task['key']]}
    state['optimization'] = {k: copy.deepcopy(result[k]) for k in ('status', 'problem_hash', 'cost', 'lower_bound', 'expanded_states', 'elapsed_ms')}
    state['optimization']['route_assignment_hash'] = digest({'stops': stops, 'assignments': assignments})
    for i,stop in enumerate(stops):
        if i and stop['vessel_id']==stops[i-1]['vessel_id']:
            note='Separate call: depart and return before picking up the next leg.'
            existing=state['comments'].get(stop['id'],'')
            if note not in existing:state['comments'][stop['id']]=(existing+'\n'+note).strip()
    try:
        restore_editor(builder, state)
        builder._optimization_undo = original;builder._optimization_undo_revision = builder.editor_revision
        builder.undo_optimization_button.setEnabled(True)
        builder.optimization_notice.setText(('Minimum proved' if result['status']=='OPTIMAL' else 'Minimum not proved')+f" / {result['cost'][0]} vessel calls / {result['cost'][1]} port calls")
    except Exception:
        restore_editor(builder, original);raise
