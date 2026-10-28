"""Native Qt table model and status/decorations."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QBrush, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle
from .theme_tokens import colors

from .domain import Status
from .appearance import is_dark_mode


HEADERS=["NO","Cargo ID","Description","From","To","Status","Comment","Completed Date"]


class TransferTableModel(QAbstractTableModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.rows=[];self.offset=0

    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(HEADERS)
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.AccessibleTextRole) and orientation==Qt.Orientation.Horizontal and 0<=section<len(HEADERS):return HEADERS[section]
        return None
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0<=index.row()<len(self.rows)):return None
        row=self.rows[index.row()]
        key=["no","cargo_tag","description","from_name","to_name","status","comment","completed_date"][index.column()]
        if role==Qt.ItemDataRole.DisplayRole:
            if index.column()==0:return str(self.offset+index.row()+1)
            return str(row.get(key) or ("—" if key=="completed_date" else ""))
        if role==Qt.ItemDataRole.UserRole:return row
        if role==Qt.ItemDataRole.TextAlignmentRole and index.column()==0:return int(Qt.AlignmentFlag.AlignCenter|Qt.AlignmentFlag.AlignVCenter)
        if role==Qt.ItemDataRole.BackgroundRole:
            if row.get("status")==Status.DONE.value:return QBrush(QColor("#25272E" if is_dark_mode() else "#FFFFFF"))
            if row.get("current_relation"):return QBrush(QColor("#232E3D" if is_dark_mode() else "#FAFBFE"))
        if role==Qt.ItemDataRole.ToolTipRole:
            if key in ('description','comment','from_name','to_name'):return str(row.get(key) or 'Not provided')
            if index.column()==0:return f"Transfer #{row['no']} · {row['cargo_tag']}"
            if key=="description" and len(str(row.get(key,"")))>70:return row.get(key)
            if key=="comment" and len(str(row.get(key,"")))>70:return row.get(key)
            if row.get("current_relation") and index.column()==0:return f"Related to current stop ({row['current_relation']})"
        if role==Qt.ItemDataRole.AccessibleTextRole:
            value=self.offset+index.row()+1 if index.column()==0 else row.get(key)
            return f"{HEADERS[index.column()]}: {value or ('Not completed' if key=='completed_date' else 'Not provided')}. Transfer {row['no']}, cargo {row['cargo_tag']}"
        if role==Qt.ItemDataRole.AccessibleDescriptionRole:
            return f"{row['description']}, from {row['from_name']} to {row['to_name']}, status {row['status']}, comment {row.get('comment') or 'none'}, completed {row.get('completed_date') or 'not completed'}"
        return None
    def replace(self,rows,offset=0):
        self.beginResetModel();self.rows=list(rows);self.offset=max(0,int(offset));self.endResetModel()
    def row_at(self,position):return self.rows[position] if 0<=position<len(self.rows) else None


class StatusDelegate(QStyledItemDelegate):
    COLORS={"Waiting":("#FFF2D6","#7A4B00"),"On Board":("#DFEDFF","#174B87"),"Done":("#E2F3E7","#17603A")}
    def paint(self,painter:QPainter,option,index):
        status=str(index.data() or "")
        if status not in self.COLORS:
            super().paint(painter,option,index);return
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect,option.palette.highlight())
        tokens=colors(is_dark_mode());role={'Waiting':'waiting','On Board':'onboard','Done':'done'}[status]
        background,foreground=tokens[role+'_surface'],tokens[role+'_text']
        width=min(option.rect.width()-16,max(54,option.fontMetrics.horizontalAdvance(status)+20))
        pill=option.rect.adjusted(8,9,-max(0,option.rect.width()-width-8),-9)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(background));painter.drawRoundedRect(pill,5,5)
        painter.setPen(QPen(QColor(foreground)))
        painter.drawText(pill,Qt.AlignmentFlag.AlignCenter,status)
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setBrush(Qt.BrushStyle.NoBrush);painter.setPen(QPen(QColor(tokens['focus']),2))
            painter.drawRect(option.rect.adjusted(1,1,-2,-2))
        painter.restore()
