"""Public product identity; storage and activation retain their legacy names."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout
from . import __version__
from .brand import PRODUCT_NAME, PRODUCT_DESCRIPTION
from .appearance import brand_pixmap


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('About MarineOps')
        self.setAccessibleName('About MarineOps')
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)
        self.logo = QLabel()
        self.logo.setAccessibleName('MarineOps logo')
        self.logo.setPixmap(brand_pixmap(240, 104))
        layout.addWidget(self.logo)
        self.title = QLabel(PRODUCT_NAME)
        font = self.title.font(); font.setPointSize(font.pointSize() + 7); font.setBold(True)
        self.title.setFont(font)
        self.version = QLabel('Version ' + __version__)
        self.description = QLabel(PRODUCT_DESCRIPTION)
        self.summary = QLabel('Manage cargo transfers, personnel movements, and voyage and berthing plans in one offline desktop workspace.')
        self.summary.setWordWrap(True)
        for label in (self.title, self.version, self.description, self.summary):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def show_about(parent):
    AboutDialog(parent).exec()
