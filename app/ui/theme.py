"""Shared Qt theme for the Thai-first desktop interface.

Widgets consume named object/property selectors instead of carrying their own
colours.  Runtime and payroll services intentionally do not appear here.
"""
from PySide6.QtGui import QColor, QFont, QPalette
from pathlib import Path


TOKENS = {
    'canvas': '#F6F8FB',
    'surface': '#FFFFFF',
    'surface_subtle': '#EEF2F6',
    'border': '#D7DEE8',
    'text': '#172033',
    'text_muted': '#5D6878',
    'primary': '#1E5AA8',
    'primary_hover': '#174982',
    'success': '#197A4A',
    'warning': '#9A6700',
    'danger': '#B42318',
    'info': '#245EA8',
    'focus': '#124F9E',
}

FONT_FAMILIES = ('Segoe UI', 'Leelawadee UI', 'Tahoma', 'sans-serif')


def stylesheet():
    """Return the application QSS built only from the shared token set."""
    t = TOKENS
    # Qt's Windows QSS parser rejects percent-encoded file URIs when the
    # project path contains spaces. A quoted forward-slash file path is valid
    # QSS and keeps the checkbox asset local to the application package.
    checkmark = Path(__file__).with_name('checkmark.svg').resolve().as_posix()
    return f"""
QMainWindow, QDialog {{ background: {t['canvas']}; color: {t['text']}; }}
QWidget {{ color: {t['text']}; font-size: 14px; }}
QLabel[role="pageTitle"] {{ font-size: 24px; font-weight: 600; }}
QLabel[role="sectionTitle"] {{ font-size: 18px; font-weight: 600; }}
QLabel[role="supporting"] {{ color: {t['text_muted']}; font-size: 13px; }}
QLabel[semantic="warning"] {{ color: {t['warning']}; font-weight: 600; }}
QLabel[semantic="error"] {{ color: {t['danger']}; font-weight: 600; }}
QWidget#sidebar {{ background: {t['surface']}; border-right: 1px solid {t['border']}; }}
QFrame[role="section"] {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QGroupBox {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; margin-top: 8px; padding: 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QPushButton {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 8px 12px; min-height: 22px; }}
QPushButton:hover {{ background: {t['surface_subtle']}; border-color: {t['primary']}; }}
QPushButton:pressed {{ background: {t['border']}; }}
QPushButton:disabled {{ color: {t['text_muted']}; background: {t['surface_subtle']}; border-color: {t['border']}; }}
QPushButton[role="primary"] {{ background: {t['primary']}; color: {t['surface']}; border-color: {t['primary']}; font-weight: 600; }}
QPushButton[role="primary"]:hover {{ background: {t['primary_hover']}; border-color: {t['primary_hover']}; }}
QPushButton[role="navigation"] {{ border: 0; border-radius: 6px; text-align: left; padding: 10px 12px; }}
QPushButton[role="navigation"]:checked {{ background: {t['surface_subtle']}; color: {t['primary']}; font-weight: 600; border-left: 3px solid {t['primary']}; }}
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTableWidget:focus {{ border: 2px solid {t['focus']}; }}
QLineEdit, QComboBox, QSpinBox {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 6px 8px; min-height: 20px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t['border']}; border-radius: 3px; background: {t['surface']}; }}
QCheckBox::indicator:checked {{ background: {t['primary']}; border-color: {t['primary']}; image: url("{checkmark}"); }}
QCheckBox::indicator:disabled {{ background: {t['surface_subtle']}; border-color: {t['border']}; }}
QCheckBox::indicator:checked:disabled {{ background: {t['text_muted']}; image: url("{checkmark}"); }}
QTableWidget {{ background-color: {t['surface']}; alternate-background-color: {t['surface_subtle']}; border: 1px solid {t['border']}; border-radius: 8px; gridline-color: {t['border']}; selection-background-color: {t['surface_subtle']}; selection-color: {t['text']}; }}
QTableWidget::viewport {{ background-color: {t['surface']}; }}
QTableWidget::item {{ background-color: {t['surface']}; color: {t['text']}; padding: 4px 6px; }}
QTableWidget::item:selected {{ background: #DCEBFA; color: {t['text']}; border: 1px solid {t['primary']}; }}
QHeaderView::section {{ background-color: {t['surface_subtle']}; border: 0; border-bottom: 1px solid {t['border']}; color: {t['text']}; font-weight: 600; padding: 8px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollArea#overviewPage,
QScrollArea#settingsPage,
QScrollArea#overviewPage::viewport,
QScrollArea#settingsPage::viewport,
QWidget#overviewViewport,
QWidget#settingsViewport,
QWidget#overviewBody,
QWidget#settingsBody {{
    background-color: {t['canvas']};
}}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 5px; min-height: 28px; }}
QStatusBar {{ background: {t['surface']}; border-top: 1px solid {t['border']}; color: {t['text_muted']}; }}
QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['surface_subtle']}; }}
QToolTip {{ background: {t['text']}; color: {t['surface']}; border: 0; padding: 6px; }}
""".strip()


def apply_theme(application):
    """Apply the single visual baseline to a QApplication instance."""
    font = QFont()
    font.setFamilies(list(FONT_FAMILIES))
    font.setPointSize(10)
    application.setFont(font)
    application.setStyleSheet(stylesheet())


def apply_canvas_background(widget):
    """Give scroll viewports a native-safe opaque canvas from the shared theme."""
    _apply_opaque_background(widget, TOKENS['canvas'])


def apply_surface_background(widget):
    """Keep table surfaces independent from the native dark palette."""
    _apply_opaque_background(widget, TOKENS['surface'])
    viewport = widget.viewport() if hasattr(widget, 'viewport') else None
    if viewport is not None:
        _apply_opaque_background(viewport, TOKENS['surface'])


def _apply_opaque_background(widget, color_name):
    palette = widget.palette()
    color = QColor(color_name)
    palette.setColor(QPalette.ColorRole.Window, color)
    palette.setColor(QPalette.ColorRole.Base, color)
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)
