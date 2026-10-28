"""Native Dashboard with read-only data, exact-visit crew and a full-list drawer."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, QThreadPool, QTimer, Qt, QRectF, QSize, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QFrame, QHeaderView, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QTabBar, QTableView, QToolButton, QVBoxLayout, QWidget)
from PySide6.QtCore import QSortFilterProxyModel, QSettings

from .appearance import application_font_size, configure_application, is_dark_mode
from .dashboard_data import read_dashboard
from .coordination import workspace_files
from .models import StatusDelegate
from .navigation import WorkspaceNavigation, ElidedLabel
from .route_layout import RouteLayout
from .theme_tokens import colors, render_style


STYLE = '''
QWidget#dashboardPage {background:@window@;}
QLabel#dashboardTitle {font-size:25pt;font-weight:600;}
QLabel#dashboardStation {font-size:__SHIP__pt;font-weight:600;}
QLabel#dashboardMetric {font-size:__METRIC__pt;font-weight:600;}
QLabel#dashboardCrewMetric {font-size:18pt;font-weight:600;}
QLabel#dashboardCurrent {color:@selection_text@;font-size:12pt;font-weight:600;}
QLabel#dashboardMuted {color:@muted@;}
QLabel#dashboardHeading {font-size:13pt;font-weight:600;}
QLabel#dashboardNotice {color:@muted@;padding:3px;}
QFrame#dashboardDivider {background:@divider@;max-width:1px;}
QTableView#dashboardTable {border:0;border-radius:0;}
QTableView#dashboardTable::item {border-bottom:1px solid @divider@;padding:4px;}
QTabBar#dashboardCrewTabs {background:@surface@;border:1px solid @border@;border-radius:6px;}
QTabBar#dashboardCrewTabs::tab {margin:0;padding:5px 10px;}
QTabBar#dashboardCrewTabs::tab:selected {background:@selection@;color:@selection_text@;}
QPushButton#dashboardLink {color:@selection_text@;background:transparent;border:0;padding:3px 7px;}
QFrame#dashboardDrawer {background:@surface@;border:1px solid @divider@;border-radius:12px;}
QFrame#dashboardShade {background:rgba(15,25,42,80);}
QPushButton#dashboardTheme:checked {background:@selection@;color:@selection_text@;border-color:@focus@;}
'''


def label(text='', name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if name:widget.setObjectName(name)
    return widget


def button(text, callback, name=None):
    widget = QPushButton(text)
    if name:widget.setObjectName(name)
    widget.clicked.connect(callback)
    return widget


def surface():
    widget = QFrame();widget.setObjectName('surface')
    return widget


class TableModel(QAbstractTableModel):
    def __init__(self, columns, parent=None):
        super().__init__(parent);self.columns=columns;self.rows=[]
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.columns)
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:return self.columns[section][0]
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.rows):return None
        row=self.rows[index.row()];value=str(row.get(self.columns[index.column()][1],'') or '')
        if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.ToolTipRole):return value
        if role==Qt.ItemDataRole.UserRole:return row
        if role==Qt.ItemDataRole.AccessibleTextRole:return self.columns[index.column()][0]+': '+value
    def replace(self,rows):
        self.beginResetModel();self.rows=list(rows);self.endResetModel()


class CrewProxy(QSortFilterProxyModel):
    def __init__(self,parent=None):
        super().__init__(parent);self.movement='All';self.query='';self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    def set_scope(self,movement,query=''):
        self.movement=movement;self.query=query.casefold().strip();self.invalidateFilter()
    def filterAcceptsRow(self,row,parent):
        value=self.sourceModel().rows[row]
        return (self.movement=='All' or value['movement']==self.movement) and self.query in (value['name']+' '+value['position']).casefold()


def table(model):
    view=QTableView();view.setObjectName('dashboardTable');view.setModel(model)
    view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers);view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QTableView.SelectionMode.SingleSelection);view.setShowGrid(False);view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(32);view.horizontalHeader().setStretchLastSection(True)
    view.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
    return view


class Donut(QWidget):
    def __init__(self,parent=None,segments=None,caption='total'):
        super().__init__(parent);self.counts={};self.available=True;self.caption=caption
        self.segments=segments or (('Waiting','#FFC356'),('On Board','#1789F6'),('Done','#32A44D'))
        self.setFixedSize(132,132);self.setAccessibleName('Cargo voyage status distribution')
    def set_counts(self,counts):
        self.available=counts is not None;self.counts=counts or {};self.setAccessibleDescription(', '.join(f'{k}: {v}' for k,v in self.counts.items()) if self.available else 'Select a current visit and a valid saved personnel plan.');self.update()
    def paintEvent(self,event):
        tokens=colors(is_dark_mode());p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total=sum(self.counts.values());rect=QRectF(12,12,108,108);angle=90*16
        for status,color in self.segments:
            span=round(360*16*self.counts.get(status,0)/total) if total else 0
            p.setPen(QPen(QColor(color),22));p.drawArc(rect,angle,-span);angle-=span
        if not total:p.setPen(QPen(QColor(tokens['divider']),22));p.drawArc(rect,0,360*16)
        p.setPen(QColor(tokens['text']));font=p.font();font.setPointSize(18);font.setBold(True);p.setFont(font)
        p.drawText(QRectF(20,39,92,30),Qt.AlignmentFlag.AlignCenter,str(total) if self.available else '-');font.setPointSize(10);font.setBold(False);p.setFont(font)
        p.drawText(QRectF(20,69,92,25),Qt.AlignmentFlag.AlignCenter,self.caption);p.end()


class VisitButton(QToolButton):
    def __init__(self,number,name,total,parent=None):
        super().__init__(parent);self.number=number;self.name=name;self.total=total;self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
        self.setText(f'{number} / {name}');self.setToolTip(self.text()+'\nClick to select; click again to clear the current visit.')
        self.setAccessibleName(f'Visit {number}: {name}')
    def presentation(self,available):
        columns=min(7,max(1,available//150));width=max(100,(available-8*(columns-1))//columns)
        metrics=self.fontMetrics();bounds=metrics.boundingRect(0,0,width-12,400,Qt.TextFlag.TextWordWrap,self.name)
        return QSize(width,54+bounds.height()+metrics.lineSpacing()),self.text()
    def paintEvent(self,event):
        t=colors(is_dark_mode());p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked() or self.underMouse():
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(t['selection'] if self.isChecked() else t['hover']));p.drawRoundedRect(self.rect(),8,8)
        center=self.width()/2;circle=QRectF(center-16,8,32,32)
        p.setPen(QPen(QColor(t['focus'] if self.isChecked() else t['border']),1));p.setBrush(QColor(t['primary'] if self.isChecked() else t['surface']));p.drawEllipse(circle)
        p.setPen(QColor(t['primary_text'] if self.isChecked() else t['text']));p.drawText(circle,Qt.AlignmentFlag.AlignCenter,str(self.number))
        p.setPen(QColor(t['selection_text'] if self.isChecked() else t['text']))
        p.drawText(self.rect().adjusted(6,46,-6,-self.fontMetrics().lineSpacing()-4),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop|Qt.TextFlag.TextWordWrap,self.name)
        if self.isChecked():p.drawText(self.rect().adjusted(4,self.height()-self.fontMetrics().lineSpacing()-4,-4,-2),Qt.AlignmentFlag.AlignCenter,'Current stop')
        if self.hasFocus():p.setPen(QPen(QColor(t['focus']),2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),8,8)
        p.end()


class JobSignals(QObject):
    done=Signal(object);failed=Signal(str)


class ReadJob(QRunnable):
    def __init__(self,function):
        super().__init__();self.function=function;self.signals=JobSignals()
    def run(self):
        try:self.signals.done.emit(self.function())
        except Exception as exc:self.signals.failed.emit(str(exc))


class DashboardPage(QWidget):
    def __init__(self,host):
        super().__init__(host);self.host=host;self.setObjectName('dashboardPage');self.data=None
        self._closed=False;self._jobs=[];self._sequence=0;self._selected_version=None;self._sync_attempt=None
        self._version_explicit=False
        self._selected_plan_visit=None
        self._plan_visit_scope=None
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True);self.refresh_timer.setInterval(80);self.refresh_timer.timeout.connect(self.refresh)
        self._build();self.apply_theme()
        action=QAction(self);action.setShortcut(QKeySequence('F5'));action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);action.triggered.connect(self.refresh_from_source);self.addAction(action)
        escape=QAction(self);escape.setShortcut(QKeySequence('Esc'));escape.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);escape.triggered.connect(self.close_drawer);self.addAction(escape)
        help_action=QAction(self);help_action.setShortcut(QKeySequence('F1'));help_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);help_action.triggered.connect(lambda:self.host.open_help('dashboard'));self.addAction(help_action)
    def _build(self):
        root=QVBoxLayout(self);root.setContentsMargins(16,10,16,6);root.setSpacing(10)
        header=QHBoxLayout();self.navigation=WorkspaceNavigation('dashboard',self);header.addWidget(self.navigation)
        self.navigation.cargo_button.clicked.connect(self.host.show_cargo);self.navigation.personnel_button.clicked.connect(self.host.open_personnel)
        self.today=ElidedLabel();self.today.setObjectName('dashboardMuted')
        self.today.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        self.today.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);header.addWidget(self.today,1)
        self.light=button('Light',lambda:self.choose_theme('light'),'dashboardTheme');self.dark=button('Dark',lambda:self.choose_theme('dark'),'dashboardTheme')
        themes=QButtonGroup(self)
        for value in (self.light,self.dark):value.setCheckable(True);themes.addButton(value);header.addWidget(value)
        header.addWidget(button('Settings',self.host.open_settings))
        self.navigation.layout().removeWidget(self.navigation.about_button)
        header.addWidget(self.navigation.about_button)
        self.navigation.setMinimumWidth(self.navigation.sizeHint().width());root.addLayout(header)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);root.addWidget(self.scroll,1)
        self.content=QWidget();self.scroll.setWidget(self.content);body=QVBoxLayout(self.content);body.setContentsMargins(0,0,0,0);body.setSpacing(12)
        self.hero=surface();hero=QVBoxLayout(self.hero);hero.setContentsMargins(24,20,24,16);hero.setSpacing(15)
        title=QHBoxLayout();title.addWidget(label('Overview','dashboardTitle'));title.addSpacing(24);title.addWidget(label('Voyage','dashboardMuted'))
        self.voyage=label('Loading…',wrap=True);title.addWidget(self.voyage,1);title.addWidget(button('Voyages',self._open_voyages));title.addWidget(button('Refresh',self.refresh_from_source));hero.addLayout(title)
        self.briefing=QWidget();self.brief=QHBoxLayout(self.briefing);self.brief.setContentsMargins(0,0,0,0);self.brief.setSpacing(24)
        station=QVBoxLayout();self.station=label('Loading current stop…','dashboardStation',True);station.addWidget(self.station)
        self.current=label('','dashboardCurrent',True);station.addWidget(self.current);station.addWidget(label('Manually selected. Personnel progress follows planned delivery visits.','dashboardMuted',True));station.addStretch();self.brief.addLayout(station,4)
        actions=QVBoxLayout();metrics=QHBoxLayout();self.pickups=label('0','dashboardMetric');self.deliveries=label('0','dashboardMetric')
        for metric,text in ((self.pickups,'ready to pick up'),(self.deliveries,'ready to deliver')):
            group=QVBoxLayout();metric.setAlignment(Qt.AlignmentFlag.AlignCenter);group.addWidget(metric);caption=label(text,'dashboardMuted');caption.setAlignment(Qt.AlignmentFlag.AlignCenter);group.addWidget(caption);metrics.addLayout(group)
        actions.addLayout(metrics);self.open_stop=button('Open current stop',self.open_current,'primaryButton');actions.addWidget(self.open_stop);actions.addStretch();self.brief.addLayout(actions,3)
        summary=QVBoxLayout();summary.addWidget(label('Cargo ledger summary','dashboardHeading'));self.total=label('','dashboardMuted',True);summary.addWidget(self.total)
        dist=QHBoxLayout();self.donut=Donut();dist.addWidget(self.donut);numbers=QVBoxLayout();self.status_totals={}
        for status in ('Waiting','On Board','Done'):
            count=label('0');count.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);row=QHBoxLayout();row.addWidget(label(status));row.addWidget(count);numbers.addLayout(row);self.status_totals[status]=count
        dist.addLayout(numbers,1);summary.addLayout(dist);summary.addStretch()
        summaries=QHBoxLayout();summaries.setSpacing(24);summaries.addLayout(summary,1)
        personnel_summary=QVBoxLayout();personnel_summary.addWidget(label('Personnel plan progress','dashboardHeading'))
        self.personnel_total=label('Select a current visit and saved plan.','dashboardMuted',True);personnel_summary.addWidget(self.personnel_total)
        personnel_dist=QHBoxLayout();self.personnel_donut=Donut(segments=(('Completed','#32A44D'),('Pending','#FFC356')),caption='person-times')
        self.personnel_donut.setAccessibleName('Current voyage personnel plan progress');personnel_dist.addWidget(self.personnel_donut)
        personnel_numbers=QVBoxLayout();self.personnel_status_totals={}
        for status in ('Completed','Pending'):
            count=label('-');count.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);row=QHBoxLayout();row.addWidget(label(status));row.addWidget(count);personnel_numbers.addLayout(row);self.personnel_status_totals[status]=count
        personnel_dist.addLayout(personnel_numbers,1);personnel_summary.addLayout(personnel_dist)
        self.personnel_progress_note=label('Completed = drop visit before current visit.','dashboardMuted',True);personnel_summary.addWidget(self.personnel_progress_note)
        summaries.addLayout(personnel_summary,1);hero.addWidget(self.briefing);hero.addLayout(summaries)
        self.route_content=QWidget();self.route_items=RouteLayout(self.route_content);hero.addWidget(self.route_content)
        self.route_empty=label('Select or create a voyage in Cargo to start.','dashboardMuted',True);hero.addWidget(self.route_empty);body.addWidget(self.hero)
        self.work=QWidget();self.work_layout=QHBoxLayout(self.work);self.work_layout.setContentsMargins(0,0,0,0);self.work_layout.setSpacing(12)
        self.cargo_panel=surface();c=QVBoxLayout(self.cargo_panel);c.setContentsMargins(18,16,18,16)
        line=QHBoxLayout();line.addWidget(label('Current stop cargo actions','dashboardHeading'));line.addStretch();self.cargo_all=button('View all',self.open_current,'dashboardLink');line.addWidget(self.cargo_all);c.addLayout(line)
        self.cargo_caption=label('','dashboardMuted');c.addWidget(self.cargo_caption)
        self.cargo_model=TableModel([('Cargo ID','cargo_tag'),('Description','description'),('From','from_name'),('To','to_name'),('Action','action'),('Status','status')],self)
        self.cargo_table=table(self.cargo_model);self.cargo_table.setItemDelegateForColumn(5,StatusDelegate(self.cargo_table));self.cargo_table.setMinimumHeight(210)
        self.cargo_table.doubleClicked.connect(self.open_cargo_detail)
        for col,width in enumerate((104,160,150,150,88,95)):self.cargo_table.setColumnWidth(col,width)
        c.addWidget(self.cargo_table,1);self.cargo_empty=label('','dashboardMuted',True);c.addWidget(self.cargo_empty)
        self.personnel_panel=surface();p=QVBoxLayout(self.personnel_panel);p.setContentsMargins(16,14,16,14);p.setSpacing(6)
        p.addWidget(label('Current stop personnel','dashboardHeading'));self.crew_scope=label('','dashboardMuted',True);p.addWidget(self.crew_scope)
        self.version_combo=QComboBox();self.version_combo.setAccessibleName('Saved personnel plan');self.version_combo.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.version_combo.setMinimumContentsLength(15);self.version_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.version_combo.currentIndexChanged.connect(self.select_version);p.addWidget(self.version_combo)
        self.plan_visit_combo=QComboBox();self.plan_visit_combo.setAccessibleName('Personnel plan visit at this vessel');self.plan_visit_combo.currentIndexChanged.connect(self.select_plan_visit);p.addWidget(self.plan_visit_combo);self.plan_visit_combo.hide()
        self.crew_notice=label('Loading…','dashboardNotice',True);p.addWidget(self.crew_notice)
        counts=QHBoxLayout();self.boarding=label('-','dashboardCrewMetric');self.leaving=label('-','dashboardCrewMetric')
        for metric,text in ((self.boarding,'Boarding'),(self.leaving,'Leaving')):
            column=QVBoxLayout();metric.setAlignment(Qt.AlignmentFlag.AlignCenter);column.addWidget(metric);caption=label(text);caption.setAlignment(Qt.AlignmentFlag.AlignCenter);column.addWidget(caption);counts.addLayout(column)
        p.addLayout(counts)
        self.crew_model=TableModel([('Name','name'),('Position','position'),('Movement','movement')],self)
        self.crew_proxy=CrewProxy(self);self.crew_proxy.setSourceModel(self.crew_model);self.crew_table=table(self.crew_proxy)
        crew_header=self.crew_table.horizontalHeader();crew_header.setStretchLastSection(False)
        for column in (0,1):crew_header.setSectionResizeMode(column,QHeaderView.ResizeMode.Stretch)
        crew_header.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        self.crew_table.verticalHeader().setDefaultSectionSize(29);self.crew_table.setFixedHeight(210);self.crew_table.setAccessibleName('Current visit boarding and leaving personnel roster');p.addWidget(self.crew_table)
        footer=QHBoxLayout();self.full_list=button('View full list',self.open_drawer);footer.addWidget(self.full_list,1);footer.addWidget(button('Open Personnel',self.host.open_personnel,'dashboardLink'));p.addLayout(footer)
        p.addStretch(1)
        self.personnel_panel.setMinimumWidth(355);self.cargo_panel.setMinimumWidth(0)
        self.work_layout.addWidget(self.cargo_panel,7);self.work_layout.addWidget(self.personnel_panel,3);body.addWidget(self.work);body.addStretch()
        self.notice=label('','dashboardNotice',True);root.addWidget(self.notice)
        self.overlay=QWidget(self);self.overlay.hide();self.shade=QPushButton(self.overlay);self.shade.setObjectName('dashboardShade');self.shade.setStyleSheet('background:rgba(15,25,42,80);border:0;border-radius:0;');self.shade.clicked.connect(self.close_drawer);self.shade.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.drawer=QFrame(self.overlay);self.drawer.setObjectName('dashboardDrawer');d=QVBoxLayout(self.drawer);d.setContentsMargins(24,20,24,20);d.setSpacing(12)
        header=QHBoxLayout();header.addWidget(label('Current stop personnel','dashboardHeading'),1);header.addWidget(button('Close',self.close_drawer));d.addLayout(header)
        self.drawer_scope=label('','dashboardMuted',True);d.addWidget(self.drawer_scope)
        self.drawer_totals=label('','dashboardCurrent',True);d.addWidget(self.drawer_totals)
        self.drawer_tabs=QTabBar();self.drawer_tabs.setObjectName('dashboardCrewTabs');self.drawer_tabs.setExpanding(True)
        for text in ('All','Boarding','Leaving'):self.drawer_tabs.addTab(text)
        self.drawer_tabs.currentChanged.connect(self.filter_drawer);d.addWidget(self.drawer_tabs)
        self.search=QLineEdit();self.search.setPlaceholderText('Search name or position');self.search.setAccessibleName('Search personnel name or position');d.addWidget(self.search)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(150);self.search_timer.timeout.connect(self.filter_drawer);self.search.textChanged.connect(lambda:self.search_timer.start())
        self.drawer_proxy=CrewProxy(self);self.drawer_proxy.setSourceModel(self.crew_model);self.drawer_table=table(self.drawer_proxy);self.drawer_table.setSortingEnabled(True);self.drawer_table.verticalHeader().setDefaultSectionSize(38);self.drawer_table.setAccessibleName('Full current visit personnel roster')
        self.drawer_table.setColumnWidth(0,220);self.drawer_table.setColumnWidth(1,200);d.addWidget(self.drawer_table,1)
        self.drawer_empty=label('','dashboardMuted',True);d.addWidget(self.drawer_empty);self.drawer_footer=label('','dashboardMuted');d.addWidget(self.drawer_footer)
        d.addWidget(button('Open Personnel',lambda:(self.close_drawer(),self.host.open_personnel())))
    def apply_theme(self):
        size=application_font_size();self.setStyleSheet(render_style(STYLE,is_dark_mode()).replace('__SHIP__',str(max(18,size*2))).replace('__METRIC__',str(max(20,size*2+4))))
        self.light.setChecked(not is_dark_mode());self.dark.setChecked(is_dark_mode());self.donut.update()
        for i in range(self.route_items.count()):self.route_items.itemAt(i).widget().update()
    def choose_theme(self,value):
        QSettings().setValue('appearance/theme',value);configure_application(QApplication.instance());self.apply_theme()
        if self.host.snapshot:self.host._set_snapshot(self.host.snapshot)
    def _open_voyages(self):
        if self.host.snapshot:self.host.open_voyages()
    def refresh_from_source(self):
        if not self.host._busy:self.host._refresh_table()
        self.schedule_refresh()
    def _scope(self):
        snapshot=self.host.snapshot or {}
        path=self.host.personnel_database_path()
        return (str(self.host.database_path.resolve()),snapshot.get('dataset_epoch'),snapshot.get('revision'),snapshot.get('current_voyage_id'),snapshot.get('current_stop_id'),str(path),workspace_files.generation(path),self._selected_version if self._version_explicit else None,snapshot.get('ledger_identity'),self._selected_plan_visit)
    def schedule_refresh(self):
        if self._closed:return
        snapshot=self.host.snapshot or {}
        visit_scope=(snapshot.get('current_voyage_id'),snapshot.get('current_stop_id'))
        if visit_scope!=self._plan_visit_scope:
            self._selected_plan_visit=None;self._plan_visit_scope=visit_scope
        self.apply_theme();self._sequence+=1
        self.crew_model.replace([]);self.boarding.setText('-');self.leaving.setText('-');self.full_list.setEnabled(False);self.crew_notice.setText('Loading the saved plan…')
        self.cargo_model.replace([]);self.cargo_caption.setText('Loading current cargo actions…')
        self.refresh_timer.start()
    def refresh(self):
        if self._closed or not self.host.snapshot:return
        token=self._scope();sequence=self._sequence;preferred=getattr(self.host,'personnel_page',None)
        preferred=preferred.plan_combo.currentData() if preferred is not None else None
        job=ReadJob(lambda:read_dashboard(token[0],token[5],token[7],preferred,token[9]));self._jobs.append(job)
        def done(value):
            self._jobs.remove(job)
            if self._closed or sequence!=self._sequence or token!=self._scope():return
            c=value['cargo']
            if c['revision']!=token[2] or c['current_stop_id']!=token[4] or (token[8] and c['identity']!=token[8]):
                self.notice.setText('Cargo changed while loading. Refreshing its source…')
                if self._sync_attempt!=token:self._sync_attempt=token;self.host._refresh_table()
                return
            self.data=value;self._render(value)
        def failed(error):
            self._jobs.remove(job)
            if not self._closed and sequence==self._sequence:
                self.notice.setText('Dashboard could not load: '+error+'. Use Refresh to try again.')
                self.crew_notice.setText('Personnel data unavailable. Open Personnel to review.');self.cargo_caption.setText('Cargo data unavailable. Open Cargo to review.')
        job.signals.done.connect(done);job.signals.failed.connect(failed);self.pool.start(job)
    def _render(self,value):
        c=value['cargo'];p=value['personnel'];current=c['current_stop']
        zone=c['settings'].get('business_timezone','Asia/Riyadh');self.today.setText(datetime.now(ZoneInfo(zone)).strftime('%d %b %Y')+' / '+zone)
        self.voyage.setText(c['voyage_name'] or 'No active voyage')
        self.station.setText(current['vessel_name_snapshot'] if current else 'Select a current stop')
        number=next((i for i,s in enumerate(c['stops'],1) if s['id']==c['current_stop_id']),0)
        self.current.setText(f'Current stop / Visit {number} of {len(c["stops"])}' if current else 'No current visit selected')
        self.pickups.setText(str(c['pickups']));self.deliveries.setText(str(c['deliveries']));self.open_stop.setEnabled(bool(current));self.cargo_all.setEnabled(bool(current))
        self.total.setText(f'{c["total"]} transfer records / current voyage');self.donut.set_counts(c['counts'])
        for status,count in self.status_totals.items():count.setText(str(c['counts'][status]))
        progress=p.get('progress');self.personnel_donut.set_counts(progress)
        for status,count in self.personnel_status_totals.items():count.setText(str(progress[status]) if progress is not None else '-')
        self.personnel_total.setText(f'{sum(progress.values())} person-times / current voyage' if progress is not None else 'Select a current visit and valid saved plan.')
        self.personnel_total.setToolTip(p.get('list_name','')+' / '+p.get('plan_label',''))
        self.personnel_progress_note.setText('Plan-based: drop visits before the current visit count as completed.' if progress is not None else p['message'])
        while self.route_items.count():
            widget=self.route_items.takeAt(0).widget();widget.hide();widget.deleteLater()
        for i,stop in enumerate(c['stops'],1):
            widget=VisitButton(i,stop['vessel_name_snapshot'],len(c['stops']));widget.setChecked(stop['id']==c['current_stop_id']);widget.clicked.connect(lambda checked=False,identifier=stop['id']:self.host._toggle_stop_id(identifier));self.route_items.addWidget(widget)
        self.route_empty.setVisible(not bool(c['stops']));self.route_content.setVisible(bool(c['stops']));self.route_items.invalidate();self.route_content.updateGeometry()
        self.cargo_model.replace(c['cargo_rows']);amount=c['pickups']+c['deliveries'];self.cargo_caption.setText(f'{amount} current actions'+(' / preview limited to 200 records; View all in Cargo' if amount>200 else ''))
        self.cargo_empty.setText('No ready cargo actions at this visit.' if not amount else '');self.cargo_empty.setVisible(not bool(amount))
        self.version_combo.blockSignals(True);self.version_combo.clear()
        if p['choices']:self.version_combo.addItem('Latest saved plan (automatic)',None)
        for choice in p['choices']:self.version_combo.addItem(choice['label'],choice['id'])
        if not p['choices']:self.version_combo.addItem('No saved plan for this voyage',None)
        self.version_combo.setCurrentIndex(max(0,self.version_combo.findData(p['selected_id'])) if self._version_explicit else 0);self.version_combo.setEnabled(bool(p['choices']));self.version_combo.blockSignals(False)
        self._selected_version=p['selected_id'];self.version_combo.setToolTip(self.version_combo.currentText())
        self.plan_visit_combo.blockSignals(True);self.plan_visit_combo.clear()
        choices=p.get('visit_choices',[])
        if p.get('visit_id') is None:self.plan_visit_combo.addItem('Choose the actual plan visit',None)
        for choice in choices:self.plan_visit_combo.addItem(choice['label'],choice['id'])
        self.plan_visit_combo.setCurrentIndex(max(0,self.plan_visit_combo.findData(p.get('visit_id'))));self.plan_visit_combo.setVisible(len(choices)>1)
        self.plan_visit_combo.blockSignals(False)
        self.crew_scope.setText(current['vessel_name_snapshot']+f' / Visit {number} / Planned' if current else 'No current visit selected')
        self.crew_scope.setToolTip((p['list_name']+' / '+p['plan_label']) if p['list_name'] else 'No saved personnel plan')
        self.boarding.setText(str(p['boarding']) if p['boarding'] is not None else '-');self.leaving.setText(str(p['leaving']) if p['leaving'] is not None else '-')
        self.crew_model.replace(p['rows']);self.crew_table.scrollToTop();self.crew_notice.setText(p['message']);self.full_list.setEnabled(p['status']=='ready')
        self.crew_table.setVisible(p['status']=='ready')
        self.drawer_scope.setText(self.crew_scope.text());self.drawer_totals.setText(f'{p["boarding"] or 0} Boarding / {p["leaving"] or 0} Leaving')
        for i,key in enumerate(('All','Boarding','Leaving')):self.drawer_tabs.setTabText(i,f'{key} ({len(p["rows"]) if i==0 else p[key.lower()] or 0})')
        self.filter_drawer();self.notice.setText('Local data / counts are planned personnel at the exact selected visit.')
        if p['status']!='ready':self.close_drawer()
        self._adapt()
    def select_version(self,index):
        identifier=self.version_combo.currentData()
        explicit=identifier is not None
        if explicit!=self._version_explicit or identifier!=self._selected_version:
            self._version_explicit=explicit;self._selected_version=identifier;self._selected_plan_visit=None;self.schedule_refresh()
    def select_plan_visit(self,index):
        self._selected_plan_visit=self.plan_visit_combo.currentData();self.schedule_refresh()
    def filter_drawer(self,*_):
        self.drawer_proxy.set_scope(('All','Boarding','Leaving')[max(0,self.drawer_tabs.currentIndex())],self.search.text())
        self.drawer_footer.setText(f'{self.drawer_proxy.rowCount()} matching people / counts apply to this visit only')
        self.drawer_empty.setText('No people match this search.' if not self.drawer_proxy.rowCount() else '');self.drawer_empty.setVisible(not bool(self.drawer_proxy.rowCount()))
    def open_current(self):
        if self.host._busy or not self.host.snapshot or self.host.snapshot['current_stop_id'] is None:return
        if self.host.show_cargo():self.host.view_current_all()
    def open_cargo_detail(self,index):
        if self.host._busy:return
        row=self.cargo_model.rows[index.row()]
        if self.host.show_cargo():self.host.open_detail(row['no'])
    def open_drawer(self):
        if not self.data or self.data['personnel']['status']!='ready':return
        self.drawer_tabs.setCurrentIndex(0);self.search.clear();self.filter_drawer();self.content.setEnabled(False);self.overlay.show();self.overlay.raise_();self._place_drawer();self.search.setFocus()
    def close_drawer(self):
        self.overlay.hide();self.content.setEnabled(True)
        if self.isVisible():self.full_list.setFocus()
    def _place_drawer(self):
        self.overlay.setGeometry(self.rect());self.shade.setGeometry(self.overlay.rect());width=min(650,max(300,self.width()-24));self.drawer.setGeometry(self.width()-width,0,width,self.height())
    def resizeEvent(self,event):
        super().resizeEvent(event);self._adapt();self._place_drawer()
    def _adapt(self):
        compact=self.width()<1050
        if getattr(self,'_compact',None)==compact:return
        self._compact=compact
        self.work_layout.removeWidget(self.cargo_panel);self.work_layout.removeWidget(self.personnel_panel)
        self.work_layout.setDirection(QHBoxLayout.Direction.TopToBottom if compact else QHBoxLayout.Direction.LeftToRight)
        self.work_layout.addWidget(self.cargo_panel,0 if compact else 7);self.work_layout.addWidget(self.personnel_panel,0 if compact else 3)
        self.personnel_panel.setMaximumWidth(16777215 if compact else 460)
    def shutdown(self):
        self._closed=True;self._sequence+=1;self.refresh_timer.stop();self.pool.waitForDone(10000)
