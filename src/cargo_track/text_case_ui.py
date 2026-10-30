"""Shared native casing preview used by Cargo and Personnel."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
    QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QTextEdit)
from .appearance import fit_to_screen
from .text_case import normalize
from .dialogs import GlassDialog


class CasePreviewDialog(GlassDialog):
    def __init__(self, proposals, parent=None):
        super().__init__(parent)
        self.proposals = proposals
        self.setWindowTitle('Normalize existing names')
        self.resize(1000, 620)
        layout = QVBoxLayout(self)
        note = QLabel('Review each proposed change. Uncheck any spelling to keep. Saved berthing plan versions retain their original text; generate a fresh plan after applying changes.')
        note.setWordWrap(True);layout.addWidget(note)
        self.rows = QTableWidget(len(proposals), 5)
        self.rows.setHorizontalHeaderLabels(['Apply', 'Record / field', 'Original', 'Suggested', 'Review'])
        self.rows.setAccessibleName('Name normalization preview')
        self.rows.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.rows.setWordWrap(True);self.rows.verticalHeader().hide()
        for row, item in enumerate(proposals):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked if item.get('review') else Qt.CheckState.Checked)
            self.rows.setItem(row, 0, check)
            for col, text in enumerate((item['label'], item['before'], item['after'], '; '.join(item.get('review', []))), 1):
                cell = QTableWidgetItem(text);cell.setToolTip(text);self.rows.setItem(row, col, cell)
        self.rows.setColumnWidth(0, 55);self.rows.setColumnWidth(1, 180)
        for col in (2, 3):self.rows.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self.rows.setColumnWidth(4, 190);self.rows.resizeRowsToContents()
        layout.addWidget(self.rows, 1)
        self.summary = QLabel();layout.addWidget(self.summary)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText('Apply selected changes')
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.rows.itemChanged.connect(self.update_summary);self.update_summary()

    def showEvent(self, event):
        fit_to_screen(self);super().showEvent(event)

    def selected(self):
        return [p for i, p in enumerate(self.proposals) if self.rows.item(i, 0).checkState() == Qt.CheckState.Checked]

    def update_summary(self, *_):
        count = len(self.selected())
        self.summary.setText(f'{count} of {len(self.proposals)} changes selected. Original text is retained in history.')
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(count > 0)


def attach_case_preview(form, fields, kind, initial_preserve=False, previous=None):
    """Live final-value preview; never rewrite text while the user is typing."""
    preserve = QCheckBox('Keep my spelling (skip automatic casing)')
    preserve.setChecked(initial_preserve)
    if kind == 'cargo':
        label = QTextEdit();label.setReadOnly(True);label.setMinimumHeight(64);label.setMaximumHeight(110)
        label.setTabChangesFocus(True)
    else:
        label = QLabel();label.setWordWrap(True);label.setTextFormat(Qt.TextFormat.PlainText)
    label.setAccessibleName('Text after saving')
    def refresh(*_):
        lines = []
        for name, widget in fields.items():
            raw = widget.toPlainText() if hasattr(widget, 'toPlainText') else widget.text()
            unchanged = previous is not None and raw.strip() == previous.get(name)
            value, notes = (raw.strip(), []) if preserve.isChecked() or unchanged else normalize(raw, kind if kind == 'cargo' else name)
            lines.append(('Description' if kind == 'cargo' else name.title()) + ': ' + (value or '—'))
            lines.extend(notes)
        if kind == 'cargo':label.setPlainText('\n'.join(lines))
        else:label.setText('\n'.join(lines))
    for widget in fields.values():widget.textChanged.connect(refresh)
    preserve.toggled.connect(refresh)
    form.addRow(preserve);form.addRow('After saving', label);refresh()
    return preserve, label
