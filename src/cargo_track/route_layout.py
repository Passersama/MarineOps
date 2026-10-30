"""A fully expanded, wrapping voyage route for the native workbench."""
from PySide6.QtCore import Qt,QRect,QSize,QMimeData,Signal
from PySide6.QtWidgets import QApplication,QLayout,QToolButton
from PySide6.QtWidgets import QStyle,QStyleOptionToolButton
from PySide6.QtGui import QDrag,QPainter,QPen


class RouteButton(QToolButton):
    def __init__(self,title,parent=None):
        super().__init__(parent);self.full_title=title;self.setText(title);self.setToolTip(title)

    def presentation(self,available):
        metrics=self.fontMetrics();width=min(max(80,available),280,metrics.horizontalAdvance(self.full_title)+58)
        budget=max(20,width-58);lines=[];remaining=self.full_title
        while remaining:
            if metrics.horizontalAdvance(remaining)<=budget:lines.append(remaining);break
            end=1
            while end<len(remaining) and metrics.horizontalAdvance(remaining[:end+1])<=budget:end+=1
            space=remaining.rfind(' ',0,end+1)
            if space>0:end=space
            lines.append(remaining[:end]);remaining=remaining[end:].lstrip()
        return QSize(width,max(34,len(lines)*metrics.lineSpacing()+14)),'\n'.join(lines)


class RouteLayout(QLayout):
    def __init__(self,parent=None):
        super().__init__(parent);self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(8)
    def addItem(self,item):self.items.append(item)
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):return Qt.Orientation(0)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),True)
    def minimumSize(self):return QSize(80,34) if self.items else QSize(0,0)
    def sizeHint(self):return self.minimumSize()
    def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect,False)
    def arrange(self,rect,measure=False):
        if not self.items:return 0
        x,y=rect.x(),rect.y();row_height=0;available=max(80,rect.width());right=rect.x()+available
        for item in self.items:
            widget=item.widget();size,text=widget.presentation(available)
            if x>rect.x() and x+size.width()>right:
                x=rect.x();y+=row_height+self.spacing();row_height=0
            if not measure:
                if widget.text()!=text:widget.setText(text)
                item.setGeometry(QRect(x,y,size.width(),size.height()))
            x+=size.width()+self.spacing();row_height=max(row_height,size.height())
        return y+row_height-rect.y()


class SidebarRouteButton(RouteButton):
    reorder_requested=Signal(int,int,bool)
    MIME='application/x-cargo-track-voyage-stop'
    def __init__(self,title,parent=None,stop_id=None,drag_scope=''):
        super().__init__(title,parent);self.stop_id=stop_id;self.drag_scope=drag_scope
        self._drag_start=None;self._drop_after=None;self.setAcceptDrops(stop_id is not None)
    def mousePressEvent(self,event):
        self._drag_start=None
        if event.button()==Qt.MouseButton.LeftButton and self.stop_id is not None:
            option=QStyleOptionToolButton();self.initStyleOption(option)
            menu=self.style().subControlRect(QStyle.ComplexControl.CC_ToolButton,option,QStyle.SubControl.SC_ToolButtonMenu,self)
            if not self.menu() or not menu.contains(event.position().toPoint()):self._drag_start=event.position().toPoint()
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if (self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint()-self._drag_start).manhattanLength()>=QApplication.startDragDistance()):
            self._drag_start=None;self.setDown(False)
            drag=QDrag(self);mime=QMimeData();mime.setData(self.MIME,f'{self.drag_scope}:{self.stop_id}'.encode('utf-8'));drag.setMimeData(mime)
            drag.setPixmap(self.grab());drag.setHotSpot(event.position().toPoint());drag.exec(Qt.DropAction.MoveAction)
            event.accept();return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        self._drag_start=None;super().mouseReleaseEvent(event)
    def _drag_stop(self,event):
        if not self.isEnabled() or not event.mimeData().hasFormat(self.MIME):return None
        try:
            scope,identifier=bytes(event.mimeData().data(self.MIME)).decode('utf-8').rsplit(':',1)
            identifier=int(identifier)
        except (ValueError,UnicodeError):return None
        return identifier if scope==self.drag_scope and identifier!=self.stop_id else None
    def dragEnterEvent(self,event):
        if self._drag_stop(event) is not None:event.setDropAction(Qt.DropAction.MoveAction);event.accept()
        else:event.ignore()
    def dragMoveEvent(self,event):
        if self._drag_stop(event) is None:event.ignore();return
        self._drop_after=(event.position().x()>=self.width()/2 if self.property('horizontalRoute') else event.position().y()>=self.height()/2);self.update();event.setDropAction(Qt.DropAction.MoveAction);event.accept()
    def dragLeaveEvent(self,event):
        self._drop_after=None;self.update();event.accept()
    def dropEvent(self,event):
        identifier=self._drag_stop(event);self._drop_after=None;self.update()
        if identifier is None:event.ignore();return
        after=(event.position().x()>=self.width()/2 if self.property('horizontalRoute') else event.position().y()>=self.height()/2)
        event.setDropAction(Qt.DropAction.MoveAction);event.accept();self.reorder_requested.emit(identifier,self.stop_id,after)
    def minimumSizeHint(self):return QSize(60,24)
    def paintEvent(self,event):
        option=QStyleOptionToolButton();self.initStyleOption(option);option.text=''
        painter=QPainter(self);self.style().drawComplexControl(QStyle.ComplexControl.CC_ToolButton,option,painter,self)
        painter.setFont(self.font())
        painter.setPen(self.palette().windowText().color())
        painter.drawText(self.rect().adjusted(12,2,-28,-2),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.text())
        if self._drop_after is not None:
            painter.setPen(QPen(self.palette().highlight().color(),3))
            if self.property('horizontalRoute'):
                x=self.width()-2 if self._drop_after else 1; painter.drawLine(x,2,x,self.height()-2)
            else:
                y=self.height()-2 if self._drop_after else 1; painter.drawLine(2,y,self.width()-2,y)


class SidebarRouteLayout(RouteLayout):
    """Read visits down the sidebar; use extra columns for long routes."""
    def hasHeightForWidth(self):return False
    def minimumSize(self):return QSize(180,0)
    def sizeHint(self):return QSize(230,400)
    def setGeometry(self,rect):
        QLayout.setGeometry(self,rect)
        if not self.items:return
        import math
        # A finite window cannot show arbitrary visits. Reflow long routes instead
        # of introducing a scrollbar or clipping the final visit.
        preferred=max(46 if len(self.items)>12 else 38,self.items[0].widget().fontMetrics().lineSpacing()+18)
        columns=max(1,math.ceil(len(self.items)*preferred/max(1,rect.height())))
        rows=math.ceil(len(self.items)/columns)
        width=max(80,(rect.width()-(columns-1)*4)//columns)
        height=min(52,max(24,rect.height()//rows))
        for i,item in enumerate(self.items):
            widget=item.widget();_,title=widget.presentation(width)
            widget.setText(title)
            item.setGeometry(QRect(rect.x()+(i//rows)*(width+4),rect.y()+(i%rows)*height,width,height-2))
