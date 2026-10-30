"""Silent, themed dialogs shared by the Cargo and Personnel workspaces."""
from pathlib import Path
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog as QtFileDialog, QFrame,
    QGraphicsBlurEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout)

from .appearance import glass_gradient, glass_intensity, is_dark_mode
from .theme_tokens import colors


class GlassDialog(QDialog):
    """A modal surface with a blurred snapshot of its own application behind it."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._glass_backdrop = QLabel(self)
        self._glass_backdrop.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._glass_backdrop.setStyleSheet('background: transparent; border: 0')
        effect = QGraphicsBlurEffect(self._glass_backdrop)
        effect.setBlurRadius(glass_intensity() * .22)
        self._glass_backdrop.setGraphicsEffect(effect)
        self._glass_tint = QFrame(self)
        self._glass_tint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._glass_tint.setStyleSheet('QFrame { background: '+glass_gradient(is_dark_mode(),glass_intensity())+'; border: 0; }')
        self._glass_backdrop.lower(); self._glass_tint.stackUnder(self._glass_backdrop); self._glass_backdrop.stackUnder(self._glass_tint)

    def showEvent(self, event):
        parent = self.parentWidget()
        if parent is not None and parent.window().isVisible():
            # Capture only the app window, never the desktop or other applications.
            image = parent.window().grab()
            if not image.isNull():
                self._glass_backdrop.setPixmap(image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        super().showEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._glass_backdrop.setGeometry(self.rect()); self._glass_tint.setGeometry(self.rect())


class PromptDialog(GlassDialog):
    def __init__(self, parent, title, message, details='', rows=(), buttons=('Cancel','Confirm'), default='Cancel'):
        super().__init__(parent)
        self.setWindowTitle(title); self.setAccessibleName(title); self.setMinimumWidth(440); self.setMaximumWidth(650)
        self.choice = None
        layout=QVBoxLayout(self); layout.setContentsMargins(24,22,24,22); layout.setSpacing(12)
        heading=QLabel(title); heading.setTextFormat(Qt.TextFormat.PlainText); heading.setObjectName('workbenchTitle'); heading.setWordWrap(True); layout.addWidget(heading)
        if len(str(message)) > 600:
            text=QTextEdit();text.setReadOnly(True);text.setPlainText(str(message));text.setMaximumHeight(180)
        else:
            text=QLabel(str(message)); text.setWordWrap(True); text.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(text)
        if details:
            if len(str(details)) > 600:
                detail=QTextEdit();detail.setReadOnly(True);detail.setPlainText(str(details));detail.setMaximumHeight(180)
            else:
                detail=QLabel(str(details)); detail.setWordWrap(True); detail.setTextFormat(Qt.TextFormat.PlainText)
            detail.setStyleSheet('color: '+colors(is_dark_mode())['muted']+';'); layout.addWidget(detail)
        if rows:
            panel=QFrame(); panel.setStyleSheet('QFrame { background: '+colors(is_dark_mode())['surface']+'; border: 1px solid '+colors(is_dark_mode())['border']+'; border-radius: 7px; } QLabel { background: transparent; border: 0; }')
            group=QVBoxLayout(panel);group.setContentsMargins(14,10,14,10);group.setSpacing(8)
            for label,value in rows:
                line=QHBoxLayout(); key=QLabel(str(label)); key.setMinimumWidth(90); key.setStyleSheet('color: '+colors(is_dark_mode())['muted'])
                value_label=QLabel(str(value)); value_label.setWordWrap(True); value_label.setTextFormat(Qt.TextFormat.PlainText)
                line.addWidget(key);line.addWidget(value_label,1);group.addLayout(line)
            layout.addWidget(panel)
        self.content_layout=layout
        footer=QHBoxLayout();footer.addStretch();self.buttons={}
        for name in buttons:
            button=QPushButton(name);self.buttons[name]=button
            if name not in ('Cancel','Discard','Close'):button.setObjectName('primaryButton')
            button.clicked.connect(lambda checked=False, value=name:self._choose(value));footer.addWidget(button)
            if name == default:button.setDefault(True);button.setFocus()
        layout.addLayout(footer)

    def _choose(self, value):
        self.choice=value
        self.accept() if value not in ('Cancel','Close') else self.reject()


def prompt(parent, title, message, details='', rows=(), buttons=('Cancel','Confirm'), default='Cancel'):
    dialog=PromptDialog(parent,title,message,details,rows,buttons,default)
    dialog.exec()
    return dialog.choice


class InputDialog:
    @staticmethod
    def getText(parent, title, label, mode=QLineEdit.EchoMode.Normal, text='', **kwargs):
        dialog=PromptDialog(parent,title,label,buttons=('Cancel','OK'),default='OK')
        field=QLineEdit(str(text));field.setEchoMode(mode);field.setAccessibleName(label)
        dialog.content_layout.insertWidget(dialog.content_layout.count()-1,field);field.setFocus();field.selectAll()
        accepted=dialog.exec()==QDialog.DialogCode.Accepted
        return (field.text() if accepted else '',accepted)

    @staticmethod
    def getItem(parent, title, label, items, current=0, editable=True, **kwargs):
        dialog=PromptDialog(parent,title,label,buttons=('Cancel','OK'),default='OK')
        field=QComboBox();field.addItems(list(items));field.setEditable(editable);field.setCurrentIndex(current);field.setAccessibleName(label)
        dialog.content_layout.insertWidget(dialog.content_layout.count()-1,field);field.setFocus()
        accepted=dialog.exec()==QDialog.DialogCode.Accepted
        return (field.currentText() if accepted else '',accepted)


class FileDialog:
    """Use Qt's accessible file chooser so it follows the application's theme."""
    @staticmethod
    def getOpenFileName(parent, caption, directory='', filter=''):
        return QtFileDialog.getOpenFileName(parent,caption,directory,filter,options=QtFileDialog.Option.DontUseNativeDialog)

    @staticmethod
    def getSaveFileName(parent, caption, directory='', filter=''):
        dialog=_SaveFileDialog(parent,caption)
        dialog.setOption(QtFileDialog.Option.DontUseNativeDialog,True)
        dialog.setOption(QtFileDialog.Option.DontConfirmOverwrite,True)
        dialog.setAcceptMode(QtFileDialog.AcceptMode.AcceptSave)
        if filter:dialog.setNameFilters(filter.split(';;'))
        if directory:
            path=Path(directory)
            if path.is_dir():dialog.setDirectory(str(path))
            else:dialog.setDirectory(str(path.parent));dialog.selectFile(path.name)
        accepted=dialog.exec()==QDialog.DialogCode.Accepted
        return (dialog.selectedFiles()[0],dialog.selectedNameFilter()) if accepted else ('','')

    @staticmethod
    def getExistingDirectory(parent, caption, directory=''):
        return QtFileDialog.getExistingDirectory(parent,caption,directory,options=QtFileDialog.Option.ShowDirsOnly|QtFileDialog.Option.DontUseNativeDialog)


class _SaveFileDialog(QtFileDialog):
    def accept(self):
        selected=self.selectedFiles()
        if not selected:return
        path=Path(selected[0])
        if not path.suffix:
            match=re.search(r'\*\.([A-Za-z0-9]+)',self.selectedNameFilter())
            if match:
                self.setDefaultSuffix(match.group(1));path=Path(self.selectedFiles()[0])
        if path.is_file():
            choice=prompt(self,'Replace file?',f'{path.name} already exists.',
                          'Replace it with the new file?',buttons=('Cancel','Replace'))
            if choice!='Replace':return
        super().accept()
