"""Blur the live application backdrop behind a panel without blurring its controls."""
from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QFrame, QGraphicsBlurEffect, QLabel, QWidget

_capturing_sources = set()


class FrostedFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._backdrop = QLabel(self)
        self._backdrop.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._backdrop.setStyleSheet('background: transparent; border: 0;')
        self._blur = QGraphicsBlurEffect(self._backdrop)
        self._blur.setBlurHints(QGraphicsBlurEffect.BlurHint.PerformanceHint)
        self._backdrop.setGraphicsEffect(self._blur)
        self._tint = QFrame(self)
        self._tint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ancestor = None
        self._watched = []
        self._scheduled = False
        self._last_background = None
        self._intensity = None
        self._backdrop.lower()
        self._tint.stackUnder(self._backdrop)
        self._backdrop.stackUnder(self._tint)
        self.refresh_material()

    def refresh_material(self, intensity=None):
        from .appearance import glass_gradient, glass_intensity, is_dark_mode
        from .theme_tokens import colors
        self._intensity = glass_intensity() if intensity is None else max(0, min(100, int(intensity)))
        self._blur.setBlurRadius(self._intensity * .22)
        tint = glass_gradient(is_dark_mode(), self._intensity)
        self._tint.setStyleSheet('QFrame {background: '+tint+'; border: 1px solid '+colors(is_dark_mode())['border']+'; border-radius: 12px;}')
        self._queue_capture()

    def _queue_capture(self):
        if not self._scheduled:
            self._scheduled = True
            QTimer.singleShot(0, self._capture)

    def _source(self):
        widget = self.parentWidget()
        while widget is not None:
            if widget.objectName() in ('dashboardContent', 'settingsPage', 'workspaceShell'):
                return widget
            widget = widget.parentWidget()
        return None

    def _capture(self):
        self._scheduled = False
        if not self.isVisible() or self.width() < 2 or self.height() < 2:
            return
        source = self._source()
        if source is None:
            return
        if source is not self._ancestor:
            for watched in self._watched:
                watched.removeEventFilter(self)
            self._watched = []
            self._ancestor = source
            watched = self.parentWidget()
            while watched is not None:
                watched.installEventFilter(self)
                self._watched.append(watched)
                if watched is source:break
                watched = watched.parentWidget()
        offset = self.mapTo(source, QPoint(0, 0))
        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        # Render the source background alone; including its children would recurse
        # into this panel and could expose or duplicate unrelated UI controls.
        _capturing_sources.add(source)
        try:
            source.render(painter, -offset, QRegion(QRect(offset, self.size())), QWidget.RenderFlag.DrawWindowBackground)
        finally:
            _capturing_sources.discard(source)
            painter.end()
        image = pixmap.toImage()
        if image != self._last_background:
            self._last_background = image
            self._backdrop.setPixmap(pixmap)

    def eventFilter(self, watched, event):
        if watched in self._watched and event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.StyleChange, QEvent.Type.PaletteChange):
            self._queue_capture()
        elif watched is self._ancestor and event.type() == QEvent.Type.Paint and watched not in _capturing_sources:
            self._queue_capture()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._backdrop.setGeometry(self.rect().adjusted(1, 1, -1, -1))
        self._tint.setGeometry(self.rect())
        self._queue_capture()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._queue_capture()

    def showEvent(self, event):
        super().showEvent(event)
        self._queue_capture()
