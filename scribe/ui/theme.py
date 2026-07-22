"""Listen's visual theme: modern UI in dark or light mode, rust accent,
grunge display font.

Body text uses Segoe UI (Windows' standard TrueType family); headings and the
app title use the most grunge-like handwritten TrueType font installed
(Ink Free ships with Windows 10/11), falling back gracefully.

Module-level colour names (BG, TEXT, ACCENT, …) always reflect the active
mode; call apply_theme(app, mode) to switch.
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

if getattr(sys, "frozen", False):
    # Running from a PyInstaller bundle: assets are bundled alongside the
    # app under sys._MEIPASS rather than two directories above this file.
    ASSETS = Path(sys._MEIPASS) / "assets"
else:
    ASSETS = Path(__file__).resolve().parents[2] / "assets"

_DARK = {
    "BG": "#15161c",           # window background
    "PANEL": "#1c1e26",        # side panels, toolbar, tables
    "SURFACE": "#262a36",      # inputs, hover states
    "BORDER": "#353b4b",
    "TEXT": "#e9ebf2",
    "MUTED": "#9aa1b4",
    "DISABLED": "#5a6072",
    "ACCENT": "#e8563f",       # rust orange
    "ACCENT_SOFT": "#f0876f",
    "INFO": "#53b4ff",
    "WARN": "#ff6b6b",
    "ALT": "#191b22",          # alternating table rows
    "GRID": "#23262f",
    "SPEAKER_COLORS": ["#53b4ff", "#c792ea", "#4ecfa5", "#ffb454",
                       "#ff6b6b", "#4dd0e1", "#d4c15c", "#9ba7ff"],
}

_LIGHT = {
    "BG": "#eef0f4",
    "PANEL": "#ffffff",
    "SURFACE": "#f1f2f7",
    "BORDER": "#d5d9e3",
    "TEXT": "#22242c",
    "MUTED": "#666d80",
    "DISABLED": "#b3b8c4",
    "ACCENT": "#d84a33",
    "ACCENT_SOFT": "#a83a27",
    "INFO": "#146bc2",
    "WARN": "#c22525",
    "ALT": "#f6f7fa",
    "GRID": "#e8eaf0",
    "SPEAKER_COLORS": ["#146bc2", "#7c3aae", "#0e8a63", "#b26a00",
                       "#c22525", "#00778a", "#7a6a00", "#4854c9"],
}

MODE = "dark"

_GRUNGE_CANDIDATES = ("Ink Free", "Segoe Print", "Segoe Script", "Comic Sans MS")


def set_mode(mode: str):
    """Point the module-level colour names at the chosen palette."""
    globals().update(_LIGHT if mode == "light" else _DARK)
    globals()["MODE"] = "light" if mode == "light" else "dark"


set_mode("dark")


def grunge_font_family() -> str:
    families = set(QFontDatabase.families())
    for name in _GRUNGE_CANDIDATES:
        if name in families:
            return name
    return "Segoe UI"


def _qss(grunge: str) -> str:
    return f"""
QWidget {{ background: {BG}; color: {TEXT}; }}
QLabel {{ background: transparent; }}

QLabel#appTitle {{
    font-family: '{grunge}';
    font-size: 28px;
    font-weight: 700;
    color: {ACCENT};
    letter-spacing: 3px;
    padding: 10px 8px 2px 8px;
    background: {PANEL};
}}

QPushButton#themeToggle {{
    background: transparent;
    color: {MUTED};
    border: 1px dashed {BORDER};
    border-radius: 12px;
    padding: 4px 14px;
    font-size: 9pt;
    font-weight: 600;
}}
QPushButton#themeToggle:hover {{ color: {ACCENT}; border-color: {ACCENT}; }}

QToolBar {{
    background: {PANEL};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    spacing: 2px;
}}
QToolButton {{
    background: transparent;
    color: {TEXT};
    padding: 7px 12px;
    border-radius: 6px;
    font-weight: 600;
}}
QToolButton:hover {{ background: {SURFACE}; color: {ACCENT_SOFT}; }}
QToolButton:pressed {{ background: {BORDER}; }}
QToolButton:disabled {{ color: {DISABLED}; }}

QListWidget {{
    background: {PANEL};
    border: none;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 9px;
    margin: 2px 4px;
    border-radius: 6px;
    border-left: 3px solid transparent;
    color: {TEXT};
}}
QListWidget::item:hover {{ background: {SURFACE}; }}
QListWidget::item:selected {{
    background: {SURFACE};
    border-left: 3px solid {ACCENT};
    color: {TEXT};
}}

QTableWidget {{
    background: {PANEL};
    border: none;
    gridline-color: {GRID};
    selection-background-color: {SURFACE};
    selection-color: {TEXT};
    alternate-background-color: {ALT};
}}
QHeaderView::section {{
    background: {PANEL};
    color: {MUTED};
    border: none;
    border-bottom: 2px solid {BORDER};
    padding: 7px;
    font-weight: 700;
}}
QTableCornerButton::section {{ background: {PANEL}; border: none; }}

QTextBrowser {{
    background: {PANEL};
    border: none;
    border-top: 1px solid {BORDER};
    padding: 10px;
}}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 9px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    outline: none;
}}

QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT_SOFT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {DISABLED}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:disabled {{ background: {PANEL}; border-color: {PANEL}; }}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 8px;
    font-weight: 700;
    color: {ACCENT_SOFT};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}

QStatusBar {{
    background: {PANEL};
    color: {MUTED};
    border-top: 1px solid {BORDER};
}}

QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:hover {{ background: {BORDER}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {BORDER}; border-radius: 5px; min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QProgressBar {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 7px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 6px;
}}

QRadioButton {{ spacing: 8px; }}
QRadioButton::indicator {{
    width: 16px; height: 16px;
    border-radius: 8px;
    border: 1px solid {BORDER};
    background: {SURFACE};
}}
QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px;
}}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {ACCENT}; }}
"""


def apply_theme(app, mode: str = "dark"):
    """Apply the Listen theme in the given mode ("dark" or "light")."""
    set_mode(mode)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(_qss(grunge_font_family()))


def logo_pixmap(color: str, height: int = 56) -> QPixmap:
    """The ear+LISTEN wordmark tinted to `color` (artwork is an alpha mask)."""
    pm = QPixmap(str(ASSETS / "logo.png"))
    painter = QPainter(pm)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pm.rect(), QColor(color))
    painter.end()
    return pm.scaledToHeight(height, Qt.SmoothTransformation)


def app_icon() -> QIcon:
    return QIcon(str(ASSETS / "icon.png"))
