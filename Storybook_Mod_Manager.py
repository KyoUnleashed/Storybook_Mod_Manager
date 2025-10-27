#!/usr/bin/env python3
"""
Storybook Mod Manager — Full merged script with update checker, multi-image previews, safer schema editing, and self-update check

What's new in this build:
- Settings bootstrapping:
  - On first run, settings.json defaults to local Mods folders next to the app:
      • Secret Rings/Mods
      • Black Knight/Mods
    These directories are created if missing. Mod scanning includes subfolders (mods with mod.ini are recognized at any depth).
- No unintended mod.ini creation:
  - The app never auto-creates mod.ini during scanning. Mod info is read if mod.ini exists; otherwise the folder name is used. mod.ini is only created when editing a mod in the Edit Mod dialog.
- Configure Mod Menu improvements:
  - Picture order dialog supports drag-and-drop reordering via a list, with a visible "≡" handle and hover highlight.
  - Only saves schema JSONs (config_schema.json, config_schema_files.json) and packed_files.bin on Save. If Cancel is pressed, these files are deleted, forcing a fresh start next time.
- Update checker:
  - Parses GameBanana (or any text/HTML) for version numbers like "Version 2", "V2", or "Version 2.1.0" → normalized to semantic format (e.g., 2.0.0).
  - Adds Mod Manager self-update check using a code URL embedded in this script (MANAGER_UPDATE_URL). The URL is not exposed via settings/UI; edit the constant in code.
- Edit Mod UI:
  - "Update Page" field removed (Update URL is enough).
- Mod list context menu:
  - Adds "Go to Author Page" option, shown only when the mod's Author URL is present.
- Logs toggle and window sizing:
  - Slightly reduced default window size.
  - Toggling Logs no longer resizes or distorts the main window.

Note:
- Attachments schema supports "previews": a list of {"ref": "packed::name" or relative path, "desc": "caption"}.
- Old single "preview": str will be migrated on load to "previews": [{"ref": preview, "desc": ""}].
"""

import sys
import os
import re
import json
import shutil
import subprocess
import base64
import zlib
import tempfile
import webbrowser
import ctypes
import requests
import time
from ctypes import wintypes
from pathlib import Path
from configparser import ConfigParser
from bs4 import BeautifulSoup
from functools import partial
from datetime import date
from urllib.request import Request, urlopen
from PyQt5.QtCore import QPropertyAnimation, QRect, QPoint, Qt, QEasingCurve, QSize, QTimer
from PyQt5.QtGui import QPixmap, QIcon, QDrag, QPainter, QPen, QColor, QMovie
from PyQt5.QtWidgets import QLabel, QCheckBox, QGraphicsOpacityEffect, QSplitter, QStyle, QStyleOptionViewItem, QStyledItemDelegate

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QTextEdit, QDialog,
    QLineEdit, QComboBox, QDialogButtonBox, QTreeWidget, QTreeWidgetItem,
    QMenu, QInputDialog, QListWidget, QListWidgetItem, QSizePolicy, QScrollArea,
    QToolButton, QFrame, QAbstractButton, QProgressBar, QAbstractItemView, QSlider,
)
from PyQt5.QtCore import (
    Qt, QTimer, QEvent, QSize, QObject, QPropertyAnimation,
    QRect, QPoint, QEasingCurve, QThread, pyqtSignal
)
from PyQt5.QtGui import QIcon, QPixmap, QBrush, QColor, QFontMetrics

# Title Bar Color, same with the one in main() [at the bottom]
def set_title_bar_color(qwidget, r=32, g=32, b=32):
    """
    Change the native Windows title bar color for this window only.
    r, g, b = 0–255 values (default is a dark grey: 68,68,68)
    """
    hwnd = int(qwidget.winId())  # Get HWND from the PyQt widget

    # DWM API constants
    DWMWA_CAPTION_COLOR = 35
    DWMWA_TEXT_COLOR = 36
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20

    # Convert RGB to COLORREF (BGR in Windows)
    def rgb_to_colorref(r, g, b):
        return b | (g << 8) | (r << 16)

    colorref = wintypes.DWORD(rgb_to_colorref(r, g, b))
    white_text = wintypes.DWORD(rgb_to_colorref(255, 255, 255))

    dwmapi = ctypes.WinDLL("dwmapi")

    # Set caption (title bar) background color
    dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_CAPTION_COLOR,
        ctypes.byref(colorref),
        ctypes.sizeof(colorref)
    )

    # Set caption text color
    dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_TEXT_COLOR,
        ctypes.byref(white_text),
        ctypes.sizeof(white_text)
    )

    # Optional: force dark mode buttons if supported
    dark_mode = wintypes.BOOL(True)
    dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(dark_mode),
        ctypes.sizeof(dark_mode)
    )

# Helper for setting up icon (Storybook UI Init)
def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    Example: resource_path("UI/help/Step1.gif")
    """
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        # Use the directory where Storybook_Mod_Manager.py lives
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

# Gives me that L-shaped mouse upon hovering over button
class SBButton(QPushButton):
    """Custom button with pointing-hand cursor by default."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor)

class UniversalStyle:
    STYLE = """
        /* --- Scroll Area Backgrounds (fix checkerboard) --- */
        QScrollArea, QAbstractScrollArea {
            background: #1E1E1E;
            border: none;
        }
        QScrollArea > QWidget {
            background: #1E1E1E;
        }

        /* --- Vertical Scrollbar --- */
        QScrollBar:vertical {
            background: #1E1E1E;
            width: 12px;
            margin: 0px;
            border: none;
        }
        QScrollBar::handle:vertical {
            background: #3A3A3A;
            min-height: 20px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover {
            background: #555555;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
            background: none;
            border: none;
        }

        /* --- Horizontal Scrollbar --- */
        QScrollBar:horizontal {
            background: #1E1E1E;
            height: 12px;
            margin: 0px;
            border: none;
        }
        QScrollBar::handle:horizontal {
            background: #3A3A3A;
            min-width: 20px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #555555;
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
            background: none;
            border: none;
        }
    """

    @staticmethod
    def apply(app):
        """
        Apply a universal dark theme + modern scrollbar style across the app.
        Replace any older scrollbar CSS you had with this.
        """
        style = r"""
        /* Base app colors (keeps your dark theme) */
        QWidget, QFrame, QScrollArea, QListWidget, QTreeWidget, QTextEdit, QPlainTextEdit {
            background-color: #121214;
            color: #e6e6e6;
        }

        /* ---------- VERTICAL SCROLLBAR ---------- */
        QScrollBar:vertical {
            background: transparent;           /* keep track invisible (overlay look) */
            width: 12px;                       /* thickness of the scrollbar */
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:vertical {
            background: #2f2f2f;               /* main handle color */
            min-height: 22px;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.03);
        }
        QScrollBar::handle:vertical:hover {
            background: #3f3f3f;
        }
        QScrollBar::handle:vertical:pressed {
            background: #4f4f4f;
        }
        /* remove arrows / lines */
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            background: none;
            height: 0px;
        }
        /* make the track transparent so it doesn't show checkerboards */
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: transparent;
        }

        /* ---------- HORIZONTAL SCROLLBAR ---------- */
        QScrollBar:horizontal {
            background: transparent;
            height: 12px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:horizontal {
            background: #2f2f2f;
            min-width: 22px;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.03);
        }
        QScrollBar::handle:horizontal:hover {
            background: #3f3f3f;
        }
        QScrollBar::handle:horizontal:pressed {
            background: #4f4f4f;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            background: none;
            width: 0px;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
            background: transparent;
        }

        /* ---------- Make scrollbars overlay (if desired) ---------- */
        QAbstractScrollArea {
            /* keeps the widget backgrounds consistent */
            background-color: #121214;
        }

        /* ---------- Fine tune for lists, trees, etc ---------- */
        QListView::item, QTreeView::item, QTreeWidget::item {
            background: transparent;
        }

        /* Clear any background-image on scrollbars/tracks that might create checkerboards */
        QScrollBar, QScrollBar::groove, QScrollBar::sub-page, QScrollBar::add-page {
            background-image: none;
        }
        """
        try:
            app.setStyleSheet(style)
        except Exception:
            # if something goes wrong, fall back silently to avoid breaking UI load
            pass

class DarkScrollArea(QScrollArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWidgetResizable(True)
        self.viewport().setStyleSheet("background-color: #1E1E1E;")
        self.setStyleSheet("""
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #1E1E1E;
                border: none;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #3A3A3A;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background: #555555;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background: none;
                border: none;
                width: 0px;
                height: 0px;
            }
        """)

# Dolphin Recognize game closes class (StorybookUI)
class GameWindowMonitor(QThread):
    game_started = pyqtSignal()
    game_closed = pyqtSignal()

    def __init__(self, ui, game_key):
        super().__init__()
        self.ui = ui
        self.game_key = game_key
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        # Wait for game window to appear (up to ~15s)
        appeared = False
        for _ in range(30):
            if not self._running:
                return
            if self.ui._game_window_present_for_key(self.game_key):
                appeared = True
                break
            time.sleep(0.5)

        if appeared:
            self.game_started.emit()
        else:
            self.game_closed.emit()
            return

        # Wait until game window disappears
        while self._running:
            if not self.ui._game_window_present_for_key(self.game_key):
                self.game_closed.emit()
                return
            time.sleep(1)

# Helper for detecting mod is png only
def _mod_is_png_only(mod_folder: Path) -> bool:
        """
        Return True if this mod folder contains ONLY PNG files (besides mod.ini, mod_data.json).
        This indicates it's a texture pack mod that needs Dolphin Custom Texture Path.
        """
        try:
            has_png = False
            has_other = False

            for dirpath, _, filenames in os.walk(mod_folder):
                for fname in filenames:
                    # Skip metadata files
                    if fname in ("mod.ini", "mod_data.json", "config_schema.json", 
                               "config.json", "config_schema_files.json", 
                               "preview.png", "file_mappings.json", "packed_files.bin"):
                        continue
                    
                    ext = Path(fname).suffix.lower()
                    if ext == ".png":
                        has_png = True
                    elif ext:  # Has extension but not PNG
                        has_other = True

            return has_png and not has_other
        except Exception:
            return False

# Helper for the SBButton class, for the windows to change the mouse to L-Shape that isn't the main window
def handify_buttons_in(widget):
    """Make every QPushButton/QToolButton and QDialogButtonBox button in `widget` use the pointing-hand cursor."""
    try:
        for b in widget.findChildren(QPushButton):
            b.setCursor(Qt.PointingHandCursor)
        for tb in widget.findChildren(QToolButton):
            tb.setCursor(Qt.PointingHandCursor)
        for box in widget.findChildren(QDialogButtonBox):
            for btn in box.buttons():
                btn.setCursor(Qt.PointingHandCursor)
    except Exception:
        pass

# This Class applies dark mode to every window, corresponds with Main
class TitleBarColorFilter(QObject):
    def eventFilter(self, obj, event):
        # Only act on QWidget instances that are top-level windows
        if isinstance(obj, QWidget) and event.type() == QEvent.Show and obj.isWindow():
            try:
                set_title_bar_color(obj, r=32, g=32, b=32)  # dark grey
            except Exception as e:
                print(f"Title bar color error: {e}")
        return super().eventFilter(obj, event)

# -----------------------
# Packed files helpers (zlib+base64 small container per-mod)
# -----------------------
def _sb_packed_file_path(mod_folder: Path) -> Path:
    return Path(mod_folder) / "packed_files.bin"

def _sb_read_packed_index(mod_folder: Path) -> dict:
    p = _sb_packed_file_path(mod_folder)
    if not p.exists():
        return {}
    try:
        comp = p.read_bytes()
        raw = zlib.decompress(comp)
        obj = json.loads(raw.decode("utf-8"))
        return {name: base64.b64decode(b64) for name, b64 in obj.items()}
    except Exception:
        return {}

def _sb_write_packed_index(mod_folder: Path, pack: dict):
    try:
        if not pack:  # If pack is empty, delete the file
            packed_path = _sb_packed_file_path(mod_folder)
            if packed_path.exists():
                packed_path.unlink()
            return
            
        # Only write if we have content
        safe = {n: base64.b64encode(b).decode("utf-8") for n, b in pack.items()}
        raw = json.dumps(safe).encode("utf-8")
        comp = zlib.compress(raw, level=9)
        _sb_packed_file_path(mod_folder).write_bytes(comp)
    except Exception:
        pass

def _sb_write_packed_files(mod_folder: Path, files: list):
    pack = _sb_read_packed_index(mod_folder)
    changed = False
    for f in files:
        try:
            p = Path(f)
            b = p.read_bytes()
            pack[p.name] = b
            changed = True
        except Exception:
            pass
    if changed:
        _sb_write_packed_index(mod_folder, pack)

def _sb_write_packed_bytes(mod_folder: Path, name: str, data: bytes):
    pack = _sb_read_packed_index(mod_folder)
    pack[name] = data
    _sb_write_packed_index(mod_folder, pack)

def _sb_would_be_empty_after_removal(mod_folder: Path, names: list) -> bool:
    """Returns True if removing these names would result in an empty packed index"""
    pack = _sb_read_packed_index(mod_folder)
    if not pack:  # If already empty
        return True
    names = set(names)
    # Count how many entries would remain after removal
    remaining = sum(1 for name in pack if name not in names)
    return remaining == 0

def _sb_remove_packed_names(mod_folder: Path, names: list):
    pack = _sb_read_packed_index(mod_folder)
    changed = False
    for n in names:
        if n in pack:
            del pack[n]
            changed = True
    if changed:
        if pack:  # Only write if there's still content
            _sb_write_packed_index(mod_folder, pack)
        else:
            # If empty, delete the files
            packed_path = mod_folder / "packed_files.bin"
            if packed_path.exists():
                packed_path.unlink()

def _sb_extract_packed_to_temp(mod_folder: Path, name: str) -> Path:
    pack = _sb_read_packed_index(mod_folder)
    if name not in pack:
        return None
    try:
        out = Path(tempfile.gettempdir()) / f"{Path(mod_folder).name}__{name}"
        out.write_bytes(pack[name])
        return out
    except Exception:
        return None

# Essentially updating (Copilot says populating) mod_data.json
def write_mod_data_snapshot(mod_folder: Path,
                            schema: dict = None,
                            attachments: dict = None,
                            config_values: dict = None,
                            applied_files: list = None):
    """
    Overwrite mod_data.json with a clean, unified snapshot:
      - SET CONFIGURE SCHEMA: { schema, attachments }
      - CONFIGURE MOD MENU:   saved runtime config values
      - APPLIED FILES:        list of relative paths touched in the vanilla tree
    Any section omitted stays empty in the written file (no merge with stale data).
    """
    data = {}

    if schema is not None or attachments is not None:
        data["SET CONFIGURE SCHEMA"] = {
            "schema": schema or {},
            "attachments": attachments or {}
        }

    if config_values is not None:
        data["CONFIGURE MOD MENU"] = config_values or {}

    if applied_files is not None:
        # Save as list for simplicity and clarity
        data["APPLIED FILES"] = list(applied_files)

    try:
        (mod_folder / "mod_data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[error] write_mod_data_snapshot failed for {mod_folder}: {e}")

# -----------------------
# App metadata & paths
# -----------------------
APP_VERSION = "1"
APP_AUTHOR = "KyoUnleashed"

# Set this to the raw URL of the latest script to enable self-update detection (not shown in UI).
MANAGER_UPDATE_URL = "https://gamebanana.com/tools/20945"  # e.g., "https://gamebanana.com/mods/whaatever"

# Handle PyInstaller executable vs script mode
if getattr(sys, 'frozen', False):
    # Running as PyInstaller executable
    APP_DIR = Path(sys.executable).parent.resolve()
    # UI resources are embedded, use sys._MEIPASS for temporary extraction
    UI_DIR = Path(sys._MEIPASS) / "UI"
else:
    # Running as Python script
    APP_DIR = Path(__file__).parent.resolve()
    UI_DIR = APP_DIR / "UI"

SETTINGS_FILE = APP_DIR / "settings.json"
# --- Embedded allowed extensions (no external file required) ---
EMBEDDED_ALLOWED_EXTS = {
    "adx","afs","arc","bin","bnr","csb","csv","dil","gncp",
    "ini","mis","one","rso","sel","sfd","tpl","txd","txt"
}

# Known top-level game data folders (mirror of your vanilla tree conventions)
GAME_FILE_FOLDERS = {
    "adx", "event", "HomeButton2", "movie", "se", "Now", "sound"
}

def normalize_ref_for_file(mod_folder: Path, file_path: Path) -> str:
    """
    Normalize a file reference for attachments and previews:
    - If outside the mod folder -> pack into packed_files.bin (return 'packed::name').
    - If inside the mod folder:
        • If top-level folder matches a known game folder (adx, event, movie, etc.) -> keep relative.
        • Otherwise (e.g. Pictures, Docs, etc.) -> keep relative, do NOT pack.
    """
    try:
        rel = file_path.relative_to(mod_folder)
        top = rel.parts[0] if rel.parts else ""
        if top in GAME_FILE_FOLDERS:
            # Valid game folder -> keep relative
            return str(rel)
        else:
            # Non-game folder but still inside mod -> keep relative, do not pack
            return str(rel)
    except ValueError:
        # Outside mod folder -> pack
        try:
            data = file_path.read_bytes()
            _sb_write_packed_bytes(mod_folder, file_path.name, data)
            return f"packed::{file_path.name}"
        except Exception as e:
            print(f"[normalize_ref_for_file] failed to pack {file_path}: {e}")
            return file_path.name


TEMP_DIR = APP_DIR / "Temp_File"
TEMP_DIR.mkdir(exist_ok=True)

GAME_KEYS = {"Secret Rings": "SecretRings", "Black Knight": "BlackKnight"}
DEFAULT_THEMES = {
    "Secret Rings": APP_DIR / "secret_rings_theme.png",
    "Black Knight": APP_DIR / "black_knight_theme.png"
}

# -----------------------
# Settings helpers
# -----------------------
def _default_mods_dir(game_name_pretty: str) -> Path:
    # e.g., APP_DIR / "Secret Rings" / "Mods"
    base = APP_DIR / game_name_pretty / "Mods"
    base.mkdir(parents=True, exist_ok=True)
    return base

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_settings(obj):
    try:
        SETTINGS_FILE.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    except Exception:
        pass

def ensure_settings():
    newly_created = not SETTINGS_FILE.exists()
    print("DEBUG ensure_settings: SETTINGS_FILE =", SETTINGS_FILE, "newly_created =", newly_created)

    s = load_settings()
    if "games" not in s:
        s["games"] = {}

    # Initialize game records
    for pretty, key in GAME_KEYS.items():
        s["games"].setdefault(key, {
            "vanilla": "",
            "mods": "",
            "dolphin_shortcut": "",
            "dolphin_texture_path": ""  # NEW: Add dolphin texture path
        })
        if newly_created:
            default_mods = _default_mods_dir(pretty)
            s["games"][key]["mods"] = str(default_mods)

    s.setdefault("theme_mode", "Dark Mode")
    if s.get("theme_mode") not in ("Dark Mode", "Storybook Themes"):
        s["theme_mode"] = "Dark Mode"
    s.setdefault("last_game", "Secret Rings")

    save_settings(s)
    return s, newly_created

# 2 First run Helpers, Needed, Correlates withe ensure_settings

def show_first_run_wizard(parent=None):
    """
    Show the first-run welcome + settings flow.
    """
    QMessageBox.information(parent, "Welcome", "Welcome to the Storybook Mod Manager!")
    QMessageBox.information(parent, "Let's Configure Our Settings!", "Let's Configure Our Settings!")
    dlg = SettingsDialog(parent)
    dlg.exec_()

def settings_ready_for_game(settings: dict, game_key: str) -> bool:
    """
    Returns True if the game has non-empty, existing mods and vanilla paths.
    """
    gconf = (settings or {}).get("games", {}).get(game_key, {})
    mods = gconf.get("mods") or ""
    vanilla = gconf.get("vanilla") or ""
    if not mods or not vanilla:
        return False
    try:
        return Path(mods).exists() and Path(vanilla).exists()
    except Exception:
        return False

# -----------------------
# INI & mod helpers
# -----------------------
INI_SECTION = "Mod"
INI_DEFAULTS = {
    "Name": "",
    "Version": "1.0.0",
    "Author": "",
    "AuthorURL": "",
    "UpdateURL": "",
    "Date": "",
    "ID": "",
    "IncludeDirectories": "",
    "Dependencies": "",
    "TexturePackMode": ""  # "copy" or "move"
}

def ensure_mod_ini(mod_folder: Path):
    """
    Only used when editing a mod. Will create mod.ini if missing.
    Scanning should not call this to avoid unintended file creation.
    """
    ini = mod_folder / "mod.ini"
    cp = ConfigParser()
    created = False
    if not ini.exists():
        cp[INI_SECTION] = dict(INI_DEFAULTS)
        cp[INI_SECTION]["Name"] = mod_folder.name
        cp[INI_SECTION]["Date"] = date.today().isoformat()
        try:
            with ini.open("w", encoding="utf-8") as f:
                cp.write(f)
            created = True
        except Exception:
            try:
                ini.write_text("", encoding="utf-8")
            except Exception:
                pass
    try:
        cp.read(ini, encoding="utf-8")
    except Exception:
        cp = ConfigParser()
        cp[INI_SECTION] = dict(INI_DEFAULTS)
        cp[INI_SECTION]["Name"] = mod_folder.name
        cp[INI_SECTION]["Date"] = date.today().isoformat()
        try:
            with ini.open("w", encoding="utf-8") as f:
                cp.write(f)
            created = True
        except Exception:
            pass
    if not cp.has_section(INI_SECTION):
        cp[INI_SECTION] = dict(INI_DEFAULTS)
        cp[INI_SECTION]["Name"] = mod_folder.name
        cp[INI_SECTION]["Date"] = date.today().isoformat()
        try:
            with ini.open("w", encoding="utf-8") as f:
                cp.write(f)
        except Exception:
            pass
    return cp, ini, created

def _read_mod_meta_from_ini(ini_path: Path):
    meta = {}
    try:
        cp = ConfigParser()
        cp.read(ini_path, encoding="utf-8")
        g = lambda k, d="": cp.get(INI_SECTION, k, fallback=d)
        meta["name"] = g("Name", ini_path.parent.name)
        meta["version"] = g("Version", "")
        meta["author"] = g("Author", "")
        meta["author_url"] = g("AuthorURL", "")
        meta["update"] = g("UpdateURL", "")
    except Exception:
        meta["name"] = ini_path.parent.name
    return meta

def scan_mods_folder(mods_root: Path):
    """
    Scan the mods folder:
    - Include direct subfolders as mods, reading mod.ini if present (but never creating it).
    - Also include any subfolder (at any depth) that contains a mod.ini (useful for nested categories).
    """
    mods = []
    if not mods_root or not mods_root.exists():
        return mods

    seen = set()

    # 1) Direct children as mods (do not create any files)
    for child in sorted(mods_root.iterdir()):
        if child.is_dir():
            # 🔥 Auto-migrate legacy JSONs into mod_data.json
            try:
                migrate_mod_jsons(child)
            except Exception:
                pass

            ini = child / "mod.ini"
            meta = {"name": child.name, "path": child}
            if ini.exists():
                meta.update(_read_mod_meta_from_ini(ini))

            mods.append(meta)
            seen.add(child.resolve())

    # 2) Nested mods (directories with mod.ini at any depth)
    for dirpath, dirnames, filenames in os.walk(mods_root):
        p = Path(dirpath)
        if p.resolve() in seen:
            continue
        if "mod.ini" in filenames:
            # 🔥 Auto-migrate legacy JSONs into mod_data.json
            try:
                migrate_mod_jsons(p)
            except Exception:
                pass

            ini = p / "mod.ini"
            meta = {"name": p.name, "path": p}
            meta.update(_read_mod_meta_from_ini(ini))
            mods.append(meta)
            seen.add(p.resolve())

    return mods

def scan_folder_extensions(root: Path):
    counts = {}
    files_list = []
    for dirpath, _, filenames in os.walk(root, followlinks=True):
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            counts[ext] = counts.get(ext, 0) + 1
            files_list.append(Path(dirpath) / fname)
    return counts, files_list

def validate_mod_against_allowed(mod_folder: Path, allowed: set, require_exts=None):
    counts, files_list = scan_folder_extensions(mod_folder)
    disallowed = [e for e in counts.keys() if e not in allowed]
    missing = []
    if require_exts:
        for r in require_exts:
            if r.lower() not in counts:
                missing.append(r)
    valid = (len(disallowed) == 0) and (len(missing) == 0)
    return valid, disallowed, missing, counts, files_list

def migrate_mod_jsons(mod_folder: Path):
    """
    Merge legacy scattered JSONs into mod_data.json if not already present.
    This consolidates:
      - config_schema.json
      - config_schema_files.json
      - config.json
      - applied_files.json
    into one unified file with section headers.
    """
    data_file = mod_folder / "mod_data.json"
    if data_file.exists():
        return  # already migrated

    merged = {}

    schema_path = mod_folder / "config_schema.json"
    attach_path = mod_folder / "config_schema_files.json"
    config_path = mod_folder / "config.json"
    applied_path = mod_folder / "applied_files.json"

    # Schema + attachments
    if schema_path.exists() or attach_path.exists():
        schema = {}
        attachments = {}
        if schema_path.exists():
            try:
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        if attach_path.exists():
            try:
                attachments = json.loads(attach_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        merged["SET CONFIGURE SCHEMA"] = {
            "schema": schema,
            "attachments": attachments
        }

    # Runtime config
    if config_path.exists():
        try:
            merged["CONFIGURE MOD MENU"] = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Applied files
    if applied_path.exists():
        try:
            merged["APPLIED FILES"] = json.loads(applied_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if merged:
        data_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")

        # Clean up old files after merging
        for f in (schema_path, attach_path, config_path, applied_path):
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                pass

# -----------------------
# Archive helpers (single compressed archive per game)
# -----------------------
def archive_path_for(game_key: str) -> Path:
    return TEMP_DIR / f"{game_key}.bin"

def load_archive(game_key: str) -> dict:
    """Load archive bytes map: {posix_rel_path: bytes}. Returns {} on missing/invalid."""
    p = archive_path_for(game_key)
    if not p.exists():
        return {}
    try:
        comp = p.read_bytes()
        raw = zlib.decompress(comp)
        obj = json.loads(raw.decode("utf-8"))
        return {k: base64.b64decode(v.encode("utf-8")) for k, v in obj.items()}
    except Exception as e:
        print(f"[error] load_archive failed for {game_key}: {e}")
        return {}


def save_archive(game_key: str, archive: dict):
    """
    Save the per-game archive into Temp_File.
    - If archive is empty, delete the .bin file.
    - If archive has entries, compress and write it.
    """
    archive_path = archive_path_for(game_key)
    try:
        if not archive:
            if archive_path.exists():
                archive_path.unlink()
                print(f"[archive] Deleted empty archive at {archive_path}")
            return

        safe = {str(k): base64.b64encode(v).decode("utf-8") for k, v in archive.items()}
        raw = json.dumps(safe).encode("utf-8")
        comp = zlib.compress(raw, level=9)

        tmp = archive_path.with_suffix(".bin.tmp")
        tmp.write_bytes(comp)
        os.replace(tmp, archive_path)
        print(f"[archive] Saved {len(archive)} entries to {archive_path}")
    except Exception as e:
        print(f"[error] save_archive failed for {game_key}: {e}")

def backup_and_replace_file_to_archive(original: Path, mod_file: Path,
                                       game_key: str, vanilla_root: Path,
                                       archive: dict, log_fn=print):
    # Normalize key as posix
    try:
        rel_key = original.relative_to(vanilla_root).as_posix()
    except Exception:
        rel_key = original.name

    if rel_key not in archive and original.exists():
        try:
            archive[rel_key] = original.read_bytes()
            log_fn(f"[backup] stored {rel_key} ({len(archive[rel_key])} bytes)")
        except Exception as e:
            log_fn(f"[error] backup read failed {original}: {e}")
            return False
    elif rel_key in archive:
        log_fn(f"[backup] {rel_key} already backed up ({len(archive[rel_key])} bytes)")
    else:
        log_fn(f"[backup] WARNING: {original} does not exist, cannot backup!")

    try:
        shutil.copy2(mod_file, original)
        log_fn(f"[replace] {mod_file} -> {original}")
        return True
    except Exception as e:
        log_fn(f"[error] copy failed {mod_file} -> {original}: {e}")
        return False

def restore_files_for_mod(mod_path: Path, game_key: str,
                          vanilla_root: Path, log_fn=print):
    """
    Restore originals for 'APPLIED FILES', prune archive, clear JSON,
    and clean mod-specific temp traces. Guarantees delete when empty.
    """
    archive = load_archive(game_key)
    log_fn(f"[restore] Loading archive for {game_key}, found {len(archive)} backed up files")

    data_file = mod_path / "mod_data.json"
    if not data_file.exists():
        log_fn(f"[restore] No mod_data.json for {mod_path.name}")
        return []

    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except Exception as e:
        log_fn(f"[restore] Could not read mod_data.json: {e}")
        return []

    applied = data.get("APPLIED FILES", [])
    if not applied:
        log_fn(f"[restore] No applied files recorded for {mod_path.name}")
        if not archive:
            save_archive(game_key, archive)  # will delete if empty
        return []

    restored = []
    for rel in applied:
        rel_key = Path(rel).as_posix()
        if rel_key not in archive:
            log_fn(f"[restore] Missing backup for {rel}")
            continue

        dst = vanilla_root / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(archive[rel_key])
            restored.append(rel)
            log_fn(f"[restore] Restored {rel}")
            del archive[rel_key]
        except Exception as e:
            log_fn(f"[restore] Failed to restore {rel}: {e}")

    log_fn(f"[debug] archive keys before finalize: {list(archive.keys())}")

    # Finalize: delete if empty; otherwise save
    save_archive(game_key, archive)

    # Clear APPLIED FILES
    try:
        data["APPLIED FILES"] = []
        data_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        log_fn(f"[restore] Failed to update mod_data.json: {e}")

    # Clean scratch for this mod only
    try:
        sys_temp = Path(tempfile.gettempdir())
        for rel in applied:
            name = Path(rel).name
            f = sys_temp / f"{mod_path.name}__{name}"
            if f.exists():
                f.unlink()
                log_fn(f"[restore] cleaned system temp file {f.name}")

        for f in TEMP_DIR.glob(f"{mod_path.name}__*"):
            f.unlink(missing_ok=True)
            log_fn(f"[restore] cleaned app temp file {f.name}")
    except Exception as e:
        log_fn(f"[restore] could not clean temp files: {e}")

    return restored

# -----------------------
# UI asset helpers
# -----------------------
def find_ui_icon(base_name: str, suffix_label: str):
    ui = UI_DIR
    if not ui.exists():
        return None
    for f in sorted(ui.iterdir()):
        name = f.stem
        if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".ico"):
            if name.lower().endswith((" - " + suffix_label).lower()) and base_name.lower() in name.lower():
                return f
    for f in sorted(ui.iterdir()):
        name = f.stem
        if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".ico"):
            if name.lower().endswith((" - " + suffix_label).lower()):
                return f
    return None

def find_settings_overview_banner(game_name: str):
    path = find_ui_icon(game_name, "Settings Overview")
    return path if path and Path(path).exists() else None

# -----------------------
# Global UI helpers (flash feedback)
# -----------------------
def flash_button(widget):
    if isinstance(widget, (QPushButton, QToolButton)):
        orig = widget.styleSheet() or ""
        flash_css = "\nQPushButton, QToolButton { background-color: rgba(255,255,255,0.22); }"
        try:
            widget.setStyleSheet(orig + flash_css)
        except Exception:
            widget.setStyleSheet(flash_css)
        t = QTimer(widget)
        t.setSingleShot(True)
        t.setInterval(140)
        def restore():
            try:
                widget.setStyleSheet(orig)
            except Exception:
                pass
        t.timeout.connect(restore)
        t.start()

def hook_flash(button):
    if isinstance(button, (QPushButton, QToolButton)):
        button.pressed.connect(lambda b=button: flash_button(b))

def beef_up_buttons(btn_box: QDialogButtonBox):
    for b in btn_box.buttons():
        b.setMinimumHeight(38)
        b.setMinimumWidth(94)
        b.setAutoDefault(False)
        b.setDefault(False)
        hook_flash(b)

# -----------------------
# Update helpers (network + parsing)
# -----------------------
def fetch_text(url: str, timeout=10):
    headers = {"User-Agent": "StorybookMM/1.0"}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as r:
            ct = r.headers.get("Content-Type", "")
            data = r.read()
            try:
                text = data.decode("utf-8", errors="ignore")
            except Exception:
                text = data.decode("latin-1", errors="ignore")
            return text, ct, None
    except Exception as e:
        return None, None, str(e)

def compare_versions(v1, v2):
    def normalize(v):
        return [int(x) for x in str(v).split('.') if x.isdigit()]
    a, b = normalize(v1), normalize(v2)
    length = max(len(a), len(b))
    a += [0] * (length - len(a))
    b += [0] * (length - len(b))
    return (a > b) - (a < b)

def normalize_version_token(token: str):
    nums = token.strip().split(".")
    nums = [n for n in nums if n != ""]
    while len(nums) < 3:
        nums.append("0")
    return ".".join(nums[:3])

def extract_mod_id(url: str) -> str:
    """Extract the mod ID from a GameBanana URL."""
    if not url:
        return None
    
    # Try to find a number at the end of the URL
    match = re.search(r'/(\d+)(?:/|$)', url)
    if match:
        return match.group(1)
    return None

def normalize_gamebanana_url(url: str) -> str:
    """Convert to GameBanana API URL to get mod info directly."""
    print(f"\n[DEBUG] Processing URL: {url}")
    
    mod_id = extract_mod_id(url)
    if mod_id:
        api_url = f"https://gamebanana.com/apiv11/Mod/{mod_id}?_csvProperties=_sName,_aSubmitter,_sVersion"
        print(f"[DEBUG] Using API URL: {api_url}")
        return api_url
    
    print("[DEBUG] Could not extract mod ID, using original URL")
    return url

def get_latest_version_and_title(url):
    if not url:
        print("[DEBUG] Error: No URL provided")
        return None, None
        
    try:
        print("\n" + "="*50)
        print(f"[DEBUG] Starting version check for URL: {url}")
        
        # Convert mod page URL to updates page URL
        original_url = url
        url = normalize_gamebanana_url(url)
        print(f"[DEBUG] Normalized URL: {url}")
        
        print("\n[DEBUG] Attempting to fetch URL...")
        try:
            response = requests.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }, timeout=10)
            print(f"[DEBUG] Response code: {response.status_code}")
            print(f"[DEBUG] Response type: {response.headers.get('content-type', 'unknown')}")
        except Exception as e:
            print(f"[DEBUG] Request failed: {str(e)}")
            return None, None
        
        if response.status_code != 200:
            print(f"[DEBUG] Bad response code: {response.status_code}")
            # Try original URL if normalized URL failed
            if url != original_url:
                print("[DEBUG] Trying original URL as fallback...")
                response = requests.get(original_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }, timeout=10)
        
        print(f"[DEBUG] Final response status: {response.status_code}")
        if response.status_code != 200:
            print("[DEBUG] Both URLs failed")
            return None, None
            
        html = response.text
        print(f"[DEBUG] HTML length: {len(html)}")
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Print all update elements found
        updates = soup.select(".UpdateModule")
        print(f"[DEBUG] Found {len(updates)} update modules")
        titles = soup.select(".UpdateTitle")
        print(f"[DEBUG] Found {len(titles)} update titles")

        print("\n[DEBUG] Checking API response...")
        
        try:
            # For API responses
            data = response.json()
            print(f"[DEBUG] API response: {data}")
            
            if isinstance(data, dict):
                version = data.get("_sVersion")
                if version:
                    version = normalize_version_token(version)
                    print(f"[DEBUG] Found version from API: {version}")
                    return version, "Latest Update"
                    
            print("[DEBUG] No version found in API response]")
            
        except ValueError:
            # If not JSON, try parsing HTML
            print("[DEBUG] Not an API response, parsing as HTML...]")
            
            # First look in update page header
            update_header = soup.select_one("._vpUpdates")
            if update_header:
                print(f"[DEBUG] Found update header: {update_header.get_text(strip=True)}")
                match = re.search(r'(\d+\.(?:\d+)?)', update_header.get_text(strip=True))
                if match:
                    version = normalize_version_token(match.group(1))
                    print(f"[DEBUG] Found version in update header: {version}")
                    return version, "Latest Update"
            
            # Try page title and description
            for meta in soup.find_all("meta", property=["og:title", "og:description"]):
                content = meta.get("content", "")
                print(f"[DEBUG] Checking meta content: {content}")
                match = re.search(r'(?:Version\s*)?(\d+\.(?:\d+)?)', content)
                if match:
                    version = normalize_version_token(match.group(1))
                    print(f"[DEBUG] Found version in meta: {version}")
                    return version, "Latest Update"
                
        # Fallback: check the update module content
        latest_update = soup.select_one(".UpdateModule")
        if latest_update:
            print("[DEBUG] Found update module")
            text = latest_update.get_text(" ", strip=True)
            print(f"[DEBUG] Raw update text: {text}")
            
            # Try to find version number in the update title first
            update_title = latest_update.select_one(".UpdateTitle")
            if update_title:
                title_text = update_title.get_text(strip=True)
                print(f"[DEBUG] Update title: {title_text}")
                
            # Look for version patterns like "Version 2.1" or "v2.1"
            match = re.search(r'(?:Version\s*|V\s*)(\d+(?:\.\d+)*)', text, re.IGNORECASE)
            if match:
                version = match.group(1)
                version = normalize_version_token(version)
                print(f"[DEBUG] Explicit version found: {version}")
                return version, "Latest Update"
                
            # Then look for version numbers after mod name (e.g. "Mod Name 2.1")
            match = re.search(r'(?:[^\d]|^)(\d+\.\d+)(?:[^\d]|$)', text)
            if match:
                version = match.group(1)
                version = normalize_version_token(version)
                print(f"[DEBUG] Version after name found: {version}")
                return version, "Latest Update"
                
            # Last fallback: any isolated number pattern
            match = re.search(r'(?:[^\d]|^)(\d+(?:\.\d+)*)(?:[^\d]|$)', text)
            if match:
                version = normalize_version_token(match.group(1))
                print(f"[DEBUG] Fallback version found: {version}")
                return version, "Latest Update"
            # Fallback to update date if no version found
            latest_date = latest_update.select_one(".UpdateDate")
            if latest_date:
                return latest_date.get_text(strip=True), "Latest Update (by date)"
        # Try looking at the update title directly
        update_title = soup.select_one(".UpdateTitle")
        if update_title:
            title_text = update_title.get_text(strip=True)
            print(f"[DEBUG] Update title text: {title_text}")
            match = re.search(r'(?:[^\d]|^)(\d+\.\d+)(?:[^\d]|$)', title_text)
            if match:
                version = normalize_version_token(match.group(1))
                print(f"[DEBUG] Version from title: {version}")
                return version, "Latest Update"
                
        print(f"[DEBUG] No version found in latest update block on {url}")
        return None, None
    except Exception as e:
        print(f"[Updater] Failed to fetch version: {e}")
        return None, None

def extract_app_version_from_script(text: str):
    """
    Parse APP_VERSION = "x.y.z" from remote script.
    """
    if not text:
        return None
    m = re.search(r'APP_VERSION\s*=\s*["\']([0-9]+(?:\.[0-9]+){0,2})["\']', text)
    if not m:
        return None
    tok = m.group(1)
    return normalize_version_token(tok)

# -----------------------
# FileMappingDialog
# -----------------------
class FileMappingDialog(QDialog):
    def __init__(self, parent, mod_folder: Path, files_override=None):
        super().__init__(parent)
        self.setWindowTitle("Map Mod Files to Game Filenames")
        self.resize(640, 420)
        self.mod_folder = mod_folder
        self.mapping_file = mod_folder / "file_mappings.json"

        if files_override is None:
            files = []
            for dirpath, _, filenames in os.walk(mod_folder):
                rel_dir = Path(dirpath).relative_to(mod_folder)
                if str(rel_dir).startswith("UI"):
                    continue
                for fname in filenames:
                    p = Path(dirpath) / fname
                    if p.name in ("mod.ini", "config_schema.json", "config.json", "config_schema_files.json", "preview.png", "file_mappings.json", "packed_files.bin"):
                        continue
                    rel = p.relative_to(mod_folder)
                    files.append(rel.as_posix())
            try:
                packed = _sb_read_packed_index(mod_folder)
                for name in packed.keys():
                    files.append(f"packed::{name}")
            except Exception:
                pass
        else:
            files = list(files_override)

        main = QVBoxLayout(self)
        self.entries = []

        if not files:
            main.addWidget(QLabel("No packable files detected in this mod. You can skip mapping and edit later."))
        else:
            main.addWidget(QLabel("Map the files in the mod to the target filenames in the game root."))
            scroll = QScrollArea()
            cont = QWidget()
            cont_layout = QVBoxLayout(cont)
            for f in files:
                row = QHBoxLayout()
                lbl = QLabel(f)
                inp = QLineEdit(f)
                inp.setMinimumHeight(30)
                row.addWidget(lbl, 3)
                row.addWidget(inp, 2)
                cont_layout.addLayout(row)
                self.entries.append((f, inp))
            cont.setLayout(cont_layout)
            scroll.setWidgetResizable(True)
            scroll.setWidget(cont)
            main.addWidget(scroll)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        beef_up_buttons(btns)
        btns.accepted.connect(self.on_save)
        btns.rejected.connect(self.reject)
        main.addWidget(btns)

        self.setStyleSheet("""
            QLineEdit, QTextEdit, QComboBox, QListWidget {
                background-color: #1A1A1A; color: #E6E6E6; border: 1px solid #333;
                selection-background-color: #3A3A3A;
            }
            QPushButton { min-height: 38px; padding: 6px 12px; }
            QToolButton { padding: 6px 12px; }
            QPushButton:pressed, QToolButton:pressed { padding: 6px 12px; margin: 0px; background-color: rgba(255,255,255,0.12); }
        """)

    def on_save(self):
        mapping = {}
        for orig, widget in self.entries:
            target = widget.text().strip()
            if target and target != orig:
                mapping[orig] = target
        try:
            self.mapping_file.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
            QMessageBox.information(self, "Saved", "File mappings saved.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Could not save mappings: {e}")

# -----------------------
# RenameChoiceFilesDialog — bulk rename/delete mapped files
# -----------------------
class RenameChoiceFilesDialog(QDialog):
    def __init__(self, parent, attachments: dict, dd_key: str, choice_name: str):
        super().__init__(parent)
        self.setWindowTitle(f"Rename/Delete Mod Files — [{choice_name}]")
        self.resize(600, 540)
        self.attachments = attachments
        self.dd_key = dd_key
        self.choice_name = choice_name

        main = QVBoxLayout(self)

        info = QLabel("Edit target filenames (right boxes). Delete rows to remove individual mappings.")
        main.addWidget(info)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        cont = QWidget()
        self.rows_layout = QVBoxLayout(cont)

        self.rows = []
        files = self.attachments.get(dd_key, {}).get(choice_name, {}).get("files", [])
        if not files:
            self.rows_layout.addWidget(QLabel("No mapped files for this choice."))
        else:
            for fm in list(files):
                roww = QHBoxLayout()
                src = fm.get("src", "")
                dst = fm.get("dst", "")
                src_name = src.split("::", 1)[1] if isinstance(src, str) and src.startswith("packed::") else Path(src).name
                src_lbl = QLabel(f"Mod file: {src_name} →")
                dst_edit = QLineEdit(dst)
                dst_edit.setMinimumHeight(34)
                btn_del = QPushButton("Delete")
                btn_del.setMinimumHeight(34)
                hook_flash(btn_del)
                roww.addWidget(src_lbl, 2)
                roww.addWidget(dst_edit, 3)
                roww.addWidget(btn_del, 1)
                frame = QFrame()
                lay = QVBoxLayout(frame)
                lay.setContentsMargins(0,0,0,0)
                lay.addLayout(roww)
                self.rows_layout.addWidget(frame)
                self.rows.append((fm, dst_edit, frame))
                btn_del.clicked.connect(lambda _, fm=fm, fr=frame: self._delete_row(fm, fr))

        self.rows_layout.addStretch(1)
        cont.setLayout(self.rows_layout)
        self.scroll.setWidget(cont)
        main.addWidget(self.scroll)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        beef_up_buttons(btns)
        btns.accepted.connect(self.on_save)
        btns.rejected.connect(self.reject)
        main.addWidget(btns)

        self.setStyleSheet("""
            QLineEdit, QTextEdit, QComboBox, QListWidget {
                background-color: #1A1A1A; color: #E6E6E6; border: 1px solid #333;
                selection-background-color: #3A3A3A;
            }
            QPushButton { min-height: 38px; padding: 6px 12px; }
            QToolButton { padding: 6px 12px; }
            QPushButton:pressed, QToolButton:pressed { padding: 6px 12px; margin: 0px; background-color: rgba(255,255,255,0.12); }
        """)
        handify_buttons_in(self)

    def _delete_row(self, fm, frame):
        try:
            files = self.attachments.get(self.dd_key, {}).get(self.choice_name, {}).get("files", [])
            if fm in files:
                files.remove(fm)
            frame.setParent(None)
        except Exception:
            pass

    def on_save(self):
        try:
            files = self.attachments.get(self.dd_key, {}).get(self.choice_name, {}).get("files", [])
            for fm, dst_edit, _fr in self.rows:
                if fm in files:
                    fm["dst"] = dst_edit.text().strip() or fm.get("dst", "")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Could not save changes: {e}")

# -----------------------
# DeleteChoiceFilesDialog — selective delete mapped files
# -----------------------
class DeleteChoiceFilesDialog(QDialog):
    def __init__(self, parent, attachments: dict, dd_key: str, choice_name: str, mod_folder: Path):
        super().__init__(parent)
        self.setWindowTitle(f"Remove Mod Files — [{choice_name}]")
        self.resize(520, 480)
        self.attachments = attachments
        self.dd_key = dd_key
        self.choice_name = choice_name
        self.mod_folder = mod_folder

        main = QVBoxLayout(self)
        main.addWidget(QLabel("Select which mapped files to remove from this choice."))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        cont = QWidget()
        self.rows_layout = QVBoxLayout(cont)

        self.rows = []
        files = self.attachments.get(dd_key, {}).get(choice_name, {}).get("files", [])
        if not files:
            self.rows_layout.addWidget(QLabel("No mapped files for this choice."))
        else:
            for fm in list(files):
                roww = QHBoxLayout()
                src = fm.get("src", "")
                dst = fm.get("dst", "")
                src_name = src.split("::", 1)[1] if isinstance(src, str) and src.startswith("packed::") else Path(src).name
                lbl = QLabel(f"{src_name} → {dst}")
                btn_del = QPushButton("Delete")
                btn_del.setMinimumHeight(34)
                hook_flash(btn_del)
                roww.addWidget(lbl, 4)
                roww.addWidget(btn_del, 1)
                frame = QFrame()
                lay = QVBoxLayout(frame)
                lay.setContentsMargins(0,0,0,0)
                lay.addLayout(roww)
                self.rows_layout.addWidget(frame)
                self.rows.append((fm, frame))
                btn_del.clicked.connect(lambda _, fm=fm, fr=frame: self._delete_one(fm, fr))

        self.rows_layout.addStretch(1)
        cont.setLayout(self.rows_layout)
        self.scroll.setWidget(cont)
        main.addWidget(self.scroll)

        controls = QHBoxLayout()
        self.btn_delete_all = QPushButton("Delete All")
        self.btn_delete_all.setMinimumHeight(40)
        hook_flash(self.btn_delete_all)
        self.btn_delete_all.clicked.connect(self._delete_all)
        controls.addStretch(1)
        controls.addWidget(self.btn_delete_all)
        main.addLayout(controls)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        beef_up_buttons(btns)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        main.addWidget(btns)

        self.setStyleSheet("""
            QLineEdit, QTextEdit, QComboBox, QListWidget {
                background-color: #1A1A1A; color: #E6E6E6; border: 1px solid #333;
                selection-background-color: #3A3A3A;
            }
            QPushButton { min-height: 38px; padding: 6px 12px; }
            QToolButton { padding: 6px 12px; }
            QPushButton:pressed, QToolButton:pressed { padding: 6px 12px; margin: 0px; background-color: rgba(255,255,255,0.12); }
        """)
        handify_buttons_in(self)

    def _delete_one(self, fm, frame):
        try:
            src = fm.get("src", "")
            to_remove = []
            if isinstance(src, str) and src.startswith("packed::"):
                to_remove.append(src.split("::", 1)[1])
            if to_remove:
                _sb_remove_packed_names(self.mod_folder, to_remove)
            files = self.attachments.get(self.dd_key, {}).get(self.choice_name, {}).get("files", [])
            if fm in files:
                files.remove(fm)
            frame.setParent(None)
        except Exception:
            pass

    def _delete_all(self):
        try:
            files = self.attachments.get(self.dd_key, {}).get(self.choice_name, {}).get("files", [])
            packed_to_remove = []
            for fm in files or []:
                src = fm.get("src", "")
                if isinstance(src, str) and src.startswith("packed::"):
                    packed_to_remove.append(src.split("::", 1)[1])
            if packed_to_remove:
                _sb_remove_packed_names(self.mod_folder, packed_to_remove)
            self.attachments[self.dd_key][self.choice_name]["files"] = []
            for _fm, frame in self.rows:
                frame.setParent(None)
            self.rows = []
        except Exception:
            pass

# -----------------------
# OrderableListWidget - Custom list widget with smooth drag-drop
# -----------------------
class OrderableListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setSpacing(2)
        self.drag_start_index = None
        self.current_drag_item = None
        self.drop_indicator_pos = None
        self.setStyleSheet("""
            QListWidget {
                background-color: #1A1A1A;
                color: #E6E6E6;
                border: 1px solid #333;
                padding: 2px;
            }
            QListWidget::item {
                border-radius: 4px;
                margin: 2px;
                background: transparent;  /* keep items transparent */
            }
            QListWidget::item:hover {
                background: transparent;
            }
            QListWidget::item:selected {
                background: transparent;
            }
            QListWidget::item:selected:active {
                background: transparent;
            }
        """)
        
    def startDrag(self, supportedActions):
        self.drag_start_index = self.currentRow()
        self.current_drag_item = self.currentItem()
        super().startDrag(supportedActions)
        
    def dragEnterEvent(self, event):
        if event.source() == self:
            event.accept()
            self.setState(QListWidget.DraggingState)
        else:
            event.ignore()
            
    def dragMoveEvent(self, event):
        if event.source() == self:
            event.accept()
            # Calculate drop indicator position
            pos = event.pos()
            index = self.indexAt(pos)
            rect = self.visualRect(index)
            self.drop_indicator_pos = pos
            self.viewport().update()
        else:
            event.ignore()
            
    def dragLeaveEvent(self, event):
        self.drop_indicator_pos = None
        self.viewport().update()
        super().dragLeaveEvent(event)
        
    def dropEvent(self, event):
        if event.source() == self:
            event.accept()

            # Let Qt handle the basic move
            super().dropEvent(event)

            # Sync backing data only; do NOT rebuild here (causes duplication)
            if hasattr(self.parent(), '_sync_previews_from_list'):
                self.parent()._sync_previews_from_list()
        else:
            event.ignore()

        self.drop_indicator_pos = None
        self.viewport().update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        
        # Draw drop indicator
        if self.drop_indicator_pos:
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor("#4A90E2"), 2, Qt.SolidLine))
            
            # Calculate indicator position
            index = self.indexAt(self.drop_indicator_pos)
            rect = self.visualRect(index)
            
            # Draw line
            y = rect.top() if self.drop_indicator_pos.y() < rect.center().y() else rect.bottom()
            painter.drawLine(0, y, self.viewport().width(), y)

class PictureOrderDialog(QDialog):
    STYLE = """
        QDialog { background-color: #121212; }

        QLabel { color: #E6E6E6; }

        QLineEdit { background-color: #141414; color: #E6E6E6; border: 1px solid #2b2b2b; padding: 6px; border-radius: 4px; }
        QLineEdit:focus { border: 1px solid #444; outline: none; }

        QPushButton { background-color: #202020; color: #E6E6E6; border: 1px solid #333; padding: 6px 10px; border-radius: 6px; }
        QPushButton:hover { background-color: rgba(255,255,255,0.04); }

        .thumb-frame { border: 1px solid #3b3b3b; border-radius: 6px; background: transparent; }

        QListWidget, QListView { background: transparent; border: none; }

        QListWidget::item, QListView::item {
            outline: none;
            border: none;
            selection-background-color: transparent;
        }

        QListView::item:selected, QListWidget::item:selected {
            selection-background-color: transparent;
        }

        QWidget#row_container { border-radius: 6px; outline: none; }
    """

    class NoFocusDelegate(QStyledItemDelegate):
        def paint(self, painter, option, index):
            opt = QStyleOptionViewItem(option)
            opt.state &= ~QStyle.State_HasFocus
            super().paint(painter, opt, index)

    class ReorderList(QListWidget):
        class Overlay(QWidget):
            def __init__(self, parent_list):
                super().__init__(parent_list.viewport())
                self.list = parent_list
                self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                self.setAttribute(Qt.WA_NoSystemBackground, True)
                self.setGeometry(parent_list.viewport().rect())
                self.raise_()

            def paintEvent(self, ev):
                painter = QPainter(self)
                self.list._overlay_paint(painter)
                painter.end()

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setSelectionMode(QAbstractItemView.SingleSelection)
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(False)
            self.setDragDropMode(QAbstractItemView.InternalMove)
            self.setDefaultDropAction(Qt.MoveAction)
            self.setSpacing(10)
            self.setMouseTracking(True)
            self.setDragDropOverwriteMode(False)  # never overwrite row widgets on drop

            # precise hotspot tracking for top-row and scrolling accuracy
            self._press_pos = None
            self._press_item_rect = None

            self._drag_pos = None
            self._drag_row = None
            self._dragging = False

            # last computed target index and rect (for snapping)
            self._target_index = -1
            self._target_rect = QRect()

            self._overlay = self.Overlay(self)
            self.viewport().installEventFilter(self)

        def eventFilter(self, obj, ev):
            # keep overlay synced on viewport changes (resize/show/scroll/update)
            if obj is self.viewport() and ev.type() in (QEvent.Resize, QEvent.Show, QEvent.Wheel, QEvent.UpdateRequest):
                self._overlay.setGeometry(self.viewport().rect())
                self._overlay.raise_()
                self._overlay.update()
            return super().eventFilter(obj, ev)

        def mousePressEvent(self, ev):
            # record press for hotspot math (helps accuracy when dragging from top row and while scrolled)
            self._press_pos = ev.pos()
            idx = self.indexAt(self._press_pos)
            self._press_item_rect = self.visualRect(idx) if idx.isValid() else None
            super().mousePressEvent(ev)

        def _compute_drop_target(self, pos: QPoint):
            """Compute drop target index and rect based on cursor position for snap-friendly behavior."""
            idx = self.indexAt(pos)
            if idx.isValid():
                rect = self.visualRect(idx)
                # Snap to top half -> insert before; bottom half -> insert after
                insert_before = pos.y() < rect.center().y()
                target_index = idx.row() if insert_before else idx.row() + 1
                # clamp
                target_index = max(0, min(target_index, self.count()))
                target_rect = rect
            else:
                # No valid row under cursor — decide based on Y relative to last row
                if self.count() > 0:
                    last_rect = self.visualRect(self.model().index(self.count() - 1, 0))
                    if pos.y() <= last_rect.top():
                        target_index = self.count() - 1
                        target_rect = last_rect
                    else:
                        target_index = self.count()
                        target_rect = QRect(last_rect.left(), last_rect.bottom(), last_rect.width(), last_rect.height())
                else:
                    target_index = 0
                    target_rect = QRect(8, 10, self.viewport().width() - 16, 60)

            self._target_index = target_index
            self._target_rect = target_rect

        def _overlay_paint(self, painter: QPainter):
            # full-row drop zone highlight for cleaner visuals and better accuracy
            if self._drag_pos is None:
                return

            self._compute_drop_target(self._drag_pos)

            # Avoid flicker when hovering in same segment (allow moving from top row down)
            if self._drag_row is not None and (self._target_index == self._drag_row or self._target_index == self._drag_row + 1):
                # Still draw target highlight to guide the user visually
                pass

            rect = self._target_rect.adjusted(4, 2, -4, -2)
            painter.setOpacity(0.28)
            painter.fillRect(rect, QColor("#4A90E2"))
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor("#4A90E2"), 1))
            painter.drawRoundedRect(rect, 6, 6)

            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#E6F0FF"))
            painter.drawText(rect, Qt.AlignCenter, "Drop to insert here")

        def startDrag(self, supportedActions):
            # use system drag; rely on hotspot tracking for top-row accuracy
            it = self.currentItem()
            if it:
                self._drag_row = self.row(it)
                self._dragging = True
            super().startDrag(supportedActions)

        def mouseMoveEvent(self, ev):
            if self._dragging:
                self._drag_pos = ev.pos()
                self._overlay.update()
            super().mouseMoveEvent(ev)

        def dragEnterEvent(self, ev):
            if ev.source() == self:
                ev.accept()
            else:
                ev.ignore()

        def dragMoveEvent(self, ev):
            if ev.source() == self:
                ev.accept()
                self._drag_pos = ev.pos()
                self._overlay.update()
            else:
                ev.ignore()

        def dragLeaveEvent(self, ev):
            ev.accept()
            self._drag_pos = None
            self._drag_row = None
            self._dragging = False
            self._overlay.update()

        def dropEvent(self, ev):
            if ev.source() == self:
                # capture descriptions BEFORE Qt shuffles widgets
                desc_by_ref = {}
                for i in range(self.count()):
                    it = self.item(i)
                    ref = it.data(Qt.UserRole)
                    w = self.itemWidget(it)
                    if w:
                        edits = w.findChildren(QLineEdit)
                        desc_by_ref[ref] = (edits[0].text().strip() if edits else "")
                    else:
                        desc_by_ref[ref] = ""

                # Let Qt perform InternalMove first (this updates model order)
                ev.setDropAction(Qt.MoveAction)
                ev.accept()
                super().dropEvent(ev)

                # Recompute new order strictly from items to avoid duplication and widget loss
                new_order = []
                seen = set()
                for i in range(self.count()):
                    it = self.item(i)
                    ref = it.data(Qt.UserRole)
                    if not ref or ref == "__placeholder__":
                        continue
                    if ref in seen:
                        continue
                    seen.add(ref)
                    new_order.append({"ref": ref, "desc": desc_by_ref.get(ref, "")})

                # Apply the new order atomically to dialog state, then rebuild rows to avoid widget detachment issues
                dlg = self.window()
                if hasattr(dlg, "previews"):
                    dlg.previews = new_order
                    dlg._rebuild_list_select(None)
            else:
                ev.ignore()

            # cleanup ui artifacts
            self._drag_pos = None
            self._drag_row = None
            self._dragging = False
            self._overlay.update()

            for i in range(self.count()):
                it = self.item(i)
                it.setBackground(QBrush(Qt.transparent))
            self.clearSelection()

            dlg = self.window()
            if hasattr(dlg, "_on_list_reordered"):
                dlg._on_list_reordered()

        def paintEvent(self, event):
            super().paintEvent(event)
            if self._overlay:
                self._overlay.raise_()

    class RowContainer(QWidget):
        def __init__(self, parent_dialog):
            super().__init__()
            self.parent_dialog = parent_dialog
            self.setObjectName("row_container")
            self.setCursor(Qt.SizeAllCursor)
            self.setFocusPolicy(Qt.NoFocus)
            self.setAttribute(Qt.WA_StyledBackground, True)
            # Ensure the row doesn't accept drops itself; let the list handle them
            self.setAcceptDrops(False)

        def mousePressEvent(self, ev):
            lw = self.parent_dialog.listw
            for i in range(lw.count()):
                it = lw.item(i)
                if lw.itemWidget(it) is self:
                    lw.setCurrentItem(it)
                    lw.setFocus()
                    break
            super().mousePressEvent(ev)

        def enterEvent(self, ev):
            lw = self.parent_dialog.listw
            for i in range(lw.count()):
                it = lw.item(i)
                if lw.itemWidget(it) is self:
                    if lw.currentItem() is not it:
                        self.setStyleSheet(
                            "background: rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.08); border-radius:6px;")
                    break
            super().enterEvent(ev)

        def leaveEvent(self, ev):
            lw = self.parent_dialog.listw
            for i in range(lw.count()):
                it = lw.item(i)
                if lw.itemWidget(it) is self:
                    if lw.currentItem() is it:
                        self.setStyleSheet(
                            "background: rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.14); border-radius:6px;")
                    else:
                        self.setStyleSheet("")
                    break
            super().leaveEvent(ev)

    def __init__(self, parent, mod_folder: Path, previews: list, temp_packed: dict):
        super().__init__(parent)
        self.setWindowTitle("Change Order / Remove Pictures")
        self.resize(820, 580)
        self.mod_folder = mod_folder
        self.previews = [dict(ref=p.get("ref"), desc=p.get("desc", "")) for p in (previews or [])]
        self.temp_packed = temp_packed or {}

        # state
        self._running_anims = []
        self._thumb_base_w = 360
        self._thumb_base_h = 200
        self._scale = 0.7
        self._move_in_progress = False

        # caches
        self._base_pix_cache = {}
        self._scaled_pix_cache = {}

        main_v = QVBoxLayout(self)
        info = QLabel("Drag items to reorder. Click a row to select. Click empty area to deselect. Edit captions; Delete removes the image.")
        info.setStyleSheet("color:#E6E6E6; padding:6px;")
        main_v.addWidget(info)

        self.listw = self.ReorderList(self)
        self.listw.setMinimumHeight(420)
        self.listw.setItemDelegate(self.NoFocusDelegate(self.listw))
        self.listw.setStyleSheet(self.STYLE + " QListWidget { padding: 8px; }")
        self.listw.itemSelectionChanged.connect(self._on_selection_changed)

        # Deselect on empty-area click: use viewport-local coords
        self.listw.viewport().installEventFilter(self)
        self.listw.installEventFilter(self)

        main_v.addWidget(self.listw, 1)

        bottom_row = QHBoxLayout()
        lbl = QLabel("View size:")
        lbl.setStyleSheet("font-weight:700; font-size:13px; color:#E6E6E6;")
        lbl.setFixedWidth(84)
        bottom_row.addWidget(lbl, 0, Qt.AlignVCenter)

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(40)
        self.size_slider.setMaximum(140)
        self.size_slider.setValue(70)
        self.size_slider.setFixedWidth(220)
        self.size_slider.valueChanged.connect(self._on_slider_changed)
        bottom_row.addWidget(self.size_slider)

        self.size_preview_label = QLabel("70%")
        self.size_preview_label.setFixedWidth(40)
        bottom_row.addWidget(self.size_preview_label)

        bottom_row.addStretch(1)
        self.btn_delete_all = QPushButton("Delete All")
        self.btn_delete_all.setMinimumSize(110, 40)
        self.btn_delete_all.setStyleSheet("""QPushButton { background-color: #6a2222; color: #E6E6E6; border: 1px solid #993333; border-radius:6px; }
                                           QPushButton:hover { background-color: #8b3333; }""")
        self.btn_delete_all.setCursor(Qt.PointingHandCursor)
        hook_flash(self.btn_delete_all)
        self.btn_delete_all.clicked.connect(self._confirm_delete_all)
        bottom_row.addWidget(self.btn_delete_all, 0, Qt.AlignRight)

        main_v.addLayout(bottom_row)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        beef_up_buttons(btns)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        main_v.addWidget(btns)

        self.setStyleSheet(self.STYLE)
        handify_buttons_in(self)

        self._populate_list()

    # ----------- Pixmap caching -----------
    def _load_base_pix(self, ref: str) -> QPixmap:
        if ref in self._base_pix_cache:
            return self._base_pix_cache[ref]
        base = QPixmap()
        try:
            if isinstance(ref, str) and ref.startswith("packed::"):
                name = ref.split("::", 1)[1]
                if name in self.temp_packed:
                    base.loadFromData(self.temp_packed[name])
                else:
                    tmp = _sb_extract_packed_to_temp(self.mod_folder, name)
                    if tmp and tmp.exists():
                        base = QPixmap(str(tmp))
            else:
                file_path = self.mod_folder / ref
                if file_path.exists():
                    base = QPixmap(str(file_path))
        except Exception:
            base = QPixmap()
        if not base or base.isNull():
            base = QPixmap()
        if len(self._base_pix_cache) > 50:
            for k in list(self._base_pix_cache.keys())[:10]:
                self._base_pix_cache.pop(k, None)
        self._base_pix_cache[ref] = base
        return base

    def _get_scaled(self, ref: str, w: int, h: int, mode=Qt.SmoothTransformation) -> QPixmap:
        key = (ref, w, h, 1 if mode == Qt.SmoothTransformation else 0)
        if key in self._scaled_pix_cache:
            return self._scaled_pix_cache[key]
        base = self._load_base_pix(ref)
        if base.isNull():
            out = QPixmap(w, h)
            out.fill(QColor("#333"))
        else:
            out = base.scaled(w, h, Qt.KeepAspectRatio, mode)
        if len(self._scaled_pix_cache) > 500:
            for k in list(self._scaled_pix_cache.keys())[:50]:
                self._scaled_pix_cache.pop(k, None)
        self._scaled_pix_cache[key] = out
        return out

    # ----------- List population -----------
    def add_preview_item(self, p_obj):
        it = QListWidgetItem()
        w = self._make_item_widget(p_obj)
        item_h = int(self._thumb_base_h * self._scale) + 32
        it.setSizeHint(QSize(self.listw.viewport().width() - 24, item_h))
        it.setData(Qt.UserRole, p_obj.get("ref"))
        it.setBackground(QBrush(Qt.transparent))
        self.listw.addItem(it)
        self.listw.setItemWidget(it, w)

    def _populate_list(self):
        self.listw.clear()
        for p in self.previews:
            self.add_preview_item(p)
        QApplication.processEvents()
        self.listw.viewport().update()

    # ----------- Row widgets -----------
    def _make_item_widget(self, p_obj):
        container = self.RowContainer(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(10)

        thumb_frame = QWidget()
        thumb_frame.setProperty("class", "thumb-frame")
        thumb_frame.setAcceptDrops(False)  # ensure row widgets don't swallow list drops
        tf_layout = QVBoxLayout(thumb_frame)
        tf_layout.setContentsMargins(6, 6, 6, 6)
        thumb = QLabel()
        thumb.setAlignment(Qt.AlignCenter)

        ref = p_obj.get("ref")
        w = int(self._thumb_base_w * self._scale)
        h = int(self._thumb_base_h * self._scale)
        pix = self._get_scaled(ref, w, h, Qt.FastTransformation)
        if pix and not pix.isNull():
            thumb.setPixmap(pix)
        thumb.setFixedSize(w, h)
        tf_layout.addWidget(thumb)
        row.addWidget(thumb_frame, 0)

        rc = QVBoxLayout()
        cap_lbl = QLabel("Caption:")
        cap_lbl.setStyleSheet("font-size:12px;")
        cap_edit = QLineEdit(p_obj.get("desc", ""))
        cap_edit.setMinimumHeight(34)
        cap_edit.setStyleSheet("font-size:12px;")
        cap_edit.setAcceptDrops(False)  # prevent editor from swallowing list drops
        rc.addWidget(cap_lbl)
        rc.addWidget(cap_edit)

        # Comfortable spacing below caption
        rc.addSpacing(6)

        btns_row = QHBoxLayout()
        btn_move_up = QPushButton("↑")
        btn_move_up.setFixedSize(36, 28)
        btn_move_up.setCursor(Qt.PointingHandCursor)
        btn_move_up.clicked.connect(lambda _, c=container: self._move_row_with_fade(c, -1))
        hook_flash(btn_move_up)
        btns_row.addWidget(btn_move_up)

        btn_move_down = QPushButton("↓")
        btn_move_down.setFixedSize(36, 28)
        btn_move_down.setCursor(Qt.PointingHandCursor)
        btn_move_down.clicked.connect(lambda _, c=container: self._move_row_with_fade(c, 1))
        hook_flash(btn_move_down)
        btns_row.addWidget(btn_move_down)

        btns_row.addStretch(1)
        btn_del = QPushButton("Delete")
        btn_del.setMinimumHeight(36)
        btn_del.setCursor(Qt.PointingHandCursor)
        hook_flash(btn_del)
        btn_del.clicked.connect(lambda _, c=container: self._delete_widget_row(c))
        btns_row.addWidget(btn_del)
        rc.addLayout(btns_row)
        rc.addStretch(1)

        row.addLayout(rc, 1)

        container.setProperty("preview_ref", ref)
        container._thumb_label = thumb
        container._caption_edit = cap_edit
        container._orig_pix = self._load_base_pix(ref)

        return container

    # ----------- Selection styling -----------
    def _on_selection_changed(self):
        cur = self.listw.currentItem()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            w = self.listw.itemWidget(it)
            if not w:
                continue
            if it is cur:
                w.setStyleSheet("background: rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.14); border-radius:6px;")
            else:
                w.setStyleSheet("")

    # ----------- Slider -----------
    def _on_slider_changed(self, value):
        self._scale = value / 100.0
        self.size_preview_label.setText(f"{value}%")
        self._update_visible_rows_fast()

    def _update_visible_rows_fast(self):
        vp = self.listw.viewport()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            rect = self.listw.visualItemRect(it)
            if not rect.isValid() or not vp.rect().intersects(rect):
                continue  # update visible rows only
            w = self.listw.itemWidget(it)
            if not w:
                continue
            ref = it.data(Qt.UserRole)
            thumb_label = getattr(w, "_thumb_label", None)
            if thumb_label:
                nw = int(self._thumb_base_w * self._scale)
                nh = int(self._thumb_base_h * self._scale)
                pix = self._get_scaled(ref, nw, nh, Qt.FastTransformation)
                thumb_label.setPixmap(pix)
                thumb_label.setFixedSize(nw, nh)
                it.setSizeHint(QSize(self.listw.viewport().width() - 24, nh + 32))
        QApplication.processEvents()
        self.listw.viewport().update()

    # ----------- Delete / Move -----------
    def _delete_widget_row(self, container):
        try:
            ref = container.property("preview_ref")
            self.previews = [p for p in self.previews if p.get("ref") != ref]
            self._rebuild_list_select(None)
        except Exception as e:
            print("_delete_widget_row error:", e)

    def _move_row_with_fade(self, container, direction):
        if self._move_in_progress:
            return
        self._move_in_progress = True
        try:
            ref = container.property("preview_ref")
            idx = None
            for i, p in enumerate(self.previews):
                if p.get("ref") == ref:
                    idx = i
                    break
            if idx is None:
                self._move_in_progress = False
                return
            new_idx = idx + direction
            if new_idx < 0 or new_idx >= len(self.previews):
                self._move_in_progress = False
                return

            eff = container.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(container)
                container.setGraphicsEffect(eff)
            anim_out = QPropertyAnimation(eff, b"opacity", self)
            anim_out.setStartValue(1.0)
            anim_out.setEndValue(0.25)
            anim_out.setDuration(160)
            anim_out.setEasingCurve(QEasingCurve.InOutCubic)

            def after_out():
                try:
                    self._sync_previews_from_list()
                    self.previews.insert(new_idx, self.previews.pop(idx))
                    self._rebuild_list_select(new_idx)
                    if 0 <= new_idx < self.listw.count():
                        nit = self.listw.item(new_idx)
                        nw = self.listw.itemWidget(nit)
                        eff2 = nw.graphicsEffect()
                        if not isinstance(eff2, QGraphicsOpacityEffect):
                            eff2 = QGraphicsOpacityEffect(nw)
                            nw.setGraphicsEffect(eff2)
                        eff2.setOpacity(0.25)
                        anim_in = QPropertyAnimation(eff2, b"opacity", self)
                        anim_in.setStartValue(0.25)
                        anim_in.setEndValue(1.0)
                        anim_in.setDuration(180)
                        anim_in.setEasingCurve(QEasingCurve.OutCubic)
                        anim_in.finished.connect(lambda a=anim_in: self._running_anims.remove(a) if a in self._running_anims else None)
                        anim_in.start()
                        self._running_anims.append(anim_in)
                except Exception as e:
                    print("_move_row_with_fade after_out error:", e)
                finally:
                    self._move_in_progress = False

            anim_out.finished.connect(after_out)
            anim_out.finished.connect(lambda a=anim_out: self._running_anims.remove(a) if a in self._running_anims else None)
            anim_out.start()
            self._running_anims.append(anim_out)
        except Exception as e:
            print("_move_row_with_fade error:", e)
            self._move_in_progress = False

    def _rebuild_list_select(self, select_index):
        self.listw.clear()
        for p in self.previews:
            self.add_preview_item(p)
        QApplication.processEvents()
        self.listw.viewport().update()
        if select_index is not None and 0 <= select_index < self.listw.count():
            it = self.listw.item(select_index)
            self.listw.setCurrentItem(it)
        self._on_selection_changed()

    def _sync_previews_from_list(self):
        new = []
        seen = set()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            ref = it.data(Qt.UserRole)
            if not ref or ref == "__placeholder__":
                continue
            if ref in seen:
                continue  # hard de-dupe against any InternalMove duplication
            seen.add(ref)
            w = self.listw.itemWidget(it)
            desc = ""
            if w:
                edits = w.findChildren(QLineEdit)
                if edits:
                    desc = edits[0].text().strip()
            new.append({"ref": ref, "desc": desc})
        self.previews = new

    # ----------- Delete All -----------
    def _confirm_delete_all(self):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Confirm Delete All")
        msg.setText("Are you sure you want to delete ALL pictures for this choice?")
        msg.setInformativeText("This action cannot be undone.")
        btn_cancel = msg.addButton("Cancel", QMessageBox.RejectRole)
        btn_yes = msg.addButton("Delete All", QMessageBox.DestructiveRole)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_yes.setCursor(Qt.PointingHandCursor)
        msg.setDefaultButton(btn_cancel)
        msg.exec_()
        if msg.clickedButton() is btn_yes:
            packed_to_remove = []
            for p in list(self.previews or []):
                ref = p.get("ref", "")
                if isinstance(ref, str) and ref.startswith("packed::"):
                    packed_to_remove.append(ref.split("::", 1)[1])
            if packed_to_remove:
                _sb_remove_packed_names(self.mod_folder, packed_to_remove)

            # Clear UI and state
            self.listw.clear()
            self.previews = []

            # Make sure the viewport updates immediately
            QApplication.processEvents()
            self.listw.viewport().update()

    # ----------- Save -----------
    def _on_save(self):
        self._sync_previews_from_list()
        self.accept()

    # ----------- Reordered feedback -----------
    def _on_list_reordered(self):
        try:
            for i in range(self.listw.count()):
                it = self.listw.item(i)
                w = self.listw.itemWidget(it)
                if not w or it.data(Qt.UserRole) == "__placeholder__":
                    continue
                eff = w.graphicsEffect()
                if not isinstance(eff, QGraphicsOpacityEffect):
                    eff = QGraphicsOpacityEffect(w)
                    w.setGraphicsEffect(eff)
                eff.setOpacity(0.6)
                anim = QPropertyAnimation(eff, b"opacity", self)
                anim.setStartValue(0.6)
                anim.setEndValue(1.0)
                anim.setDuration(220)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.finished.connect(lambda a=anim: self._running_anims.remove(a) if a in self._running_anims else None)
                anim.start()
                self._running_anims.append(anim)
            # keep state and view in sync after internal moves
            QTimer.singleShot(100, lambda: (self._sync_previews_from_list(), self._rebuild_list_select(None)))
        except Exception as e:
            print("_on_list_reordered error:", e)

    # ----------- Empty-area deselection -----------
    def eventFilter(self, obj, event):
        try:
            # Use viewport-local coordinates; do not mapFromGlobal
            if event.type() == QEvent.MouseButtonPress and (obj is self.listw.viewport() or obj is self.listw):
                pos = event.pos() if obj is self.listw.viewport() else self.listw.viewport().mapFrom(self.listw, event.pos())
                item = self.listw.itemAt(pos)
                if item is None:
                    self.listw.clearSelection()
                    self.listw.clearFocus()
                    return True
        except Exception as e:
            print("eventFilter error:", e)
        return super().eventFilter(obj, event)

# LOADING CLASS FOR THE SCHEMA UI (or anything else)
class LoadingPopup(QDialog):
    """Generic modal loading popup with a determinate progress bar styled like the update checker."""
    def __init__(self, parent=None, message="Loading…", maximum=0):
        super().__init__(parent)
        self.setWindowTitle("Please Wait")
        self.setModal(True)
        self.setFixedSize(420, 120)

        layout = QVBoxLayout(self)
        label = QLabel(message)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(label)

        self.progress = QProgressBar()
        self.progress.setRange(0, maximum)  # determinate (0..maximum)
        self.progress.setValue(0)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background: #222;
                text-align: center;
                color: #DDD;
            }
            QProgressBar::chunk {
                background-color: #3daee9;
                width: 20px;
            }
        """)
        layout.addWidget(self.progress)

class ConfigureModSchemaDialog(QDialog):
    def __init__(self, parent, mod_folder: Path):
        super().__init__(parent)
        self.setWindowTitle("Set Configure Mod Menu")
        self.resize(1000, 720)
        self.mod_folder = mod_folder
        self.schema_file = mod_folder / "config_schema.json"
        self.attach_file = mod_folder / "config_schema_files.json"

        # In-memory state
        self.schema = self._load_schema()
        self.attachments = self._load_attachments()
        self.schema_description = self.schema.get("__description__", "")
        self._temp_packed = {}
        self._preview_index = {}
        self._deleted_dropdowns = set()

        # Preview system state
        self._layer_current = None
        self._layer_next = None
        self._fade_enter = None
        self._fade_exit = None
        self._arrow_flash_timer = None
        self._current_showing_ref = None
        self._fade_in_duration = 180
        self._fade_out_duration = 120
        self._last_click_ms = 0
        self._busy = False

        # Caches
        self._pix_cache = {}
        self._base_pix_cache = {}

        # --- Layout ---
        main = QHBoxLayout(self)

        # LEFT: dropdown list + buttons + description
        left = QVBoxLayout()
        self.list_entries = QListWidget()
        self.list_entries.setMinimumHeight(220)
        self.list_entries.currentItemChanged.connect(self.on_entry_selected)
        left.addWidget(self.list_entries)

        btn_row = QHBoxLayout()
        self.btn_add_dropdown = QPushButton("Add Dropdown")
        self.btn_remove_selected = QPushButton("Remove Selected")
        for b in (self.btn_add_dropdown, self.btn_remove_selected):
            b.setMinimumHeight(70)
            hook_flash(b)
        btn_row.addWidget(self.btn_add_dropdown)
        btn_row.addWidget(self.btn_remove_selected)
        left.addLayout(btn_row)

        left.addWidget(QLabel("Mod Description:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Write the mod description here.")
        self.desc_edit.setPlainText(self.schema_description or "")
        self.desc_edit.setFixedHeight(150)
        left.addWidget(self.desc_edit)

        main.addLayout(left, 3)

        # RIGHT: editor + preview + mapping + buttons
        right = QVBoxLayout()

        form = QFormLayout()
        self.ed_label = QLineEdit()
        self.ed_label.setMinimumHeight(32)
        form.addRow("Label:", self.ed_label)

        self.choices_list = QListWidget()
        self.choices_list.setMinimumHeight(150)
        self.choices_list.currentItemChanged.connect(self.on_choice_selected)
        self.btn_add_choice = QPushButton("Add Choice")
        self.btn_remove_choice = QPushButton("Remove Choice")
        for b in (self.btn_add_choice, self.btn_remove_choice):
            b.setMinimumHeight(38)
            hook_flash(b)
        ch_row = QHBoxLayout()
        ch_row.addWidget(self.btn_add_choice)
        ch_row.addWidget(self.btn_remove_choice)
        form.addRow("Choices:", self.choices_list)
        form.addRow("", ch_row)

        self.ed_default = QComboBox()
        self.ed_default.addItems(["Enabled", "Disabled"])
        self.ed_default.setMinimumHeight(34)
        form.addRow("Default:", self.ed_default)
        right.addLayout(form)

        mapping_row = QHBoxLayout()
        self.mapping_label = QLabel("Mod file: —")
        self.mapping_label.setStyleSheet("color:#C8C8C8;")
        mapping_row.addWidget(self.mapping_label, 1)
        self.btn_rename_files_here = QPushButton("Rename/Delete Mod Files")
        self.btn_rename_files_here.setMinimumHeight(38)
        hook_flash(self.btn_rename_files_here)
        mapping_row.addWidget(self.btn_rename_files_here, 0, Qt.AlignRight)
        right.addLayout(mapping_row)

        right.addWidget(QLabel("Preview:"))

        prev_wrap = QHBoxLayout()
        self.btn_prev = QToolButton()
        self.btn_prev.setText("◀")
        self.btn_prev.setFixedSize(44, 44)
        self.btn_prev.setStyleSheet("""
            QToolButton {
                font-size: 22px;
                background: #1A1A1A;
                color: #FFFFFF;
                border: 1px solid #333333;
                border-radius: 6px;
            }
            QToolButton:hover {
                background: #2A2A2A;
            }
        """)
        self.btn_prev.clicked.connect(lambda: self._arrow_flash_and_cycle(-1))
        self.btn_prev.setEnabled(False)

        mid = QVBoxLayout()
        self.preview_image_label = QLabel()
        self.preview_image_label.setFixedSize(480, 360)
        self.preview_image_label.setStyleSheet("background: transparent;")
        mid.addWidget(self.preview_image_label, 0, Qt.AlignCenter)

        self.preview_caption = QLabel()
        self.preview_caption.setAlignment(Qt.AlignCenter)
        self.preview_caption.setFixedWidth(420)
        self.preview_caption.setStyleSheet("color: #AAAAAA; font-size: 13px; margin-top: 8px;")
        mid.addWidget(self.preview_caption, 0, Qt.AlignCenter)

        self.btn_next = QToolButton()
        self.btn_next.setText("▶")
        self.btn_next.setFixedSize(44, 44)
        self.btn_next.setStyleSheet("""
            QToolButton {
                font-size: 22px;
                background: #1A1A1A;
                color: #FFFFFF;
                border: 1px solid #333333;
                border-radius: 6px;
            }
            QToolButton:hover {
                background: #2A2A2A;
            }
        """)
        self.btn_next.clicked.connect(lambda: self._arrow_flash_and_cycle(1))
        self.btn_next.setEnabled(False)

        prev_wrap.addWidget(self.btn_prev, 0, Qt.AlignVCenter)
        prev_wrap.addLayout(mid, 0)
        prev_wrap.addWidget(self.btn_next, 0, Qt.AlignVCenter)
        right.addLayout(prev_wrap)

        btns_row = QHBoxLayout()
        self.btn_add_mod_here = QPushButton("Add Mod to Choice")
        self.btn_remove_mod_here = QPushButton("Remove Mod from Choice")
        self.btn_add_picture_here = QPushButton("Add Picture to Choice")
        self.btn_remove_picture_here = QPushButton("Change Order/Remove Picture From Choice")
        for b in (self.btn_add_mod_here, self.btn_remove_mod_here,
                  self.btn_add_picture_here, self.btn_remove_picture_here):
            b.setMinimumHeight(38)
            hook_flash(b)
        btns_row.addWidget(self.btn_add_mod_here)
        btns_row.addWidget(self.btn_remove_mod_here)
        btns_row.addWidget(self.btn_add_picture_here)
        btns_row.addWidget(self.btn_remove_picture_here)
        right.addLayout(btns_row)

        bottom_btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        beef_up_buttons(bottom_btns)
        bottom_btns.accepted.connect(self.on_save)
        bottom_btns.rejected.connect(self.on_cancel)
        right.addWidget(bottom_btns)

        main.addLayout(right, 4)

        # Wire up
        self.btn_add_dropdown.clicked.connect(self.add_dropdown)
        self.btn_remove_selected.clicked.connect(self.remove_selected)
        self.btn_add_choice.clicked.connect(self.add_choice)
        self.btn_remove_choice.clicked.connect(self.remove_choice)
        self.btn_add_picture_here.clicked.connect(self.add_picture_here)
        self.btn_remove_picture_here.clicked.connect(self.change_order_remove_pictures)
        self.btn_add_mod_here.clicked.connect(self.add_mod_here)
        self.btn_remove_mod_here.clicked.connect(self.remove_mod_selective)
        self.btn_rename_files_here.clicked.connect(self.rename_files_here)

        handify_buttons_in(self)

        # Kick off loading popup
        self._show_loading_ui_popup()

    # ---------------- Loading popups (sequential, determinate) ----------------
    def _show_loading_ui_popup(self):
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()
        self.setEnabled(False)

        # Two steps: reload list + select/refresh
        steps = 2
        self.loading_ui_popup = LoadingPopup(self, "Preparing Configure Mod Menu…", maximum=steps)
        QTimer.singleShot(100, self._finish_ui_setup)
        self.loading_ui_popup.exec_()
        self.setEnabled(True)  # re-enable only after popup closes

        # After the UI popup is closed, start image preloading
        self._start_preloading(all_choices=True)

    def _finish_ui_setup(self):
        try:
            current = 0
            self._reload_list()
            current += 1
            self.loading_ui_popup.progress.setValue(current)
            QApplication.processEvents()

            self._select_first_and_refresh()
            current += 1
            self.loading_ui_popup.progress.setValue(current)
            QApplication.processEvents()
        finally:
            if hasattr(self, "loading_ui_popup"):
                self.loading_ui_popup.accept()  # end modal loop

    def _start_preloading(self, all_choices=False):
        total = self._count_total_images() if all_choices else self._count_current_choice_images()
        self.loading_pictures_popup = LoadingPopup(self, "Preloading preview images…", maximum=total or 1)
        QTimer.singleShot(75, lambda: self._preload_images(all_choices))
        self.loading_pictures_popup.exec_()  # blocks until accept()

    def _count_total_images(self):
        total = 0
        for dd_key, choices_dict in (self.attachments or {}).items():
            for choice, entry in (choices_dict or {}).items():
                total += len(entry.get("previews", []))
        return total

    def _count_current_choice_images(self):
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        if not dd or not ch:
            return 0
        return len(self.attachments.get(dd, {}).get(ch, {}).get("previews", []))

    def _preload_images(self, all_choices=False):
        try:
            loaded = 0
            if all_choices:
                for dd_key, choices_dict in (self.attachments or {}).items():
                    for choice, entry in (choices_dict or {}).items():
                        for preview in entry.get("previews", []):
                            ref = preview.get("ref", "")
                            if ref:
                                self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
                            loaded += 1
                            self.loading_pictures_popup.progress.setValue(loaded)
                            if loaded % 3 == 0:
                                QApplication.processEvents()
            else:
                dd = self._current_dropdown_key()
                ch = self._current_choice_name()
                previews = self.attachments.get(dd, {}).get(ch, {}).get("previews", [])
                for preview in previews:
                    ref = preview.get("ref", "")
                    if ref:
                        self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
                    loaded += 1
                    self.loading_pictures_popup.progress.setValue(loaded)
                    if loaded % 3 == 0:
                        QApplication.processEvents()
        finally:
            if hasattr(self, "loading_pictures_popup"):
                self.loading_pictures_popup.accept()  # ensure modal loop ends

    # ---------------- Schema and attachments I/O ----------------
    def _load_attachments(self):
        """
        Read from unified mod_data.json ("SET CONFIGURE SCHEMA" → "attachments").
        Fallback to legacy config_schema_files.json. Migrate preview→previews.
        """
        data_file = self.mod_folder / "mod_data.json"
        if data_file.exists():
            try:
                data = json.loads(data_file.read_text(encoding="utf-8"))
                section = data.get("SET CONFIGURE SCHEMA", {}) or {}
                attachments = section.get("attachments", {}) or {}
                for dd, choices in list(attachments.items()):
                    for ch, entry in list((choices or {}).items()):
                        if isinstance(entry, dict) and "preview" in entry and "previews" not in entry:
                            ref = entry.get("preview")
                            if ref:
                                entry["previews"] = [{"ref": ref, "desc": ""}]
                            entry.pop("preview", None)
                return attachments or {}
            except Exception as e:
                print(f"[load_attachments] error: {e}")

        # Legacy fallback
        p = self.mod_folder / "config_schema_files.json"
        if p.exists():
            try:
                attachments = json.loads(p.read_text(encoding="utf-8"))
                for dd, choices in list(attachments.items()):
                    for ch, entry in list((choices or {}).items()):
                        if isinstance(entry, dict) and "preview" in entry and "previews" not in entry:
                            ref = entry.get("preview")
                            if ref:
                                entry["previews"] = [{"ref": ref, "desc": ""}]
                            entry.pop("preview", None)
                return attachments or {}
            except Exception as e:
                print(f"[load_attachments legacy] error: {e}")
        return {}

    def _load_schema(self):
        """
        Read from unified mod_data.json ("SET CONFIGURE SCHEMA" → "schema").
        Fallback to legacy config_schema.json. Ensure dropdown normalization.
        """
        data_file = self.mod_folder / "mod_data.json"
        if data_file.exists():
            try:
                data = json.loads(data_file.read_text(encoding="utf-8"))
                section = data.get("SET CONFIGURE SCHEMA", {}) or {}
                schema = section.get("schema", {}) or {}
                for k, v in list(schema.items()):
                    if k.startswith("__"):
                        continue
                    if v.get("type") == "dropdown":
                        v.setdefault("choices", ["Enabled", "Disabled"])
                        v.setdefault("default", "Disabled")
                if schema:
                    return schema
            except Exception as e:
                print(f"[load_schema] error: {e}")

        # Legacy fallback
        p = self.mod_folder / "config_schema.json"
        if p.exists():
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
                for k, v in list(s.items()):
                    if k.startswith("__"):
                        continue
                    if v.get("type") == "dropdown":
                        v.setdefault("choices", ["Enabled", "Disabled"])
                        v.setdefault("default", "Disabled")
                return s
            except Exception as e:
                print(f"[load_schema legacy] error: {e}")

        # Default schema when nothing exists
        return {
            "preset": {"label": "Preset", "type": "dropdown",
                       "choices": ["Enabled", "Disabled"], "default": "Disabled"}
        }

    def _save_schema_to_disk(self):
        """
        Deprecated in unified model, but keep thin wrapper if needed by other code.
        Use on_save() for unified persistence.
        """
        try:
            has_content = any(not k.startswith('__') for k in self.schema.keys())
            if has_content:
                self.schema_file.write_text(json.dumps(self.schema, indent=2), encoding="utf-8")
            else:
                if self.schema_file.exists():
                    self.schema_file.unlink()
        except Exception as e:
            print(f"[save_schema thin] error: {e}")

    # ---------------- UI plumbing ----------------
    def _reload_list(self):
        self.list_entries.clear()
        for key, spec in list(self.schema.items()):
            if key.startswith("__"):
                continue
            display = spec.get("label", key)
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, key)
            self.list_entries.addItem(item)

    def _select_first_and_refresh(self):
        if self.list_entries.count() > 0:
            self.list_entries.setCurrentRow(0)
            cur = self.list_entries.currentItem()
            if cur:
                self.on_entry_selected(cur)
                if self.choices_list.count() > 0:
                    self.choices_list.setCurrentRow(0)
                self._refresh_choice_summary_and_preview()
        else:
            self._update_preview_default()

    def _current_dropdown_key(self):
        it = self.list_entries.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _current_choice_name(self):
        it = self.choices_list.currentItem()
        return it.text() if it else None

    def _generate_key(self, label):
        base = re.sub(r'[^a-zA-Z0-9_-]', '_', label.strip()) or "option"
        k = base
        i = 1
        while k in self.schema:
            k = f"{base}_{i}"
            i += 1
        return k

    def add_dropdown(self):
        label, ok = QInputDialog.getText(self, "Add Dropdown", "Label for dropdown:")
        if not ok or not label.strip():
            return
        key = self._generate_key(label)
        self.schema[key] = {"label": label, "type": "dropdown",
                            "choices": ["Enabled", "Disabled"], "default": "Disabled"}
        self._reload_list()
        for i in range(self.list_entries.count()):
            it = self.list_entries.item(i)
            if it.data(Qt.UserRole) == key:
                self.list_entries.setCurrentItem(it)
                break
        self._load_choice_ui(key)
        self._refresh_choice_summary_and_preview()

    def _drop_choice_cleanup(self, key, choice, cleanup_packed=True):
        if key in self.attachments and choice in self.attachments[key]:
            entry = self.attachments[key][choice]
            packed_to_remove = []
            for fm in entry.get("files", []):
                src = fm.get("src", "")
                if isinstance(src, str) and src.startswith("packed::"):
                    packed_to_remove.append(src.split("::", 1)[1])
            for pv in entry.get("previews", []):
                ref = pv.get("ref")
                if isinstance(ref, str) and ref.startswith("packed::"):
                    packed_to_remove.append(ref.split("::", 1)[1])
            for n in packed_to_remove:
                self._temp_packed.pop(n, None)
                if cleanup_packed:
                    try:
                        _sb_remove_packed_names(self.mod_folder, [n])
                    except Exception:
                        pass
            del self.attachments[key][choice]
            if not self.attachments[key]:
                del self.attachments[key]

    def remove_selected(self):
        it = self.list_entries.currentItem()
        if not it:
            return
        key = it.data(Qt.UserRole)
        if key in self.schema:
            if QMessageBox.question(
                self, "Remove",
                f"Remove '{self.schema[key].get('label','')}' and all its data?"
            ) == QMessageBox.Yes:
                try:
                    packed_to_remove = set()
                    if key in self.attachments:
                        for choice in list(self.attachments[key].keys()):
                            entry = self.attachments[key].get(choice, {})
                            for fm in entry.get("files", []):
                                src = fm.get("src", "")
                                if isinstance(src, str) and src.startswith("packed::"):
                                    packed_to_remove.add(src.split("::", 1)[1])
                            for pv in entry.get("previews", []):
                                ref = pv.get("ref")
                                if isinstance(ref, str) and ref.startswith("packed::"):
                                    packed_to_remove.add(ref.split("::", 1)[1])
                            self._drop_choice_cleanup(key, choice, cleanup_packed=False)
                        if key in self.attachments:
                            del self.attachments[key]

                    if packed_to_remove:
                        try:
                            _sb_remove_packed_names(self.mod_folder, list(packed_to_remove))
                        except Exception:
                            pass
                except Exception:
                    pass

                del self.schema[key]
                self._deleted_dropdowns.add(key)

                self._reload_list()
                self.preview_image_label.setText('No preview')
                self.preview_image_label.setPixmap(QPixmap())
                self.preview_caption.setText("")
                self.mapping_label.setText("Mod file: —")
                self.mapping_label.setToolTip("")
                self._select_first_and_refresh()

    def _load_choice_ui(self, key):
        self.choices_list.clear()
        spec = self.schema.get(key, {})
        choices = spec.get("choices", [])
        for c in choices:
            self.choices_list.addItem(c)

        self.ed_default.clear()
        self.ed_default.addItems(choices if choices else ["Enabled", "Disabled"])
        default = spec.get("default", "Disabled")
        items = [self.ed_default.itemText(i) for i in range(self.ed_default.count())]
        if default in items:
            self.ed_default.setCurrentText(default)
        else:
            self.ed_default.setCurrentIndex(0)

        if self.choices_list.count() > 0:
            self.choices_list.setCurrentRow(0)
        else:
            # No choices → clear preview (do not load default)
            self.mapping_label.setText("Mod file: —")
            self.mapping_label.setToolTip("")
            self._update_preview_idle()


    def on_entry_selected(self, current: QListWidgetItem, previous=None):
        # Clear any existing preview first to avoid sticky images
        self._update_preview_idle()
    
        if not current:
            self.ed_label.setText("")
            self.ed_default.clear()
            self.ed_default.addItems(["Enabled", "Disabled"])
            self.mapping_label.setText("Mod file: —")
            self.mapping_label.setToolTip("")
            return
    
        key = current.data(Qt.UserRole)
        spec = self.schema.get(key, {})
        self.ed_label.setText(spec.get("label", key))
    
        self._load_choice_ui(key)
        self._refresh_choice_summary_and_preview()

    def on_choice_selected(self, current: QListWidgetItem, previous=None):
        self._refresh_choice_summary_and_preview()

    def _refresh_choice_summary_and_preview(self):
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()

        if not dd or not ch:
            self.mapping_label.setText("Mod file: —")
            self.mapping_label.setToolTip("")
            self._update_preview_idle()
            return

        entry = self.attachments.get(dd, {}).get(ch, {}) or {}
        # Build mapping summary
        summary = []
        for fm in entry.get("files", []):
            src = fm.get("src", "")
            dst = fm.get("dst", "")
            src_name = src.split("::", 1)[1] if isinstance(src, str) and src.startswith("packed::") else Path(src).name
            summary.append(f"{src_name} → {dst}")

        full_text = "Mod file: " + (", ".join(summary) if summary else "—")
        fm = QFontMetrics(self.mapping_label.font())
        width = max(120, self.mapping_label.width() - 10)
        elided = fm.elidedText(full_text, Qt.ElideRight, width)
        self.mapping_label.setText(elided)
        self.mapping_label.setToolTip(full_text if elided != full_text else "")

        previews = entry.get("previews", []) or []
        self._ensure_index(dd, ch, len(previews))

        if not previews:
            # No previews → strictly clear the preview area
            self._update_preview_idle()
            return

        self._set_preview_by_index(previews)

    def _ensure_index(self, dd, ch, count):
        key = (dd, ch)
        if key not in self._preview_index:
            self._preview_index[key] = 0
        if count == 0:
            self._preview_index[key] = 0
        else:
            self._preview_index[key] = max(0, min(self._preview_index[key], count - 1))

    def _switch_preview(self, delta):
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        if not dd or not ch:
            return
        entry = self.attachments.get(dd, {}).get(ch, {})
        previews = entry.get("previews", [])
        if not previews:
            return
        key = (dd, ch)
        idx = (self._preview_index.get(key, 0) + delta) % len(previews)
        self._preview_index[key] = idx
        self._set_preview_by_index(previews)

    def _set_preview_by_index(self, previews):
        if not previews:
            self._update_preview_default()
            self.preview_caption.setText("")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            return
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        key = (dd, ch)
        idx = self._preview_index.get(key, 0)
        idx = max(0, min(idx, len(previews)-1))
        ref = previews[idx].get("ref")
        desc = previews[idx].get("desc","")
        pix = self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
        if pix and not pix.isNull():
            self._crossfade_to(pix, hover=False)
            self.preview_caption.setText(desc)
            self._current_showing_ref = ref
        else:
            self._update_preview_default()
            self.preview_caption.setText(desc)
        multi = len(previews) > 1
        self.btn_prev.setEnabled(multi)
        self.btn_next.setEnabled(multi)

    # ---------------- Preview helpers ----------------
    def _cache_key(self, ref: str, w: int, h: int, mode: int) -> str:
        return f"{ref}|{w}x{h}|{mode}"

    def _load_base_pix(self, ref: str) -> QPixmap:
        if ref in self._base_pix_cache:
            return self._base_pix_cache[ref]

        base = QPixmap()
        try:
            if isinstance(ref, str) and ref.startswith("packed::"):
                name = ref.split("::", 1)[1]
                if name in self._temp_packed:
                    data = self._temp_packed[name]
                    base.loadFromData(data)
                else:
                    tmp = _sb_extract_packed_to_temp(self.mod_folder, name)
                    if tmp and tmp.exists():
                        base = QPixmap(str(tmp))
            elif isinstance(ref, str):
                file_path = self.mod_folder / ref
                if file_path.exists():
                    base = QPixmap(str(file_path))
        except Exception as e:
            print(f"[DEBUG] Error loading {ref}: {e}")
            base = QPixmap()

        if not base or base.isNull():
            return QPixmap()

        if len(self._base_pix_cache) > 50:
            oldest = list(self._base_pix_cache.keys())[:10]
            for k in oldest:
                self._base_pix_cache.pop(k, None)

        self._base_pix_cache[ref] = base
        return base

    def _get_scaled_from_cache_or_base(self, ref: str, transform_mode) -> QPixmap:
        if not ref:
            return QPixmap()

        w = max(1, int(self.preview_image_label.width()))
        h = max(1, int(self.preview_image_label.height()))
        mode_flag = 1 if transform_mode == Qt.SmoothTransformation else 0
        key = self._cache_key(ref, w, h, mode_flag)

        if key in self._pix_cache:
            return self._pix_cache[key]

        base = self._load_base_pix(ref)
        if not base or base.isNull():
            return QPixmap()

        scaled = base.scaled(w, h, Qt.KeepAspectRatio, transform_mode)

        if len(self._pix_cache) > 500:
            oldest = list(self._pix_cache.keys())[:50]
            for k in oldest:
                self._pix_cache.pop(k, None)

        self._pix_cache[key] = scaled
        return scaled

    def _crossfade_to(self, pix, hover=False):
        if self._layer_next:
            try:
                self._layer_next.deleteLater()
            except Exception:
                pass
            self._layer_next = None
        self._layer_next = QLabel(self.preview_image_label)
        self._layer_next.setAlignment(Qt.AlignCenter)
        self._layer_next.setGeometry(self.preview_image_label.rect())
        self._layer_next.setStyleSheet("background: transparent;")
        self._layer_next.setPixmap(pix)
        self._layer_next.show()

        if not self._layer_current:
            self._layer_current = self._layer_next
            self._layer_next = None
            eff = QGraphicsOpacityEffect()
            self._layer_current.setGraphicsEffect(eff)
            self._fade_enter = QPropertyAnimation(eff, b"opacity", self)
            self._fade_enter.setDuration(self._fade_in_duration)
            self._fade_enter.setStartValue(0.0)
            self._fade_enter.setEndValue(1.0)
            self._fade_enter.setEasingCurve(QEasingCurve.InOutCubic)
            self._fade_enter.finished.connect(lambda: setattr(self, "_fade_enter", None))
            self._fade_enter.start()
            return

        duration = self._fade_out_duration if hover else self._fade_in_duration
        eff_out = QGraphicsOpacityEffect()
        self._layer_current.setGraphicsEffect(eff_out)
        eff_in = QGraphicsOpacityEffect()
        self._layer_next.setGraphicsEffect(eff_in)

        self._fade_exit = QPropertyAnimation(eff_out, b"opacity", self)
        self._fade_exit.setDuration(duration)
        self._fade_exit.setStartValue(1.0)
        self._fade_exit.setEndValue(0.0)
        self._fade_exit.setEasingCurve(QEasingCurve.InOutCubic)

        self._fade_enter = QPropertyAnimation(eff_in, b"opacity", self)
        self._fade_enter.setDuration(duration)
        self._fade_enter.setStartValue(0.0)
        self._fade_enter.setEndValue(1.0)
        self._fade_enter.setEasingCurve(QEasingCurve.InOutCubic)

        def finish():
            try:
                if self._layer_current:
                    self._layer_current.deleteLater()
            except Exception:
                pass
            self._layer_current = self._layer_next
            self._layer_next = None
            self._fade_enter = None
            self._fade_exit = None

        self._fade_exit.finished.connect(finish)
        self._fade_enter.start()
        self._fade_exit.start()

    def _arrow_flash_and_cycle(self, delta):
        btn = self.btn_prev if delta < 0 else self.btn_next
        if self._arrow_flash_timer and self._arrow_flash_timer.isActive():
            return
        orig = btn.styleSheet()
        btn.setStyleSheet(orig + "\nQToolButton { background: rgba(255, 255, 255, 0.3); }")
        self._arrow_flash_timer = QTimer(self)
        self._arrow_flash_timer.setSingleShot(True)
        self._arrow_flash_timer.setInterval(140)
        def restore():
            btn.setStyleSheet(orig)
            self._arrow_flash_timer = None
        self._arrow_flash_timer.timeout.connect(restore)
        self._arrow_flash_timer.start()
        self._cycle_guarded(delta)

    def _cycle_guarded(self, delta):
        now = int(time.time() * 1000)
        if now - self._last_click_ms < 160 or self._busy:
            return
        self._last_click_ms = now
        self._busy = True
        try:
            dd = self._current_dropdown_key()
            ch = self._current_choice_name()
            if not dd or not ch:
                return
            entry = self.attachments.get(dd, {}).get(ch, {})
            previews = entry.get("previews", [])
            if not previews:
                return
            key = (dd, ch)
            idx = (self._preview_index.get(key, 0) + delta) % len(previews)
            self._preview_index[key] = idx

            next_idx = (idx + 1) % len(previews)
            prev_idx = (idx - 1) % len(previews)
            QTimer.singleShot(0, lambda: self._preload_image(previews[next_idx].get("ref", "")))
            QTimer.singleShot(0, lambda: self._preload_image(previews[prev_idx].get("ref", "")))

            ref = previews[idx].get("ref", "")
            desc = previews[idx].get("desc", "")
            pix = self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
            if not pix or pix.isNull():
                pix = self._get_scaled_from_cache_or_base(ref, Qt.FastTransformation)
            if pix and not pix.isNull():
                self._crossfade_to(pix, hover=False)
                self.preview_caption.setText(desc)
                self._current_showing_ref = ref
        finally:
            QTimer.singleShot(80, lambda: setattr(self, "_busy", False))

    def _preload_image(self, ref):
        if ref:
            try:
                self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
            except Exception:
                pass

    # ---------------- File/preview management actions ----------------
    def add_picture_here(self):
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        if not dd or not ch:
            QMessageBox.information(self, "No choice", "Select a dropdown and choice first.")
            return

        files, _ = QFileDialog.getOpenFileNames(
            self, "Select image(s) for this choice", str(self.mod_folder),
            "Images (*.png *.jpg *.jpeg);;All Files (*)"
        )
        if not files:
            return

        try:
            self.attachments.setdefault(dd, {}).setdefault(ch, {}).setdefault("previews", [])
            appended = 0
            new_previews = []

            for f in files:
                p = Path(f)
                # Apply rule via helper
                ref = normalize_ref_for_file(self.mod_folder, p)

                # If helper generated a packed::ref (file outside mod), also stage in _temp_packed
                if isinstance(ref, str) and ref.startswith("packed::"):
                    name = ref.split("::", 1)[1]
                    try:
                        data = p.read_bytes()
                        self._temp_packed[name] = data
                    except Exception as e:
                        print(f"[add_picture_here] staging packed failed for {name}: {e}")

                new_previews.append({"ref": ref, "desc": ""})
                appended += 1

            # Extend existing previews with newly staged ones
            self.attachments[dd][ch]["previews"].extend(new_previews)

            # Keep buddy in sync for Enabled/Disabled
            if ch in ("Enabled", "Disabled"):
                buddy = "Disabled" if ch == "Enabled" else "Enabled"
                self.attachments.setdefault(dd, {}).setdefault(buddy, {}).setdefault("previews", [])
                # Deep copy semantics to avoid shared references
                self.attachments[dd][buddy]["previews"] = list(self.attachments[dd][ch]["previews"])

            QMessageBox.information(self, "Staged", f"Added {appended} image(s) for choice '{ch}'. They will be saved on Save.")
            self._refresh_choice_summary_and_preview()
        except Exception as e:
            QMessageBox.warning(self, "Failed", f"Failed to stage images: {e}")

    def change_order_remove_pictures(self):
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        if not dd or not ch:
            QMessageBox.information(self, "No choice", "Select a dropdown and choice first.")
            return
        entry = self.attachments.get(dd, {}).get(ch, {})
        previews = entry.get("previews", [])
        if not previews:
            QMessageBox.information(self, "No pictures", "This choice has no pictures.")
            return

        dlg = PictureOrderDialog(self, self.mod_folder, previews, self._temp_packed)
        dlg.listw.clear()
        for pobj in previews:
            dlg.add_preview_item(pobj)

        if dlg.exec_() == QDialog.Accepted:
            # Use a new list object to avoid shared references across buddy choices
            new_previews = list(dlg.previews or [])
            self.attachments.setdefault(dd, {}).setdefault(ch, {})["previews"] = new_previews

            # Keep Enabled/Disabled buddies in sync (deep copy semantics)
            if ch in ("Enabled", "Disabled"):
                buddy = "Disabled" if ch == "Enabled" else "Enabled"
                self.attachments.setdefault(dd, {}).setdefault(buddy, {})["previews"] = list(new_previews)

            # Immediately refresh preview summary
            self._refresh_choice_summary_and_preview()

    def add_mod_here(self):
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        if not dd or not ch:
            QMessageBox.information(self, "No choice", "Select a dropdown and choice first.")
            return

        # NEW: Check if this is a PNG-only mod
        is_png_only = _mod_is_png_only(self.mod_folder)

        # Adjust file dialog filter based on mod type
        if is_png_only:
            file_filter = "PNG Textures (*.png);;All Files (*)"
            dialog_title = "Select PNG texture(s) for this choice (will target Dolphin Custom Texture Path)"
        else:
            file_filter = "All Files (*)"
            dialog_title = "Select mod file(s) for this choice (will be packed on Save)"

        files, _ = QFileDialog.getOpenFileNames(
            self, dialog_title,
            str(Path.home()), file_filter
        )
        if not files:
            return

        try:
            self.attachments.setdefault(dd, {}).setdefault(ch, {}).setdefault("files", [])
            temp_files = []

            for f in files:
                p = Path(f)
                # Apply rule via helper
                ref = normalize_ref_for_file(self.mod_folder, p)

                # If helper generated a packed::ref (file outside mod), also stage in _temp_packed
                if isinstance(ref, str) and ref.startswith("packed::"):
                    name = ref.split("::", 1)[1]
                    try:
                        data = p.read_bytes()
                        self._temp_packed[name] = data
                    except Exception as e:
                        print(f"[add_mod_here] staging packed failed for {name}: {e}")

                temp_files.append({"src": ref, "dst": ""})

            self.attachments[dd][ch]["files"].extend(temp_files)

            # Prompt for renames (existing dialog)
            dlg = RenameChoiceFilesDialog(self, self.attachments, dd, ch)

            # NEW: Update the dialog prompt if PNG-only
            if is_png_only:
                try:
                    for lbl in dlg.findChildren(QLabel):
                        if "target filenames" in lbl.text().lower():
                            lbl.setText("Edit target texture names (these will go to Dolphin Custom Texture Path)")
                except Exception:
                    pass
                
            if dlg.exec_() != QDialog.Accepted:
                # Roll back staged items on cancel
                for fm in temp_files:
                    src = fm.get("src", "")
                    if isinstance(src, str) and src.startswith("packed::"):
                        self._temp_packed.pop(src.split("::", 1)[1], None)
                    try:
                        if fm in self.attachments[dd][ch]["files"]:
                            self.attachments[dd][ch]["files"].remove(fm)
                    except Exception:
                        pass
                self._refresh_choice_summary_and_preview()
                return

            file_type = "texture(s)" if is_png_only else "file(s)"
            QMessageBox.information(self, "Staged", f"Mapped {len(temp_files)} {file_type} for choice '{ch}'. They will be saved on Save.")
            self._refresh_choice_summary_and_preview()
        except Exception as e:
            QMessageBox.warning(self, "Pack failed", f"Could not stage files: {e}")

    def rename_files_here(self):
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        if not dd or not ch:
            QMessageBox.information(self, "No choice", "Select a dropdown and choice first.")
            return
        entry = self.attachments.get(dd, {}).get(ch, {})
        if not entry or not entry.get("files"):
            QMessageBox.information(self, "No files", "This choice has no mapped mod files.")
            return
        dlg = RenameChoiceFilesDialog(self, self.attachments, dd, ch)
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_choice_summary_and_preview()

    def remove_mod_selective(self):
        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        if not dd or not ch:
            QMessageBox.information(self, "No choice", "Select a dropdown and choice first.")
            return
        entry = self.attachments.get(dd, {}).get(ch, {})
        if not entry or not entry.get("files"):
            QMessageBox.information(self, "Nothing to remove", "This choice has no mapped mod files.")
            return
        dlg = DeleteChoiceFilesDialog(self, self.attachments, dd, ch, self.mod_folder)
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_choice_summary_and_preview()

    def add_choice(self):
        cur = self.list_entries.currentItem()
        if not cur:
            return
        key = cur.data(Qt.UserRole)
        spec = self.schema.get(key, {})
        if spec.get("type") != "dropdown":
            return
        label, ok = QInputDialog.getText(self, "Add Choice", "Choice name:")
        if not ok or not label.strip():
            return
        choice = label.strip()
        if "choices" not in spec:
            spec["choices"] = []
        if choice in spec["choices"]:
            QMessageBox.information(self, "Exists", "That choice already exists.")
            return
        spec["choices"].append(choice)
        self._load_choice_ui(key)
        self._refresh_choice_summary_and_preview()

    def remove_choice(self):
        cur = self.list_entries.currentItem()
        if not cur:
            return
        key = cur.data(Qt.UserRole)
        spec = self.schema.get(key, {})
        row = self.choices_list.currentRow()
        if row < 0:
            return
        if "choices" not in spec or not spec["choices"]:
            return
        choice = spec["choices"][row]
        if QMessageBox.question(self, "Remove Choice",
                                f"Remove choice '{choice}' and its data?") != QMessageBox.Yes:
            return
        try:
            self._drop_choice_cleanup(key, choice)
        except Exception:
            pass
        spec["choices"].remove(choice)
        if spec.get("default") == choice:
            spec["default"] = spec["choices"][0] if spec["choices"] else "Disabled"
        self._load_choice_ui(key)
        self._refresh_choice_summary_and_preview()

    # ---------------- Save / Cancel ----------------
    def on_save(self):
        # Update current entry from UI
        cur = self.list_entries.currentItem()
        if cur:
            key = cur.data(Qt.UserRole)
            label = self.ed_label.text().strip() or self.schema[key].get("label", key)
            self.schema[key]["label"] = label
            if self.ed_default.count() > 0:
                self.schema[key]["default"] = self.ed_default.currentText()
        self.schema["__description__"] = self.desc_edit.toPlainText()

        # Unified write to mod_data.json
        try:
            data_file = self.mod_folder / "mod_data.json"
            if data_file.exists():
                data = json.loads(data_file.read_text(encoding="utf-8"))
            else:
                data = {}

            # Ensure attachments persist, even when empty lists (e.g., after Delete All)
            data["SET CONFIGURE SCHEMA"] = {
                "schema": self.schema or {},
                "attachments": self.attachments or {}
            }
            data_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save schema:\n{e}")
            return

        # Remove legacy files if present
        for fname in ("config_schema.json", "config_schema_files.json"):
            f = self.mod_folder / fname
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

        # Write packed_files.bin (prune unused + add staged)
        try:
            still_needed = set()
            for dd, choices in (self.attachments or {}).items():
                for ch, entry in (choices or {}).items():
                    for fm in entry.get("files", []):
                        src = fm.get("src", "")
                        if isinstance(src, str) and src.startswith("packed::"):
                            still_needed.add(src.split("::", 1)[1])
                    for pv in entry.get("previews", []):
                        ref = pv.get("ref", "")
                        if isinstance(ref, str) and ref.startswith("packed::"):
                            still_needed.add(ref.split("::", 1)[1])

            existing = _sb_read_packed_index(self.mod_folder)
            pruned = {n: b for n, b in existing.items() if n in still_needed}
            pruned.update(self._temp_packed)
            _sb_write_packed_index(self.mod_folder, pruned)

            try:
                print(f"[packed] wrote {len(pruned)} entries (after pruning)")
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "Packed Save Failed", f"Could not save packed files:\n{e}")

        QMessageBox.information(self, "Saved", "Config Mod Saved!")
        self.accept()


    def on_cancel(self):
        """
        Cancel behavior:
        - If nothing existed on disk, cancel just closes.
        - If things existed, reload from disk, but keep confirmed deletions, and persist them.
        """
        try:
            schema_exists = self.schema_file.exists()
            attach_exists = self.attach_file.exists()
            packed_exists = (_sb_packed_file_path(self.mod_folder)).exists()

            if not schema_exists and not attach_exists and not packed_exists:
                self.reject()
                return

            # Reload schema/attachments from disk
            self.schema = self._load_schema()
            self.attachments = self._load_attachments()
            self._temp_packed.clear()

            # Re-apply confirmed deletions
            for key in list(self._deleted_dropdowns):
                self.schema.pop(key, None)
                self.attachments.pop(key, None)

            # Persist deletions back to mod_data.json so ConfigureModDialog sees them
            try:
                data_file = self.mod_folder / "mod_data.json"
                if data_file.exists():
                    data = json.loads(data_file.read_text(encoding="utf-8"))
                else:
                    data = {}
                data["SET CONFIGURE SCHEMA"] = {
                    "schema": self.schema or {},
                    "attachments": self.attachments or {}
                }
                data_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[cancel] failed to persist deletions: {e}")
        except Exception as e:
            print(f"[cancel] error: {e}")

        self.reject()

    # ---------------- Preview defaults ----------------
    def _update_preview_default(self):
        try:
            packed = _sb_read_packed_index(self.mod_folder)
            if 'preview.png' in packed:
                tmp = _sb_extract_packed_to_temp(self.mod_folder, 'preview.png')
                if tmp and tmp.exists():
                    pix = QPixmap(str(tmp))
                    pix = pix.scaled(self.preview_image_label.width(),
                                     self.preview_image_label.height(),
                                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.preview_image_label.setPixmap(pix)
                    return
        except Exception:
            pass
        if (self.mod_folder / 'preview.png').exists():
            p = self.mod_folder / 'preview.png'
        else:
            p = find_ui_icon(self.mod_folder.name.lower(), 'Picture')
        if p and Path(p).exists():
            try:
                pix = QPixmap(str(p))
                pix = pix.scaled(self.preview_image_label.width(),
                                 self.preview_image_label.height(),
                                 Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_image_label.setPixmap(pix)
            except Exception:
                self.preview_image_label.setText('Preview (load failed)')

    def _update_preview_idle(self):
        """
        Strictly clear the preview area:
        - stop any running fade animations
        - delete layered labels
        - clear the base preview label
        - reset caption and navigation buttons
        - reset current ref
        """
        # Stop animations
        try:
            if hasattr(self, "_fade_enter") and self._fade_enter:
                self._fade_enter.stop()
                self._fade_enter = None
            if hasattr(self, "_fade_exit") and self._fade_exit:
                self._fade_exit.stop()
                self._fade_exit = None
        except Exception:
            pass

        # Delete any layered labels
        for attr in ("_layer_current", "_layer_next"):
            try:
                lbl = getattr(self, attr, None)
                if lbl:
                    lbl.deleteLater()
            except Exception:
                pass
            setattr(self, attr, None)

        # Clear the base image label and caption
        try:
            self.preview_image_label.clear()
        except Exception:
            pass
        self.preview_caption.setText("")
        self._current_showing_ref = None

        # Disable arrows
        try:
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
        except Exception:
            pass

    def _set_preview_by_index(self, previews):
        if not previews:
            # Runtime switching with no images should be blank
            self._update_preview_idle()
            return

        dd = self._current_dropdown_key()
        ch = self._current_choice_name()
        key = (dd, ch)
        idx = max(0, min(self._preview_index.get(key, 0), len(previews) - 1))

        ref = previews[idx].get("ref", "")
        desc = previews[idx].get("desc", "")

        if not ref:
            # Defensive: no ref → clear
            self._update_preview_idle()
            return

        pix = self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
        if pix and not pix.isNull():
            self._crossfade_to(pix, hover=False)
            self.preview_caption.setText(desc)
            self._current_showing_ref = ref
        else:
            # Missing/invalid → clear
            self._update_preview_idle()

        multi = len(previews) > 1
        self.btn_prev.setEnabled(multi)
        self.btn_next.setEnabled(multi)

    def _finish_transition(self, new_pixmap):
        # Set the final image and clean up
        self.preview_image_label.setPixmap(new_pixmap)
        self.preview_image_label.setGeometry(self._next_label.geometry())
        self._next_label.deleteLater()
        self._next_label = None
        self._anim_exit = None
        self._anim_enter = None

# -----------------------
# ConfigureModDialog (runtime)
# -----------------------
class ConfigureModDialog(QDialog):
    def __init__(self, parent, mod_folder: Path):
        super().__init__(parent)
        self.setWindowTitle(f"Configure [{mod_folder.name}]")
        # Default resolution retained at 1000x600
        self.resize(1200, 600)
        self.mod_folder = mod_folder

        # Data / state
        self.schema = self._load_schema()
        self.values = self._load_values()
        self.attachments = self._load_attachments()
        self.schema_description = self.schema.get("__description__", "")
        self.widgets = {}
        self._label_to_combo = {}
        self._row_frames = {}
        self._current_preview_idx = {}
        self._active_key = None
        self._last_click_ms = 0
        self._busy = False

        # Caches
        self._pix_cache = {}       # scaled pixmaps cache (by ref+size+mode)
        self._base_pix_cache = {}  # base pixmaps cache (by ref only)

        # Drag/resize throttle
        self._is_dragging_splitter = False
        self._drag_idle_timer = QTimer(self)
        self._drag_idle_timer.setSingleShot(True)
        # Reduced debounce to allow continuous responsive resizing while dragging
        self._drag_idle_timer.setInterval(40)  # smaller interval for smoother live updates

        # Arrow flash timer
        self._arrow_flash_timer = None

        # Crossfade pieces
        self._layer_current = None
        self._layer_next = None
        self._fade_enter = None
        self._fade_exit = None
        self._fade_duration = 300
        self._fade_out_duration = 180

        # Layout
        outer = QVBoxLayout(self)
        headline = QLabel("<span style='font-size:10pt; font-weight:600;'>Configure Mod Options</span>")
        headline.setAlignment(Qt.AlignCenter)
        outer.addWidget(headline)

        # After creating labels and dropdowns
        for lbl in self._label_to_combo.keys():
            lbl.installEventFilter(self)
            
        for combo in self._label_to_combo.values():
            combo.installEventFilter(self)

        # LEFT: scrollable form
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(300)
        left_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        left_wrap = QWidget()
        left_col = QVBoxLayout(left_wrap)
        left_col.setSpacing(8)
        left_col.setContentsMargins(0, 0, 12, 0)

        for key, spec in self.schema.items():
            if key.startswith("__"):
                continue
            typ = spec.get("type", "dropdown")
            label_text = spec.get("label", key)

            if typ == "title":
                lbl = QLabel(f"<b>{label_text}</b>")
                lbl.setStyleSheet("font-size:16px;")
                left_col.addWidget(lbl)
                continue

            row_frame = QFrame()
            row_frame.setObjectName(f"row_{key}")
            row_frame.setFrameShape(QFrame.NoFrame)
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(6, 6, 6, 6)
            row_layout.setSpacing(10)

            name_lbl = QLabel(label_text + ":")
            name_lbl.setStyleSheet("font-size:15px; font-weight:700; border: none;")
            name_lbl.setCursor(Qt.PointingHandCursor)
            name_lbl.setWordWrap(True)
            name_lbl._hover_key = key
            name_lbl.installEventFilter(self)

            name_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            row_layout.addWidget(name_lbl, 2)

            if typ == "toggle":
                w = QPushButton(label_text)
                w.setCheckable(True)
                w.setChecked(bool(self.values.get(key, spec.get("default", False))))
                w.setMinimumHeight(34)
                w.setStyleSheet("font-size:14px;")
                hook_flash(w)
                row_layout.addStretch(1)
                row_layout.addWidget(w, 0)
                self.widgets[key] = w

            elif typ == "dropdown":
                w = QComboBox()
                w.setMinimumWidth(160)
                w.setMaximumWidth(360)
                w.setMinimumHeight(34)
                w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                w.setCursor(Qt.PointingHandCursor)
                w.setStyleSheet("""
                    QComboBox {
                        background-color: #1A1A1A;
                        color: #E6E6E6;
                        border: 1px solid #444444;
                        selection-background-color: #3A3A3A;
                        font-size: 15px;
                        padding: 6px 8px;
                        min-height: 34px;
                    }
                    QComboBox QAbstractItemView {
                        background-color: #1A1A1A;
                        color: #E6E6E6;
                        font-size:14px;
                    }
                """)

                for c in spec.get("choices", []):
                    w.addItem(c)
                default = str(self.values.get(key, spec.get("default", "")))
                idx = w.findText(default) if default else -1
                idx = idx if idx >= 0 else 0
                w.setCurrentIndex(int(idx))

                w._hover_key = key
                w.installEventFilter(self)
                w.currentIndexChanged.connect(lambda _, k=key: self._on_combo_changed(k))

                row_layout.addWidget(w, 3)

                self._label_to_combo[name_lbl] = w
                self._row_frames[name_lbl] = row_frame
                name_lbl.mousePressEvent = lambda ev, k=key: self._on_label_clicked(k)

                self.widgets[key] = w

            else:
                w = QLineEdit(str(self.values.get(key, spec.get("default", ""))))
                w.setMinimumHeight(34)
                w.setStyleSheet("font-size:15px;")
                row_layout.addWidget(w, 1)
                self.widgets[key] = w

            row_frame.setStyleSheet("""
                QFrame {
                    border: 1px solid #333333;
                    border-radius: 6px;
                    background: transparent;
                }
                QFrame[hover="true"] {
                    border: 1px solid rgba(255,255,255,0.06);
                    background: rgba(255,255,255,0.015);
                }
                QFrame[selected="true"] {
                    border: 1px solid rgba(255,255,255,0.25);
                    background: rgba(255,255,255,0.03);
                }
            """)
            left_col.addWidget(row_frame)

        left_col.addStretch(1)
        left_wrap.setLayout(left_col)
        left_scroll.setWidget(left_wrap)

        # RIGHT: preview area
        right_panel = QWidget()
        # Move description area slightly away from the divider by increasing left content margin
        right_col = QVBoxLayout(right_panel)
        right_col.setSpacing(8)
        right_col.setContentsMargins(40, 0, 0, 0)  # scoot everything in the right column 24px right
        right_panel.setMinimumWidth(420)
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(10)
        preview_row.setContentsMargins(0, 0, 0, 0)

        self.btn_prev = QToolButton()
        self.btn_prev.setText("◀")
        self.btn_prev.setFixedSize(44, 44)
        self.btn_prev.setStyleSheet("""
            QToolButton {
                font-size: 22px;
                background: #1A1A1A;
                color: #FFFFFF;
                border: 1px solid #333333;
                border-radius: 6px;
            }
            QToolButton:hover {
                background: #2A2A2A;
            }
        """)
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(lambda: self._arrow_flash_and_cycle(-1))

        # Central image label (will scale responsively)
        self.picture_label = QLabel()
        self.picture_label.setAlignment(Qt.AlignCenter)
        self.picture_label.setMinimumSize(220, 140)
        self.picture_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.picture_label.setStyleSheet("background: transparent;")

        self.btn_next = QToolButton()
        self.btn_next.setText("▶")
        self.btn_next.setFixedSize(44, 44)
        self.btn_next.setStyleSheet("""
            QToolButton {
                font-size: 22px;
                background: #1A1A1A;
                color: #FFFFFF;
                border: 1px solid #333333;
                border-radius: 6px;
            }
            QToolButton:hover {
                background: #2A2A2A;
            }
        """)
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(lambda: self._arrow_flash_and_cycle(1))

        preview_row.addWidget(self.btn_prev, 0, Qt.AlignVCenter)
        preview_row.addWidget(self.picture_label, 1)
        preview_row.addWidget(self.btn_next, 0, Qt.AlignVCenter)
        right_col.addLayout(preview_row)

        # Caption
        self.preview_caption = QLabel("")
        self.preview_caption.setWordWrap(True)
        self.preview_caption.setStyleSheet("color:#DADADA; font-size:14px;")
        self.preview_caption.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right_col.addWidget(self.preview_caption)

        # Description label + box (scaled but not oversized)
        self.desc_label = QLabel("Description:")
        self.desc_label.setStyleSheet("font-size:15px; margin-top:2px; font-weight:700;")

        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setPlainText(self.schema_description or "")
        self.desc_text.setStyleSheet("font-size:14px;")
        self.desc_text.setFrameStyle(QFrame.NoFrame)
        self.desc_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.desc_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 🔥 Key adjustments
        self.desc_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.desc_text.setFixedHeight(100)   # about 3–4 lines tall by default

        desc_stack = QVBoxLayout()
        desc_stack.setSpacing(4)
        desc_stack.setContentsMargins(0, 0, 0, 0)
        desc_stack.addWidget(self.desc_label, 0, Qt.AlignLeft)
        desc_stack.addWidget(self.desc_text)

        desc_row = QHBoxLayout()
        desc_row.addStretch(1)
        desc_row.addLayout(desc_stack)
        right_col.addLayout(desc_row)

        # Footer
        footer = QHBoxLayout()
        footer.setAlignment(Qt.AlignCenter)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        beef_up_buttons(btns)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        footer.addWidget(btns)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setOpaqueResize(True)
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2A2A2A;
                width: 8px;
            }
            QSplitter::handle:hover {
                background-color: #3A3A3A;
            }
        """)
        splitter.addWidget(left_scroll)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        initial_left = max(300, int(self.width() * 0.36))
        initial_right = max(420, int(self.width() * 0.64))
        splitter.setSizes([initial_left, initial_right])

        splitter.splitterMoved.connect(self._on_splitter_moved)
        self._drag_idle_timer.timeout.connect(self._rerender_current_preview_smooth)

        outer.addWidget(splitter, 1)
        outer.addLayout(footer)

        # init
        self._update_preview_idle()
        self._refresh_buttons_enabled()

        self.setStyleSheet("""
            QLineEdit, QTextEdit, QListWidget {
                background-color: #1A1A1A;
                color: #E6E6E6;
                border: 1px solid #333;
                selection-background-color: #3A3A3A;
            }
            QComboBox {
                background-color: #1A1A1A;
                color: #E6E6E6;
                border: 1px solid #444444;
                selection-background-color: #3A3A3A;
                font-size: 14px;
                padding: 2px 8px;
                min-height: 32px;
            }
            QComboBox QAbstractItemView {
                background-color: #1A1A1A;
                color: #E6E6E6;
                selection-background-color: #3A3A3A;
                font-size: 14px;
            }
        """)

    # Live splitter handlers
    def _on_splitter_moved(self, pos, index):
        # Called continuously while dragging thanks to opaque resize True.
        self._is_dragging_splitter = True
        # Immediately re-render at fast transformation so image visually shrinks while dragging
        self._rerender_current_preview_fast()
        # Start/refresh the idle timer to switch to smooth rendering shortly after drag stops
        self._drag_idle_timer.start()

    def _rerender_current_preview_fast(self):
        # Keep the caption width in sync with picture width
        try:
            self.desc_text.setFixedWidth(self.picture_label.width())
        except Exception:
            pass
        # Fast (nearest) transform to keep UI snappy while dragging
        self._render_current_preview(transform_mode=Qt.FastTransformation)

    def _rerender_current_preview_smooth(self):
        # Switch back to smooth transform for final render
        self._is_dragging_splitter = False
        self._render_current_preview(transform_mode=Qt.SmoothTransformation)

    def _render_current_preview(self, transform_mode=Qt.SmoothTransformation):
        key = self._active_key
        if key and key in self.widgets and isinstance(self.widgets[key], QComboBox):
            combo = self.widgets[key]
            choice = combo.currentText()
            entry = self.attachments.get(key, {}).get(choice or "", {})
            previews = entry.get("previews", [])
            if previews:
                idx = self._current_preview_idx.get((key, choice), 0)
                idx = max(0, min(idx, len(previews)-1))
                ref = previews[idx].get("ref", "")
                pix = self._get_scaled_from_cache_or_base(ref, transform_mode)
                if pix and not pix.isNull():
                    self._crossfade_to(pix, hover=False)

    # Caching + base loader
    def _cache_key(self, ref: str, w: int, h: int, mode: int) -> str:
        return f"{ref}|{w}x{h}|{mode}"

    def _load_base_pix(self, ref: str) -> QPixmap:
        if ref in self._base_pix_cache:
            return self._base_pix_cache[ref]
        
        base = QPixmap()
        try:
            if isinstance(ref, str) and ref.startswith("packed::"):
                packed_name = ref.split("::", 1)[1]
                tmp = _sb_extract_packed_to_temp(self.mod_folder, packed_name)
                if tmp and tmp.exists():
                    base = QPixmap(str(tmp))
            else:
                file_path = self.mod_folder / ref
                if file_path.exists():
                    base = QPixmap(str(file_path))
        except Exception:
            base = QPixmap()
        
        if not base or base.isNull():
            return QPixmap()
        
        # Limit base cache size to prevent memory bloat
        if len(self._base_pix_cache) > 20:  # Keep only 20 base images
            oldest_keys = list(self._base_pix_cache.keys())[:5]
            for old_key in oldest_keys:
                del self._base_pix_cache[old_key]
        
        self._base_pix_cache[ref] = base
        return base

    def _get_scaled_from_cache_or_base(self, ref: str, transform_mode: Qt.TransformationMode) -> QPixmap:
        if not ref:
            return QPixmap()
        
        # Use current visible picture_label size so scaling reflects splitter changes immediately
        w = max(1, int(self.picture_label.width()))
        h = max(1, int(self.picture_label.height()))
        mode_flag = 1 if transform_mode == Qt.SmoothTransformation else 0
        key = self._cache_key(ref, w, h, mode_flag)
        
        # Check scaled cache first
        if key in self._pix_cache:
            return self._pix_cache[key]
        
        # Load base image
        base = self._load_base_pix(ref)
        if not base or base.isNull():
            return QPixmap()
        
        # Performance optimization: Skip scaling if image is already close to target size
        base_w, base_h = base.width(), base.height()
        if abs(base_w - w) <= 20 and abs(base_h - h) <= 20:
            # Image is already very close to target size, just apply outline
            outlined = self._outlined(base)
            self._pix_cache[key] = outlined
            return outlined
        
        # Scale the image
        sp = base.scaled(w, h, Qt.KeepAspectRatio, transform_mode)
        outlined = self._outlined(sp)
        
        # Limit cache size to prevent memory bloat (keep 40 most recent)
        if len(self._pix_cache) > 40:
            # Remove oldest entries (simple FIFO)
            oldest_keys = list(self._pix_cache.keys())[:10]
            for old_key in oldest_keys:
                del self._pix_cache[old_key]
        
        # Cache per (ref,w,h,mode) to avoid re-scaling when user drags back and forth
        self._pix_cache[key] = outlined
        return outlined

    def _outlined(self, pix: QPixmap) -> QPixmap:
        if not pix or pix.isNull():
            return pix
        out = QPixmap(pix.size())
        out.fill(Qt.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.drawPixmap(0, 0, pix)
        pen = QPen(QColor("#555"), 1)
        painter.setPen(pen)
        painter.drawRect(0, 0, out.width() - 1, out.height() - 1)
        painter.end()
        return out

    # Make preview responsive to window resize as well
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # Re-render immediately in fast mode while resizing for visual continuity
        self._rerender_current_preview_fast()
        # After resize ends, switch to smooth priority shortly after
        self._drag_idle_timer.start()
        try:
            self.preview_caption.update()
        except Exception:
            pass

    def _rerender_current_preview(self):
        # kept for older callsites (fast)
        self._rerender_current_preview_fast()

    # Arrow flash helper
    def _arrow_flash_and_cycle(self, delta):
        btn = self.btn_prev if delta < 0 else self.btn_next
        if self._arrow_flash_timer and self._arrow_flash_timer.isActive():
            return
        orig = btn.styleSheet()
        flash_css = orig + "\nQToolButton { background: rgba(255, 255, 255, 0.3); }"
        btn.setStyleSheet(flash_css)
        self._arrow_flash_timer = QTimer(self)
        self._arrow_flash_timer.setSingleShot(True)
        self._arrow_flash_timer.setInterval(140)
        def restore():
            btn.setStyleSheet(orig)
            self._arrow_flash_timer = None
        self._arrow_flash_timer.timeout.connect(restore)
        self._arrow_flash_timer.start()
        self._cycle_guarded(delta)

    # interactions (label / combo)
    def _on_label_clicked(self, key):
        if self._active_key == key:
            self._deselect_all()
            return
        self._active_key = key
        combo = self.widgets.get(key)
        if isinstance(combo, QComboBox):
            combo.setFocus(Qt.MouseFocusReason)
        self._apply_row_selection(key, selected=True)
        self._show_preview_for_active_instant()

    def _on_combo_changed(self, key):
        self._active_key = key
        self._apply_row_selection(key, selected=True)
        self._show_preview_for_active_instant()

    def _apply_row_selection(self, key, selected=False):
        for lbl, combo in self._label_to_combo.items():
            row = self._row_frames.get(lbl)
            if row is None:
                continue
            is_this = (self.widgets.get(key) is combo)
            row.setProperty("selected", is_this and selected)
            row.setProperty("hover", False)
            row.style().unpolish(row)
            row.style().polish(row)
            row.update()

    def _deselect_all(self):
        self._active_key = None
        for lbl, combo in self._label_to_combo.items():
            row = self._row_frames.get(lbl)
            if row:
                row.setProperty("selected", False)
                row.setProperty("hover", False)
                row.style().unpolish(row)
                row.style().polish(row)
                row.update()
        self._update_preview_idle()
        self._refresh_buttons_enabled()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self._deselect_all()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def mousePressEvent(self, ev):
        if not self._click_hits_interactive(ev.pos()):
            self._deselect_all()
        super().mousePressEvent(ev)

    def _click_hits_interactive(self, pos: QPoint) -> bool:
        for lbl, combo in self._label_to_combo.items():
            row = self._row_frames.get(lbl)
            if row:
                rp = row.mapFrom(self, pos)
                if QRect(QPoint(0, 0), row.size()).contains(rp):
                    return True
        for w in self.widgets.values():
            if isinstance(w, QComboBox):
                wp = w.mapFrom(self, pos)
                if QRect(QPoint(0, 0), w.size()).contains(wp):
                    return True
        return False

    # eventFilter: hover shows preview
    def eventFilter(self, obj, ev):
        # Existing hover and selection logic
        if (isinstance(obj, QLabel) or isinstance(obj, QComboBox)) and hasattr(obj, "_hover_key"):
            key = obj._hover_key
            row = self._row_frames.get(obj)

            # Hover Enter Event
            if ev.type() == QEvent.Enter:
                # Prevent preview changes when a row is already selected
                if self._active_key is None:
                    combo = self._label_to_combo.get(obj) if isinstance(obj, QLabel) else obj
                    if combo:
                        choice = combo.currentText()
                        if choice:
                            # Show preview for the current dropdown's choice
                            self._show_preview_for_key_choice(key, choice, hover=True)

                            # Update row hover styling
                            if row:
                                row.setProperty("hover", True)
                                row.style().unpolish(row)
                                row.style().polish(row)
                                row.update()
                return False

            # Hover Leave Event
            elif ev.type() == QEvent.Leave:
                # Prevent fade out when a row is selected
                if self._active_key is None:
                    self._fade_out_preview()
                    if row:
                        row.setProperty("hover", False)
                        row.style().unpolish(row)
                        row.style().polish(row)
                        row.update()
                return False

        # [NEW] Dropdown Choice Hover Preview Logic
        if isinstance(obj, QComboBox) and ev.type() == QEvent.HoverMove:
            # Ensure a row is selected and we're hovering over choices
            if self._active_key is not None:
                choice = obj.currentText()

                # Check if the choice has a different preview
                entry = self.attachments.get(self._active_key, {}).get(choice, {})
                previews = entry.get("previews", [])

                # Update preview for non-default choices with unique images
                if choice not in ["Enabled", "Disabled"] and previews:
                    ref = previews[0].get("ref", "")
                    desc = previews[0].get("desc", "")

                    # Generate and display preview
                    pix = self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
                    if pix and not pix.isNull():
                        # Modify this to prevent aggressive fading when row is selected
                        self._crossfade_to(pix, hover=False)  # Changed from hover=True
                        self.preview_caption.setText(desc)

            return False

        # Dropdown Selection Event
        if isinstance(obj, QComboBox) and ev.type() == QEvent.MouseButtonPress:
            # Set active key and select entire row
            self._active_key = key
            self._apply_row_selection(key, selected=True)

            # Show preview for the selected choice
            choice = obj.currentText()
            entry = self.attachments.get(key, {}).get(choice, {})
            previews = entry.get("previews", [])

            if previews:
                ref = previews[0].get("ref", "")
                desc = previews[0].get("desc", "")
                pix = self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
                if pix and not pix.isNull():
                    self._crossfade_to(pix, hover=False)
                    self.preview_caption.setText(desc)

            return False

        return super().eventFilter(obj, ev)

    def mouseMoveEvent(self, ev):
        # Check if mouse is over any dropdown row
        over_any_row = False
        for lbl in self._label_to_combo.keys():
            row = self._row_frames.get(lbl)
            if row:
                row_pos = row.mapFrom(self, ev.pos())
                if QRect(QPoint(0, 0), row.size()).contains(row_pos):
                    over_any_row = True
                    break
        
        # Store the hover state and start/reset fade timer
        if hasattr(self, '_hover_fade_timer'):
            self._hover_fade_timer.stop()
        else:
            self._hover_fade_timer = QTimer(self)
            self._hover_fade_timer.setSingleShot(True)
            self._hover_fade_timer.timeout.connect(self._check_and_fade_preview)
        
        if over_any_row:
            # Mouse is over a row, cancel any pending fade
            pass
        else:
            # Mouse not over any row, start fade timer
            if self._active_key is None:
                self._hover_fade_timer.start(50)  # 50ms delay for faster response
        
        super().mouseMoveEvent(ev)

    def leaveEvent(self, ev):
        # Fade out preview when mouse leaves the entire dialog
        if self._active_key is None:
            if self._layer_current and self._layer_current.isVisible():
                self._fade_out_preview()
        super().leaveEvent(ev)

    def _check_and_fade_preview(self):
        # Double-check that mouse is still not over any dropdown before fading
        if self._active_key is None:
            try:
                cursor_pos = self.mapFromGlobal(self.cursor().pos())
                over_any_row = False
                
                # Check if cursor is within the dialog bounds first
                dialog_rect = QRect(QPoint(0, 0), self.size())
                if not dialog_rect.contains(cursor_pos):
                    # Mouse is outside dialog, definitely fade out
                    if self._layer_current and self._layer_current.isVisible():
                        self._fade_out_preview()
                    return
                
                # Check each dropdown row
                for lbl in self._label_to_combo.keys():
                    row = self._row_frames.get(lbl)
                    if row and row.isVisible():
                        row_pos = row.mapFrom(self, cursor_pos)
                        row_rect = QRect(QPoint(0, 0), row.size())
                        if row_rect.contains(row_pos):
                            over_any_row = True
                            break
                
                if not over_any_row and self._layer_current and self._layer_current.isVisible():
                    self._fade_out_preview()
            except Exception:
                # If there's any error, just fade out to be safe
                if self._layer_current and self._layer_current.isVisible():
                    self._fade_out_preview()

    # preview helpers (cache + crossfade)
    def _get_scaled_from_cache_or_base_public(self, ref: str, transform_mode: Qt.TransformationMode) -> QPixmap:
        return self._get_scaled_from_cache_or_base(ref, transform_mode)

    def _update_preview_idle(self):
        if self._layer_current:
            try:
                self._layer_current.deleteLater()
            except Exception:
                pass
            self._layer_current = None
        if self._layer_next:
            try:
                self._layer_next.deleteLater()
            except Exception:
                pass
            self._layer_next = None
        self._current_showing_ref = None  # Clear the reference when going idle
        self.preview_caption.setText("")

    def _refresh_buttons_enabled(self, key=None):
        if key is None:
            key = self._active_key
        if not key or key not in self.widgets or not isinstance(self.widgets[key], QComboBox):
            try:
                self.btn_prev.setEnabled(False)
                self.btn_next.setEnabled(False)
            except Exception:
                pass
            return
        combo = self.widgets[key]
        choice = combo.currentText()
        previews = self.attachments.get(key, {}).get(choice or "", {}).get("previews", [])
        multi = len(previews) > 1
        self.btn_prev.setEnabled(multi)
        self.btn_next.setEnabled(multi)

    def _show_preview_for_active(self):
        self._show_preview_for_key_choice(self._active_key, None, hover=False)

    def _show_preview_for_active_instant(self):
        key = self._active_key
        if not key or key not in self.widgets or not isinstance(self.widgets[key], QComboBox):
            self._update_preview_idle()
            self._refresh_buttons_enabled()
            return
        combo = self.widgets[key]
        choice = combo.currentText()
        if not choice:
            self._update_preview_idle()
            self._refresh_buttons_enabled(key)
            return
        entry = self.attachments.get(key, {}).get(choice or "", {})
        previews = entry.get("previews", [])
        if not previews:
            self._update_preview_idle()
            self._refresh_buttons_enabled(key)
            return
        idx = self._current_preview_idx.get((key, choice), 0)
        idx = max(0, min(idx, len(previews) - 1))
        ref = previews[idx].get("ref", "")
        desc = previews[idx].get("desc", "")
        
        # Check if we're already showing this exact same image to avoid redundant fade-in
        current_ref = getattr(self, '_current_showing_ref', None)
        if current_ref == ref and self._layer_current and self._layer_current.isVisible():
            # Just update the caption, no need to re-fade the same image
            self.preview_caption.setText(desc or "")
        else:
            pix = self._get_scaled_from_cache_or_base(ref, Qt.SmoothTransformation)
            if pix and not pix.isNull():
                self._crossfade_to(pix, hover=False)
                self.preview_caption.setText(desc or "")
                self._current_showing_ref = ref
            else:
                self._update_preview_idle()
        self._refresh_buttons_enabled(key)

    def _show_instant(self, pix: QPixmap):
        if self._layer_current:
            try:
                self._layer_current.deleteLater()
            except Exception:
                pass
        if self._layer_next:
            try:
                self._layer_next.deleteLater()
            except Exception:
                pass

        self._layer_current = QLabel(self.picture_label)
        self._layer_current.setAlignment(Qt.AlignCenter)
        self._layer_current.setGeometry(self.picture_label.rect())
        self._layer_current.setStyleSheet("background: transparent;")
        self._layer_current.setPixmap(pix)
        self._layer_current.show()
        self._layer_next = None

    def _show_preview_for_key_choice(self, key, choice=None, hover=False):
        if not key or key not in self.widgets or not isinstance(self.widgets[key], QComboBox):
            if not hover:
                self._update_preview_idle()
                self._refresh_buttons_enabled()
            return
        combo = self.widgets[key]
        if choice is None:
            choice = combo.currentText()
        if not choice:
            if not hover:
                self._update_preview_idle()
                self._refresh_buttons_enabled(key)
            return
        entry = self.attachments.get(key, {}).get(choice or "", {})
        previews = entry.get("previews", [])
        if not previews:
            if not hover:
                self._update_preview_idle()
                self._refresh_buttons_enabled(key)
            return
        idx = self._current_preview_idx.get((key, choice), 0)
        idx = max(0, min(idx, len(previews)-1))
        ref = previews[idx].get("ref", "")
        desc = previews[idx].get("desc", "")
        
        # Check if we're already showing this exact same image to avoid redundant fade-in
        current_ref = getattr(self, '_current_showing_ref', None)
        if current_ref == ref and self._layer_current and self._layer_current.isVisible():
            # Just update the caption, no need to re-fade the same image
            self.preview_caption.setText(desc or "")
        else:
            mode = Qt.FastTransformation if self._is_dragging_splitter else Qt.SmoothTransformation
            pix = self._get_scaled_from_cache_or_base(ref, mode)
            if pix and not pix.isNull():
                self._crossfade_to(pix, hover=hover)
                self.preview_caption.setText(desc or "")
                self._current_showing_ref = ref
            else:
                if not hover:
                    self._update_preview_idle()
        self._refresh_buttons_enabled(key)

    def _fade_out_preview(self):
        # Stop any ongoing crossfade animations first
        if hasattr(self, '_fade_enter') and self._fade_enter:
            try:
                self._fade_enter.stop()
                self._fade_enter = None
            except Exception:
                pass
        if hasattr(self, '_fade_exit') and self._fade_exit:
            try:
                self._fade_exit.stop()
                self._fade_exit = None
            except Exception:
                pass
        
        # Clean up any next layer that might be in transition
        if self._layer_next:
            try:
                self._layer_next.deleteLater()
            except Exception:
                pass
            self._layer_next = None
        
        if not self._layer_current:
            self._update_preview_idle()
            return
            
        eff = self._layer_current.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(self._layer_current)
            self._layer_current.setGraphicsEffect(eff)
            eff.setOpacity(1.0)
        
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(self._fade_out_duration)
        anim.setStartValue(eff.opacity())  # Start from current opacity, not always 1.0
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InOutCubic)

        def done():
            try:
                self._layer_current.deleteLater()
            except Exception:
                pass
            self._layer_current = None
            self._current_showing_ref = None  # Clear the reference when fading out
            self.preview_caption.setText("")

        anim.finished.connect(done)
        anim.start()

    def _crossfade_to(self, pix: QPixmap, hover=False):
        if self._layer_next:
            try:
                self._layer_next.deleteLater()
            except Exception:
                pass
            self._layer_next = None
        self._layer_next = QLabel(self.picture_label)
        self._layer_next.setAlignment(Qt.AlignCenter)
        self._layer_next.setGeometry(self.picture_label.rect())
        self._layer_next.setStyleSheet("background: transparent;")
        self._layer_next.setPixmap(pix)
        self._layer_next.show()

        if not self._layer_current:
            # Even for first show, add a nice fade-in effect
            eff = QGraphicsOpacityEffect(self._layer_next)
            self._layer_next.setGraphicsEffect(eff)
            eff.setOpacity(0.0)
            
            duration = 250 if hover else 200  # Slightly faster for hover responsiveness
            self._fade_enter = QPropertyAnimation(eff, b"opacity", self)
            self._fade_enter.setDuration(duration)
            self._fade_enter.setStartValue(0.0)
            self._fade_enter.setEndValue(1.0)
            self._fade_enter.setEasingCurve(QEasingCurve.InOutCubic)
            
            def finish_first():
                self._layer_current = self._layer_next
                self._layer_next = None
                self._fade_enter = None
            
            self._fade_enter.finished.connect(finish_first)
            self._fade_enter.start()
            return

        for layer in (self._layer_current, self._layer_next):
            if not isinstance(layer.graphicsEffect(), QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(layer)
                layer.setGraphicsEffect(eff)
                eff.setOpacity(1.0 if layer is self._layer_current else 0.0)

        eff_cur = self._layer_current.graphicsEffect()
        eff_next = self._layer_next.graphicsEffect()
        duration = 250 if hover else 200  # Slightly faster for hover responsiveness

        self._fade_exit = QPropertyAnimation(eff_cur, b"opacity", self)
        self._fade_exit.setDuration(self._fade_out_duration)
        self._fade_exit.setStartValue(1.0)
        self._fade_exit.setEndValue(0.0)
        self._fade_exit.setEasingCurve(QEasingCurve.InOutCubic)

        self._fade_enter = QPropertyAnimation(eff_next, b"opacity", self)
        self._fade_enter.setDuration(duration)
        self._fade_enter.setStartValue(0.0)
        self._fade_enter.setEndValue(1.0)
        self._fade_enter.setEasingCurve(QEasingCurve.InOutCubic)

        def finish():
            try:
                if self._layer_current:
                    self._layer_current.deleteLater()
            except Exception:
                pass
            self._layer_current = self._layer_next
            self._layer_next = None
            self._fade_enter = None
            self._fade_exit = None

        self._fade_exit.finished.connect(finish)
        self._fade_enter.start()
        self._fade_exit.start()

    def _cycle_guarded(self, delta: int):
        now = int(time.time() * 1000)
        if now - self._last_click_ms < 160 or self._busy:
            return
        self._last_click_ms = now
        self._busy = True
        try:
            key = self._active_key
            if not key or key not in self.widgets or not isinstance(self.widgets[key], QComboBox):
                return
            combo = self.widgets[key]
            choice = combo.currentText()
            if not choice:
                return
            previews = self.attachments.get(key, {}).get(choice or "", {}).get("previews", [])
            if not previews:
                return
            idx = (self._current_preview_idx.get((key, choice), 0) + delta) % len(previews)
            self._current_preview_idx[(key, choice)] = int(idx)
            mode = Qt.FastTransformation if self._is_dragging_splitter else Qt.SmoothTransformation

            # perform a crossfade transition when cycling pictures
            ref = previews[idx].get("ref", "")
            if not ref:
                return

            new_pix = self._get_scaled_from_cache_or_base(ref, mode)
            if not new_pix or new_pix.isNull():
                return

            # If there is currently no visible layer, just show instantly
            if not self._layer_current:
                self._crossfade_to(new_pix, hover=False)
            else:
                # Prepare next layer and crossfade (non-hover fade_duration)
                if self._layer_next:
                    try:
                        self._layer_next.deleteLater()
                    except Exception:
                        pass
                    self._layer_next = None

                self._layer_next = QLabel(self.picture_label)
                self._layer_next.setAlignment(Qt.AlignCenter)
                self._layer_next.setGeometry(self.picture_label.rect())
                self._layer_next.setStyleSheet("background: transparent;")
                self._layer_next.setPixmap(new_pix)
                self._layer_next.show()

                # Ensure both layers have opacity effects
                for layer in (self._layer_current, self._layer_next):
                    if not isinstance(layer.graphicsEffect(), QGraphicsOpacityEffect):
                        eff = QGraphicsOpacityEffect(layer)
                        layer.setGraphicsEffect(eff)
                        eff.setOpacity(1.0 if layer is self._layer_current else 0.0)

                eff_cur = self._layer_current.graphicsEffect()
                eff_next = self._layer_next.graphicsEffect()

                fade_out = QPropertyAnimation(eff_cur, b"opacity", self)
                fade_out.setDuration(self._fade_out_duration)
                fade_out.setStartValue(1.0)
                fade_out.setEndValue(0.0)
                fade_out.setEasingCurve(QEasingCurve.InOutCubic)

                fade_in = QPropertyAnimation(eff_next, b"opacity", self)
                fade_in.setDuration(self._fade_duration)
                fade_in.setStartValue(0.0)
                fade_in.setEndValue(1.0)
                fade_in.setEasingCurve(QEasingCurve.InOutCubic)

                def on_finished():
                    try:
                        if self._layer_current:
                            self._layer_current.deleteLater()
                    except Exception:
                        pass
                    self._layer_current = self._layer_next
                    self._layer_next = None

                fade_out.finished.connect(on_finished)
                fade_in.start()
                fade_out.start()

            # Update caption for this new index
            desc = previews[idx].get("desc", "")
            try:
                self.preview_caption.setText(desc or "")
            except Exception:
                pass

            self._refresh_buttons_enabled(key)
        finally:
            QTimer.singleShot(120, lambda: setattr(self, "_busy", False))

    # ---------- Data loaders (unchanged) ----------
    def _load_schema(self):
        data_file = self.mod_folder / "mod_data.json"
        if data_file.exists():
            try:
                data = json.loads(data_file.read_text(encoding="utf-8"))
                section = data.get("SET CONFIGURE SCHEMA", {}) or {}
                schema = section.get("schema", {}) or {}
                for k, v in list(schema.items()):
                    if k.startswith("__"):
                        continue
                    if v.get("type") == "dropdown":
                        v.setdefault("choices", ["Enabled", "Disabled"])
                        v.setdefault("default", "Disabled")
                if schema:
                    return schema
            except Exception:
                pass
        p = self.mod_folder / "config_schema.json"
        if p.exists():
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
                for k, v in list(s.items()):
                    if k.startswith("__"):
                        continue
                    if v.get("type") == "dropdown":
                        v.setdefault("choices", ["Enabled", "Disabled"])
                        v.setdefault("default", "Disabled")
                return s
            except Exception:
                pass
        return {"preset": {"label": "Preset", "type": "dropdown", "choices": ["Enabled", "Disabled"], "default": "Disabled"}}

    def _load_values(self):
        # First try the new unified mod_data.json format
        data_file = self.mod_folder / "mod_data.json"
        if data_file.exists():
            try:
                data = json.loads(data_file.read_text(encoding="utf-8"))
                config_values = data.get("CONFIGURE MOD MENU", {})
                if config_values:
                    print(f"[DEBUG] Loaded values from mod_data.json: {config_values}")
                    return config_values
            except Exception:
                pass
        
        # Fallback to legacy config.json
        p = self.mod_folder / "config.json"
        if p.exists():
            try:
                values = json.loads(p.read_text(encoding="utf-8"))
                print(f"[DEBUG] Loaded values from legacy config.json: {values}")
                return values
            except Exception:
                return {}
        
        print("[DEBUG] No saved values found, using defaults")
        return {}

    def _load_attachments(self):
        try:
            data_file = self.mod_folder / "mod_data.json"
            if data_file.exists():
                try:
                    data = json.loads(data_file.read_text(encoding="utf-8"))
                    section = data.get("SET CONFIGURE SCHEMA", {}) or {}
                    attachments = section.get("attachments", {}) or {}
                    for dd, choices in list((attachments or {}).items()):
                        for ch, entry in list((choices or {}).items()):
                            if isinstance(entry, dict) and "preview" in entry and "previews" not in entry:
                                ref = entry.get("preview")
                                if ref:
                                    entry["previews"] = [{"ref": ref, "desc": ""}]
                                entry.pop("preview", None)
                    return attachments or {}
                except Exception:
                    pass
            p = self.mod_folder / "config_schema_files.json"
            data = {}
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
            for dd, choices in list((data or {}).items()):
                for ch, entry in list((choices or {}).items()):
                    if isinstance(entry, dict) and "preview" in entry and "previews" not in entry:
                        ref = entry.get("preview")
                        if ref:
                            entry["previews"] = [{"ref": ref, "desc": ""}]
                        entry.pop("preview", None)
            return data or {}
        except Exception:
            pass
        return {}

    def _save(self):
        mod = Path(self.mod_folder)
        out = {}
        print(f"[DEBUG] Saving config for mod: {mod}")
        print(f"[DEBUG] Found {len(self.widgets)} widgets to save")
        
        for key, w in self.widgets.items():
            if isinstance(w, QComboBox):
                value = w.currentText()
                current_index = w.currentIndex()
                all_items = [w.itemText(i) for i in range(w.count())]
                out[key] = value
                print(f"[DEBUG] ComboBox {key} = '{value}' (index {current_index})")
                print(f"[DEBUG]   Available items: {all_items}")
            elif isinstance(w, QPushButton) and w.isCheckable():
                value = w.isChecked()
                out[key] = value
                print(f"[DEBUG] CheckableButton {key} = {value}")
            elif isinstance(w, QLineEdit):
                value = w.text().strip()
                out[key] = value
                print(f"[DEBUG] LineEdit {key} = {value}")
            else:
                try:
                    value = str(w.text()).strip()
                    out[key] = value
                    print(f"[DEBUG] Other widget {key} = {value}")
                except Exception:
                    print(f"[DEBUG] Failed to get value for {key}")
                    pass
        
        print(f"[DEBUG] Final config to save: {out}")
        try:
            data_file = mod / "mod_data.json"
            print(f"[DEBUG] Writing to: {data_file}")
            data = json.loads(data_file.read_text(encoding="utf-8")) if data_file.exists() else {}
            print(f"[DEBUG] Existing data: {data}")
            data["CONFIGURE MOD MENU"] = out
            print(f"[DEBUG] Updated data: {data}")
            data_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"[DEBUG] Successfully wrote mod_data.json")
            legacy = mod / "config.json"
            if legacy.exists():
                try:
                    legacy.unlink()
                    print(f"[DEBUG] Removed legacy config.json")
                except Exception:
                    pass
        except Exception as e:
            print(f"[DEBUG] Save error: {e}")
            QMessageBox.critical(self, "Save Failed", f"Could not write mod_data.json:\n{e}")
            return
        try:
            configs_dir = mod / "configs"
            if configs_dir.exists():
                for jf in configs_dir.glob("*.json"):
                    if jf.stem not in out:
                        jf.unlink()
        except Exception:
            pass
        
        # Close the dialog after successful save
        self.accept()

# -----------------------
# UpdateCheckDialog — scrollable update results
# -----------------------
class UpdateCheckDialog(QDialog):
    def __init__(self, updates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mod Updates")
        self.setModal(True)

        # Your original default size
        self.resize(710, 562)
        self.setMaximumSize(900, 700)

        self._entry_pixmaps = []
        self._thumb_labels = []
        self._viewport = None
        self._mod_entries = []
        self._scroll = None

        main = QVBoxLayout(self)

        headline = QLabel("<span style='font-size:16pt; font-weight:600;'>The Following Mods have Updates:</span>")
        headline.setAlignment(Qt.AlignCenter)
        main.addWidget(headline)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._viewport = scroll.viewport()
        self._scroll = scroll

        container = QWidget()
        list_layout = QVBoxLayout(container)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(16)

        if not updates:
            empty = QLabel("<b>Everything is up to date.</b>")
            empty.setAlignment(Qt.AlignCenter)
            list_layout.addWidget(empty)
        else:
            for u in updates:
                entry_frame = QFrame()
                entry = QVBoxLayout(entry_frame)
                entry.setSpacing(10)

                name_label = QLabel(f"<b>{u.get('name','(mod)')}</b>")
                name_label.setAlignment(Qt.AlignCenter)
                name_label.setStyleSheet("font-size: 13pt;")
                entry.addWidget(name_label)

                ver_label = QLabel(f"{u.get('current','?')} → {u.get('latest','?')}")
                ver_label.setAlignment(Qt.AlignCenter)
                ver_label.setStyleSheet("font-size: 11pt; color: #C8C8C8;")
                entry.addWidget(ver_label)

                thumb_label = QLabel()
                thumb_label.setAlignment(Qt.AlignCenter)
                thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                thumb_label.setMaximumHeight(900)

                pix = self._load_thumbnail_from_page(u.get("url", ""))
                if pix:
                    self._entry_pixmaps.append(pix)
                    self._thumb_labels.append(thumb_label)
                    thumb_label.setPixmap(self._scaled_pix(pix, thumb_label))
                else:
                    self._entry_pixmaps.append(None)
                    self._thumb_labels.append(thumb_label)
                    thumb_label.setText("[No Thumbnail]")

                entry.addWidget(thumb_label, 0, Qt.AlignCenter)

                btn_row = QHBoxLayout()
                btn_row.setSpacing(100)  # keep your spacing
                btn_row.setAlignment(Qt.AlignCenter)

                close_btn = QPushButton("Close")
                close_btn.setMinimumSize(150, 50)
                close_btn.setCursor(Qt.PointingHandCursor)
                close_btn.clicked.connect(self.reject)

                page_btn = QPushButton("Go to Page")
                page_btn.setMinimumSize(150, 50)
                page_btn.setCursor(Qt.PointingHandCursor)

                idx = len(self._mod_entries)
                page_btn.clicked.connect(lambda _, link=u.get("url",""), i=idx: self._open_and_scroll(link, i))

                btn_row.addWidget(close_btn)
                btn_row.addWidget(page_btn)
                entry.addLayout(btn_row)

                self._mod_entries.append(entry_frame)
                list_layout.addWidget(entry_frame)

                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                list_layout.addWidget(line)

        container.setLayout(list_layout)
        scroll.setWidget(container)
        main.addWidget(scroll)

        self.setStyleSheet("""
            QScrollArea { background-color: #1A1A1A; border: none; }
            QLabel { color: #E6E6E6; }
            QPushButton {
                min-height: 36px;
                padding: 6px 12px;
                background-color: #1F1F1F;
                color: #E0E0E0;
                border: 1px solid #333;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2A2A2A; }
            QPushButton:pressed { background-color: #111; }
        """)

    # --- Browser open + smooth scroll ---
    def _open_and_scroll(self, url, idx):
        self._open(url)
        next_idx = idx + 1
        if next_idx < len(self._mod_entries):
            self._smooth_scroll_to_widget(self._mod_entries[next_idx])

    def _open(self, url):
        try:
            if url:
                webbrowser.open(url)
        except Exception:
            try:
                os.startfile(url)  # type: ignore
            except Exception:
                pass

    def _load_thumbnail_from_page(self, page_url: str) -> QPixmap:
        if not page_url:
            return None
        try:
            resp = requests.get(page_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            meta = soup.find("meta", property="og:image")
            img_url = meta.get("content") if meta else None
            if not img_url:
                return None
            data = urlopen(img_url).read()
            pix = QPixmap()
            if pix.loadFromData(data):
                return pix
            return None
        except Exception:
            return None

    def _scaled_pix(self, pix: QPixmap, lbl: QLabel) -> QPixmap:
        if not pix or pix.isNull():
            return pix
        nat_w, nat_h = pix.width(), pix.height()
        vp = self._viewport or self
        avail_w = max(300, vp.width() - 80)
        avail_h = min(lbl.maximumHeight(), max(180, vp.height() - 180))
        box_w = min(avail_w, nat_w)
        box_h = min(avail_h, nat_h)
        return pix.scaled(box_w, box_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def resizeEvent(self, ev):
        for pix, lbl in zip(self._entry_pixmaps, self._thumb_labels):
            if pix and isinstance(lbl, QLabel):
                lbl.setPixmap(self._scaled_pix(pix, lbl))
        return super().resizeEvent(ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        for pix, lbl in zip(self._entry_pixmaps, self._thumb_labels):
            if pix and isinstance(lbl, QLabel):
                lbl.setPixmap(self._scaled_pix(pix, lbl))

    # --- Smooth scroll helper ---
    def _smooth_scroll_to_widget(self, widget):
        if not self._scroll or not widget:
            return
        bar = self._scroll.verticalScrollBar()
        target_y = widget.pos().y()
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setDuration(500)
        anim.setStartValue(bar.value())
        anim.setEndValue(target_y)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start()
        self._anim = anim  # keep reference

# -----------------------
# UpdateProgressDialog — simple progress bar to load Update
# -----------------------
class UpdateProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Checking for Updates…")
        self.setModal(True)
        self.resize(420, 120)

        layout = QVBoxLayout(self)

        label = QLabel("<b>Checking for updates, please wait…</b>")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.setStyleSheet("""
            QLabel { color: #E6E6E6; font-size: 18pt; }
            QProgressBar {
                border: 1px solid #333;
                border-radius: 4px;
                background: #111;
                height: 14px;
            }
            QProgressBar::chunk {
                background-color: #4A90E2;
                width: 20px;
            }
        """)

# -----------------------
# Settings dialog (Dark Mode + Storybook Themes only)
# -----------------------
class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Settings")
        self.resize(640, 520)

        s = load_settings()

        layout = QVBoxLayout(self)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Mode", "Storybook Themes (WIP)"])
        current_theme = s.get("theme_mode", "Dark Mode")
        if current_theme not in ("Dark Mode", "Storybook Themes"):
            current_theme = "Dark Mode"
        self.theme_combo.setCurrentText(current_theme)
        self.theme_combo.setMinimumHeight(36)
        theme_row.addWidget(self.theme_combo, 1)
        layout.addLayout(theme_row)

        sr_banner_path = find_settings_overview_banner("Secret Rings")
        if sr_banner_path:
            sr_banner_lbl = QLabel()
            sr_banner_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            sr_banner_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            sr_pix = QPixmap(str(sr_banner_path)).scaledToHeight(79, Qt.SmoothTransformation)
            sr_banner_lbl.setPixmap(sr_pix)
            layout.addWidget(sr_banner_lbl)
        else:
            sr_hdr = QHBoxLayout()
            sr_icon_path = find_ui_icon(GAME_KEYS["Secret Rings"].lower(), "Settings")
            sr_icon_lbl = QLabel()
            if sr_icon_path and Path(sr_icon_path).exists():
                sr_pix = QPixmap(str(sr_icon_path)).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                sr_icon_lbl.setPixmap(sr_pix)
            name_sr = QLabel("Secret Rings")
            name_sr.setStyleSheet("font-size: 18px; font-weight: 700;")
            name_sr.setAlignment(Qt.AlignCenter)
            sr_hdr.addWidget(sr_icon_lbl)
            sr_hdr.addWidget(name_sr, 1, Qt.AlignCenter)
            layout.addLayout(sr_hdr)

        self.sr_game = QLineEdit(s["games"]["SecretRings"]["vanilla"])
        self.sr_mods = QLineEdit(s["games"]["SecretRings"]["mods"])
        self.sr_dolphin = QLineEdit(s["games"]["SecretRings"]["dolphin_shortcut"])
        self._row(layout, "Set Game Files", self.sr_game, partial(self._browse_folder, self.sr_game, "Select Game Files (Secret Rings)"))
        self._row(layout, "Set Mods Folder", self.sr_mods, partial(self._browse_folder, self.sr_mods, "Select Mods Folder (Secret Rings)"))
        self._row(layout, "Set Dolphin Shortcut", self.sr_dolphin, partial(self._browse_file, self.sr_dolphin, "Select Dolphin exe/shortcut (Secret Rings)"))

        bk_banner_path = find_settings_overview_banner("Black Knight")
        if bk_banner_path:
            bk_banner_lbl = QLabel()
            bk_banner_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            bk_banner_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            bk_pix = QPixmap(str(bk_banner_path)).scaledToHeight(79, Qt.SmoothTransformation)
            bk_banner_lbl.setPixmap(bk_pix)
            layout.addWidget(bk_banner_lbl)
        else:
            bk_hdr = QHBoxLayout()
            bk_icon_path = find_ui_icon(GAME_KEYS["Black Knight"].lower(), "Settings")
            bk_icon_lbl = QLabel()
            if bk_icon_path and Path(bk_icon_path).exists():
                bk_pix = QPixmap(str(bk_icon_path)).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                bk_icon_lbl.setPixmap(bk_pix)
            name_bk = QLabel("Black Knight")
            name_bk.setStyleSheet("font-size: 18px; font-weight: 700;")
            name_bk.setAlignment(Qt.AlignCenter)
            bk_hdr.addWidget(bk_icon_lbl)
            bk_hdr.addWidget(name_bk, 1, Qt.AlignCenter)
            layout.addLayout(bk_hdr)

        self.bk_game = QLineEdit(s["games"]["BlackKnight"]["vanilla"])
        self.bk_mods = QLineEdit(s["games"]["BlackKnight"]["mods"])
        self.bk_dolphin = QLineEdit(s["games"]["BlackKnight"]["dolphin_shortcut"])
        self._row(layout, "Set Game Files", self.bk_game, partial(self._browse_folder, self.bk_game, "Select Game Files (Black Knight)"))
        self._row(layout, "Set Mods Folder", self.bk_mods, partial(self._browse_folder, self.bk_mods, "Select Mods Folder (Black Knight)"))
        self._row(layout, "Set Dolphin Shortcut", self.bk_dolphin, partial(self._browse_file, self.bk_dolphin, "Select Dolphin exe/shortcut (Black Knight)"))

        # Check Updates on Startup checkbox (bottom-left)
        self.check_updates_cb = QCheckBox("Check Updates on Startup")
        self.check_updates_cb.setChecked(bool(s.get("check_updates_on_startup", False)))
        cb_row = QHBoxLayout()
        cb_row.addWidget(self.check_updates_cb)
        cb_row.addStretch()
        layout.addLayout(cb_row)

        # Quit Dolphin with Storybook Game checkbox (default ON)
        self.quit_dolphin_cb = QCheckBox("Quit Dolphin with Storybook Game")
        self.quit_dolphin_cb.setChecked(bool(s.get("quit_dolphin_with_game", True)))
        quit_row = QHBoxLayout()
        quit_row.addWidget(self.quit_dolphin_cb)
        quit_row.addStretch()
        layout.addLayout(quit_row)

        # How to Setup button (bottom-left)
        self.btn_help_setup = SBButton("How to Setup?")
        self.btn_help_setup.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_help_setup.setFixedHeight(33)
        self.btn_help_setup.clicked.connect(self._on_help_setup_clicked)

        help_row = QHBoxLayout()
        help_row.addWidget(self.btn_help_setup)
        layout.addSpacing(2)
        layout.addLayout(help_row)

        # NEW: Bottom row with Dolphin Texture Packs button and Save/Cancel
        bottom_row = QHBoxLayout()
        
        # Dolphin Texture Packs button (left side, with icon)
        self.btn_dolphin_textures = SBButton("  Dolphin Texture Packs")
        dolphin_icon_path = UI_DIR / "Dolphin Icon.png"
        if dolphin_icon_path.exists():
            self.btn_dolphin_textures.setIcon(QIcon(str(dolphin_icon_path)))
            self.btn_dolphin_textures.setIconSize(QSize(20, 20))
        self.btn_dolphin_textures.setMinimumHeight(38)
        self.btn_dolphin_textures.setMinimumWidth(94)
        hook_flash(self.btn_dolphin_textures)
        self.btn_dolphin_textures.clicked.connect(self._on_dolphin_textures_clicked)
        bottom_row.addWidget(self.btn_dolphin_textures)
        
        bottom_row.addStretch(1)
        
        # Save/Cancel buttons (right side)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        beef_up_buttons(btns)
        btns.accepted.connect(self.do_save)
        btns.rejected.connect(self.reject)
        bottom_row.addWidget(btns)
        
        layout.addLayout(bottom_row)

        self.setStyleSheet("""
            QLineEdit, QTextEdit, QComboBox {
                background-color: #1A1A1A; color: #E6E6E6; border: 1px solid #333;
            }
            QPushButton:pressed { background-color: rgba(255,255,255,0.2); }
          """)

    def _row(self, parent_layout, label, edit: QLineEdit, browse_cb):
        row = QHBoxLayout()
        lab = QLabel(label)
        lab.setStyleSheet("font-size: 14px;")
        row.addWidget(lab)
        edit.setMinimumWidth(380)
        edit.setMinimumHeight(34)
        row.addWidget(edit, 1)
        btn = QPushButton("Browse…")
        btn.setMinimumHeight(42)
        hook_flash(btn)
        btn.clicked.connect(browse_cb)
        row.addWidget(btn)
        parent_layout.addLayout(row)

    def _browse_folder(self, edit: QLineEdit, title: str):
        path = QFileDialog.getExistingDirectory(self, title, edit.text() or str(Path.home()))
        if path:
            edit.setText(path)

    def _browse_file(self, edit: QLineEdit, title: str):
        path, _ = QFileDialog.getOpenFileName(
            self, title, edit.text() or str(Path.home()),
            "Executable/Shortcut (*.exe *.lnk);;All Files (*)"
        )
        if path:
            edit.setText(path)

    def do_save(self):
        s = load_settings()
        s["games"]["SecretRings"]["vanilla"] = self.sr_game.text()
        s["games"]["SecretRings"]["mods"] = self.sr_mods.text()
        s["games"]["SecretRings"]["dolphin_shortcut"] = self.sr_dolphin.text()
        s["games"]["BlackKnight"]["vanilla"] = self.bk_game.text()
        s["games"]["BlackKnight"]["mods"] = self.bk_mods.text()
        s["games"]["BlackKnight"]["dolphin_shortcut"] = self.bk_dolphin.text()

        mode = self.theme_combo.currentText()
        s["theme_mode"] = mode if mode in ("Dark Mode", "Storybook Themes") else "Dark Mode"

        # Save the "Check Updates on Startup" preference
        try:
            s["check_updates_on_startup"] = bool(self.check_updates_cb.isChecked())
        except Exception:
            s["check_updates_on_startup"] = False

        # Save the "Quit Dolphin with Storybook Game" preference (default True)
        try:
            s["quit_dolphin_with_game"] = bool(self.quit_dolphin_cb.isChecked())
        except Exception:
            s["quit_dolphin_with_game"] = True

        save_settings(s)
        self.accept()

    def _on_help_setup_clicked(self):
        parent = self.parentWidget()
        if parent and hasattr(parent, "show_help_setup"):
            parent.show_help_setup()

    def _on_dolphin_textures_clicked(self):
        # Close settings dialog and open texture packs dialog
        self.accept()  # Close settings dialog

        # Open the Dolphin Texture Packs dialog
        dlg = DolphinTexturePackDialog(self.parent)
        try:
            self.parent._handify_buttons(dlg)
        except Exception:
            pass
        
        result = dlg.exec_()

        # If user clicked "Back", reopen settings dialog
        if hasattr(dlg, '_back_clicked') and dlg._back_clicked:
            # Reopen settings dialog
            settings_dlg = SettingsDialog(self.parent)
            try:
                self.parent._handify_buttons(settings_dlg)
            except Exception:
                pass
            settings_dlg.exec_()

# -----------------------
# Help Setup Dialog Class, for the help button
# -----------------------
class HelpSetupDialog(QDialog):
    def __init__(self, parent=None, slides=None):
        super().__init__(parent)
        self.setWindowTitle("How to Setup")
        self.setMinimumSize(800, 550)

        self.slides = slides or []
        self.current_index = 0

        # --- Widgets ---
        self.text_label = QLabel("", self)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.text_label.setStyleSheet("font-size: 16px; padding: 8px;")

        self.image_label = QLabel("", self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #1E1E1E; padding: 6px;")

        # Apply opacity effect to the image label
        self.opacity_effect = QGraphicsOpacityEffect(self.image_label)
        self.image_label.setGraphicsEffect(self.opacity_effect)
        
        # Create animation object
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(140)  # milliseconds (how fast it goes)

        # Previous < Arrow Button + Size
        self.btn_prev = SBButton("← Previous")
        self.btn_prev.setFixedHeight(35)
        # Next > Arrow Button + Size
        self.btn_next = SBButton("Next →")
        self.btn_next.setFixedHeight(35)
        # Clicked Connect Wire
        self.btn_prev.clicked.connect(self.prev_slide)
        self.btn_next.clicked.connect(self.next_slide)

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.addWidget(self.text_label)
        layout.addWidget(self.image_label, 1)

        nav = QHBoxLayout()
        nav.addStretch()
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        layout.addLayout(nav)

        self.update_slide()

    def update_slide(self):
        if not self.slides:
            self.text_label.setText("No setup instructions available.")
            self.image_label.clear()
            return

        text, img_path = self.slides[self.current_index]
        self.text_label.setText(text)

        # Stop any ongoing fade and disconnect to avoid stacking
        try:
            self.fade_anim.stop()
            self.fade_anim.finished.disconnect()
        except Exception:
            pass

        def _swap():
            # Disconnect fade to avoid recursion
            try:
                self.fade_anim.finished.disconnect()
            except Exception:
                pass

            # --- GIF branch ---
            if img_path.lower().endswith(".gif"):
                # Clean up any previous movie
                if hasattr(self, "movie") and self.movie:
                    try:
                        self.movie.frameChanged.disconnect()
                    except Exception:
                        pass
                    self.movie.stop()
                    self.movie = None

                self.movie = QMovie(img_path)
                if self.movie.isValid():
                    def _scale_frame(_=None):
                        frame = self.movie.currentPixmap()
                        if not frame.isNull():
                            scaled = frame.scaled(
                                self.image_label.size(),
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation
                            )
                            self.image_label.setPixmap(scaled)

                    self.movie.frameChanged.connect(_scale_frame)
                    self.movie.start()
                    _scale_frame()
                else:
                    self.image_label.setText("[GIF not found]")

            # --- Static image branch ---
            else:
                # Stop any leftover movie so it doesn’t overwrite
                if hasattr(self, "movie") and self.movie:
                    try:
                        self.movie.frameChanged.disconnect()
                    except Exception:
                        pass
                    self.movie.stop()
                    self.movie = None

                pixmap = QPixmap(img_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        self.image_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.image_label.setPixmap(scaled)
                else:
                    self.image_label.setText("[Image not found]")

            # Fade back in
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.start()

        # Fade out, then swap
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(_swap)
        self.fade_anim.start()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-scale current content without restarting fade
        if hasattr(self, "movie") and self.movie and self.movie.state() == QMovie.Running:
            frame = self.movie.currentPixmap()
            if not frame.isNull():
                scaled = frame.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled)
        else:
            pix = self.image_label.pixmap()
            if pix and not pix.isNull():
                scaled = pix.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled)

    def prev_slide(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_slide()

    def next_slide(self):
        if self.current_index < len(self.slides) - 1:
            self.current_index += 1
            self.update_slide()

    def _set_slide_content(self, text, img_path):
        # Disconnect to avoid stacking signals
        try:
            self.fade_anim.finished.disconnect()
        except TypeError:
            pass

        self.text_label.setText(text)

        if img_path.lower().endswith(".gif"):
            self.movie = QMovie(img_path)
            if self.movie.isValid():
                self.movie.setScaledSize(self.image_label.size())
                self.image_label.setMovie(self.movie)
                self.movie.start()
            else:
                self.image_label.setText("[GIF not found]")
        else:
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled)
            else:
                self.image_label.setText("[Image not found]")

        # Fade back in
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

# -----------------------
# ModEditDialog (centered Configure button)
# -----------------------
class ModEditDialog(QDialog):
    def __init__(self, parent, mod_folder: Path):
        super().__init__(parent)
        self.setWindowTitle("Edit Mod")
        self.resize(540, 520)
        self.mod_folder = mod_folder

        cp, ini, _ = ensure_mod_ini(mod_folder)
        outer = QVBoxLayout(self)

        form_wrap = QWidget()
        form = QFormLayout(form_wrap)
        g = lambda k, d="": cp.get(INI_SECTION, k, fallback=d)

        self.ed_name = QLineEdit(g("Name", mod_folder.name))
        self.ed_ver = QLineEdit(g("Version", "1.0.0"))
        self.ed_author = QLineEdit(g("Author", ""))
        self.ed_authorurl = QLineEdit(g("AuthorURL", ""))
        self.ed_update = QLineEdit(g("UpdateURL", ""))
        self.ed_date = QLineEdit(g("Date", ""))
        self.ed_id = QLineEdit(g("ID", ""))
        self.ed_include = QLineEdit(g("IncludeDirectories", ""))
        self.ed_deps = QLineEdit(g("Dependencies", ""))

        for w in (self.ed_name, self.ed_ver, self.ed_author, self.ed_authorurl,
                  self.ed_update, self.ed_date,
                  self.ed_id, self.ed_include, self.ed_deps):
            w.setMinimumHeight(34)
            w.setStyleSheet("font-size: 14px;")

        form.addRow("Name:", self.ed_name)
        form.addRow("Version:", self.ed_ver)
        form.addRow("Author:", self.ed_author)
        form.addRow("Author URL:", self.ed_authorurl)
        form.addRow("Update URL:", self.ed_update)
        form.addRow("Date (YYYY-MM-DD):", self.ed_date)
        form.addRow("ID:", self.ed_id)
        form.addRow("IncludeDirectories:", self.ed_include)
        form.addRow("Dependencies:", self.ed_deps)

        outer.addWidget(form_wrap)

        self.btn_schema = QPushButton("Set Configure Mod…")
        self.btn_schema.setMinimumHeight(56)
        self.btn_schema.setMinimumWidth(220)
        self.btn_schema.setStyleSheet("font-size: 16px;")
        hook_flash(self.btn_schema)
        self.btn_schema.clicked.connect(self.open_schema_builder)

        schema_row = QHBoxLayout()
        schema_row.addStretch(1)
        schema_row.addWidget(self.btn_schema)
        schema_row.addStretch(1)
        outer.addLayout(schema_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        beef_up_buttons(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

        self.setStyleSheet("""
            QLineEdit, QTextEdit, QComboBox, QListWidget {
                background-color: #1A1A1A; color: #E6E6E6; border: 1px solid #333;
            }
            QPushButton { min-height: 38px; padding: 6px 12px; }
            QToolButton { padding: 6px 12px; }
            QPushButton:pressed, QToolButton:pressed { padding: 6px 12px; margin: 0px; background-color: rgba(255,255,255,0.12); }
        """)

    def open_schema_builder(self):
        dlg = ConfigureModSchemaDialog(self, self.mod_folder)
        dlg.exec_()

    def values(self):
        return {
            "Name": self.ed_name.text().strip(),
            "Version": self.ed_ver.text().strip(),
            "Author": self.ed_author.text().strip(),
            "AuthorURL": self.ed_authorurl.text().strip(),
            "UpdateURL": self.ed_update.text().strip(),
            "Date": self.ed_date.text().strip(),
            "ID": self.ed_id.text().strip(),
            "IncludeDirectories": self.ed_include.text().strip(),
            "Dependencies": self.ed_deps.text().strip()
        }

    def accept(self):
        if not self.ed_name.text().strip():
            QMessageBox.warning(self, "Missing Name", "Name cannot be empty.")
            return
        d = self.ed_date.text().strip()
        if d:
            try:
                yy, mm, dd = d.split("-")
                _ = date(int(yy), int(mm), int(dd))
            except Exception:
                QMessageBox.warning(self, "Invalid date", "Date must be in YYYY-MM-DD format.")
                return
        super().accept()

# ---------------------------------------
# Re-usable "are you sure?" pop-up window
# ---------------------------------------
class ConfirmDeleteDialog(QDialog):
    def __init__(self, parent, mod_name: str):
        super().__init__(parent)
        self.setWindowTitle("Confirm Delete")
        self.resize(380, 150)

        layout = QVBoxLayout(self)

        # Centered, larger text with no background block
        lbl = QLabel(f"Are you sure you want to delete mod '{mod_name}'?")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #E6E6E6; font-size: 18px; font-weight: 600;")
        layout.addWidget(lbl, 1, Qt.AlignCenter)

        # Button row
        row = QHBoxLayout()
        btn_no = QPushButton("No")
        btn_yes = QPushButton("Yes")

        # Slightly smaller buttons (than before)
        for b in (btn_no, btn_yes):
            b.setMinimumHeight(32)
            b.setMinimumWidth(85)
            hook_flash(b)

        # Position: No (left), Yes (right)
        row.addWidget(btn_no, 0, Qt.AlignLeft)
        row.addStretch(1)
        row.addWidget(btn_yes, 0, Qt.AlignRight)
        layout.addLayout(row)

        btn_no.clicked.connect(self.reject)
        btn_yes.clicked.connect(self.accept)

        # Smooth grey background, no block behind text
        self.setStyleSheet("""
            QLabel {
                color: #E6E6E6;
                font-size: 18px;
                font-weight: 600;
            }
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.25);  /* brighter hover */
            }
            QPushButton:pressed {
                background-color: rgba(255,255,255,0.2);
            }
        """)
        handify_buttons_in(self)

# ---------------------------------------
# Conflicted mods (with another) warning popup window.
# ---------------------------------------
class ConflictWarningDialog(QDialog):
    def __init__(self, parent, conflicts: dict):
        super().__init__(parent)
        self.setWindowTitle("Mod File Conflicts Detected")
        self.setModal(True)
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        
        # Play Windows error sound
        QApplication.beep()

        # Headline
        headline = QLabel(
            "<span style='font-size:16pt; font-weight:600; color:#FF6B6B;'>"
            "⚠ Warning: File Conflicts Detected</span>"
        )
        headline.setAlignment(Qt.AlignCenter)
        layout.addWidget(headline)
        
        # Explanation
        info = QLabel(
            "Multiple enabled mods are trying to modify the same file(s).\n"
            "If you continue, only the FIRST mod listed will be applied for each conflict."
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("font-size: 12pt; padding: 10px;")
        layout.addWidget(info)
        
        # Scrollable conflict list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        conflict_container = QWidget()
        conflict_layout = QVBoxLayout(conflict_container)
        
        for filename, mod_list in conflicts.items():
            # File header
            file_label = QLabel(f"<b>File: {filename}</b>")
            file_label.setStyleSheet("color: #FFD700; font-size: 13pt; padding-top: 8px;")
            conflict_layout.addWidget(file_label)
            
            # Mod list
            for i, (mod_name, choice) in enumerate(mod_list):
                prefix = "✓ WILL APPLY" if i == 0 else "✗ WILL SKIP"
                color = "#90EE90" if i == 0 else "#FF6B6B"
                
                mod_label = QLabel(f"  {prefix}: <b>{mod_name}</b> ({choice})")
                mod_label.setStyleSheet(f"color: {color}; font-size: 11pt; padding-left: 20px;")
                conflict_layout.addWidget(mod_label)
            
            # Separator
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            conflict_layout.addWidget(line)
        
        conflict_layout.addStretch()
        scroll.setWidget(conflict_container)
        layout.addWidget(scroll)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)
        
        self.continue_btn = QPushButton("Continue Anyway")
        self.continue_btn.setMinimumSize(160, 40)
        self.continue_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF8C00;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #FFA500;
            }
        """)
        self.continue_btn.setCursor(Qt.PointingHandCursor)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumSize(120, 40)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        
        btn_layout.addWidget(self.continue_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        
        self.clicked_button = None
        self.continue_btn.clicked.connect(lambda: self._on_clicked(self.continue_btn))
        self.cancel_btn.clicked.connect(lambda: self._on_clicked(self.cancel_btn))
        
        self.setStyleSheet("""
            QDialog { background-color: #1A1A1A; }
            QLabel { color: #E6E6E6; }
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.15);
            }
            QScrollArea {
                background-color: #121212;
                border: 1px solid #333;
            }
        """)
    
    def _on_clicked(self, button):
        self.clicked_button = button
        self.accept()

# ---------------------------------------
# UnsavedChangesDialog — warns about unsaved changes through WINDOW
# ---------------------------------------
class UnsavedChangesDialog(QDialog):
    def __init__(self, unsaved_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unsaved Changes")
        self.setModal(True)

        # Base size, can grow
        self.resize(400, 240)
        self.setMaximumSize(600, 400)

        layout = QVBoxLayout(self)

        # Big, bold, centered headline
        headline = QLabel("<span style='font-size:16pt; font-weight:600;'>You have Unsaved Changes in this window:</span>")
        headline.setAlignment(Qt.AlignCenter)
        layout.addWidget(headline)

        # Scroll area for unsaved list
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)

        if unsaved_list:
            for name in unsaved_list:
                lbl = QLabel(f"<b>• {name}</b>")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("font-size: 18pt;")
                list_layout.addWidget(lbl)

        scroll.setWidget(list_container)
        layout.addWidget(scroll)

        # Buttons centered
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)

        self.save_quit_btn = QPushButton("Save and Quit")
        self.quit_btn = QPushButton("Quit")
        self.close_btn = QPushButton("Cancel")

        # Make buttons bigger
        self.save_quit_btn.setMinimumSize(140, 40)
        self.quit_btn.setMinimumSize(100, 36)
        self.close_btn.setMinimumSize(120, 36)

        # Set cursor to pointing hand
        self.save_quit_btn.setCursor(Qt.PointingHandCursor)
        self.quit_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setCursor(Qt.PointingHandCursor)

        btn_layout.addWidget(self.save_quit_btn)
        btn_layout.addWidget(self.quit_btn)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        # Connect buttons
        self.clicked_button = None
        self.save_quit_btn.clicked.connect(lambda: self._on_clicked(self.save_quit_btn))
        self.quit_btn.clicked.connect(lambda: self._on_clicked(self.quit_btn))
        self.close_btn.clicked.connect(lambda: self._on_clicked(self.close_btn))

    def _on_clicked(self, button):
        self.clicked_button = button
        self.accept()   # ensures the dialog closes properly

# ---------------------------------------
# TexturePackModeRequiredDialog – warns user to configure texture pack mode
# ---------------------------------------
class TexturePackModeRequiredDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Texture Pack Mode Required")
        self.setModal(True)
        self.resize(420, 180)

        # Play Windows error sound
        QApplication.beep()

        layout = QVBoxLayout(self)

        # Headline
        headline = QLabel(
            "<span style='font-size:14pt; font-weight:600;'>"
            "Please Configure Texture Pack Mode</span>"
        )
        headline.setAlignment(Qt.AlignCenter)
        headline.setStyleSheet("background: transparent;")
        layout.addWidget(headline)

        # Message
        message = QLabel(
            "You must enable one of the options (Copy or Move)\n"
            "in the Dolphin Texture Pack Config window\n"
            "before applying this texture pack mod."
        )
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("font-size: 12pt; padding: 12px; background: transparent;")
        message.setWordWrap(True)
        layout.addWidget(message)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)

        self.settings_btn = QPushButton("Go to Settings")
        self.cancel_btn = QPushButton("Cancel")

        self.settings_btn.setMinimumSize(140, 40)
        self.cancel_btn.setMinimumSize(100, 40)

        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)

        btn_layout.addWidget(self.settings_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.clicked_button = None
        self.settings_btn.clicked.connect(lambda: self._on_clicked(self.settings_btn))
        self.cancel_btn.clicked.connect(lambda: self._on_clicked(self.cancel_btn))

        self.setStyleSheet("""
            QDialog { background-color: #1A1A1A; }
            QLabel { color: #E6E6E6; }
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.15);
            }
            QPushButton:pressed {
                background-color: rgba(255,255,255,0.25);
            }
        """)

    def _on_clicked(self, button):
        self.clicked_button = button
        self.accept()

# -----------------------
# DolphinTexturePackConfigDialog - CONTEXT MENU Configure copy/move mode for texture packs
# -----------------------
class DolphinTexturePackConfigDialog(QDialog):
    def __init__(self, parent, mod_folder: Path):
        super().__init__(parent)
        self.setWindowTitle("Dolphin Texture Pack Config")
        self.resize(480, 280)
        self.mod_folder = mod_folder
        self.parent_ui = parent

        # Read current setting from mod.ini
        cp, ini, _ = ensure_mod_ini(mod_folder)
        current_mode = cp.get(INI_SECTION, "TexturePackMode", fallback="copy")

        layout = QVBoxLayout(self)

        # Info label
        info = QLabel(
            "<b>Configure Texture Pack Mode</b><br><br>"
            "Choose how this texture pack's PNG files are handled:"
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 14px;")
        layout.addWidget(info)

        # Radio buttons for copy/move
        self.radio_copy = QCheckBox("Copy PNGs to Dolphin Custom Texture Path")
        self.radio_copy.setStyleSheet("font-size: 13px; padding: 8px;")
        self.radio_copy.setToolTip("Copies texture files (keeps originals in mod folder)")
        
        self.radio_move = QCheckBox("Move PNGs to Dolphin Custom Texture Path")
        self.radio_move.setStyleSheet("font-size: 13px; padding: 8px;")
        self.radio_move.setToolTip("Moves texture files (saves disk space, removes from mod folder)")

        # Make them mutually exclusive
        self.radio_copy.toggled.connect(lambda checked: self.radio_move.setChecked(not checked) if checked else None)
        self.radio_move.toggled.connect(lambda checked: self.radio_copy.setChecked(not checked) if checked else None)

        # Set initial state - both unchecked if no mode set
        self.initial_mode = current_mode
        if current_mode == "move":
            self.radio_move.setChecked(True)
            self.radio_copy.setChecked(False)
        elif current_mode == "copy":
            self.radio_copy.setChecked(True)
            self.radio_move.setChecked(False)
        else:
            # Both unchecked - user must choose
            self.radio_copy.setChecked(False)
            self.radio_move.setChecked(False)

        layout.addWidget(self.radio_copy)
        layout.addWidget(self.radio_move)

        # Warning label
        warning = QLabel(
            "<i>Note: If you choose 'Move', the PNG files will be removed from the mod folder "
            "and placed in your Dolphin Custom Texture Path. If you switch back to 'Copy', "
            "the textures will be copied back to the mod folder.</i>"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #FFA500; font-size: 12px; padding: 8px;")
        layout.addWidget(warning)

        layout.addStretch(1)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        beef_up_buttons(btns)
        btns.accepted.connect(self.on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.setStyleSheet("""
            QLineEdit, QTextEdit, QComboBox {
                background-color: #1A1A1A; color: #E6E6E6; border: 1px solid #333;
            }
            QCheckBox {
                color: #E6E6E6;
            }
            QPushButton:pressed { background-color: rgba(255,255,255,0.2); }
        """)
        handify_buttons_in(self)

    def on_save(self):
        try:
            # Validate that user selected an option
            if not self.radio_copy.isChecked() and not self.radio_move.isChecked():
                QMessageBox.warning(
                    self,
                    "Selection Required",
                    "Please select either 'Copy' or 'Move' mode before saving."
                )
                return

            cp, ini, _ = ensure_mod_ini(self.mod_folder)

            new_mode = "move" if self.radio_move.isChecked() else "copy"

            # If switching from move to copy, copy textures back to mod folder
            if self.initial_mode == "move" and new_mode == "copy":
                self._copy_textures_back_to_mod()

            # Save the new mode
            cp.set(INI_SECTION, "TexturePackMode", new_mode)

            with ini.open("w", encoding="utf-8") as f:
                cp.write(f)

            QMessageBox.information(
                self, 
                "Saved", 
                "Texture pack mode saved successfully!\n\n"
                "This setting will be applied the next time you Save/Apply mods."
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save texture pack config:\n{e}")

    def _copy_textures_back_to_mod(self):
        """Copy moved textures back to the mod folder from Dolphin texture path"""
        try:
            # Get dolphin texture path from settings
            game_key = GAME_KEYS[self.parent_ui.current_game]
            settings = load_settings()
            dolphin_texture_path_str = settings.get("games", {}).get(game_key, {}).get("dolphin_texture_path", "")
            
            if not dolphin_texture_path_str:
                self.parent_ui.log(f"[texture_restore] No Dolphin texture path configured")
                return
            
            dolphin_texture_path = Path(dolphin_texture_path_str)
            if not dolphin_texture_path.exists():
                self.parent_ui.log(f"[texture_restore] Dolphin texture path does not exist")
                return
            
            # Read applied files from mod_data.json
            data_file = self.mod_folder / "mod_data.json"
            if not data_file.exists():
                self.parent_ui.log(f"[texture_restore] No mod_data.json found")
                return
            
            try:
                data = json.loads(data_file.read_text(encoding="utf-8"))
                applied = data.get("APPLIED FILES", [])
                
                if not applied:
                    self.parent_ui.log(f"[texture_restore] No applied files to restore")
                    return
                
                restored_count = 0
                for rel in applied:
                    texture_file = dolphin_texture_path / rel
                    if texture_file.exists() and texture_file.suffix.lower() == ".png":
                        # Copy back to mod folder
                        dest = self.mod_folder / texture_file.name
                        try:
                            shutil.copy2(texture_file, dest)
                            restored_count += 1
                            self.parent_ui.log(f"[texture_restore] Copied back {texture_file.name}")
                        except Exception as e:
                            self.parent_ui.log(f"[texture_restore] Failed to copy {texture_file.name}: {e}")
                
                if restored_count > 0:
                    self.parent_ui.log(f"[texture_restore] Copied {restored_count} texture(s) back to mod folder")
                    
            except Exception as e:
                self.parent_ui.log(f"[texture_restore] Error reading mod_data.json: {e}")
                
        except Exception as e:
            self.parent_ui.log(f"[texture_restore] Error: {e}")

# -----------------------
# DolphinTexturePackDialog - Configure Dolphin Custom Texture Path
# -----------------------
class DolphinTexturePackDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_ui = parent
        self._back_clicked = False  # For going back to the settings window
        self.setWindowTitle("Dolphin Texture Packs")
        self.resize(620, 460)  # Made bigger for 2 game sections

        s = load_settings()

        layout = QVBoxLayout(self)

        # === SECRET RINGS SECTION ===
        sr_banner_path = UI_DIR / "Secret Rings - Setting Texture Pack.png"
        if not sr_banner_path.exists():
            sr_banner_path = find_settings_overview_banner("Secret Rings")
        
        if sr_banner_path and sr_banner_path.exists():
            sr_banner_lbl = QLabel()
            sr_banner_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            sr_banner_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            sr_banner_pix = QPixmap(str(sr_banner_path)).scaledToHeight(79, Qt.SmoothTransformation)
            sr_banner_lbl.setPixmap(sr_banner_pix)
            layout.addWidget(sr_banner_lbl)
        else:
            # Fallback: game name header
            sr_hdr = QHBoxLayout()
            sr_icon_path = find_ui_icon("secretrings", "Settings")
            sr_icon_lbl = QLabel()
            if sr_icon_path and Path(sr_icon_path).exists():
                sr_pix = QPixmap(str(sr_icon_path)).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                sr_icon_lbl.setPixmap(sr_pix)
            sr_name_lbl = QLabel("Secret Rings")
            sr_name_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
            sr_name_lbl.setAlignment(Qt.AlignCenter)
            sr_hdr.addWidget(sr_icon_lbl)
            sr_hdr.addWidget(sr_name_lbl, 1, Qt.AlignCenter)
            layout.addLayout(sr_hdr)

        # Text field for Secret Rings
        current_sr_path = s.get("games", {}).get("SecretRings", {}).get("dolphin_texture_path", "")
        self.sr_texture_path_edit = QLineEdit(current_sr_path)
        self.sr_texture_path_edit.setMinimumHeight(34)
        self._row(layout, "Set Dolphin Custom Texture Path", self.sr_texture_path_edit, 
                  lambda: self._browse_folder(self.sr_texture_path_edit, "Secret Rings"))

        # === BLACK KNIGHT SECTION ===
        bk_banner_path = UI_DIR / "Black Knight - Setting Texture Pack.png"
        if not bk_banner_path.exists():
            bk_banner_path = find_settings_overview_banner("Black Knight")
        
        if bk_banner_path and bk_banner_path.exists():
            bk_banner_lbl = QLabel()
            bk_banner_lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            bk_banner_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            bk_banner_pix = QPixmap(str(bk_banner_path)).scaledToHeight(79, Qt.SmoothTransformation)
            bk_banner_lbl.setPixmap(bk_banner_pix)
            layout.addSpacing(50)
            layout.addWidget(bk_banner_lbl)
        else:
            # Fallback: game name header
            bk_hdr = QHBoxLayout()
            bk_icon_path = find_ui_icon("blackknight", "Settings")
            bk_icon_lbl = QLabel()
            if bk_icon_path and Path(bk_icon_path).exists():
                bk_pix = QPixmap(str(bk_icon_path)).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                bk_icon_lbl.setPixmap(bk_pix)
            bk_name_lbl = QLabel("Black Knight")
            bk_name_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
            bk_name_lbl.setAlignment(Qt.AlignCenter)
            bk_hdr.addWidget(bk_icon_lbl)
            bk_hdr.addWidget(bk_name_lbl, 1, Qt.AlignCenter)
            layout.addLayout(bk_hdr)

        # Text field for Black Knight
        current_bk_path = s.get("games", {}).get("BlackKnight", {}).get("dolphin_texture_path", "")
        self.bk_texture_path_edit = QLineEdit(current_bk_path)
        self.bk_texture_path_edit.setMinimumHeight(34)
        self._row(layout, "Set Dolphin Custom Texture Path", self.bk_texture_path_edit, 
                  lambda: self._browse_folder(self.bk_texture_path_edit, "Black Knight"))

        layout.addStretch(1)

        # How to Setup Custom Textures button (bottom-left, stretches horizontally)
        self.btn_help_setup = SBButton("How to Setup Custom Textures?")
        self.btn_help_setup.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_help_setup.setMinimumHeight(33)
        self.btn_help_setup.clicked.connect(self._on_help_setup_clicked)

        help_row = QHBoxLayout()
        help_row.addWidget(self.btn_help_setup, 1)  # stretch=1 makes it expand horizontally
        layout.addLayout(help_row)

        # Save/Back buttons
        btns = QDialogButtonBox()
        save_btn = btns.addButton("Save", QDialogButtonBox.AcceptRole)
        back_btn = btns.addButton("Back", QDialogButtonBox.RejectRole)
        beef_up_buttons(btns)
        btns.accepted.connect(self.do_save)
        btns.rejected.connect(self.on_back)
        layout.addWidget(btns)

        self.setStyleSheet("""
            QLineEdit, QTextEdit, QComboBox {
                background-color: #1A1A1A; color: #E6E6E6; border: 1px solid #333;
            }
            QPushButton:pressed { background-color: rgba(255,255,255,0.2); }
        """)

    def _row(self, parent_layout, label, edit: QLineEdit, browse_cb):
        row = QHBoxLayout()
        lab = QLabel(label)
        lab.setStyleSheet("font-size: 14px;")
        row.addWidget(lab)
        edit.setMinimumWidth(280)
        edit.setMinimumHeight(34)
        row.addWidget(edit, 1)
        btn = QPushButton("Browse…")
        btn.setMinimumHeight(42)
        hook_flash(btn)
        btn.clicked.connect(browse_cb)
        row.addWidget(btn)
        parent_layout.addLayout(row)

    def _browse_folder(self, edit_widget, game_name):
        path = QFileDialog.getExistingDirectory(
            self, f"Select Dolphin Custom Texture Folder ({game_name})",
            edit_widget.text() or str(Path.home())
        )
        if path:
            edit_widget.setText(path)

    def do_save(self):
        s = load_settings()
        s["games"].setdefault("SecretRings", {})
        s["games"]["SecretRings"]["dolphin_texture_path"] = self.sr_texture_path_edit.text()
        
        s["games"].setdefault("BlackKnight", {})
        s["games"]["BlackKnight"]["dolphin_texture_path"] = self.bk_texture_path_edit.text()
        
        save_settings(s)
        QMessageBox.information(self, "Saved", "Dolphin Custom Texture Paths saved successfully!")
        self.accept()

    def on_back(self):
        """Handle Back button click - mark that we're going back to settings."""
        self._back_clicked = True
        self.reject()

    def _on_help_setup_clicked(self):
        # Dolphin texture setup help slides
        slides = [
            (
                "Step 1: Find your Game ID from your Modified Game by Right-Click > Properties, than go to the Info tab.",
                resource_path("UI/help/CustomTextures/DolphinStep1.gif")
            ),
            (
                "Step 2: Go to your 'Load' > Textures and Create a folder with the name of your Game ID.",
                resource_path("UI/help/CustomTextures/DolphinStep2.gif")
            ),
            (
                "Step 3: Set your Load > Textures > [Game ID] Folder paths to the Settings Window (Do the same for Both)",
                resource_path("UI/help/CustomTextures/DolphinStep3.gif")
            ),
            (
                "Step 4: Enable the 'Load Custom Textures Option' In the Dolphin Graphics Settings (Advanced Tab)",
                resource_path("UI/help/CustomTextures/DolphinStep4.gif")
            ),
            (
                "End: Now you have Custom Textures!",
                resource_path("UI/help/CustomTextures/Custom Textures Compare.gif")
            ),
        ]

        dlg = HelpSetupDialog(self, slides=slides)
        dlg.exec_()

# -----------------------
# Storybook main UI
# -----------------------
class StorybookUI(QWidget):
    def __init__(self, settings, first_run):
        super().__init__()
        self.settings = settings
        self._first_run = first_run
        self.current_game = self.settings.get("last_game", "Secret Rings")

        self.temp_build = None
        self.last_selected_mod_path = None

        self.setWindowTitle(f"Storybook Mod Manager")
        
        # Set window icon for taskbar
        icon_file = resource_path("Storybook_Icon.ico")
        self.setWindowIcon(QIcon(icon_file))
        
        # Slightly smaller default size; do not auto-resize when toggling logs
        self.resize(900, 800)
        self.setMinimumSize(780, 600)

        main = QVBoxLayout(self)

        # --- Header ---
        header = QHBoxLayout()
        header_left = QVBoxLayout()
        self.lbl_title = QLabel("<b>Storybook Mod Manager</b>")
        header_left.addWidget(self.lbl_title)

        self.logs_enabled = True
        # SBButton → pointing-hand cursor for the logs toggle
        self.btn_toggle_logs = SBButton("Logs: Enabled")
        self.btn_toggle_logs.setMinimumHeight(34)
        self.btn_toggle_logs.setMaximumWidth(140)
        self.btn_toggle_logs.setStyleSheet("font-size: 12px;")
        hook_flash(self.btn_toggle_logs)
        self.btn_toggle_logs.clicked.connect(self.toggle_logs)
        header_left.addWidget(self.btn_toggle_logs, 0, Qt.AlignLeft)

        header.addLayout(header_left)
        header.addStretch(1)

        right_header = QHBoxLayout()
        # --- Mod List button (small, next to version label) ---
        self.btn_mod_list = SBButton("Mod List")
        self.btn_mod_list.setMinimumHeight(31)
        self.btn_mod_list.setMinimumWidth(73)
        self.btn_mod_list.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 4px 8px;
                border: 1px solid #444;
                border-radius: 4px;
                background-color: #1F1F1F;
                color: #E0E0E0;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.12);
            }
            QPushButton:pressed {
                background-color: rgba(255,255,255,0.25);
            }
        """)
        hook_flash(self.btn_mod_list)
        self.btn_mod_list.clicked.connect(self.show_mod_list_menu)
        right_header.addWidget(self.btn_mod_list)

        self.lbl_author = QLabel(f"v{APP_VERSION} by {APP_AUTHOR}")
        right_header.addWidget(self.lbl_author)

        self.btn_update_check = QToolButton()
        self.btn_update_check.setObjectName("updateButton")
        self.btn_update_check.setToolTip("Check all mods (and manager) for updates")
        up_icon_path = find_ui_icon("Update", "Icon") or (APP_DIR / "Update - Icon.png")
        if up_icon_path and Path(up_icon_path).exists():
            self.btn_update_check.setIcon(QIcon(str(up_icon_path)))
        else:
            self.btn_update_check.setText("⟳")
        self.btn_update_check.setIconSize(QSize(22, 22))
        self.btn_update_check.setMinimumSize(40, 40)
        self.btn_update_check.setCursor(Qt.PointingHandCursor)
        hook_flash(self.btn_update_check)
        self.btn_update_check.clicked.connect(self.on_check_all_updates)
        right_header.addWidget(self.btn_update_check)

        header.addLayout(right_header)
        main.addLayout(header)

        # --- Mods tree ---
        self.tree = QTreeWidget()
        try:
            self.tree.header().setStyleSheet("QHeaderView::section { background-color: transparent; color: #E0E0E0; }")
        except Exception:
            pass
        self.tree.setHeaderLabels(["Name", "Version", "Author"])
        self.tree.setAlternatingRowColors(False)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_context_menu)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.currentItemChanged.connect(self.on_current_item_changed)
        self.tree.setColumnWidth(0, 420)
        main.addWidget(self.tree, 10)

        # --- Checkbox styling with PNG ---
        check_png = UI_DIR / "Checkmark.png"
        check_url = str(check_png).replace("\\", "/")

        self.tree.setUniformRowHeights(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemsExpandable(False)

        self.tree.setStyleSheet(f"""
            QTreeWidget::indicator {{
                width: 15px; height: 15px;
                margin-left: 6px; margin-right: 6px;
                border: 1px solid #666;
                background-color: transparent;
                border-radius: 3px;
            }}
            QTreeWidget::indicator:checked {{
                image: url('{check_url}');
                background-color: transparent;
            }}
            QTreeWidget::indicator:unchecked {{
                image: none;
                background-color: transparent;
            }}
        """)
        # --- Logs panel ---
        self.log_container = QWidget()
        log_layout = QVBoxLayout(self.log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(2)
        log_layout.addWidget(QLabel("Log:"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFixedHeight(140)
        log_layout.addWidget(self.log_area)
        main.addWidget(self.log_container, 2)

        # start with logs disabled
        self.logs_enabled = False
        self.log_container.setVisible(False)
        self.btn_toggle_logs.setText("Logs: Disabled")

        # --- Bottom bar ---
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self.game_icon_label = QLabel()
        self.game_icon_label.setFixedSize(64, 64)
        self.game_icon_label.setAlignment(Qt.AlignCenter)
        bottom.addWidget(self.game_icon_label)

        self.game_text_label = QLabel("Game:")
        self.game_text_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        bottom.addWidget(self.game_text_label)

        self.game_combo = QComboBox()
        self.game_combo.setMinimumWidth(280)
        self.game_combo.setMinimumHeight(38)
        self.game_combo.setStyleSheet("font-size: 15px;")
        for gname in GAME_KEYS.keys():
            self.game_combo.addItem(gname)
        self.game_combo.setCurrentText(self.current_game)
        self.game_combo.currentTextChanged.connect(self.switch_game)
        bottom.addWidget(self.game_combo)

        bottom.addStretch(1)

        # --- Action buttons (SBButton for consistent cursor + hover) ---
        self.btn_save = SBButton("Save")
        self.btn_save.setMinimumHeight(48)
        hook_flash(self.btn_save)
        self.btn_save.clicked.connect(self.on_save)

        self.btn_save_play = SBButton("Save and Play")
        self.btn_save_play.setMinimumHeight(48)
        hook_flash(self.btn_save_play)
        self.btn_save_play.clicked.connect(self.on_save_and_play)

        self.btn_refresh = SBButton("Refresh")
        self.btn_refresh.setMinimumHeight(48)
        hook_flash(self.btn_refresh)
        self.btn_refresh.clicked.connect(self.on_refresh_mods)

        self.btn_add_mod = SBButton("Add Mod")
        self.btn_add_mod.setMinimumHeight(48)
        hook_flash(self.btn_add_mod)
        self.btn_add_mod.clicked.connect(self.on_add_mod)

        self.btn_settings = QToolButton()
        self.btn_settings.setToolTip("Settings")
        self.btn_settings.setAutoRaise(True)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setObjectName("gearButton")
        settings_icon = find_ui_icon("Gear Icon", "Setting") or (APP_DIR / "gear.png")
        if settings_icon and Path(settings_icon).exists():
            self.btn_settings.setIcon(QIcon(str(settings_icon)))
        else:
            self.btn_settings.setText("⚙")
        self.btn_settings.setIconSize(QSize(24, 24))
        self.btn_settings.setMinimumSize(48, 48)
        self.btn_settings.clicked.connect(self.on_settings)
        self.btn_settings.clicked.connect(self._shine_settings_icon)
        hook_flash(self.btn_settings)

        for b in (self.btn_save, self.btn_save_play, self.btn_refresh, self.btn_add_mod):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            bottom.addWidget(b, 1)

        # --- Status label at top center ---
        self.game_status_label = QLabel("")
        self.game_status_label.setAlignment(Qt.AlignCenter)
        self.game_status_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #C0C0C0;")
        
        # Instead of stacking it above the gear button in the bottom bar,
        # add it to your header layout so it sits centered at the top.
        # Example:
        header = QHBoxLayout()
        
        # Left side (title, logs toggle, etc.)
        header.addLayout(header_left)
        
        # Centered status label
        header.addWidget(self.game_status_label, 1)  # stretch=1 keeps it centered
        
        # Right side (mod list, version, update, etc.)
        header.addLayout(right_header)
        
        main.addLayout(header)
        
        # --- Bottom bar (gear button alone, no status label here) ---
        bottom.addWidget(self.btn_settings, 0, Qt.AlignRight)
        main.addLayout(bottom)


        self.saved_lbl = QLabel("Settings Saved", self)
        self.saved_lbl.setStyleSheet("background: rgba(10,10,10,0.85); color: #E0E0E0; padding:6px; border-radius:4px;")
        self.saved_lbl.setVisible(False)

        # Apply theme last so styles are consistent at startup
        self.load_game(self.current_game)
        self.apply_background_theme()
        self._update_game_icon()

        # Keep your small sizing tweaks and toolbutton borders
        self.setStyleSheet(self.styleSheet() + """
            QPushButton { min-height: 40px; padding: 6px 12px; }
            QToolButton { min-height: 40px; padding: 6px 12px; }
            QPushButton:pressed, QToolButton:pressed { padding: 6px 12px; margin: 0px; }
            QToolButton#gearButton, QToolButton#updateButton { border: 1px solid rgba(255,255,255,0.25); border-radius: 6px; padding: 4px; }
            QToolButton#gearButton:hover, QToolButton#updateButton:hover { border-color: rgba(255,255,255,0.5); }
        """)

        # Ensure every button in the window has the pointing‑hand cursor (not just the bottom row)
        self._handify_buttons(self)

        # Flags to track Unsaved Changes
        self.unsaved_modlist = False
        self.unsaved_schema = False
        self.unsaved_config = False
        self.unsaved_settings = False

    # --- Make pointing‑hand cursor universal for buttons (QPushButton, QToolButton, and QDialogButtonBox buttons) ---
    def _handify_buttons(self, root_widget):
        try:
            # All QPushButtons
            for w in root_widget.findChildren(QPushButton):
                w.setCursor(Qt.PointingHandCursor)
            # All QToolButtons
            for w in root_widget.findChildren(QToolButton):
                w.setCursor(Qt.PointingHandCursor)
            # Buttons inside QDialogButtonBox
            for box in root_widget.findChildren(QDialogButtonBox):
                for b in box.buttons():
                    b.setCursor(Qt.PointingHandCursor)
        except Exception:
            pass

    # --- Updates (mods + manager) ---
    def on_check_all_updates(self):
        # Show progress dialog
        progress = UpdateProgressDialog(self)

        def run():
            updates = []

            # Collect mods from the tree
            mods = []
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                mod = item.data(0, Qt.UserRole)
                if mod != 0:
                    mods.append(mod)

            # Check mod updates
            for mod in mods:
                try:
                    current_ver = mod.get("version")
                    mod_url = mod.get("update") or mod.get("url") or mod.get("update_url") or mod.get("homepage")
                    if not mod_url:
                        continue

                    latest_ver, latest_title = get_latest_version_and_title(mod_url)
                    if latest_ver and compare_versions(current_ver, latest_ver) < 0:
                        updates.append({
                            "name": mod.get("name", "Unknown"),
                            "current": current_ver,
                            "latest": latest_ver,
                            "url": mod_url
                        })
                except Exception as e:
                    print(f"Error checking {mod.get('name','Unknown')}: {e}")

            # NEW: Manager self-update check using GameBanana
            if MANAGER_UPDATE_URL:
                try:
                    self.log("[update] Checking Mod Manager for updates...")
                    latest_ver, latest_title = get_latest_version_and_title(MANAGER_UPDATE_URL)

                    if latest_ver:
                        current_manager_ver = APP_VERSION
                        if compare_versions(current_manager_ver, latest_ver) < 0:
                            updates.insert(0, {  # Insert at top so it shows first
                                "name": "Storybook Mod Manager",
                                "current": current_manager_ver,
                                "latest": latest_ver,
                                "url": MANAGER_UPDATE_URL
                            })
                            self.log(f"[update] Manager update available: {current_manager_ver} -> {latest_ver}")
                        else:
                            self.log(f"[update] Manager is up to date (v{current_manager_ver})")
                    else:
                        self.log("[update] Could not detect manager version from GameBanana")
                except Exception as e:
                    self.log(f"[update] Manager update check failed: {e}")

            progress.accept()  # close progress dialog

            if updates:
                dlg = UpdateCheckDialog(updates, self)
                handify_buttons_in(dlg)
                dlg.exec_()
            else:
                QMessageBox.information(self, "Up to Date", "All mods and the Mod Manager are up to date!")

        # Run after dialog shows
        QTimer.singleShot(50, run)
        progress.exec_()

    # --- Logs ---
    def toggle_logs(self):
        # Keep window size stable; only toggle visibility
        self.logs_enabled = not self.logs_enabled
        self.log_container.setVisible(self.logs_enabled)
        self.btn_toggle_logs.setText(f"Logs: {'Enabled' if self.logs_enabled else 'Disabled'}")

    def log(self, s):
        if self.logs_enabled:
            self.log_area.append(s)
        print(s)

    def _shine_settings_icon(self):
        orig = self.btn_settings.styleSheet() or ""
        flash_css = "\nQToolButton#gearButton { background-color: rgba(255,255,255,0.18); border-radius: 6px; }"
        try:
            self.btn_settings.setStyleSheet(orig + flash_css)
        except Exception:
            self.btn_settings.setStyleSheet(flash_css)
        t = QTimer(self.btn_settings)
        t.setSingleShot(True)
        t.setInterval(140)
        def restore():
            try:
                self.btn_settings.setStyleSheet(orig)
            except Exception:
                pass
        t.timeout.connect(restore)
        t.start()

    # --- Game switching ---
    def switch_game(self, name):
        self.current_game = name
        self.settings["last_game"] = name
        save_settings(self.settings)
        self.load_game(name)
        self.apply_background_theme()
        self.game_combo.setCurrentText(name)
        self._update_game_icon()
        self.log(f"[ui] switched to {name}")

    def _update_game_icon(self):
        base = GAME_KEYS[self.current_game].lower()
        icon_path = find_ui_icon(base, "Game") or find_ui_icon(base, "Settings")
        if icon_path and Path(icon_path).exists():
            pix = QPixmap(str(icon_path)).scaled(self.game_icon_label.width(), self.game_icon_label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.game_icon_label.setPixmap(pix)
        else:
            self.game_icon_label.clear()

    def show_mod_list_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1A1A1A;
                color: #E6E6E6;
                border: 1px solid #333;
                padding: 6px;
            }
            QMenu::item {
                padding: 6px 18px;
            }
            QMenu::item:selected {
                background-color: rgba(255,255,255,0.08);
                color: #FFFFFF;
            }
        """)

        act_enable_all = menu.addAction("Enable All")
        act_disable_all = menu.addAction("Disable All")

        chosen = menu.exec_(self.btn_mod_list.mapToGlobal(self.btn_mod_list.rect().bottomLeft()))

        if chosen == act_enable_all:
            self.enable_all_mods()
        elif chosen == act_disable_all:
            self.disable_all_mods()
    
    # --- Reordering enabled mods to top ---
    def _reorder_enabled_mods(self):
        """
        Reorder tree so checked (enabled) mods appear first.
        Rebuilds rows and creates fresh gear widgets (avoids reparenting bugs).
        Short, robust, and preserves visible gear icons.
        """
        try:
            # Collect all mod metadata and their check state
            rows = []
            for i in range(self.tree.topLevelItemCount()):
                it = self.tree.topLevelItem(i)
                if not it:
                    continue
                meta = it.data(0, Qt.UserRole) or {}
                checked = (it.checkState(0) == Qt.Checked)
                rows.append((meta, checked))

            # Enabled first, keep relative order otherwise
            ordered = [r for r in rows if r[1]] + [r for r in rows if not r[1]]

            self.tree.blockSignals(True)
            self.tree.clear()

            for idx, (meta, checked) in enumerate(ordered):
                name = meta.get("name", "") or ""
                ver = meta.get("version", "") or ""
                author = meta.get("author", "") or ""
                path_str = meta.get("path", "") or ""

                # Create item
                item = QTreeWidgetItem([name, ver, author, ""])
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                item.setData(0, Qt.UserRole, meta)

                # Alternating background like load_game
                color = "#1F1F1F" if idx % 2 == 0 else "#171717"
                for c in range(self.tree.columnCount()):
                    try:
                        item.setBackground(c, QBrush(QColor(color)))
                    except Exception:
                        pass

                self.tree.addTopLevelItem(item)

                # Create compact gear widget (fresh instance)
                try:
                    container = QWidget()
                    container.setAttribute(Qt.WA_TranslucentBackground, True)
                    container.setStyleSheet("background: transparent;")
                    container.setFixedHeight(36)
                    layout = QHBoxLayout(container)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.setSpacing(0)

                    gear_btn = QToolButton()
                    gear_btn.setCursor(Qt.PointingHandCursor)
                    gear_btn.setAutoRaise(True)
                    gear_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
                    gear_btn.setFixedSize(30, 30)
                    gear_btn.setIconSize(QSize(18, 18))
                    try:
                        icon_path = UI_DIR / "White Gear - Config.png"
                        if icon_path.exists():
                            gear_btn.setIcon(QIcon(str(icon_path)))
                        else:
                            gear_btn.setText("\u2699")
                            gear_btn.setStyleSheet("font-size:14px; margin-bottom:3px;")
                    except Exception:
                        gear_btn.setText("\u2699")

                    gear_btn.setToolTip("Configure Mod Menu")

                    # Click handler opens configure dialog (same behavior as load_game)
                    def _on_gear(_checked=False, p=path_str):
                        try:
                            dlg = ConfigureModDialog(self, Path(p))
                            try:
                                dlg.setStyle(self.style())
                                dlg.setPalette(self.palette())
                                dlg.setWindowModality(Qt.ApplicationModal)
                            except Exception:
                                pass
                            try:
                                # ensure pointing-hand for dialog buttons
                                for btn in dlg.findChildren(QPushButton):
                                    btn.setCursor(Qt.PointingHandCursor)
                                for tbtn in dlg.findChildren(QToolButton):
                                    tbtn.setCursor(Qt.PointingHandCursor)
                            except Exception:
                                pass
                            dlg.exec_()
                        except Exception as ex:
                            QMessageBox.warning(self, "Configure", f"Could not open Configure dialog:\n{ex}")

                    gear_btn.clicked.connect(_on_gear)

                    # Dim gear if no meaningful config
                    try:
                        has_cfg = self._mod_has_config(Path(path_str))
                    except Exception:
                        has_cfg = True
                    if not has_cfg:
                        try:
                            from PyQt5.QtWidgets import QGraphicsOpacityEffect
                            eff = QGraphicsOpacityEffect(gear_btn)
                            eff.setOpacity(0.35)
                            gear_btn.setGraphicsEffect(eff)
                        except Exception:
                            gear_btn.setEnabled(False)
                        gear_btn.setToolTip("No configure options (Preset only)")

                    layout.addStretch(1)
                    layout.addWidget(gear_btn, 0, Qt.AlignCenter)
                    layout.addStretch(1)

                    self.tree.setItemWidget(item, 3, container)
                except Exception:
                    # If anything fails creating the widget, continue without it
                    pass

            # Restore sensible widths (same as load_game defaults)
            try:
                self.tree.setColumnWidth(0, 220)
                self.tree.setColumnWidth(1, 130)
                self.tree.setColumnWidth(2, 260)
                self.tree.setColumnWidth(3, 52)
            except Exception:
                pass

        except Exception as e:
            try:
                self.log(f"[reorder_enabled_mods] error: {e}")
            except Exception:
                pass
        finally:
            try:
                self.tree.blockSignals(False)
            except Exception:
                pass
    
    # --- Themes (merged hover rules for consistency) ---
    def apply_background_theme(self):
        mode = load_settings().get("theme_mode", "Dark Mode")
        if mode not in ("Dark Mode", "Storybook Themes"):
            mode = "Dark Mode"

        if mode == "Dark Mode":
            self.setStyleSheet("""
                QWidget { background-color: #121212; color: #E0E0E0; }

                QTreeWidget {
                    background-color: #1A1A1A;
                    color: #E0E0E0;
                    border: 1px solid #333;
                    border-radius: 4px;
                    padding: 4px;
                }
                QTreeWidget::item {
                    border-radius: 2px;
                    padding: 4px;
                    margin: 1px 0;
                }
                QTreeWidget::item:hover {
                    background-color: rgba(255,255,255,0.1);
                }
                QTreeWidget::item:selected {
                    background-color: rgba(255,255,255,0.15);
                }
                QTreeWidget::item:selected:active {
                    background-color: rgba(255,255,255,0.2);
                }
                QTreeWidget QHeaderView::section {
                    background-color: #1F1F1F;
                    color: #E6E6E6;
                    border: none;
                    border-bottom: 1px solid #333;
                    padding: 6px;
                    font-weight: bold;
                }

                /* Buttons: consistent base + hover + press */
                QPushButton {
                    background-color: #1F1F1F;
                    color: #E0E0E0;
                    border: 1px solid #333;
                    border-radius: 4px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #2A2A2A;
                }
                QPushButton:pressed {
                    background-color: #111111;
                }

                QLineEdit, QTextEdit, QComboBox, QListWidget {
                    background-color: #1A1A1A;
                    color: #E0E0E0;
                    border: 1px solid #333;
                    selection-background-color: #3A3A3A;
                    border-radius: 4px;
                }
                QTextEdit { padding: 4px; }

                QToolButton { color: #E0E0E0; }
                QToolButton#gearButton, QToolButton#updateButton {
                    border: 1px solid rgba(255,255,255,0.25);
                    border-radius: 6px;
                    padding: 4px;
                }
                QToolButton#gearButton:hover, QToolButton#updateButton:hover {
                    border-color: rgba(255,255,255,0.5);
                    background-color: rgba(255,255,255,0.12);
                }
            """)
            return

        ui_theme = find_ui_icon(GAME_KEYS[self.current_game].lower(), "Themes")
        use_img = ui_theme if ui_theme and Path(ui_theme).exists() else DEFAULT_THEMES.get(self.current_game)
        if use_img and Path(use_img).exists():
            p = str(use_img).replace("\\", "/")
            self.setStyleSheet(
                f"""
                QWidget {{
                    background-image: url('{p}');
                    background-repeat: no-repeat;
                    background-position: center;
                    background-attachment: fixed;
                    color: #E0E0E0;
                }}

                QTreeWidget, QTextEdit {{ background-color: rgba(0,0,0,0.35); color: #E0E0E0; }}
                QTreeWidget QHeaderView::section {{
                    background-color: rgba(0,0,0,0.45);
                    color: #E6E6E6;
                    border: none;
                    border-bottom: 1px solid #444;
                    padding: 6px;
                    font-weight: bold;
                }}

                /* Buttons: consistent base + hover + press */
                QPushButton {{
                    background-color: rgba(0,0,0,0.40);
                    color: #E0E0E0;
                    border: 1px solid #444;
                    border-radius: 4px;
                    padding: 6px 12px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255,255,255,0.15);
                }}
                QPushButton:pressed {{
                    background-color: rgba(255,255,255,0.25);
                }}

                QLineEdit, QTextEdit, QComboBox, QListWidget {{
                    background-color: rgba(0,0,0,0.45);
                    color: #E0E0E0;
                    border: 1px solid #444;
                    selection-background-color: #3A3A3A;
                    border-radius: 4px;
                }}

                QToolButton {{ color: #E0E0E0; }}
                QToolButton#gearButton, QToolButton#updateButton {{
                    border: 1px solid rgba(255,255,255,0.25);
                    border-radius: 6px;
                    padding: 4px;
                }}
                QToolButton#gearButton:hover, QToolButton#updateButton:hover {{
                    border-color: rgba(255,255,255,0.5);
                    background-color: rgba(255,255,255,0.12);
                }}
                """
            )


    # --- 2 Helpers that help with Gear Icon Config ---
    def _mod_has_config(self, mod_folder: Path) -> bool:
        """
        Return True if this mod folder contains a non-default Configure/Config section.
        Checks mod_data.json (unified), config_schema.json, and configs/ for anything
        beyond just a fallback 'Preset'.
        """
        try:
            md = Path(mod_folder)
            # unified format (mod_data.json)
            p = md / "mod_data.json"
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    cfg = data.get("CONFIGURE MOD MENU", {}) or {}
                    if cfg:
                        keys = [k for k in cfg.keys() if k and str(k).strip().lower() != "preset"]
                        if keys:
                            return True
                        if any(str(v).strip() for v in cfg.values()):
                            return True
                except Exception:
                    pass
                
            # legacy schema
            p2 = md / "config_schema.json"
            if p2.exists():
                try:
                    s = json.loads(p2.read_text(encoding="utf-8"))
                    real = [k for k in s.keys() if not str(k).startswith("__") and k.lower() != "preset"]
                    if real:
                        return True
                except Exception:
                    pass
                
            # configs directory
            configs_dir = md / "configs"
            if configs_dir.exists() and configs_dir.is_dir():
                js = [f for f in configs_dir.glob("*.json") if f.is_file() and f.stem.lower() != "preset"]
                if js:
                    return True
    
        except Exception:
            pass
        return False
    
    def open_configure_mod_menu(self, mod_folder):
        """Open the Configure Mod Menu dialog for the given mod folder (Path or str)."""
        try:
            mf = Path(mod_folder)
            dlg = ConfigureModSchemaDialog(self, mf)
            # optional helper to set pointing-hand cursors etc (if you have it)
            try:
                self._handify_buttons(dlg)
            except Exception:
                pass
            dlg.exec_()
            # mark potential changes
            self.unsaved_schema = True
        except Exception as e:
            QMessageBox.warning(self, "Open Configure Menu", f"Could not open Configure Mod Menu:\n{e}")

    # Updates the Conext menu to fallback to the mod_data.json to see if it was a texture pack mod or not (if user has moved)
    def _is_texture_pack_via_applied_files(self, mod_folder: Path) -> bool:
        """
        Fallback detection: check if mod_data.json has APPLIED FILES with .png extensions.
        This catches texture packs where PNGs have already been moved to Dolphin path.
        """
        try:
            data_file = mod_folder / "mod_data.json"
            if not data_file.exists():
                return False
            
            data = json.loads(data_file.read_text(encoding="utf-8"))
            applied = data.get("APPLIED FILES", [])
            
            if not applied:
                return False
            
            # Check if any applied file is a PNG
            return any(str(f).lower().endswith(".png") for f in applied)
        except Exception:
            return False

    # --- Mods list population ---
    def load_game(self, name):
        """
        Populate the mods tree:
          - Keeps header vertical dividers and removes the bottom header line
          - DOES NOT touch checkbox/indicator styling (fixes white check issue)
          - Balanced column widths, adjustable headers
          - Centered gear icon in Config column, slightly nudged up
          - Dialog opened via gear inherits style and gets pointing-hand cursors on its buttons
          - Sorts enabled mods to the top deterministically without in-place reordering
        """
        from pathlib import Path
        try:
            # ---- Basic tree setup ----
            self.tree.setColumnCount(4)
            self.tree.setHeaderLabels(["Name", "Version", "Author", "Config"])
            self.tree.blockSignals(True)
            self.tree.clear()
    
            # ---- Header-only stylesheet (no indicator changes)
            try:
                from PyQt5.QtWidgets import QHeaderView
                header = self.tree.header()
                hdr_style = """
                QHeaderView::section {
                    background: transparent;
                    border-bottom: none;
                    border-right: 1px solid #2b2b2b;
                    padding: 6px 8px;
                }
                QHeaderView::section:last {
                    border-right: none;
                }
                """
                header.setStyleSheet(hdr_style)
                header.setSectionResizeMode(0, QHeaderView.Interactive)
                header.setSectionResizeMode(1, QHeaderView.Interactive)
                header.setSectionResizeMode(2, QHeaderView.Interactive)
                header.setSectionResizeMode(3, QHeaderView.Fixed)
                header.setStretchLastSection(False)
                header.setSectionsClickable(True)
            except Exception:
                pass
            
            # ---- Resolve settings / mods dir ----
            try:
                key = GAME_KEYS[name]
            except Exception:
                self.log(f"[load_game] Invalid game name: {name}")
                self.tree.blockSignals(False)
                return
    
            settings = load_settings()
            mods_dir = Path(settings.get("games", {}).get(key, {}).get("mods", "") or "")
            enabled_list = set(settings.get("games", {}).get(key, {}).get("enabled_mods", []))
    
            # ---- Gather mods ----
            try:
                mod_entries = list(scan_mods_folder(mods_dir))
            except Exception:
                mod_entries = []
    
            if not mod_entries and mods_dir.exists():
                for d in sorted(mods_dir.iterdir()):
                    if d.is_dir():
                        mod_entries.append({"name": d.name, "version": "", "author": "", "path": str(d)})
    
            if not mod_entries:
                placeholder = QTreeWidgetItem(["(No mods found)", "", "", ""])
                placeholder.setFlags(Qt.ItemIsEnabled)
                self.tree.addTopLevelItem(placeholder)
                self.tree.blockSignals(False)
                self.log(f"[load_game] No mods found in {mods_dir}")
                return
    
            # ---- Sort enabled mods to the top (stable, then by name) ----
            def is_enabled(meta):
                p = Path(meta.get("path", "") or "")
                try:
                    rp = str(p.resolve())
                except Exception:
                    rp = str(p)
                return rp in enabled_list
    
            mod_entries.sort(
                key=lambda m: (not is_enabled(m), (m.get("name") or "").lower())
            )
    
            # Prefer ConfigureModDialog if present
            DialogClass = None
            try:
                DialogClass = ConfigureModDialog
            except Exception:
                try:
                    DialogClass = ConfigureModSchemaDialog
                except Exception:
                    DialogClass = None
    
            # ---- Populate rows ----
            for i, m in enumerate(mod_entries):
                try:
                    mod_name = m.get("name", "") or ""
                    version = m.get("version", "") or ""
                    author = m.get("author", "") or ""
                    mod_path = Path(m.get("path", "") or "")
    
                    item = QTreeWidgetItem([mod_name, version, author, ""])
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    
                    try:
                        resolved_path = str(mod_path.resolve()) if mod_path else ""
                    except Exception:
                        resolved_path = str(mod_path)
                    item.setCheckState(0, Qt.Checked if resolved_path in enabled_list else Qt.Unchecked)
                    item.setData(0, Qt.UserRole, m)
    
                    # Alternating row color
                    color = "#1F1F1F" if i % 2 == 0 else "#171717"
                    for c in range(self.tree.columnCount()):
                        item.setBackground(c, QBrush(QColor(color)))
    
                    self.tree.addTopLevelItem(item)
    
                    # ---- Config column: gear button ----
                    container = QWidget()
                    container.setStyleSheet("background: transparent;")
                    container.setFixedHeight(36)
    
                    layout = QHBoxLayout(container)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.setSpacing(0)
    
                    gear_btn = QToolButton(container)
                    gear_btn.setCursor(Qt.PointingHandCursor)
                    gear_btn.setAutoRaise(True)
                    gear_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
                    gear_btn.setFixedSize(30, 30)
                    gear_btn.setIconSize(QSize(18, 18))
                    try:
                        gear_btn.setStyleSheet("margin-bottom:3px;")
                    except Exception:
                        pass
                    
                    try:
                        icon_path = UI_DIR / "White Gear - Config.png"
                        if icon_path.exists():
                            gear_btn.setIcon(QIcon(str(icon_path)))
                        else:
                            gear_btn.setText("⚙")
                            gear_btn.setStyleSheet("font-size:14px; margin-bottom:3px;")
                    except Exception:
                        gear_btn.setText("⚙")
    
                    gear_btn.setToolTip("Configure Mod Menu")
    
                    def _on_gear_clicked(_checked=False, p=mod_path):
                        try:
                            if DialogClass is None:
                                QMessageBox.information(self, "Configure", "Configure dialog class not found.")
                                return
                            dlg = DialogClass(self, p)
                            try:
                                dlg.setStyle(self.style())
                                dlg.setPalette(self.palette())
                                dlg.setWindowModality(Qt.ApplicationModal)
                            except Exception:
                                pass
                            try:
                                from PyQt5.QtWidgets import QPushButton, QToolButton
                                for btn in dlg.findChildren(QPushButton):
                                    try:
                                        btn.setCursor(Qt.PointingHandCursor)
                                    except Exception:
                                        pass
                                for tbtn in dlg.findChildren(QToolButton):
                                    try:
                                        tbtn.setCursor(Qt.PointingHandCursor)
                                    except Exception:
                                        pass
                                try:
                                    if hasattr(self, "_handify_buttons"):
                                        self._handify_buttons(dlg)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            try:
                                dlg.exec_()
                            except Exception:
                                try:
                                    dlg.show(); dlg.raise_(); dlg.activateWindow()
                                except Exception as ex_show:
                                    QMessageBox.warning(self, "Configure", f"Could not open dialog:\n{ex_show}")
                        except Exception as ex:
                            QMessageBox.warning(self, "Configure", f"Failed to open configure dialog:\n{ex}")
    
                    gear_btn.clicked.connect(_on_gear_clicked)
    
                    try:
                        has_cfg = self._mod_has_config(mod_path)
                    except Exception:
                        has_cfg = True
                    if not has_cfg:
                        try:
                            from PyQt5.QtWidgets import QGraphicsOpacityEffect
                            eff = QGraphicsOpacityEffect(gear_btn)
                            eff.setOpacity(0.35)
                            gear_btn.setGraphicsEffect(eff)
                        except Exception:
                            gear_btn.setEnabled(False)
                        gear_btn.setToolTip("No configure options (Preset only)")
    
                    layout.addStretch(1)
                    layout.addWidget(gear_btn, 0, Qt.AlignCenter)
                    layout.addStretch(1)
                    self.tree.setItemWidget(item, 3, container)
    
                except Exception as e:
                    self.log(f"[load_game] Skipped mod due to error: {e}")
                    continue
                
            # ---- Column widths ----
            try:
                self.tree.setColumnWidth(0, 220)
                self.tree.setColumnWidth(1, 130)
                self.tree.setColumnWidth(2, 260)
                self.tree.setColumnWidth(3, 52)
            except Exception:
                pass
            
            self.tree.blockSignals(False)
            self.log(f"[load_game] Loaded {len(mod_entries)} mods from {mods_dir}")
    
        except Exception as e:
            try:
                QMessageBox.critical(self, "Load Mods Error", f"load_game failed:\n{e}")
            except Exception:
                pass
            self.tree.blockSignals(False)
            self.log(f"[load_game] fatal error: {e}")

    # --- Mod list context menu, ENABLE AND DISABLE FUNCTIONS ---
    def enable_all_mods(self):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            it.setCheckState(0, Qt.Checked)
        self._save_enabled_mods()
        self.log("[ui] enabled all mods")

    def disable_all_mods(self):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            it.setCheckState(0, Qt.Unchecked)
        self._save_enabled_mods()
        self.log("[ui] disabled all mods")

    def _save_enabled_mods(self):
        """Save currently enabled mods into settings.json for persistence."""
        enabled_paths = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                m = it.data(0, Qt.UserRole)
                if m:
                    enabled_paths.append(str(Path(m["path"]).resolve()))

        key = GAME_KEYS[self.current_game]
        s = load_settings()
        s["games"].setdefault(key, {})
        s["games"][key]["enabled_mods"] = enabled_paths
        save_settings(s)
        self.settings = s  # keep in sync

    # --- Toolbar actions ---
    def on_refresh_mods(self):
        # Reload mods from disk using last-saved settings only
        self.load_game(self.current_game)
        self.log("[ui] refreshed mods list (from saved state)")

    def on_current_item_changed(self, current, previous):
        try:
            if current:
                m = current.data(0, Qt.UserRole)
                if m:
                    self.last_selected_mod_path = Path(m["path"])
        except Exception:
            pass

    def get_enabled_mods(self):
        enabled = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                enabled.append(it.data(0, Qt.UserRole))
        return enabled

    # --- Surgical apply ---
    def _resolve_vanilla_target(self, vanilla: Path, dst_name: str) -> Path:
        """
        Resolve destination path inside the vanilla tree.
        - If dst_name contains a subfolder (e.g., 'adx/sng_system1.adx'), use it directly.
        - If dst_name is just a filename (e.g., 'sng_system1.adx'), search the vanilla tree.
          Prefer matches inside 'adx'; otherwise use the first match.
          If no match exists, fall back to vanilla/dst_name (but we log).
        """
        dst_name = dst_name.replace("\\", "/").strip()
        # If caller provided a subfolder path, use it directly
        if "/" in dst_name:
            return vanilla / dst_name

        # Search for the filename under vanilla
        candidates = []
        try:
            for dirpath, _, filenames in os.walk(vanilla, followlinks=True):
                if dst_name in filenames:
                    candidates.append(Path(dirpath) / dst_name)
        except Exception:
            pass

        if not candidates:
            # Fallback: root (we try to avoid this; log later)
            return vanilla / dst_name

        # Prefer a match inside 'adx'
        for c in candidates:
            if "adx" in [p.lower() for p in c.parts]:
                return c
        return candidates[0]

    # --- Detect whether a mod is being conflicted with another, lmao ---
    def _detect_file_conflicts(self, enabled_mods: list) -> dict:
        """
        Detect file conflicts across enabled mods.
        Returns: {filename: [(mod_name, choice_name), ...]} for files with 2+ mods
        """
        file_to_mods = {}  # {filename: [(mod_name, choice_name), ...]}

        for m in enabled_mods:
            mod_path = Path(m['path'])
            mod_name = m.get('name', mod_path.name)

            files_this_mod_touches = set()

            # Load mod_data.json to check configs
            data_file = mod_path / "mod_data.json"
            cfg = {}
            attachments = {}

            if data_file.exists():
                try:
                    data = json.loads(data_file.read_text(encoding="utf-8"))
                    cfg = data.get("CONFIGURE MOD MENU", {}) or {}
                    section = data.get("SET CONFIGURE SCHEMA", {}) or {}
                    attachments = section.get("attachments", {}) or {}
                except Exception:
                    pass
                
            # Check if mod has config
            if cfg and attachments:
                # Has config: check what's currently selected
                for dropdown_key, selected_value in cfg.items():
                    if not isinstance(selected_value, str):
                        continue
                    
                    # Get files for this dropdown's selected choice
                    entry = attachments.get(dropdown_key, {}).get(selected_value, {})
                    if entry:
                        for fm in entry.get("files", []):
                            dst_name = fm.get("dst")
                            if dst_name:
                                files_this_mod_touches.add((dst_name, f"{dropdown_key}: {selected_value}"))
            else:
                # No config: scan all files in mod folder
                choice_label = "All Files"

                # Check file_mappings.json for explicit mappings
                mapping_file = mod_path / "file_mappings.json"
                if mapping_file.exists():
                    try:
                        mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
                        for src_rel, dst_name in mapping.items():
                            if dst_name:
                                files_this_mod_touches.add((dst_name, choice_label))
                    except Exception:
                        pass
                    
                # Walk mod folder for implicit files
                game_key = GAME_KEYS[self.current_game]
                gconf = self.settings["games"].get(game_key, {})
                vanilla = Path(gconf.get("vanilla") or "")

                if vanilla.exists():
                    valid_game_dirs = {p.name for p in vanilla.iterdir() if p.is_dir()}

                    for dirpath, _, filenames in os.walk(mod_path, followlinks=True):
                        rel_dir = Path(dirpath).relative_to(mod_path)

                        # Skip non-game directories
                        if rel_dir.parts and rel_dir.parts[0] not in valid_game_dirs:
                            continue
                        
                        for fname in filenames:
                            if fname in ("packed_files.bin", "mod.ini", "config_schema.json",
                                         "config.json", "config_schema_files.json",
                                         "preview.png", "file_mappings.json", "mod_data.json"):
                                continue
                            
                            # Use just the filename as the conflict key
                            files_this_mod_touches.add((fname, choice_label))

            # Add to tracking map
            for filename, choice in files_this_mod_touches:
                if filename not in file_to_mods:
                    file_to_mods[filename] = []
                file_to_mods[filename].append((mod_name, choice))

        # Filter to only conflicts (2+ mods touching same file)
        conflicts = {f: mods for f, mods in file_to_mods.items() if len(mods) >= 2}

        return conflicts

    def apply_mods_surgical(self):
        """
        Apply enabled mods into the game's vanilla tree.
        - If the mod has at least one dropdown = 'Enabled': backup/replace and record APPLIED FILES.
        - If the mod has all dropdowns 'Disabled' (or no config): restore originals and save the pruned archive.
        - NEW: PNG-only mods require Dolphin Custom Texture Path to be set.
        """
        enabled = self.get_enabled_mods()
        game_key = GAME_KEYS[self.current_game]

        # Guardrail: settings must be valid before applying
        if not settings_ready_for_game(self.settings, game_key):
            QMessageBox.warning(self, "Configure your settings!", "You must configure your settings before launching this game.")
            return False

        gconf = self.settings["games"].get(game_key, {})
        vanilla = Path(gconf.get("vanilla") or "")
        dolphin_texture_path_str = gconf.get("dolphin_texture_path", "")
        dolphin_texture_path = Path(dolphin_texture_path_str) if dolphin_texture_path_str and dolphin_texture_path_str.strip() else None

        if not vanilla.exists():
            QMessageBox.warning(self, "Missing Game Files", "Set Game Files (vanilla) in Settings first.")
            return False

        # NEW: Check for PNG-only mods without Dolphin texture path configured
        for m in enabled:
            mod_path = Path(m['path'])
            is_texture_pack = _mod_is_png_only(mod_path)

            if is_texture_pack:
                # Check if texture path is set and valid
                texture_path_str = gconf.get("dolphin_texture_path", "")

                if not texture_path_str or not texture_path_str.strip():
                    QMessageBox.warning(
                        self, 
                        "Dolphin Texture Path Required",
                        f"The mod '{m.get('name', mod_path.name)}' contains only PNG textures.\n\n"
                        "Please configure the Dolphin Custom Texture Path in Settings:\n"
                        "Settings > Dolphin Texture Packs"
                    )
                    return False

                test_path = Path(texture_path_str)
                if not test_path.exists():
                    QMessageBox.warning(
                        self, 
                        "Dolphin Texture Path Invalid",
                        f"The mod '{m.get('name', mod_path.name)}' requires a valid Dolphin Custom Texture Path.\n\n"
                        f"The configured path does not exist:\n{texture_path_str}\n\n"
                        "Please update it in Settings > Dolphin Texture Packs"
                    )
                    return False

        valid_game_dirs = {p.name for p in vanilla.iterdir() if p.is_dir()}
        archive = load_archive(game_key)

        for m in enabled:
            mod_path = Path(m['path'])
            mod_name = m.get('name', mod_path.name)
            self.log(f"[surgical] applying mod {mod_name}")

            # Check if this is a PNG-only (texture pack) mod
            is_texture_pack = _mod_is_png_only(mod_path)
            
            # Get texture pack mode from mod.ini
            texture_pack_mode = "copy"  # default
            if is_texture_pack:
                try:
                    cp, _, _ = ensure_mod_ini(mod_path)
                    texture_pack_mode = cp.get(INI_SECTION, "TexturePackMode", fallback="copy")
                except Exception:
                    texture_pack_mode = "copy"
                self.log(f"[surgical] {mod_name} texture pack mode: {texture_pack_mode}")

            # --- Load unified mod_data.json (cfg, schema, attachments) ---
            cfg, schema, attachments = {}, {}, {}
            data_file = mod_path / "mod_data.json"
            if data_file.exists():
                try:
                    data = json.loads(data_file.read_text(encoding="utf-8"))
                    cfg = data.get("CONFIGURE MOD MENU", {}) or {}
                    section = data.get("SET CONFIGURE SCHEMA", {}) or {}
                    schema = section.get("schema", {}) or {}
                    attachments = section.get("attachments", {}) or {}
                except Exception:
                    cfg, schema, attachments = {}, {}, {}
            else:
                # Legacy fallback if needed
                cfgp = mod_path / "config.json"
                if cfgp.exists():
                    try:
                        cfg = json.loads(cfgp.read_text(encoding="utf-8")) or {}
                    except Exception:
                        cfg = {}
                attachp = mod_path / "config_schema_files.json"
                if attachp.exists():
                    try:
                        attachments = json.loads(attachp.read_text(encoding="utf-8")) or {}
                    except Exception:
                        attachments = {}

            # --- Determine if this mod should apply or restore based on dropdowns ---
            has_enabled_choice = any(
                isinstance(v, str) and v.strip().lower() == "enabled"
                for v in (cfg or {}).values()
            )
            
            # NEW: If no config exists at all, treat mod as "enabled" (apply its files)
            if not cfg and not schema and not attachments:
                has_enabled_choice = True
                self.log(f"[surgical] {mod_name} has no config, applying all files")
            
            # NEW: If config exists but is set to Disabled, DON'T skip root files
            # Only skip if we're in restore mode (previously had files applied)
            if not has_enabled_choice:
                data_file = mod_path / "mod_data.json"
                previously_applied = False
                if data_file.exists():
                    try:
                        data = json.loads(data_file.read_text(encoding="utf-8"))
                        previously_applied = bool(data.get("APPLIED FILES", []))
                    except Exception:
                        pass
                    
                if previously_applied:
                    # This mod was previously applied, now disabled → restore
                    if is_texture_pack:
                        if texture_pack_mode == "move":
                            self._restore_dolphin_textures(mod_path, game_key, dolphin_texture_path)
                        restored = self._restore_dolphin_textures(mod_path, game_key, dolphin_texture_path)
                        if restored:
                            self.log(f"[apply] {mod_name}: texture pack disabled → restored {len(restored)} texture(s)")
                    else:
                        restored = restore_files_for_mod(mod_path, game_key, vanilla, log_fn=self.log)
                        if restored:
                            self.log(f"[apply] {mod_name}: all choices Disabled → restored {len(restored)} file(s)")
                            archive = load_archive(game_key)
                    continue
                else:
                    # No previous application, and disabled → treat as "has no meaningful config"
                    # (i.e., apply root files if they exist)
                    has_enabled_choice = True
                    self.log(f"[surgical] {mod_name}: config disabled but no previous application, applying root files")

            # NEW: For PNG-only mods without config, treat as "enabled" (apply textures)
            if is_texture_pack and not cfg:
                has_enabled_choice = True
                self.log(f"[surgical] {mod_name} is a texture pack without config, applying all PNGs")

            # NEW: Handle "Disabled" choices for texture packs (restore/delete those specific textures)
            if is_texture_pack and cfg:
                for keyname, chosen in (cfg or {}).items():
                    if not isinstance(chosen, str):
                        continue
                    if chosen.strip().lower() == "disabled":
                        # This choice is disabled, restore/delete its textures
                        entry = attachments.get(keyname, {}).get(chosen, {})
                        if entry:
                            files_to_restore = []
                            for fm in entry.get("files", []):
                                dst_name = fm.get("dst")
                                if dst_name:
                                    files_to_restore.append(dst_name)

                            # Also check Enabled entry for this dropdown (since we're switching away from it)
                            enabled_entry = attachments.get(keyname, {}).get("Enabled", {})
                            if enabled_entry:
                                for fm in enabled_entry.get("files", []):
                                    dst_name = fm.get("dst")
                                    if dst_name:
                                        files_to_restore.append(dst_name)

                            # Restore or delete each file, and if move mode, copy back to mod folder
                            for dst_name in files_to_restore:
                                dst = dolphin_texture_path / dst_name
                                rel_key = f"texture::{Path(dst_name).as_posix()}"

                                if rel_key in archive:
                                    # Restore from backup
                                    try:
                                        dst.parent.mkdir(parents=True, exist_ok=True)
                                        dst.write_bytes(archive[rel_key])
                                        self.log(f"[restore] Restored texture {dst_name} (dropdown disabled)")
                                        del archive[rel_key]
                                    except Exception as e:
                                        self.log(f"[restore] Failed to restore texture {dst_name}: {e}")
                                else:
                                    # No backup, delete from dolphin path
                                    try:
                                        if dst.exists():
                                            # If move mode, copy back to mod folder before deleting
                                            if texture_pack_mode == "move":
                                                try:
                                                    mod_dest = mod_path / dst.name
                                                    shutil.copy2(dst, mod_dest)
                                                    self.log(f"[restore] Copied texture {dst.name} back to mod folder (disabled)")
                                                except Exception as copy_err:
                                                    self.log(f"[restore] Failed to copy back {dst.name}: {copy_err}")
                                            dst.unlink()
                                            self.log(f"[restore] Deleted mod-added texture {dst_name} (dropdown disabled)")
                                    except Exception as e:
                                        self.log(f"[restore] Failed to delete texture {dst_name}: {e}")

            if not has_enabled_choice:
                # All choices disabled → restore
                if is_texture_pack:
                    # If move mode, copy textures back to mod folder first
                    if texture_pack_mode == "move":
                        self._restore_dolphin_textures(mod_path, game_key, dolphin_texture_path)
                    # Restore from dolphin texture archive
                    restored = self._restore_dolphin_textures(mod_path, game_key, dolphin_texture_path)
                    if restored:
                        self.log(f"[apply] {mod_name}: texture pack disabled → restored {len(restored)} texture(s)")
                else:
                    # Normal game file restore
                    restored = restore_files_for_mod(mod_path, game_key, vanilla, log_fn=self.log)
                    if restored:
                        self.log(f"[apply] {mod_name}: all choices Disabled → restored {len(restored)} file(s)")
                        archive = load_archive(game_key)
                continue
            
            # ---- Otherwise, proceed with application for Enabled state ----
            touched = []

            # --- file_mappings.json (explicit mappings) ---
            mapping = {}
            mapping_p = mod_path / "file_mappings.json"
            if mapping_p.exists():
                try:
                    mapping = json.loads(mapping_p.read_text(encoding="utf-8"))
                except Exception:
                    mapping = {}

            # --- Handle packed mappings in file_mappings.json ---
            try:
                packed_index = _sb_read_packed_index(mod_path)
                for orig_rel, target_name in list(mapping.items()):
                    if str(orig_rel).startswith("packed::"):
                        packed_name = orig_rel.split("::", 1)[1]
                        if packed_name in packed_index:
                            tmp = _sb_extract_packed_to_temp(mod_path, packed_name)
                            if not tmp or not tmp.exists():
                                self.log(f"[surgical] packed source missing: {packed_name}")
                                return False

                            # NEW: Route to texture path if PNG-only mod
                            if is_texture_pack:
                                dst = dolphin_texture_path / (target_name or packed_name)
                                dst.parent.mkdir(parents=True, exist_ok=True)
                                rel_dst = dst.relative_to(dolphin_texture_path)
                                if dst.exists():
                                    if not self._backup_and_replace_dolphin_texture(dst, tmp, game_key, dolphin_texture_path):
                                        return False
                                else:
                                    shutil.copy2(tmp, dst)
                                    self.log(f"[surgical] created texture {dst} (from packed)")
                                touched.append(rel_dst.as_posix())
                            else:
                                # Normal game file path
                                dst = self._resolve_vanilla_target(vanilla, target_name or packed_name)
                                dst.parent.mkdir(parents=True, exist_ok=True)
                                rel_dst = dst.relative_to(vanilla)
                                if dst.exists():
                                    if not backup_and_replace_file_to_archive(dst, tmp, game_key, vanilla, archive, log_fn=self.log):
                                        return False
                                else:
                                    shutil.copy2(tmp, dst)
                                    self.log(f"[surgical] created {dst} (from packed)")
                                touched.append(rel_dst.as_posix())
                            del mapping[orig_rel]
            except Exception as e:
                self.log(f"[surgical] error processing packed mapping: {e}")
                return False

            # --- Walk mod files ---
            for dirpath, _, filenames in os.walk(mod_path, followlinks=True):
                rel_dir = Path(dirpath).relative_to(mod_path)

                # Skip non-game directories for non-texture-pack mods
                if not is_texture_pack and rel_dir.parts and rel_dir.parts[0] not in valid_game_dirs:
                    continue
                
                for fname in filenames:
                    if fname in ("packed_files.bin", "mod.ini", "config_schema.json",
                                 "config.json", "config_schema_files.json",
                                 "preview.png", "file_mappings.json", "mod_data.json"):
                        continue
                    
                    src = Path(dirpath) / fname
                    rel = (rel_dir / fname).as_posix() if str(rel_dir) != "." else fname

                    # NEW: Handle texture pack files
                    if is_texture_pack:
                        # For texture packs, copy PNGs directly to dolphin texture path
                        if src.suffix.lower() != ".png":
                            continue
                        
                        target_name = mapping.get(rel, fname)
                        dst = dolphin_texture_path / target_name
                        dst.parent.mkdir(parents=True, exist_ok=True)

                        try:
                            rel_dst = dst.relative_to(dolphin_texture_path)
                        except ValueError:
                            rel_dst = Path(target_name)

                        if dst.exists():
                            if not self._backup_and_replace_dolphin_texture(dst, src, game_key, dolphin_texture_path):
                                return False
                        else:
                            # Use copy or move based on texture pack mode
                            if texture_pack_mode == "move":
                                shutil.move(str(src), str(dst))
                                self.log(f"[surgical] moved texture {src} -> {dst}")
                            else:
                                shutil.copy2(src, dst)
                                self.log(f"[surgical] copied texture {src} -> {dst}")
                        touched.append(rel_dst.as_posix())
                    else:
                        # Normal game file handling
                        target_name = mapping.get(rel)
                        if target_name:
                            dst = self._resolve_vanilla_target(vanilla, target_name)
                        else:
                            candidate = vanilla / rel
                            if not candidate.exists():
                                continue
                            dst = candidate

                        dst.parent.mkdir(parents=True, exist_ok=True)
                        rel_dst = dst.relative_to(vanilla)
                        if dst.exists():
                            if not backup_and_replace_file_to_archive(dst, src, game_key, vanilla, archive, log_fn=self.log):
                                return False
                        else:
                            shutil.copy2(src, dst)
                            self.log(f"[surgical] created {dst}")
                        touched.append(rel_dst.as_posix())

            # --- Attachment handling (apply only for Enabled choices) ---
            for keyname, chosen in (cfg or {}).items():
                if not isinstance(chosen, str) or not chosen:
                    continue
                if chosen.strip().lower() != "enabled":
                    continue
                
                entry = attachments.get(keyname, {}).get(chosen, {})
                if not entry:
                    continue
                
                for fm in entry.get("files", []):
                    src_ref = fm.get("src")
                    dst_name = fm.get("dst")
                    if not dst_name:
                        continue
                    
                    if isinstance(src_ref, str) and src_ref.startswith("packed::"):
                        packed_name = src_ref.split("::", 1)[1]
                        tmp = _sb_extract_packed_to_temp(mod_path, packed_name)
                        if not tmp or not tmp.exists():
                            self.log(f"[attach] packed source missing: {packed_name}")
                            continue
                        src_path = tmp
                    else:
                        src_path = (mod_path / src_ref).resolve()
                        if not src_path.exists():
                            self.log(f"[attach] attached source missing: {src_path}")
                            continue
                        
                    # NEW: Route to texture path if PNG and texture pack mod
                    if is_texture_pack and src_path.suffix.lower() == ".png":
                        dest_path = dolphin_texture_path / dst_name
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            rel_dst = dest_path.relative_to(dolphin_texture_path)
                        except ValueError:
                            rel_dst = Path(dst_name)
                        if dest_path.exists():
                            if not self._backup_and_replace_dolphin_texture(dest_path, src_path, game_key, dolphin_texture_path):
                                return False
                        else:
                            # Use copy or move based on texture pack mode
                            if texture_pack_mode == "move":
                                shutil.move(str(src_path), str(dest_path))
                                self.log(f"[attach] moved texture {src_path} -> {dest_path}")
                            else:
                                shutil.copy2(src_path, dest_path)
                                self.log(f"[attach] copied texture {src_path} -> {dest_path}")
                        touched.append(rel_dst.as_posix())
                    else:
                        # Normal game file
                        dest_path = self._resolve_vanilla_target(vanilla, dst_name)
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        rel_dst = dest_path.relative_to(vanilla)
                        if dest_path.exists():
                            if not backup_and_replace_file_to_archive(dest_path, src_path, game_key, vanilla, archive, log_fn=self.log):
                                return False
                        else:
                            shutil.copy2(src_path, dest_path)
                            self.log(f"[attach] created {dest_path}")
                        touched.append(rel_dst.as_posix())

            # --- Write unified mod_data.json snapshot with APPLIED FILES ---
            unique_touched = sorted(set(touched))
            if unique_touched:
                try:
                    write_mod_data_snapshot(mod_path,
                                            schema=schema,
                                            attachments=attachments,
                                            config_values=cfg,
                                            applied_files=unique_touched)
                    self.log(f"[applied] Writing {len(unique_touched)} touched files for {mod_name}: {unique_touched}")
                except Exception as e:
                    self.log(f"[warn] could not write mod_data.json snapshot: {e}")

        # Finalize archive once: delete if empty; write if non-empty
        save_archive(game_key, archive)
        self.log("[surgical] finished applying mods")
        return True

    # --- Tree interactions ---
    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        try:
            m = item.data(0, Qt.UserRole)
            if not m:
                return
            # Mark mod list as having unsaved changes
            self.unsaved_modlist = True
        except Exception as e:
            self.log(f"[error] on_item_changed: {e}")

    def on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)

        # Styling: hover "shine" that matches your dark theme
        menu.setStyleSheet("""
            QMenu {
                background-color: #1A1A1A;
                color: #E6E6E6;
                border: 1px solid #333;
                padding: 6px;
            }
            QMenu::item {
                padding: 6px 18px;
            }
            QMenu::item:selected {
                background-color: rgba(255,255,255,0.08);
                color: #FFFFFF;
            }
        """)

        # Small event filter to set pointing-hand only when hovering actions
        class _MenuHoverCursorFilter(QObject):
            def eventFilter(self, obj, ev):
                try:
                    if ev.type() in (QEvent.MouseMove, QEvent.HoverMove):
                        w = obj.childAt(ev.pos())
                        if w is not None:
                            try:
                                w.setCursor(Qt.PointingHandCursor)
                            except Exception:
                                obj.setCursor(Qt.PointingHandCursor)
                        else:
                            try:
                                obj.setCursor(Qt.PointingHandCursor)
                            except Exception:
                                pass
                    elif ev.type() in (QEvent.Leave, QEvent.Hide):
                        try:
                            obj.unsetCursor()
                        except Exception:
                            pass
                except Exception:
                    pass
                return super().eventFilter(obj, ev)

        # Build menu actions
        if item:
            m = item.data(0, Qt.UserRole) or {}
            mod_path = Path(m.get("path", ""))
            is_texture_pack = (_mod_is_png_only(mod_path) or self._is_texture_pack_via_applied_files(mod_path)) if mod_path.exists() else False
            
            # Different menu for texture packs vs regular mods
            if is_texture_pack:
                # Redefine Dolphin icon for this context with size control
                dolphin_icon_path = UI_DIR / "Dolphin Icon.png"
                
                if dolphin_icon_path.exists():
                    # Load the original pixmap
                    original_pixmap = QPixmap(str(dolphin_icon_path))
                    
                    # Create a larger pixmap
                    large_pixmap = original_pixmap.scaled(
                        100, 100,  # Adjust size as needed
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    
                    # Create icon from the large pixmap
                    large_icon = QIcon(large_pixmap)
                    
                    # Globally set icon size for menus (if needed)
                    QApplication.instance().setStyleSheet("""
                        QMenu::icon {
                            min-width: 50px;
                            min-height: 50px;
                        }
                    """)
                    
                    # Texture pack specific option first
                    act_texture_config = menu.addAction(large_icon, " Dolphin Texture Pack Config...")
                else:
                    # Fallback if icon doesn't exist
                    act_texture_config = menu.addAction(" Dolphin Texture Pack Config...")
                
                menu.addSeparator()
                # Keep all the standard options
                act_config = menu.addAction("Configure Mod…")
                act_edit   = menu.addAction("Edit Mod…")
                act_open   = menu.addAction("Open Folder")
                act_update = menu.addAction("Check for Update")
                act_author = None
                if m.get("author_url"):
                    act_author = menu.addAction("Go to Author Page")
                menu.addSeparator()
                act_delete = menu.addAction("Delete…")
                
                # Install the hover filter and exec the menu
                f = _MenuHoverCursorFilter(menu)
                menu.installEventFilter(f)
                chosen = menu.exec_(self.tree.mapToGlobal(pos))
                menu.removeEventFilter(f)
                
                # Action handling - texture pack specific first
                if chosen == act_texture_config:
                    self.on_texture_pack_config(item)
                elif chosen == act_config:
                    self.on_configure_mod(item)
                elif chosen == act_edit:
                    self.on_edit_mod(item)
                elif chosen == act_open:
                    try:
                        os.startfile(str(m["path"]))
                    except Exception as e:
                        self.log(f"[error] open folder: {e}")
                elif chosen == act_update:
                    self.on_check_update(item)
                elif act_author and chosen == act_author:
                    try:
                        webbrowser.open(m.get("author_url"))
                    except Exception:
                        try:
                            os.startfile(m.get("author_url"))  # type: ignore
                        except Exception:
                            pass
                elif chosen == act_delete:
                    self.on_delete_mod(item)
            else:
                # Regular mod menu (unchanged)
                act_config = menu.addAction("Configure Mod…")
                act_edit   = menu.addAction("Edit Mod…")
                act_open   = menu.addAction("Open Folder")
                act_update = menu.addAction("Check for Update")
                act_author = None
                if m.get("author_url"):
                    act_author = menu.addAction("Go to Author Page")
                menu.addSeparator()
                act_delete = menu.addAction("Delete…")

                # Install the hover filter and exec the menu
                f = _MenuHoverCursorFilter(menu)
                menu.installEventFilter(f)
                chosen = menu.exec_(self.tree.mapToGlobal(pos))
                menu.removeEventFilter(f)

                # Action handling
                if chosen == act_config:
                    self.on_configure_mod(item)
                elif chosen == act_edit:
                    self.on_edit_mod(item)
                elif chosen == act_open:
                    try:
                        os.startfile(str(m["path"]))
                    except Exception as e:
                        self.log(f"[error] open folder: {e}")
                elif chosen == act_update:
                    self.on_check_update(item)
                elif act_author and chosen == act_author:
                    try:
                        webbrowser.open(m.get("author_url"))
                    except Exception:
                        try:
                            os.startfile(m.get("author_url"))  # type: ignore
                        except Exception:
                            pass
                elif chosen == act_delete:
                    self.on_delete_mod(item)
        else:
            # No item: show disabled placeholder with pointing-hand and shine
            placeholder = menu.addAction("(no mod selected)")
            placeholder.setEnabled(False)
            f = _MenuHoverCursorFilter(menu)
            menu.installEventFilter(f)
            menu.exec_(self.tree.mapToGlobal(pos))
            menu.removeEventFilter(f)

    def on_texture_pack_config(self, item):
            try:
                m = item.data(0, Qt.UserRole)
                dlg = DolphinTexturePackConfigDialog(self, Path(m["path"]))
                self._handify_buttons(dlg)
                dlg.exec_()
            except Exception as e:
                self.log(f"[error] texture pack config: {e}")

    def on_configure_mod(self, item):
        try:
            m = item.data(0, Qt.UserRole)
            dlg = ConfigureModDialog(self, Path(m["path"]))
            # Handify dialog buttons before showing
            self._handify_buttons(dlg)
            dlg.exec_()
        except Exception as e:
            self.log(f"[error] configure mod: {e}")

    def on_edit_mod(self, item):
        try:
            m = item.data(0, Qt.UserRole)
            dlg = ModEditDialog(self, Path(m["path"]))
            # Handify dialog buttons
            self._handify_buttons(dlg)
            if dlg.exec_() == QDialog.Accepted:
                vals = dlg.values()
                cp, ini, _ = ensure_mod_ini(Path(m["path"]))
                for k, v in vals.items():
                    cp.set(INI_SECTION, k, v)
                with ini.open("w", encoding="utf-8") as f:
                    cp.write(f)
                self.load_game(self.current_game)
        except Exception as e:
            self.log(f"[error] edit mod: {e}")

    def on_dolphin_texture_packs(self, item):
        try:
            m = item.data(0, Qt.UserRole)
            game_key = GAME_KEYS[self.current_game]
            dlg = DolphinTexturePackDialog(self, Path(m["path"]), game_key)
            self._handify_buttons(dlg)
            dlg.exec_()
        except Exception as e:
            self.log(f"[error] dolphin texture packs: {e}")

    def on_check_update(self, item):
        progress = UpdateProgressDialog(self)

        def run():
            try:
                m = item.data(0, Qt.UserRole)
                url = m.get("update") or ""
                if not url:
                    progress.accept()
                    QMessageBox.information(self, "No update URL", "This mod does not have an update URL.")
                    return

                latest_ver, latest_title = get_latest_version_and_title(url)
                if not latest_ver:
                    progress.accept()
                    QMessageBox.information(self, "No version found", "Could not detect a version on the update page.")
                    return

                current_ver = m.get("version", "0.0.0")
                cmp = compare_versions(current_ver, latest_ver)

                progress.accept()

                if cmp < 0:
                    dlg = UpdateCheckDialog(
                        [{"name": m.get("name", "(mod)"),
                          "current": current_ver,
                          "latest": latest_ver,
                          "url": url}],
                        self
                    )
                    handify_buttons_in(dlg)
                    dlg.exec_()
                elif cmp == 0:
                    QMessageBox.information(self, "Up to date", f"You already have the latest version ({current_ver}).")
                else:
                    QMessageBox.information(self, "Ahead", f"Your version ({current_ver}) is newer than the one online ({latest_ver}).")

            except Exception as e:
                progress.accept()
                self.log(f"[error] check update: {e}")

        QTimer.singleShot(50, run)
        progress.exec_()

    def on_delete_mod(self, item):
        try:
            m = item.data(0, Qt.UserRole)
            dlg = ConfirmDeleteDialog(self, m['name'])
            if dlg.exec_() != QDialog.Accepted:
                return
            shutil.rmtree(m["path"], ignore_errors=True)
            self.load_game(self.current_game)
            self.log(f"[delete] removed {m['name']}")
        except Exception as e:
            self.log(f"[error] delete mod: {e}")

    # --- Save / Play ---
    def on_save(self):
        key = GAME_KEYS[self.current_game]
        # Guard: settings must be valid for this game before saving/applying
        if not settings_ready_for_game(self.settings, key):
            QMessageBox.warning(self, "Configure your settings!", "You must configure your settings before launching this game.")
            return
        
        s = load_settings()

        # Previously committed enabled mods
        prev_enabled = set(s["games"].get(key, {}).get("enabled_mods", []))

        # Currently checked mods in the UI
        now_enabled = set()
        enabled_mods_list = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                m = it.data(0, Qt.UserRole)
                if m:
                    now_enabled.add(str(Path(m["path"]).resolve()))
                    enabled_mods_list.append(m)
        
        # ⚠️ NEW: Check for file conflicts
        conflicts = self._detect_file_conflicts(enabled_mods_list)
        if conflicts:
            dlg = ConflictWarningDialog(self, conflicts)
            self._handify_buttons(dlg)
            dlg.exec_()

            if dlg.clicked_button != dlg.continue_btn:
                # User cancelled
                return
            # User chose to continue - conflicts will be handled by first-mod-wins logic

        # NEW: Check texture pack modes before applying
        gconf = self.settings["games"].get(key, {})
        dolphin_texture_path_str = gconf.get("dolphin_texture_path", "")

        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                m = it.data(0, Qt.UserRole)
                if m:
                    mod_path = Path(m["path"])
                    is_texture_pack = _mod_is_png_only(mod_path) or self._is_texture_pack_via_applied_files(mod_path)

                    if is_texture_pack:
                        # Check if texture path is configured
                        if not dolphin_texture_path_str or not dolphin_texture_path_str.strip():
                            QMessageBox.warning(
                                self,
                                "Dolphin Texture Path Required",
                                f"The mod '{m.get('name', mod_path.name)}' is a texture pack.\n\n"
                                "Please configure the Dolphin Custom Texture Path in Settings:\n"
                                "Settings > Dolphin Texture Packs"
                            )
                            return

                        # Check if texture pack mode is configured
                        try:
                            cp, _, _ = ensure_mod_ini(mod_path)
                            texture_mode = cp.get(INI_SECTION, "TexturePackMode", fallback="")

                            if not texture_mode or texture_mode.strip() == "":
                                dlg = TexturePackModeRequiredDialog(self)
                                self._handify_buttons(dlg)
                                dlg.exec_()

                                if dlg.clicked_button == dlg.settings_btn:
                                    # Open the texture pack config dialog
                                    config_dlg = DolphinTexturePackConfigDialog(self, mod_path)
                                    self._handify_buttons(config_dlg)
                                    config_dlg.exec_()

                                # Abort save process regardless
                                return
                        except Exception as e:
                            self.log(f"[texture_check] Error checking texture mode: {e}")

        # Restore files for mods that were enabled before but are now disabled
        gconf = self.settings["games"].get(key, {})
        vanilla = Path(gconf.get("vanilla") or "")
        dolphin_texture_path = Path(gconf.get("dolphin_texture_path") or "")
        
        if not vanilla.exists():
            QMessageBox.warning(self, "Missing Game Files", "Set Game Files (vanilla) in Settings first.")
            return

        to_restore = prev_enabled - now_enabled
        for pstr in to_restore:
            mod_path = Path(pstr)
            
            # Check if it's a texture pack (including via applied files)
            is_texture_pack = _mod_is_png_only(mod_path) or self._is_texture_pack_via_applied_files(mod_path)
            
            try:
                if is_texture_pack:
                    # Restore/delete textures using dolphin path
                    if dolphin_texture_path and dolphin_texture_path.exists():
                        restored = self._restore_dolphin_textures(mod_path, key, dolphin_texture_path)
                        if restored:
                            self.log(f"[restore] Processed {len(restored)} texture(s) for {mod_path.name}")
                else:
                    # Normal game file restore
                    restored = restore_files_for_mod(mod_path, key, vanilla, log_fn=self.log)
                    if restored:
                        self.log(f"[restore] Restored {len(restored)} file(s) for {mod_path.name}")
            except Exception as e:
                self.log(f"[restore] failed for {pstr}: {e}")

        # Apply surgical changes for currently enabled mods
        if self.apply_mods_surgical():
            s["games"].setdefault(key, {})
            s["games"][key]["enabled_mods"] = list(now_enabled)
            save_settings(s)
            self.settings = s

            self._show_saved_label()
            self._reorder_enabled_mods()

            self.unsaved_modlist = False
            self.unsaved_schema = False
            self.unsaved_config = False
            self.unsaved_settings = False

    def on_save_and_play(self):
        key = GAME_KEYS[self.current_game]
        # Guard: settings must be valid for this game before saving/applying/launch
        if not settings_ready_for_game(self.settings, key):
            QMessageBox.warning(self, "Configure your settings!", "You must configure your settings before launching this game.")
            return

        s = load_settings()

        prev_enabled = set(s["games"].get(key, {}).get("enabled_mods", []))

        now_enabled = set()
        enabled_mods_list =[]
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                m = it.data(0, Qt.UserRole)
                if m:
                    now_enabled.add(str(Path(m["path"]).resolve()))
                    enabled_mods_list.append(m)

        # ⚠️ NEW: Check for file conflicts
        conflicts = self._detect_file_conflicts(enabled_mods_list)
        if conflicts:
            dlg = ConflictWarningDialog(self, conflicts)
            self._handify_buttons(dlg)
            dlg.exec_()

            if dlg.clicked_button != dlg.continue_btn:
                # User cancelled
                return
            # User chose to continue - conflicts will be handled by first-mod-wins logic

        # NEW: Check texture pack modes before applying
        gconf = self.settings["games"].get(key, {})
        dolphin_texture_path_str = gconf.get("dolphin_texture_path", "")

        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                m = it.data(0, Qt.UserRole)
                if m:
                    mod_path = Path(m["path"])
                    is_texture_pack = _mod_is_png_only(mod_path) or self._is_texture_pack_via_applied_files(mod_path)

                    if is_texture_pack:
                        # Check if texture path is configured
                        if not dolphin_texture_path_str or not dolphin_texture_path_str.strip():
                            QMessageBox.warning(
                                self,
                                "Dolphin Texture Path Required",
                                f"The mod '{m.get('name', mod_path.name)}' is a texture pack.\n\n"
                                "Please configure the Dolphin Custom Texture Path in Settings:\n"
                                "Settings > Dolphin Texture Packs"
                            )
                            return

                        # Check if texture pack mode is configured
                        try:
                            cp, _, _ = ensure_mod_ini(mod_path)
                            texture_mode = cp.get(INI_SECTION, "TexturePackMode", fallback="")

                            if not texture_mode or texture_mode.strip() == "":
                                dlg = TexturePackModeRequiredDialog(self)
                                self._handify_buttons(dlg)
                                dlg.exec_()

                                if dlg.clicked_button == dlg.settings_btn:
                                    # Open the texture pack config dialog
                                    config_dlg = DolphinTexturePackConfigDialog(self, mod_path)
                                    self._handify_buttons(config_dlg)
                                    config_dlg.exec_()

                                # Abort save process regardless
                                return
                        except Exception as e:
                            self.log(f"[texture_check] Error checking texture mode: {e}")

        # Restore files for mods that were enabled before but are now disabled
        gconf = self.settings["games"].get(key, {})
        vanilla = Path(gconf.get("vanilla") or "")
        dolphin_texture_path = Path(gconf.get("dolphin_texture_path") or "")
        
        if not vanilla.exists():
            QMessageBox.warning(self, "Missing Game Files", "Set Game Files (vanilla) in Settings first.")
            return

        to_restore = prev_enabled - now_enabled
        for pstr in to_restore:
            mod_path = Path(pstr)
            
            # Check if it's a texture pack (including via applied files)
            is_texture_pack = _mod_is_png_only(mod_path) or self._is_texture_pack_via_applied_files(mod_path)
            
            try:
                if is_texture_pack:
                    # Restore/delete textures using dolphin path
                    if dolphin_texture_path and dolphin_texture_path.exists():
                        restored = self._restore_dolphin_textures(mod_path, key, dolphin_texture_path)
                        if restored:
                            self.log(f"[restore] Processed {len(restored)} texture(s) for {mod_path.name}")
                else:
                    # Normal game file restore
                    restored = restore_files_for_mod(mod_path, key, vanilla, log_fn=self.log)
                    if restored:
                        self.log(f"[restore] Restored {len(restored)} file(s) for {mod_path.name}")
            except Exception as e:
                self.log(f"[restore] failed for {pstr}: {e}")

        if self.apply_mods_surgical():
            s["games"].setdefault(key, {})
            s["games"][key]["enabled_mods"] = list(now_enabled)
            save_settings(s)
            self.settings = s

            self._show_saved_label()
            self._reorder_enabled_mods()
            self.launch_game()

            self.unsaved_modlist = False
            self.unsaved_schema = False
            self.unsaved_config = False
            self.unsaved_settings = False

    def _show_saved_label(self):
        self.saved_lbl.move(self.width() - 200, self.height() - 70)
        self.saved_lbl.show()
        t = QTimer(self)
        t.setSingleShot(True)
        t.setInterval(2000)
        t.timeout.connect(lambda: self.saved_lbl.setVisible(False))
        t.start()

    def launch_game(self):
        key = GAME_KEYS[self.current_game]
        dolphin = Path(self.settings["games"][key]["dolphin_shortcut"] or "")
        if not dolphin.exists():
            QMessageBox.warning(self, "Missing Dolphin", "Set Dolphin shortcut in Settings first.")
            return

        try:
            # Snapshot PIDs of any Dolphin instances before launch
            before_pids = self._list_dolphin_pids()

            self._current_game_key = key
            # Launch Dolphin via the saved shortcut/exe
            self._dolphin_proc = subprocess.Popen([str(dolphin)], shell=True)

            # Detect the newly launched Dolphin PID(s) — up to ~5 seconds
            launched_pids = set()
            for _ in range(10):
                time.sleep(0.5)
                after_pids = self._list_dolphin_pids()
                diff = after_pids - before_pids
                if diff:
                    launched_pids = diff
                    break

            # Store only the Dolphin processes we launched (could be one or more, depending on shortcut behavior)
            self._launched_dolphin_pids = launched_pids

            # Start monitor thread (non-blocking)
            self._monitor = GameWindowMonitor(self, key)
            self._monitor.game_started.connect(lambda: self._set_game_status_text(key, True))
            self._monitor.game_closed.connect(lambda: self._on_game_closed(key))
            self._monitor.start()

            # Show status immediately
            self._set_game_status_text(key, True)
        except Exception as e:
            QMessageBox.warning(self, "Launch Error", f"Could not start Dolphin:\n{e}")

#------------------------------
    # Dolphin Helpers
#------------------------------
    def _find_window_titles(self):
        """Return a list of all visible top-level window titles."""
        import ctypes
        from ctypes import wintypes

        titles = []
        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        IsWindowVisible = user32.IsWindowVisible
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW

        def _iter(hwnd, lparam):
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            if title:
                titles.append(title)
            return True

        EnumWindows(EnumWindowsProc(_iter), 0)
        return titles

    def _game_window_present(self):
        """Check if the specific game window is open."""
        titles = self._find_window_titles()
        if self._current_game_key == "SecretRings":
            return any("Secret Rings" in t for t in titles)
        elif self._current_game_key == "BlackKnight":
            return any("Black Knight" in t for t in titles)
        return False

    def _close_dolphin(self):
        """Force-close Dolphin."""
        try:
            import subprocess
            subprocess.Popen(["taskkill", "/IM", "Dolphin.exe", "/F"], shell=False)
        except Exception:
            pass

    def _cleanup_dolphin_state(self):
        """Clear status label and reset state."""
        self._current_game_key = None
        self.game_status_label.setText("")

    def _game_window_present_for_key(self, game_key):
        titles = self._find_window_titles()
        if game_key == "SecretRings":
            return any("Secret Rings" in t for t in titles)
        elif game_key == "BlackKnight":
            return any("Black Knight" in t for t in titles)
        return False

    def _set_game_status_text(self, game_key, running):
        if running:
            pretty = "Sonic and the Secret Rings" if game_key == "SecretRings" else "Sonic and the Black Knight"
            self.game_status_label.setText(f"[{pretty} is running]")
        else:
            self.game_status_label.setText("")

    def _on_game_closed(self, key):
        self._set_game_status_text(key, False)

        if self.settings.get("quit_dolphin_with_game", True):
            # Close only the Dolphin processes we launched (leave unrelated instances alone)
            pids = getattr(self, "_launched_dolphin_pids", set()) or set()
            for pid in list(pids):
                try:
                    subprocess.Popen(
                        ["taskkill", "/PID", str(pid), "/F"],
                        shell=False,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                except Exception:
                    pass
            # Clear tracked list after closing
            self._launched_dolphin_pids = set()

        if hasattr(self, "_monitor") and self._monitor:
            self._monitor.stop()
            self._monitor = None

    def _backup_and_replace_dolphin_texture(self, original: Path, mod_file: Path, game_key: str, texture_root: Path) -> bool:
        """
        Backup and replace a Dolphin custom texture file.
        Uses the same archive system as game files but with texture-specific keys.
        """
        archive = load_archive(game_key)

        try:
            rel_key = f"texture::{original.relative_to(texture_root).as_posix()}"
        except Exception:
            rel_key = f"texture::{original.name}"

        if rel_key not in archive and original.exists():
            try:
                archive[rel_key] = original.read_bytes()
                self.log(f"[backup] stored texture {rel_key} ({len(archive[rel_key])} bytes)")
            except Exception as e:
                self.log(f"[error] backup texture read failed {original}: {e}")
                return False
        elif rel_key in archive:
            self.log(f"[backup] texture {rel_key} already backed up ({len(archive[rel_key])} bytes)")
        else:
            self.log(f"[backup] WARNING: texture {original} does not exist, cannot backup!")

        try:
            shutil.copy2(mod_file, original)
            self.log(f"[replace] texture {mod_file} -> {original}")
            save_archive(game_key, archive)
            return True
        except Exception as e:
            self.log(f"[error] copy texture failed {mod_file} -> {original}: {e}")
            return False

    def _restore_dolphin_textures(self, mod_path: Path, game_key: str, texture_root: Path) -> list:
        """
        Restore/remove Dolphin textures for a mod.
        For texture packs: moves files back (move mode) or deletes them (copy mode).
        Does NOT use backup archive for texture packs.
        """
        data_file = mod_path / "mod_data.json"
        if not data_file.exists():
            self.log(f"[restore] No mod_data.json for {mod_path.name}, nothing to restore")
            return []
    
        try:
            data = json.loads(data_file.read_text(encoding="utf-8"))
        except Exception as e:
            self.log(f"[restore] Could not read mod_data.json: {e}")
            return []
    
        applied = data.get("APPLIED FILES", [])
        if not applied:
            self.log(f"[restore] No applied textures recorded for {mod_path.name}")
            return []
    
        # Check if this is move mode
        try:
            cp, _, _ = ensure_mod_ini(mod_path)
            texture_pack_mode = cp.get(INI_SECTION, "TexturePackMode", fallback="copy")
        except Exception:
            texture_pack_mode = "copy"
    
        self.log(f"[restore] Restoring texture pack in '{texture_pack_mode}' mode")
    
        deleted = []
        moved_back = []
        
        for rel in applied:
            # The texture file in Dolphin's path
            dst = texture_root / rel
            
            if texture_pack_mode == "move":
                # Move it back to mod folder
                try:
                    if dst.exists():
                        mod_dest = mod_path / Path(rel).name
                        shutil.move(str(dst), str(mod_dest))
                        moved_back.append(rel)
                        self.log(f"[restore] Moved texture {Path(rel).name} back to mod folder")
                    else:
                        self.log(f"[restore] Texture {rel} not found in Dolphin path (already moved?)")
                except Exception as e:
                    self.log(f"[restore] Failed to move back texture {rel}: {e}")
            else:
                # Copy mode → just delete from Dolphin path
                try:
                    if dst.exists():
                        dst.unlink()
                        deleted.append(rel)
                        self.log(f"[restore] Deleted texture {Path(rel).name} from Dolphin path")
                    else:
                        self.log(f"[restore] Texture {rel} already gone from Dolphin path")
                except Exception as e:
                    self.log(f"[restore] Failed to delete texture {rel}: {e}")
    
        # Clear APPLIED FILES
        try:
            data["APPLIED FILES"] = []
            data_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            self.log(f"[restore] Failed to update mod_data.json: {e}")
    
        if deleted:
            self.log(f"[restore] Deleted {len(deleted)} texture(s) from Dolphin path")
        if moved_back:
            self.log(f"[restore] Moved {len(moved_back)} texture(s) back to mod folder")
    
        return deleted + moved_back

    def _restore_moved_textures_to_mod(self, mod_path: Path, game_key: str, texture_root: Path):
        """Move textures back to mod folder from Dolphin texture path when disabling (move mode only)"""
        try:
            data_file = mod_path / "mod_data.json"
            if not data_file.exists():
                self.log(f"[restore_moved] No mod_data.json for {mod_path.name}")
                return

            data = json.loads(data_file.read_text(encoding="utf-8"))
            applied = data.get("APPLIED FILES", [])

            if not applied:
                self.log(f"[restore_moved] No applied files to restore for {mod_path.name}")
                return

            moved_count = 0
            for rel in applied:
                # The texture is currently in Dolphin's texture path
                dolphin_texture_file = texture_root / rel

                # We want to move it back to the mod folder
                mod_dest = mod_path / Path(rel).name  # Just the filename, not the full path

                if dolphin_texture_file.exists() and dolphin_texture_file.suffix.lower() == ".png":
                    try:
                        # Move from Dolphin path back to mod folder (not copy!)
                        shutil.move(str(dolphin_texture_file), str(mod_dest))
                        moved_count += 1
                        self.log(f"[restore_moved] Moved {dolphin_texture_file.name} from Dolphin path back to mod folder")
                    except Exception as e:
                        self.log(f"[restore_moved] Failed to move {dolphin_texture_file.name}: {e}")
                else:
                    self.log(f"[restore_moved] Texture not found in Dolphin path: {dolphin_texture_file}")

            if moved_count > 0:
                self.log(f"[restore_moved] Moved {moved_count} texture(s) back to mod folder from Dolphin path")
            else:
                self.log(f"[restore_moved] No textures were moved back (either missing or already restored)")

        except Exception as e:
            self.log(f"[restore_moved] Error: {e}")

    def _list_dolphin_pids(self):
        """
        Return a set of PIDs for running Dolphin.exe processes using tasklist.
        Avoids external deps; works on Windows.
        """
        try:
            # tasklist output example header: "Image Name                     PID ... "
            out = subprocess.check_output(
                ["tasklist", "/FI", "imagename eq Dolphin.exe"],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            lines = out.decode("utf-8", errors="ignore").splitlines()
            pids = set()
            for ln in lines:
                # Rough parse: columns are fixed-width; PID column follows image name
                if "Dolphin.exe" in ln:
                    parts = ln.split()
                    # Find the first numeric token as PID
                    for tok in parts:
                        if tok.isdigit():
                            pids.add(int(tok))
                            break
            return pids
        except Exception:
            return set()

    # --- Showing Help Setup ---
    def show_help_setup(self):
        """
        Opens the Help Setup dialog with hard-coded slides.
        Each slide is a (text, image_path) tuple.
        """
        slides = [
            (
                "Step 1: In Dolphin Emulator, Add a path directory to your Storybook ROM.",
                resource_path("UI/help/Step1.gif")
            ),
            (
                "Step 2: Make a new folder and extract your game files.",
                resource_path("UI/help/Step2.gif")
            ),
            (
                "Step 3: Now Add a path directory to the extracted game files.",
                resource_path("UI/help/Step3.gif")
            ),
            (
                "Step 4: Create a Dolphin shortcut from the game files version of the game.",
                resource_path("UI/help/Step4.gif")
            ),
            (
                "Step 5: Set your Game Files and Shortcut Accordingly",
                resource_path("UI/help/Step5.gif")
            ),
            (
                "End: You're Done! You can now Use the Mod Manager",
                resource_path("UI/help/Step6.jpg")
            ),
        ]

        dlg = HelpSetupDialog(self, slides=slides)
        dlg.exec_()

    # --- Add mod ---
    def on_add_mod(self):
        mods_dir = Path(self.settings["games"][GAME_KEYS[self.current_game]]["mods"] or "")
        if not mods_dir.exists():
            QMessageBox.warning(self, "Missing Mods Folder", "Set Mods Folder in Settings first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select Mod Folder", str(Path.home()))
        if not folder:
            return
        try:
            dest = mods_dir / Path(folder).name
            if dest.exists():
                QMessageBox.warning(self, "Exists", "A mod with that name already exists.")
                return
            shutil.copytree(folder, dest)

            # immediately create mod.ini with defaults
            ensure_mod_ini(dest)

            self.load_game(self.current_game)
            self.log(f"[add] added mod {dest.name}")
        except Exception as e:
            self.log(f"[error] add mod: {e}")

    # --- Close Window Unsaved Changes ---
    def closeEvent(self, event):
        # Collect unsaved windows
        unsaved = []
        if self.unsaved_modlist:
            unsaved.append("Mod List")
        if self.unsaved_schema:
            unsaved.append("Set Configure Mod Menu")
        if self.unsaved_config:
            unsaved.append("Config Menu")
        if self.unsaved_settings:
            unsaved.append("Settings")

        if not unsaved:
            event.accept()
            return

        dlg = UnsavedChangesDialog(unsaved, self)
        dlg.exec_()

        if dlg.clicked_button == dlg.save_quit_btn:
            self.on_save()
            event.accept()
        elif dlg.clicked_button == dlg.quit_btn:
            event.accept()
        else:
            # "Close" → dismiss prompt, do not exit
            event.ignore()

    # --- Settings ---
    def on_settings(self):
        dlg = SettingsDialog(self)
        # Handify dialog buttons before showing
        self._handify_buttons(dlg)
        dlg.exec_()
        self.settings = load_settings()
        self.apply_background_theme()
        self._update_game_icon()

# -----------------------
# Main entry point
# -----------------------
def main():
    app = QApplication(sys.argv)
    # Univeral Grey Scroll bar >:(
    UniversalStyle.apply(app)
    filter = TitleBarColorFilter()
    app.installEventFilter(filter)

    # Creates UI :D
    settings, first_run = ensure_settings()
    ui = StorybookUI(settings, first_run)
    ui.show()

    # If this is the first run, show the welcome + settings wizard
    if first_run:
        QTimer.singleShot(100, lambda: show_first_run_wizard(ui))

    # Run update check on startup if user enabled it
    try:
        
        s = load_settings()
        if s.get("check_updates_on_startup", False):
            # delay slightly so UI finishes initial paint
            QTimer.singleShot(500, ui.on_check_all_updates)
    except Exception:
        pass

    set_title_bar_color(ui, r=32, g=32, b=32)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
