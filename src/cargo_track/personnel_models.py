"""Model-backed personnel tables and lightweight, on-demand editor state."""
from PySide6.QtCore import Qt, QObject, Signal, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import QTableView, QComboBox, QStyledItemDelegate, QAbstractItemView


class CheckState(QObject):
    toggled=Signal(bool)
    def __init__(self):
        super().__init__();self.checked=False;self.name=''
    def isChecked(self):return self.checked
    def setChecked(self,value):
        value=bool(value)
        if value!=self.checked:self.checked=value;self.toggled.emit(value)
    def setAccessibleName(self,value):self.name=value
    def accessibleName(self):return self.name


class ChoiceState(QObject):
    currentIndexChanged=Signal(int)
    def __init__(self):
        super().__init__();self.options=[];self.index=-1;self.name='';self.tooltip=''
    def count(self):return len(self.options)
    def clear(self):self.options=[];self.index=-1
    def addItem(self,label,value=None):
        self.options.append((label,value))
        if self.index<0:self.index=0
    def insertItem(self,index,label,value=None):self.options.insert(index,(label,value));self.index+=1
    def findData(self,value):return next((i for i,(_,v) in enumerate(self.options) if v==value),-1)
    def currentData(self):return self.options[self.index][1] if 0<=self.index<len(self.options) else None
    def currentText(self):return self.options[self.index][0] if 0<=self.index<len(self.options) else ''
    def currentIndex(self):return self.index
    def setCurrentIndex(self,index):
        if index!=self.index:self.index=index;self.currentIndexChanged.emit(index)
    def setToolTip(self,value):self.tooltip=value
    def setAccessibleName(self,value):self.name=value
    def accessibleName(self):return self.name


class Cell:
    def __init__(self,model,row,column):self.model,self.r,self.c=model,row,column
    def text(self):return self.model.values[self.r][self.c]
    def setText(self,value):self.model.setData(self.model.index(self.r,self.c),value)
    def row(self):return self.r
    def column(self):return self.c
    def flags(self):return self.model.flags(self.model.index(self.r,self.c))
    def setFlags(self,value):self.model.cell_flags[self.r,self.c]=value
    def setToolTip(self,value):self.model.tips[self.r,self.c]=value


class PersonnelTableModel(QAbstractTableModel):
    edited=Signal(object)
    def __init__(self,headers,parent=None):
        super().__init__(parent);self.headers=headers;self.values=[];self.controls={};self.cell_flags={};self.tips={};self.records=[]
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.values)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.headers)
    def replace(self,values):
        self.beginResetModel();self.values=[[str(v if v is not None else '') for v in row] for row in values]
        self.controls={};self.cell_flags={};self.tips={};self.endResetModel()
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if orientation==Qt.Orientation.Horizontal and role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.AccessibleTextRole):return self.headers[section]
    def flags(self,index):
        result=self.cell_flags.get((index.row(),index.column()),Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsEditable)
        control=self.controls.get((index.row(),index.column()))
        if isinstance(control,CheckState):result|=Qt.ItemFlag.ItemIsUserCheckable
        if isinstance(control,ChoiceState):result|=Qt.ItemFlag.ItemIsEditable
        return result
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        r,c=index.row(),index.column();value=self.values[r][c];control=self.controls.get((r,c))
        if role==Qt.ItemDataRole.CheckStateRole and isinstance(control,CheckState):return Qt.CheckState.Checked if control.checked else Qt.CheckState.Unchecked
        if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.EditRole):return control.currentText() if isinstance(control,ChoiceState) else value
        if role==Qt.ItemDataRole.ToolTipRole:return control.tooltip if isinstance(control,ChoiceState) else self.tips.get((r,c),value)
        if role in (Qt.ItemDataRole.AccessibleTextRole,Qt.ItemDataRole.AccessibleDescriptionRole):
            if control:return control.accessibleName()+': '+(control.currentText() if isinstance(control,ChoiceState) else ('included' if control.checked else 'excluded'))
            return self.headers[c]+': '+value
    def setData(self,index,value,role=Qt.ItemDataRole.EditRole):
        if not index.isValid():return False
        r,c=index.row(),index.column();control=self.controls.get((r,c))
        if role==Qt.ItemDataRole.CheckStateRole and isinstance(control,CheckState):control.setChecked(value==Qt.CheckState.Checked or value==Qt.CheckState.Checked.value)
        else:self.values[r][c]=str(value);self.edited.emit(Cell(self,r,c))
        self.dataChanged.emit(index,index);return True
    def set_control(self,row,column,control):
        self.controls[row,column]=control
        signal=control.toggled if isinstance(control,CheckState) else control.currentIndexChanged
        signal.connect(lambda *_,r=row,c=column:self.dataChanged.emit(self.index(r,c),self.index(r,c)))


class ChoiceDelegate(QStyledItemDelegate):
    def createEditor(self,parent,option,index):
        model=index.model();source=index
        if isinstance(model,QSortFilterProxyModel):source=model.mapToSource(index);model=model.sourceModel()
        state=model.controls.get((source.row(),source.column()))
        if not isinstance(state,ChoiceState):return super().createEditor(parent,option,index)
        editor=QComboBox(parent);editor.setAccessibleName(state.accessibleName())
        for label,value in state.options:editor.addItem(label,value)
        editor.setCurrentIndex(state.currentIndex());editor.activated.connect(lambda *_:self.commitData.emit(editor))
        editor._choice_state=state
        return editor
    def setEditorData(self,editor,index):
        if hasattr(editor,'_choice_state'):editor.setCurrentIndex(editor._choice_state.currentIndex())
        else:super().setEditorData(editor,index)
    def setModelData(self,editor,model,index):
        if hasattr(editor,'_choice_state'):editor._choice_state.setCurrentIndex(editor.currentIndex())
        else:super().setModelData(editor,model,index)


class ModelTable(QTableView):
    itemChanged=Signal(object)
    itemSelectionChanged=Signal()
    def __init__(self,headers,parent=None):
        super().__init__(parent);self.source_model=PersonnelTableModel(headers,self);self.setModel(self.source_model)
        self.source_model.edited.connect(lambda item:self.itemChanged.emit(item))
        self.selectionModel().selectionChanged.connect(lambda *_:self.itemSelectionChanged.emit())
        self.setItemDelegate(ChoiceDelegate(self));self.verticalHeader().hide();self.setWordWrap(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True);self.horizontalHeader().setStretchLastSection(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed)
    def rowCount(self):return self.model().rowCount()
    def columnCount(self):return self.model().columnCount()
    def item(self,row,column):
        index=self.model().index(row,column)
        if isinstance(self.model(),QSortFilterProxyModel):index=self.model().mapToSource(index)
        return Cell(self.source_model,index.row(),index.column())
    def currentRow(self):return self.currentIndex().row()
    def setCurrentCell(self,row,column):self.setCurrentIndex(self.model().index(row,column))
    def horizontalHeaderItem(self,column):
        class Header:
            def text(inner):return self.source_model.headers[column]
        return Header()
    def visualItemRect(self,item):return self.visualRect(self.source_model.index(item.r,item.c))
    def setCellWidget(self,row,column,control):self.source_model.set_control(row,column,control)
    def cellWidget(self,row,column):return self.source_model.controls.get((row,column))


class CrewFilter(QSortFilterProxyModel):
    def __init__(self,parent=None):super().__init__(parent);self.query='';self.vessel=None;self.direction=''
    def apply(self,query,vessel,direction):self.query=query.casefold();self.vessel=vessel;self.direction=direction;self.invalidateFilter()
    def filterAcceptsRow(self,row,parent):
        record=self.sourceModel().records[row]
        if self.direction and record.get('direction')!=self.direction:return False
        if self.vessel is not None and self.vessel not in (record.get('from_id'),record.get('to_id')):return False
        return self.query in ' '.join(str(record.get(k,'')) for k in ('name','position','from_name','to_name','comment')).casefold()
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if index.column()==0 and role==Qt.ItemDataRole.DisplayRole:return str(index.row()+1)
        return super().data(index,role)
