"""One explicit light theme and shared branding for native Windows widgets."""

from pathlib import Path
import sys
import re

from PySide6.QtCore import Qt,QSettings
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette


def asset_path(name):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "assets" / "branding" / name


APP_STYLE = """
QMainWindow, QDialog { background: #F5F5F7; }
QWidget { color: #24262B; font-family: "Inter", "Segoe UI", "Microsoft YaHei UI"; font-size: __FONT_SIZE__pt; }
QFrame#surface { background: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 12px; }
QLabel#sectionTitle { color: #666970; font-size: __FONT_SIZE__pt; font-weight: 600; }
QLabel#stopName { padding-left: 8px; }
QPushButton, QToolButton { background: #FFFFFF; border: 1px solid #DCDDE2; border-radius: 7px; padding: 5px 12px; min-height: 22px; }
QPushButton:hover, QToolButton:hover { background: #F0F3F8; border-color: #C2C9D5; }
QPushButton:pressed, QToolButton:pressed { background: #E7EDF5; }
QPushButton:focus, QToolButton:focus { border-color: #007AFF; }
QPushButton:disabled, QToolButton:disabled { color: #8D9098; background: #F5F5F7; border-color: #E5E5EA; }
QToolButton:checked { background: #EAF3FF; color: #0066CC; border-color: #C9DFFF; }
QToolButton::menu-button { subcontrol-origin: border; subcontrol-position: right center; width: 25px; border: none; background: transparent; }
QToolButton::menu-button:hover { background: #E8EFF8; border-top-right-radius: 7px; border-bottom-right-radius: 7px; }
QToolButton::menu-arrow { image: url(__CHEVRON__); width: 10px; height: 7px; }
QToolButton::menu-indicator { image: none; width: 0; }
QComboBox { background: #FFFFFF; border: 1px solid #DCDDE2; border-radius: 7px; padding: 5px 30px 5px 12px; min-height: 22px; }
QComboBox:hover { border-color: #BBC5D3; background: #FAFBFD; }
QComboBox:focus { border-color: #007AFF; }
QComboBox:disabled { color: #858992; background: #F5F5F7; border-color: #E5E5EA; }
QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: top right; width: 28px; border: none; background: transparent; }
QComboBox::down-arrow { image: url(__CHEVRON__); width: 10px; height: 7px; }
QComboBox::down-arrow:disabled { image: url(__CHEVRON_DISABLED__); }
QComboBox QAbstractItemView { padding: 5px; background: #FFFFFF; border: 1px solid #DCDDE2; border-radius: 8px; outline: none; selection-background-color: #007AFF; selection-color: #FFFFFF; }
QComboBox QAbstractItemView::item { min-height: 26px; padding: 3px 8px; }
QLineEdit, QTextEdit { background: #FFFFFF; border: 1px solid #DCDDE2; border-radius: 8px; padding: 5px 10px; min-height: 22px; selection-background-color: #D5E8FF; }
QLineEdit:focus, QTextEdit:focus { border: 1px solid #007AFF; background: #FFFFFF; }
QPushButton#primaryButton { color: #FFFFFF; background: #0066D6; border-color: #0066D6; font-weight: 600; }
QPushButton#primaryButton:hover { background: #006BE0; }
QTabBar { background: #E9EAEE; border-radius: 8px; }
QTabBar::tab { background: transparent; color: #62656D; padding: 7px 13px; margin: 3px; border: 0; border-radius: 6px; }
QTabBar::tab:selected { color: #24262B; background: #FFFFFF; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #DFE2E8; }
QAbstractItemView { background: #FFFFFF; alternate-background-color: #FAFAFC; color: #24262B; border: 1px solid #E5E5EA; border-radius: 8px; selection-background-color: #EAF3FF; selection-color: #24262B; }
QAbstractItemView::item:selected { background: #EAF3FF; color: #24262B; }
QAbstractItemView::item:focus { border: 1px solid #007AFF; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #FFFFFF; border: 0; }
QHeaderView { color: #6D7078; background: #FAFAFC; }
QHeaderView::section { color: #6D7078; background: #FAFAFC; border: 0; border-bottom: 1px solid #E5E5EA; padding: 7px 8px; font-weight: 600; }
QTableCornerButton::section { background: #FAFAFC; border: 0; }
QMenu { background: #FFFFFF; color: #24262B; border: 1px solid #DCDDE2; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 20px; border-radius: 5px; }
QMenu::item:selected { background: #007AFF; color: #FFFFFF; }
QMenu::item:disabled { color: #8D9098; }
QMenu::separator { height: 1px; background: #E5E5EA; margin: 5px 8px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle { background: #BFC2C9; border-radius: 3px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background: #999DA6; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: #FFFFFF; color: #24262B; border: 1px solid #DCDDE2; padding: 4px; }
QStatusBar { color: #6D7078; background: #F5F5F7; }
"""



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
    style=APP_STYLE
    if is_dark_mode():
        style=re.sub(r"#[0-9A-Fa-f]{6}",lambda m:DARK_COLORS.get(m.group().upper(),m.group()),style)
        style+="\nQLabel#brand { background: #F5F5F7; border-radius: 6px; } QPushButton#primaryButton { color: #FFFFFF; } QComboBox QAbstractItemView { selection-color: #081827; } QMenu::item:selected { color: #081827; }"
    return style

def configure_application(app):
    root=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[2]))
    for file in ("Inter-Regular.ttf","Inter-SemiBold.ttf"):
        if QFontDatabase.addApplicationFont(str(root/"assets/fonts"/file))<0:raise RuntimeError("The bundled Inter font could not be loaded.")
    # Native Windows dark colors otherwise leak into unstyled viewports and headers.
    app.setStyle("Fusion")
    if hasattr(app.styleHints(), "setColorScheme"):
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if is_dark_mode() else Qt.ColorScheme.Light)
    palette = QPalette()
    colors = {
        "Window": "#F4F6FA", "WindowText": "#17243A", "Base": "#FFFFFF",
        "AlternateBase": "#F8FAFC", "Text": "#17243A", "Button": "#FFFFFF",
        "ButtonText": "#17243A", "ToolTipBase": "#FFFFFF", "ToolTipText": "#17243A",
        "Highlight": "#E8F0FA", "HighlightedText": "#17243A", "BrightText": "#FFFFFF",
        "Light": "#FFFFFF", "Midlight": "#F4F6FA", "Dark": "#C9D3E0",
        "Mid": "#DCE3ED", "Shadow": "#788496", "Link": "#174B87",
        "LinkVisited": "#6F4CC3", "PlaceholderText": "#65738A",
    }
    if is_dark_mode():
        colors.update(Window="#191B20",WindowText="#E6E8ED",Base="#25272E",AlternateBase="#202329",Text="#E6E8ED",Button="#25272E",ButtonText="#E6E8ED",ToolTipBase="#25272E",ToolTipText="#E6E8ED",Highlight="#183D61",HighlightedText="#E6E8ED",Light="#414650",Midlight="#30333B",Dark="#17191D",Mid="#373A43",Shadow="#080A0D",Link="#A6D0FF",LinkVisited="#C5ACFF",PlaceholderText="#A4ABB7")
    for role, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#9299A6" if is_dark_mode() else "#65738A"))
    app.setPalette(palette)
    app.setFont(QFont(application_font_family(), application_font_size()))
    app.setStyleSheet(theme_style().replace("__FONT_SIZE__",str(application_font_size())).replace('"Inter"','"'+application_font_family()+'"').replace("__CHEVRON__", asset_path("chevron-dark.svg" if is_dark_mode() else "chevron.svg").as_posix()).replace("__CHEVRON_DISABLED__", asset_path("chevron-disabled-dark.svg" if is_dark_mode() else "chevron-disabled.svg").as_posix()))
    app.setWindowIcon(QIcon(str(asset_path("cargo-track.ico"))))


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
