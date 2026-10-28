"""One brand and workspace selector for both native workbenches."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QButtonGroup
from .appearance import brand_pixmap
from .brand import PRODUCT_NAME
from .about_ui import show_about


class WorkspaceNavigation(QWidget):
    def __init__(self, active='cargo', parent=None):
        super().__init__(parent)
        self.setAccessibleName('Workspace navigation')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.brand = QLabel()
        self.brand.setObjectName('brand')
        self.brand.setAccessibleName('MarineOps logo')
        self.brand.setPixmap(brand_pixmap(76, 36))
        self.brand.setFixedSize(76, 36)
        layout.addWidget(self.brand)
        self.title = QLabel(PRODUCT_NAME)
        font = self.title.font(); font.setBold(True); self.title.setFont(font)
        layout.addWidget(self.title)
        self.group = QButtonGroup(self)
        self.dashboard_button = QPushButton('Dashboard')
        self.cargo_button = QPushButton('Cargo')
        self.personnel_button = QPushButton('Personnel')
        for name, button in (('dashboard', self.dashboard_button), ('cargo', self.cargo_button), ('personnel', self.personnel_button)):
            button.setCheckable(True)
            button.setObjectName('workspaceTab')
            button.setAccessibleName('Open '+name.capitalize()+' workspace')
            button.setToolTip(name.capitalize()+' workspace')
            self.group.addButton(button)
            button.setChecked(name == active)
            layout.addWidget(button)
        self.about_button = QPushButton('About')
        self.about_button.setAccessibleName('About MarineOps')
        self.about_button.clicked.connect(lambda: show_about(self.window()))
        layout.addWidget(self.about_button)


class ElidedLabel(QLabel):
    """Keep long context labels readable, with the full value in the tooltip."""
    def setText(self,text):
        self.full_text=text;self.setToolTip(text);self._render_text()
    def _render_text(self):
        super().setText(self.fontMetrics().elidedText(getattr(self,'full_text',''),Qt.TextElideMode.ElideRight,max(10,self.width())))
    def resizeEvent(self,event):
        super().resizeEvent(event);self._render_text()
