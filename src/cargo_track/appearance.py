"""One explicit light theme and shared branding for native Windows widgets."""

from pathlib import Path
import sys

from .theme_tokens import colors, render_style, palette_colors
from .brand import LOGO_FILE, ICON_FILE

from PySide6.QtCore import Qt,QSettings,QLocale
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette, QPixmap


def asset_path(name):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "assets" / "branding" / name


def brand_pixmap(width, height):
    """Render the transparent approved ribbon without cropping or a theme tile."""
    pixmap = QPixmap(str(asset_path(LOGO_FILE))).scaled(width * 3, height * 3,
        Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    pixmap.setDevicePixelRatio(3)
    return pixmap


STYLE_TEMPLATE = """
QMainWindow, QDialog { background: @window@; }
QWidget { color: @text@; font-family: "Inter", "Segoe UI", "Microsoft YaHei UI"; font-size: __FONT_SIZE__pt; }
QFrame#surface { background: @surface@; border: 1px solid @divider@; border-radius: 12px; }
QLabel#sectionTitle { color: @muted@; font-size: __FONT_SIZE__pt; font-weight: 600; }
QLabel#stopName { padding-left: 8px; }
QLabel#workbenchTitle { font-size: 14pt; font-weight: 600; }
QFrame#routeSidebar { border: 0; border-right: 1px solid @divider@; }
QFrame#routeSidebar QPushButton, QFrame#routeSidebar QToolButton { padding: 5px 6px; font-size: 10pt; }
QListWidget#stopList { border: 0; border-radius: 0; background: @window@; }
QListWidget#stopList::item { border-bottom: 1px solid @divider@; padding: 4px 6px; }
QTabWidget#personnelTabs::pane, QTabWidget#planViews::pane { border: 0; background: @window@; }
QTabWidget#personnelTabs > QTabBar { background: transparent; }
QToolButton#routeStop { text-align: left; border: 0; border-bottom: 1px solid @divider@; border-radius: 0; padding: 4px 28px 4px 10px; }
QFrame#routeSidebar QToolButton#routeStop { font-size: __FONT_SIZE__pt; }
QToolButton#routeStop:checked { border-left: 3px solid @focus@; background: @selection@; color: @text@; }
QPushButton#countLink { border: 0; background: transparent; padding: 4px 10px; }
QTabBar#scopeTabs { background: transparent; }
QTabBar#scopeTabs::tab { background: @surface@; border: 1px solid @border@; margin: 0 8px 0 0; padding: 8px 14px; }
QTabBar#scopeTabs::tab:selected { background: @selection@; border-color: @focus@; }
QPushButton, QToolButton { background: @surface@; border: 1px solid @border@; border-radius: 7px; padding: 5px 12px; min-height: 22px; }
QPushButton:hover, QToolButton:hover { background: @hover@; border-color: @hover_border@; }
QPushButton:pressed, QToolButton:pressed { background: @pressed@; }
QPushButton:focus, QToolButton:focus { border-color: @focus@; }
QPushButton:disabled, QToolButton:disabled { color: @disabled@; background: @window@; border-color: @divider@; }
QToolButton:checked { background: @selection@; color: @selection_text@; border-color: @selection_border@; }
QToolButton::menu-button { subcontrol-origin: border; subcontrol-position: right center; width: 25px; border: none; background: transparent; }
QToolButton::menu-button:hover { background: @menu_hover@; border-top-right-radius: 7px; border-bottom-right-radius: 7px; }
QToolButton::menu-arrow { image: url(__CHEVRON__); width: 10px; height: 7px; }
QToolButton::menu-indicator { image: none; width: 0; }
QComboBox { background: @surface@; border: 1px solid @border@; border-radius: 7px; padding: 5px 30px 5px 12px; min-height: 22px; }
QComboBox:hover { border-color: @field_hover_border@; background: @field_hover@; }
QComboBox:focus { border-color: @focus@; }
QComboBox:disabled { color: @field_disabled@; background: @window@; border-color: @divider@; }
QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: top right; width: 28px; border: none; background: transparent; }
QComboBox::down-arrow { image: url(__CHEVRON__); width: 10px; height: 7px; }
QComboBox::down-arrow:disabled { image: url(__CHEVRON_DISABLED__); }
QComboBox QAbstractItemView { padding: 5px; background: @surface@; border: 1px solid @border@; border-radius: 8px; outline: none; selection-background-color: @focus@; selection-color: @menu_selection_text@; }
QComboBox QAbstractItemView::item { min-height: 26px; padding: 3px 8px; }
QLineEdit, QTextEdit { background: @surface@; border: 1px solid @border@; border-radius: 8px; padding: 5px 10px; min-height: 22px; selection-background-color: @text_selection@; }
QLineEdit:focus, QTextEdit:focus { border: 1px solid @focus@; background: @surface@; }
QPushButton#primaryButton { color: @primary_text@; background: @primary@; border-color: @primary@; font-weight: 600; }
QPushButton#primaryButton:hover { background: @primary_hover@; }
QPushButton#primaryButton:disabled { color: @disabled@; background: @window@; border-color: @divider@; }
QPushButton#workspaceTab:checked { background: @primary@; color: @primary_text@; border: 1px solid @selection_border@; font-weight: 600; }
QTabBar { background: @tab_track@; border-radius: 8px; }
QTabBar::tab { background: transparent; color: @tab_text@; padding: 7px 13px; margin: 3px; border: 0; border-radius: 6px; }
QTabBar::tab:selected { color: @text@; background: @surface@; font-weight: 600; }
QTabBar::tab:hover:!selected { background: @tab_hover@; }
QAbstractItemView { background: @surface@; alternate-background-color: @alternate@; color: @text@; border: 1px solid @divider@; border-radius: 8px; selection-background-color: @selection@; selection-color: @text@; }
QAbstractItemView::item:selected { background: @selection@; color: @text@; }
QAbstractItemView::item:focus { border: 1px solid @focus@; }
QScrollArea, QScrollArea > QWidget > QWidget { background: @surface@; border: 0; }
QHeaderView { color: @header@; background: @alternate@; }
QHeaderView::section { color: @header@; background: @alternate@; border: 0; border-bottom: 1px solid @divider@; padding: 7px 8px; font-weight: 600; }
QTableCornerButton::section { background: @alternate@; border: 0; }
QMenu { background: @surface@; color: @text@; border: 1px solid @border@; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 20px; border-radius: 5px; }
QMenu::item:selected { background: @focus@; color: @menu_selection_text@; }
QMenu::item:disabled { color: @disabled@; }
QMenu::separator { height: 1px; background: @divider@; margin: 5px 8px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle { background: @scrollbar@; border-radius: 3px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background: @scrollbar_hover@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: @surface@; color: @text@; border: 1px solid @border@; padding: 4px; }
QStatusBar { color: @header@; background: @window@; }
"""
APP_STYLE = render_style(STYLE_TEMPLATE)



DARK_COLORS={
    "#FFFFFF":"#25272E", "#24262B":"#E6E8ED", "#F5F5F7":"#191B20", "#E5E5EA":"#373A43",
    "#666970":"#ADB4C1", "#DCDDE2":"#414650", "#F0F3F8":"#303744", "#C2C9D5":"#596578",
    "#E7EDF5":"#38475D", "#8D9098":"#9299A6", "#EAF3FF":"#183D61", "#0066CC":"#A6D0FF",
    "#C9DFFF":"#315B83", "#E8EFF8":"#38475D", "#BBC5D3":"#626C7D", "#FAFBFD":"#30333B",
    "#858992":"#9299A6", "#D5E8FF":"#315B83", "#007AFF":"#4199FF", "#E9EAEE":"#262931",
    "#62656D":"#B6BDCA", "#DFE2E8":"#353B46", "#FAFAFC":"#202329", "#6D7078":"#ADB4C1",
    "#BFC2C9":"#626A78", "#999DA6":"#8993A3",
}

def is_dark_mode():return QSettings().value("appearance/theme","light")=="dark"

def themed_color(light,dark):return dark if is_dark_mode() else light

def theme_style():
    style=render_style(STYLE_TEMPLATE,is_dark_mode())
    return style


def configure_application(app):
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    root=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[2]))
    if app.property('cargoTrackFontRoot') != str(root):
        for file in ("Inter-Regular.ttf","Inter-SemiBold.ttf"):
            if QFontDatabase.addApplicationFont(str(root/"assets/fonts"/file))<0:raise RuntimeError("The bundled Inter font could not be loaded.")
        app.setProperty('cargoTrackFontRoot',str(root))
    # Native Windows dark colors otherwise leak into unstyled viewports and headers.
    app.setStyle("Fusion")
    if hasattr(app.styleHints(), "setColorScheme"):
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if is_dark_mode() else Qt.ColorScheme.Light)
    palette = QPalette()
    palette_values = palette_colors(is_dark_mode())
    for role, color in palette_values.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors(is_dark_mode())["disabled"]))
    app.setPalette(palette)
    app.setFont(QFont(application_font_family(), application_font_size()))
    app.setStyleSheet(theme_style().replace("__FONT_SIZE__",str(application_font_size())).replace('"Inter"','"'+application_font_family()+'"').replace("__CHEVRON__", asset_path("chevron-dark.svg" if is_dark_mode() else "chevron.svg").as_posix()).replace("__CHEVRON_DISABLED__", asset_path("chevron-disabled-dark.svg" if is_dark_mode() else "chevron-disabled.svg").as_posix()))
    app.setWindowIcon(QIcon(str(asset_path(ICON_FILE))))


def fit_to_screen(widget):
    screen = widget.screen()
    if screen is None:
        return
    available = screen.availableGeometry()
    widget.resize(min(widget.width(), available.width() - 24),
                  min(widget.height(), available.height() - 48))


def application_font_family():
    return "Inter" if "Inter" in QFontDatabase.families() else "Segoe UI"


def application_font_size():
    try:size=int(QSettings().value("appearance/font_size",11))
    except (TypeError,ValueError):size=11
    return size if size in (10,11,12) else 11
