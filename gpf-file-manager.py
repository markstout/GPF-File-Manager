# Get Productive Fast:  File Manager
# Version 1.7.1 (06-13-2026)
# Copyright 2025 Mark A. Stout
# Licensed under MIT License
# For more information see : https://sites.google.com/view/getproductivefast/file-manager
# last working on open with, it is not working.abs

# Variables near start
APP_NAME = "Get Productive Fast:  File Manager"
APP_COPYRIGHT = "Copyright 2025 Mark A. Stout"
APP_VERSION = "Version 1.7.1 (06-13-2026)"
APP_SHORT_NAME = "GPFFileManager"

import sys
import multiprocessing
import os
import json
import shutil
import subprocess
import uuid
import time
import traceback
import zipfile
import sqlite3
import csv
import ctypes
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
import stat
try:
    import winreg
except ImportError:
    pass

import urllib.request
import urllib.error

# --- Safe Delete Library ---
try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

# --- Watchdog Library (Real-time Monitoring) ---
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

# --- Metadata Libraries ---
try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    import mutagen
    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QSplitter, QTreeView, QListView, 
                             QToolBar, QLabel, QComboBox, 
                             QPushButton, QMenu, QLineEdit, QDockWidget, 
                             QListWidget, QAbstractItemView, QDialog, 
                             QDialogButtonBox, QFrame, QGridLayout, QMessageBox,
                             QStyle, QHeaderView, QCheckBox, QButtonGroup, QSizePolicy,
                             QListWidgetItem, QFormLayout, QScrollArea, QProgressDialog,
                             QStyledItemDelegate, QStyleOptionViewItem, QInputDialog,
                             QTreeWidget, QTreeWidgetItem, QFileIconProvider, QTextEdit, QTextBrowser, 
                             QFileDialog, QSpinBox, QStackedWidget, QStatusBar, QProgressBar,
                             QWidgetAction)

from PyQt6.QtCore import (Qt, QSize, QDir, QUrl, QMimeData, QSettings, 
                          QStandardPaths, QPoint, QFileInfo, qInstallMessageHandler,
                          QThread, pyqtSignal, QObject, QRunnable, QThreadPool, 
                          QPersistentModelIndex, QModelIndex, QTimer, QStorageInfo, QLockFile)

from PyQt6.QtGui import (QAction, QIcon, QDesktopServices, QDrag, QActionGroup, 
                         QColor, QPalette, QPixmap, QFileSystemModel, QImageReader, 
                         QKeySequence, QCursor, QPainter, QImage, QStandardItemModel, 
                         QStandardItem, QTextDocument, QFont, QFontMetrics)

# --- PDF Support ---
try:
    from PyQt6.QtPrintSupport import QPrinter
    HAS_PRINTER = True
except ImportError:
    HAS_PRINTER = False

# --- Windows Device Change Constants ---
WM_DEVICECHANGE = 0x0219
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004



# --- Field Definitions ---
FIELD_DEFINITIONS = {
    "General": [
        "Name", "Date Modified", "Type", "Size", "Date Created", 
        "Attributes", "Date Accessed", "Author", "Tags", "Title", "Comments", "Owner", "Permissions"
    ],
    "Images": [
        "Date Taken", "Dimensions", "Resolution", "Camera Model", 
        "F-Stop", "ISO Speed", "Focal Length", "Shutter Speed"
    ],
    "Music": [
        "Album", "Album Artist", "Artist", "Genre", "Year", 
        "Duration", "Track Number", "Bit Rate", "Contributing Artists", 
        "Composer", "Rating", "Lyrics", "Publisher"
    ]
}

# --- FIX: Resource Path for PyInstaller ---
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

ICON_PATH = get_resource_path("app_icon.ico")
# --------------------------------------------

# --- Helper: Debug Logging ---
def log_debug(msg):
    try:
        # [FIX] Write to AppData so any user can write, even if installed in Program Files
        app_data = os.getenv('APPDATA')
        if not app_data: return
        
        base_dir = os.path.join(app_data, "GPFFileManager")
        if not os.path.exists(base_dir): os.makedirs(base_dir, exist_ok=True)
        
        log_path = os.path.join(base_dir, "debug_crash.txt")
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S.%f')} - {msg}\n")
    except: pass

# --- Helper: Global Exception Handler ---
def exception_hook(exctype, value, traceback_obj):
    # Log to file
    traceback_str = ''.join(traceback.format_exception(exctype, value, traceback_obj))
    log_debug(f"CRITICAL UNHANDLED EXCEPTION:\n{traceback_str}")
    
    # Show Visual Alert
    # We need to ensure QApplication exists, though usually it does by the time this hits
    if QApplication.instance():
        try:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Critical Error")
            msg.setText("An unhandled error occurred.")
            msg.setInformativeText(f"{value}\n\nSee debug_crash.txt in your AppData folder for details.")
            msg.setDetailedText(traceback_str)
            msg.exec()
        except:
            # If even QMessageBox fails (e.g. OOM), just print to stderr
            sys.__excepthook__(exctype, value, traceback_obj)
    else:
        sys.__excepthook__(exctype, value, traceback_obj)

sys.excepthook = exception_hook

# --- Helper: Suppress JPEG Warnings ---
def qt_message_handler(mode, context, message):
    if "Corrupt JPEG" in message or "bad Huffman code" in message:
        return
qInstallMessageHandler(qt_message_handler)

# --- Helper: Metadata Loader ---
class MetadataLoader:
    _cache = {}

    @staticmethod
    def get_metadata(path):
        try:
            if not path or not os.path.exists(path):
                return {}
            
            if path in MetadataLoader._cache:
                return MetadataLoader._cache[path]

            data = {}
            ext = os.path.splitext(path)[1].lower()
            
            # --- Images (Pillow) ---
            if HAS_PILLOW and ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
                try:
                    with Image.open(path) as img:
                        data["Dimensions"] = f"{img.size[0]} x {img.size[1]}"
                        if 'dpi' in img.info:
                            data["Resolution"] = f"{int(img.info['dpi'][0])} dpi"
                        
                        exif = img._getexif()
                        if exif:
                            # Map Exif IDs to names
                            exif_data = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                            
                            data["Camera Model"] = exif_data.get("Model", "")
                            data["Date Taken"] = exif_data.get("DateTimeOriginal", "")
                            data["ISO Speed"] = str(exif_data.get("ISOSpeedRatings", ""))
                            
                            f_num = exif_data.get("FNumber")
                            if f_num: data["F-Stop"] = f"f/{f_num}"
                            
                            exp = exif_data.get("ExposureTime")
                            if exp: data["Shutter Speed"] = f"{exp} sec"
                            
                            foc = exif_data.get("FocalLength")
                            if foc: data["Focal Length"] = f"{foc} mm"
                            
                except Exception:
                    pass

            # --- Audio (Mutagen) ---
            elif HAS_MUTAGEN and ext in ['.mp3', '.flac', '.ogg', '.m4a']:
                try:
                    f = mutagen.File(path, easy=True)
                    if f:
                        data["Title"] = f.get("title", [""])[0]
                        data["Artist"] = f.get("artist", [""])[0]
                        data["Album"] = f.get("album", [""])[0]
                        data["Genre"] = f.get("genre", [""])[0]
                        data["Year"] = f.get("date", [""])[0]
                        data["Track Number"] = f.get("tracknumber", [""])[0]
                        data["Composer"] = f.get("composer", [""])[0]
                        data["Publisher"] = f.get("organization", [""])[0]
                    
                    # Specific Bitrate/Length for MP3
                    if ext == '.mp3':
                        try:
                            audio = MP3(path)
                            data["Duration"] = time.strftime('%M:%S', time.gmtime(audio.info.length))
                            data["Bit Rate"] = f"{int(audio.info.bitrate / 1000)} kbps"
                        except: pass
                        
                except Exception:
                    pass

            MetadataLoader._cache[path] = data
            return data
        except Exception:
            return {}

# --- Custom File System Model ---
class DetailedFileSystemModel(QFileSystemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.custom_columns = []
        self.root_path = ""

    def set_custom_columns(self, columns):
        self.custom_columns = [c for c in columns if c not in ["Name", "Size", "Type", "Date Modified"]]
        self.layoutChanged.emit()

    def columnCount(self, parent=QModelIndex()):
        # Base 4 columns + custom columns
        return 4 + len(self.custom_columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section < 4:
                return super().headerData(section, orientation, role)
            else:
                return self.custom_columns[section - 4]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        try:
            if index.column() < 4:
                return super().data(index, role)
            
            if role == Qt.ItemDataRole.DisplayRole:
                col_name = self.custom_columns[index.column() - 4]
                file_path = self.filePath(index.siblingAtColumn(0))
                
                # Handle Standard Extended Fields (Dates)
                try:
                    info = QFileInfo(file_path)
                    if col_name == "Date Created":
                        return info.birthTime().toString("yyyy-MM-dd HH:mm")
                    if col_name == "Date Accessed":
                        return info.lastRead().toString("yyyy-MM-dd HH:mm")
                    if col_name == "Owner":
                        return info.owner()
                    if col_name == "Permissions":
                        perms = []
                        p = info.permissions()
                        if p & QFileInfo.Permission.ReadUser: perms.append("R")
                        if p & QFileInfo.Permission.WriteUser: perms.append("W")
                        if p & QFileInfo.Permission.ExeUser: perms.append("X")
                        return "".join(perms)
                except Exception:
                    return "Restricted"

                # Handle Metadata (Images/Audio)
                try:
                    meta = MetadataLoader.get_metadata(file_path)
                    return meta.get(col_name, "")
                except Exception:
                    return ""
            
            return None
        except Exception:
            return None

# --- Helper: Create Windows Shortcut (No extra libs) ---
def create_windows_shortcut(target_path, shortcut_path):
    """Creates a .lnk file using PowerShell to avoid pywin32 dependency."""
    try:
        # PowerShell command to create shortcut
        target = os.path.abspath(target_path)
        link = os.path.abspath(shortcut_path)
        
        # Escape single quotes for PowerShell
        target = target.replace("'", "''")
        link = link.replace("'", "''")
        
        cmd = f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{link}');$s.TargetPath='{target}';$s.Save()"
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception as e:
        print(f"Shortcut creation failed: {e}")
        return False

# --- Helper: Get Associated Apps ---
# --- Helper: Get Associated Apps ---
def get_associated_apps(extension):
    """
    Retrieves a list of (display_name, executable_path) for a given extension
    by querying the Windows Registry (ProgIDs, OpenWithList, etc.).
    """
    log_debug(f"get_associated_apps called for: {extension}")
    apps = []
    seen_paths = set()
    
    if not extension: return []
    extension = extension.lower()
    
    # Helper to resolve a command string to a clean path
    def clean_command(cmd):
        if not cmd: return None
        try:
            # Split by arguments logic is tricky, usually the exe is quoted or first token
            if cmd.startswith('"'):
                end_quote = cmd.find('"', 1)
                if end_quote != -1:
                    return cmd[1:end_quote]
            
            parts = cmd.split(' ')
            if parts and os.path.exists(parts[0]):
                return parts[0]
                
            lower_cmd = cmd.lower()
            if ".exe" in lower_cmd:
                idx = lower_cmd.find(".exe")
                candidate = cmd[:idx+4]
                if candidate.startswith('"'): candidate = candidate[1:]
                return candidate
            return cmd
        except: return cmd

    # 1. Get ProgIDs from HKCR\.ext\OpenWithProgids
    prog_ids = []
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{extension}\\OpenWithProgids") as key:
            i = 0
            while True:
                try:
                    name, _, _ = winreg.EnumValue(key)
                    if name: prog_ids.append(name)
                    i += 1
                except OSError: break
    except Exception as e:
        log_debug(f"Error reading OpenWithProgids: {e}")
    
    # Also check user choice ProgID
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\{extension}\\UserChoice") as key:
             prog_id, _ = winreg.QueryValueEx(key, "ProgId")
             if prog_id and prog_id not in prog_ids: prog_ids.append(prog_id)
    except Exception as e:
        log_debug(f"Error reading UserChoice: {e}")

    log_debug(f"Found ProgIDs: {prog_ids}")

    # Resolve ProgIDs to Commands
    for prog_id in prog_ids:
        try:
            cmd_key = f"{prog_id}\\shell\\open\\command"
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, cmd_key) as key:
                cmd_str, _ = winreg.QueryValueEx(key, "")
                clean_path = clean_command(cmd_str)
                if clean_path and os.path.exists(clean_path):
                    clean_path = os.path.abspath(clean_path)
                    if clean_path.lower() not in seen_paths:
                        friendly = prog_id
                        try:
                            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id) as pkey:
                                friendly, _ = winreg.QueryValueEx(pkey, "") 
                                if not friendly: friendly = winreg.QueryValueEx(pkey, "FriendlyTypeName")[0]
                        except: 
                            friendly = os.path.splitext(os.path.basename(clean_path))[0].title()
                        
                        apps.append((friendly, clean_path))
                        seen_paths.add(clean_path.lower())
        except Exception as e:
             # log_debug(f"Error resolving ProgID {prog_id}: {e}")
             pass

    # 2. Look in OpenWithList (HKCU and HKCR) AND SystemFileAssociations
    roots = [
        (winreg.HKEY_CURRENT_USER, f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\{extension}\\OpenWithList"),
        (winreg.HKEY_CLASSES_ROOT, f"{extension}\\OpenWithList"),
        (winreg.HKEY_CLASSES_ROOT, f"SystemFileAssociations\\{extension}\\OpenWithList")
    ]
    
    potential_exes = []
    for root, key_path in roots:
        try:
            with winreg.OpenKey(root, key_path) as key:
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key)
                        if len(name) == 1 and isinstance(val, str) and val.lower().endswith(".exe"):
                            potential_exes.append(val)
                        i += 1
                    except OSError: break
        except Exception as e:
            # log_debug(f"Error reading OpenWithList at {key_path}: {e}")
            pass

    log_debug(f"Potential EXEs from OpenWithList: {potential_exes}")

    # Resolve these EXEs users might have used
    for list_exe in potential_exes:
        found_path = None
        try:
             with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{list_exe}") as key:
                 found_path, _ = winreg.QueryValueEx(key, "")
        except: pass
        
        if not found_path:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"Applications\\{list_exe}\\shell\\open\\command") as key:
                    cmd_str, _ = winreg.QueryValueEx(key, "")
                    clean = clean_command(cmd_str)
                    if clean and os.path.exists(clean):
                        found_path = clean
            except: pass

        if not found_path and os.path.exists(list_exe): 
            found_path = list_exe
            
        if found_path and os.path.exists(found_path):
            found_path = os.path.abspath(found_path)
            if found_path.lower() not in seen_paths:
                 display = os.path.splitext(os.path.basename(found_path))[0].title()
                 apps.append((display, found_path))
                 seen_paths.add(found_path.lower())

    log_debug(f"Final Associated Apps: {apps}")
    return sorted(apps, key=lambda x: x[0])


# --- NEW Helper: Resolve Windows Shortcut ---
def resolve_windows_shortcut(lnk_path):
    """Resolves a .lnk file to its target path using PowerShell."""
    try:
        lnk_path = os.path.abspath(lnk_path).replace("'", "''")
        cmd = f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{lnk_path}');$s.TargetPath"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.strip()
    except Exception:
        return None

# --- NEW Helper: Get LNK Properties ---
def get_lnk_properties(lnk_path):
    """Retrieves TargetPath and WorkingDirectory from a .lnk file using PowerShell."""
    try:
        lnk_path = os.path.abspath(lnk_path).replace("'", "''")
        # Use a pipe delimiter, as | is illegal in Windows paths
        cmd = f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{lnk_path}');Write-Output ($s.TargetPath + '|' + $s.WorkingDirectory)"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        output = result.stdout.strip()
        if '|' in output:
            parts = output.split('|', 1)
            return parts[0], parts[1]
        return output, ""
    except Exception:
        return None, None

# --- Helper: Safe Launch with Elevation Fallback ---
def safe_launch(executable, arguments=None, cwd=None, shell=False):
    """
    Launches an executable. If it requires elevated privileges (WinError 740),
    falls back to ShellExecuteW to prompt for UAC elevation in Windows.
    """
    import subprocess
    import ctypes
    
    try:
        if arguments:
            args = [executable]
            if isinstance(arguments, list):
                args.extend(arguments)
            else:
                args.append(arguments)
            return subprocess.Popen(args, cwd=cwd, shell=shell)
        else:
            return subprocess.Popen([executable], cwd=cwd, shell=shell)
    except OSError as e:
        if getattr(e, 'winerror', None) == 740:  # ERROR_ELEVATION_REQUIRED
            try:
                args_str = None
                if arguments:
                    if isinstance(arguments, list):
                        args_str = " ".join(f'"{arg}"' for arg in arguments)
                    else:
                        args_str = f'"{arguments}"'
                
                # Use ShellExecuteW
                hwnd = None
                ret = ctypes.windll.shell32.ShellExecuteW(hwnd, "open", executable, args_str, cwd, 1)
                if ret <= 32:
                    ret = ctypes.windll.shell32.ShellExecuteW(hwnd, "runas", executable, args_str, cwd, 1)
                return ret > 32
            except Exception as ctypes_err:
                log_debug(f"ctypes.ShellExecuteW failed: {ctypes_err}")
                raise e
        else:
            raise e

# --- Helper: Get Startup Shortcut Path ---
def get_startup_shortcut_path():
    """Returns the path to the shortcut in the Windows Startup folder."""
    startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    return os.path.join(startup_folder, f"{APP_SHORT_NAME}.lnk")

# --- Helper: Settings Manager ---
# --- Helper: Settings Manager ---
class SettingsManager:
    def __init__(self):
        # [FIX] Do not use QStandardPaths.AppDataLocation because it appends APP_NAME (which has a colon).
        # Instead, get the root Roaming folder and manually append the safe APP_SHORT_NAME.
        if sys.platform == "win32":
            app_data = os.getenv('APPDATA') # C:\Users\Name\AppData\Roaming
        else:
            # Fallback for non-Windows (Linux/Mac)
            app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)

        self.base_dir = os.path.join(app_data, APP_SHORT_NAME)
        self.path = os.path.join(self.base_dir, "prefs.json")
        self.shortcuts_dir = os.path.join(self.base_dir, "shortcuts")
        self.trash_dir = os.path.join(self.base_dir, "trash_staging") 
        self.db_path = os.path.join(self.base_dir, "file_index.db") 
        
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.shortcuts_dir, exist_ok=True)
        os.makedirs(self.trash_dir, exist_ok=True)
        
    def load(self):
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading settings (resetting): {e}")
            return None 
            
    def save(self, data):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            
    def get_shortcut_path(self, filename):
        return os.path.join(self.shortcuts_dir, filename)

# --- Database Manager ---
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path, timeout=30)

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                extension TEXT,
                size_bytes INTEGER,
                modified_ts REAL,
                created_ts REAL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename ON files(filename)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_extension ON files(extension)')
        conn.commit()
        conn.close()

class ReportManager:
    def __init__(self, db_path):
        self.db_path = db_path

    def export_csv(self, target_file, max_size_bytes):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files")
            
            base, ext = os.path.splitext(target_file)
            file_index = 1
            current_file_path = target_file
            
            f = open(current_file_path, 'w', newline='', encoding='utf-8')
            writer = csv.writer(f)
            
            header = [d[0] for d in cursor.description]
            writer.writerow(header)
            
            for row in cursor:
                writer.writerow(row)
                if f.tell() >= max_size_bytes:
                    f.close()
                    file_index += 1
                    current_file_path = f"{base}_{file_index}{ext}"
                    f = open(current_file_path, 'w', newline='', encoding='utf-8')
                    writer = csv.writer(f)
                    writer.writerow(header)
                    
            f.close()
            conn.close()
            return True, "Export Successful"
        except Exception as e:
            if 'f' in locals() and not f.closed: f.close()
            return False, str(e)

    def generate_stats(self, target_file):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(f"File System Statistics - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("==================================================\n\n")
                
                # Top extensions by Count
                f.write("Top 10 File Types by Count:\n")
                f.write("-" * 30 + "\n")
                cursor.execute("SELECT extension, COUNT(*) as c FROM files GROUP BY extension ORDER BY c DESC LIMIT 10")
                for row in cursor.fetchall():
                    ext = row[0] if row[0] else "(no extension)"
                    f.write(f"{ext:<15} : {row[1]}\n")
                
                # Top extensions by Size
                f.write("\nTop 10 File Types by Total Size:\n")
                f.write("-" * 30 + "\n")
                cursor.execute("SELECT extension, SUM(size_bytes) as s FROM files GROUP BY extension ORDER BY s DESC LIMIT 10")
                for row in cursor.fetchall():
                    ext = row[0] if row[0] else "(no extension)"
                    size_mb = row[1] / (1024*1024)
                    f.write(f"{ext:<15} : {size_mb:,.2f} MB\n")
                    
                # Largest Files
                f.write("\nTop 10 Largest Files:\n")
                f.write("-" * 30 + "\n")
                cursor.execute("SELECT filename, folder_path, size_bytes FROM files ORDER BY size_bytes DESC LIMIT 10")
                for row in cursor.fetchall():
                    size_mb = row[2] / (1024*1024)
                    path = os.path.join(row[1], row[0])
                    f.write(f"{size_mb:,.2f} MB : {path}\n")

                # Oldest Files
                f.write("\nOldest 10 Files (by modification date):\n")
                f.write("-" * 30 + "\n")
                cursor.execute("SELECT filename, folder_path, modified_ts FROM files ORDER BY modified_ts ASC LIMIT 10")
                for row in cursor.fetchall():
                    try:
                        dt = datetime.fromtimestamp(row[2]).strftime('%Y-%m-%d %H:%M:%S')
                    except: dt = "Unknown"
                    path = os.path.join(row[1], row[0])
                    f.write(f"{dt} : {path}\n")
                    
            conn.close()
            return True, "Report Generated"
        except Exception as e:
            return False, str(e)

class ExportWorker(QThread):
    finished = pyqtSignal(bool, str) # success, message
    progress = pyqtSignal(int) # optional, maybe for row count

    def __init__(self, db_path, target_file, max_size_bytes, ignore_recycle):
        super().__init__()
        self.db_path = db_path
        self.target_file = target_file
        self.max_size_bytes = max_size_bytes
        self.ignore_recycle = ignore_recycle
        self.is_running = True

    def run(self):
        conn = None
        f = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = "SELECT * FROM files"
            if self.ignore_recycle:
                query += " WHERE folder_path NOT LIKE '%$RECYCLE.BIN%'"
                
            cursor.execute(query)
            
            base, ext = os.path.splitext(self.target_file)
            file_index = 1
            current_file_path = self.target_file
            
            f = open(current_file_path, 'w', newline='', encoding='utf-8')
            writer = csv.writer(f)
            
            header = [d[0] for d in cursor.description]
            writer.writerow(header)
            
            count = 0
            for row in cursor:
                if not self.is_running: break
                writer.writerow(row)
                count += 1
                
                if self.max_size_bytes > 0 and f.tell() >= self.max_size_bytes:
                    f.close()
                    file_index += 1
                    current_file_path = f"{base}_{file_index}{ext}"
                    f = open(current_file_path, 'w', newline='', encoding='utf-8')
                    writer = csv.writer(f)
                    writer.writerow(header)
            
            self.finished.emit(True, f"Export Complete. {count} records exported.")
            
        except Exception as e:
            self.finished.emit(False, str(e))
        finally:
            if f and not f.closed: f.close()
            if conn: conn.close()

    def stop(self):
        self.is_running = False

# --- Indexer Worker (With Crash Protection & Restart Fix) ---
class IndexerWorker(QThread):
    progress_signal = pyqtSignal(int) 
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    
    def __init__(self, db_path, ignore_recycle=True):
        super().__init__()
        self.db_path = db_path
        self.is_running = True
        self.exclusions = ['System Volume Information', 'Windows']
        if ignore_recycle:
            self.exclusions.append('$RECYCLE.BIN')

    def run(self):
        # --- FIX: Ensure flag is reset on run ---
        self.is_running = True
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files")
            conn.commit()
            
            count = 0
            batch_data = []
            batch_size = 1000
            drives = QDir.drives()
            for drive in drives:
                root_path = drive.absoluteFilePath()
                for root, dirs, files in os.walk(root_path):
                    if not self.is_running: break
                    
                    # Exclude based on user settings and system folders
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in self.exclusions]
                    
                    for file in files:
                        if not self.is_running: break
                        try:
                            full_path = os.path.join(root, file)
                            stat = os.stat(full_path)
                            batch_data.append((file, root, os.path.splitext(file)[1].lower(), stat.st_size, stat.st_mtime, stat.st_ctime))
                            count += 1
                            if len(batch_data) >= batch_size:
                                cursor.executemany('''INSERT INTO files (filename, folder_path, extension, size_bytes, modified_ts, created_ts) VALUES (?, ?, ?, ?, ?, ?)''', batch_data)
                                conn.commit()
                                batch_data = []
                                self.progress_signal.emit(count)
                        except (PermissionError, OSError):
                            continue
                if not self.is_running: break
            if batch_data:
                cursor.executemany('''INSERT INTO files (filename, folder_path, extension, size_bytes, modified_ts, created_ts) VALUES (?, ?, ?, ?, ?, ?)''', batch_data)
                conn.commit()
            
            self.finished_signal.emit()
            
        except Exception:
            self.error_signal.emit(traceback.format_exc())
        finally:
            if conn:
                conn.close()

    def stop(self):
        self.is_running = False

# --- Watchdog Event Handler ---
if HAS_WATCHDOG:
    class IndexEventHandler(FileSystemEventHandler):
        def __init__(self, db_path):
            self.db_path = db_path

        def _get_conn(self):
            return sqlite3.connect(self.db_path, timeout=30)

        def on_created(self, event):
            if event.is_directory: return
            try:
                conn = self._get_conn()
                cursor = conn.cursor()
                filename = os.path.basename(event.src_path)
                folder = os.path.dirname(event.src_path)
                ext = os.path.splitext(filename)[1].lower()
                stat = os.stat(event.src_path)
                
                cursor.execute('''INSERT INTO files (filename, folder_path, extension, size_bytes, modified_ts, created_ts) 
                                VALUES (?, ?, ?, ?, ?, ?)''', 
                                (filename, folder, ext, stat.st_size, stat.st_mtime, stat.st_ctime))
                conn.commit()
                conn.close()
            except: pass

        def on_deleted(self, event):
            if event.is_directory: return
            try:
                conn = self._get_conn()
                cursor = conn.cursor()
                filename = os.path.basename(event.src_path)
                folder = os.path.dirname(event.src_path)
                cursor.execute("DELETE FROM files WHERE filename=? AND folder_path=?", (filename, folder))
                conn.commit()
                conn.close()
            except: pass

        def on_moved(self, event):
            if event.is_directory: return
            try:
                conn = self._get_conn()
                cursor = conn.cursor()
                old_name = os.path.basename(event.src_path)
                old_folder = os.path.dirname(event.src_path)
                new_name = os.path.basename(event.dest_path)
                new_folder = os.path.dirname(event.dest_path)
                
                cursor.execute("UPDATE files SET filename=?, folder_path=? WHERE filename=? AND folder_path=?", 
                               (new_name, new_folder, old_name, old_folder))
                conn.commit()
                conn.close()
            except: pass

        def on_modified(self, event):
            if event.is_directory: return
            try:
                conn = self._get_conn()
                cursor = conn.cursor()
                stat = os.stat(event.src_path)
                filename = os.path.basename(event.src_path)
                folder = os.path.dirname(event.src_path)
                
                cursor.execute("UPDATE files SET size_bytes=?, modified_ts=? WHERE filename=? AND folder_path=?",
                               (stat.st_size, stat.st_mtime, filename, folder))
                conn.commit()
                conn.close()
            except: pass

    class FileSystemWatcher:
        def __init__(self, db_path):
            self.observer = Observer()
            self.handler = IndexEventHandler(db_path)
            
        def start(self):
            drives = QDir.drives()
            for drive in drives:
                path = drive.absoluteFilePath()
                try:
                    self.observer.schedule(self.handler, path, recursive=True)
                    # log_debug(f"Watchdog started for {path}")
                except Exception as e:
                    # Permission errors are common here on Windows for root drives or network shares
                    # log_debug(f"Could not watch {path}: {e}")
                    pass
            try:
                self.observer.start()
            except Exception as e:
                log_debug(f"Watchdog start failed: {e}")

        def stop(self):
            try:
                if self.observer and self.observer.is_alive():
                    self.observer.stop()
                    try:
                        self.observer.join(1.0)
                    except RuntimeError:
                        pass
            except Exception:
                pass

# --- Search Worker (With Advanced Syntax) ---
class SearchWorker(QThread):
    results_ready = pyqtSignal(list)

    def __init__(self, db_path, query, ignore_recycle=True):
        super().__init__()
        self.db_path = db_path
        self.query = query
        self.ignore_recycle = ignore_recycle

    def run(self):
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            
            # Base Query
            sql = "SELECT filename, folder_path, size_bytes, modified_ts FROM files WHERE 1=1"
            
            # [FIX] Apply Recycle Bin Filter during Search Query
            if self.ignore_recycle:
                sql += " AND folder_path NOT LIKE '%$RECYCLE.BIN%'"
            
            params = []
            
            # --- Advanced Parsing ---
            tokens = self.query.split()
            for token in tokens:
                lower_token = token.lower()
                
                # Extension Filter (ext:jpg)
                if lower_token.startswith("ext:"):
                    ext = lower_token.split(":", 1)[1]
                    if not ext.startswith("."): ext = "." + ext
                    sql += " AND extension = ?"
                    params.append(ext)
                
                # Name Force (name:report)
                elif lower_token.startswith("name:"):
                    name = token.split(":", 1)[1]
                    sql += " AND filename LIKE ?"
                    params.append(f"%{name}%")
                    
                # Size Filter (size:>10MB, size:<500KB)
                elif lower_token.startswith("size:"):
                    val_str = lower_token.split(":", 1)[1]
                    operator = "="
                    if val_str.startswith(">"): 
                        operator = ">"
                        val_str = val_str[1:]
                    elif val_str.startswith("<"): 
                        operator = "<"
                        val_str = val_str[1:]
                    
                    # Convert units
                    multiplier = 1
                    if val_str.endswith("gb"): multiplier = 1024**3; val_str = val_str[:-2]
                    elif val_str.endswith("mb"): multiplier = 1024**2; val_str = val_str[:-2]
                    elif val_str.endswith("kb"): multiplier = 1024; val_str = val_str[:-2]
                    elif val_str.endswith("b"): val_str = val_str[:-1]
                    
                    try:
                        size_val = float(val_str) * multiplier
                        sql += f" AND size_bytes {operator} ?"
                        params.append(size_val)
                    except ValueError:
                        pass # Ignore invalid size

                # Date Filter (modified:2023-01-01, created:>2022-01-01)
                elif lower_token.startswith("modified:") or lower_token.startswith("created:"):
                    is_created = lower_token.startswith("created:")
                    col = "created_ts" if is_created else "modified_ts"
                    val_str = token.split(":", 1)[1]
                    
                    operator = "="
                    if val_str.startswith(">"): 
                        operator = ">"
                        val_str = val_str[1:]
                    elif val_str.startswith("<"): 
                        operator = "<"
                        val_str = val_str[1:]
                        
                    try:
                        dt = datetime.strptime(val_str, "%Y-%m-%d")
                        ts = dt.timestamp()
                        
                        if operator == ">":
                            # > Date means after the END of that date
                            sql += f" AND {col} > ?"
                            params.append(ts + 86400)
                        elif operator == "<":
                            # < Date means before the START of that date
                            sql += f" AND {col} < ?"
                            params.append(ts)
                        else:
                            # = Date means WITHIN that day
                            sql += f" AND {col} >= ? AND {col} < ?"
                            params.append(ts)
                            params.append(ts + 86400)
                    except ValueError:
                        pass 
                
                # Default: Partial Name Match
                else:
                    sql += " AND filename LIKE ?"
                    params.append(f"%{token}%")
            
            sql += " LIMIT 500"
            cursor.execute(sql, params)
            results = cursor.fetchall()
            conn.close()
            self.results_ready.emit(results)
        except Exception as e:
            print(f"Search Error: {e}")
            self.results_ready.emit([])

# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        self.settings_mgr = SettingsManager()
        
        # --- FIX: Check if file exists BEFORE loading so we can show license ---
        loaded_data = self.settings_mgr.load()
        is_first_run = loaded_data is None 
        # is_first_run = False # [DEBUG] SKIP LICENSE
        self.settings = loaded_data or {}
        
        # Ensure profiles dict exists
        if "profiles" not in self.settings:
            self.settings["profiles"] = {}
            
        self.db_mgr = DatabaseManager(self.settings_mgr.db_path)
        self.report_mgr = ReportManager(self.settings_mgr.db_path)
        
        # --- Helper for thread safe file ops ---
        self.threadpool = QThreadPool()
        
        self.setup_ui()
        # self.apply_theme() # [FIX] Method missing/undefined
        
        # Start Indexer in background if needed
        # self.start_file_indexer() # [FIX] Method missing/undefined
        
        # Setup Watchdog
        if HAS_WATCHDOG:
            log_debug("Starting Watchdog...")
            try:
                self.fs_watcher = FileSystemWatcher(self.settings_mgr.db_path)
                self.fs_watcher.start()
                log_debug("Watchdog started.")
            except Exception as e:
                log_debug(f"Watchdog failed to start: {e}")
            
        # First Run License Check
        if is_first_run:
            log_debug("Scheduling License Dialog...")
            QTimer.singleShot(100, self.show_license_dialog)
            
    def showEvent(self, event):
        log_debug("MainWindow.showEvent triggered")
        super().showEvent(event)
            
    def show_license_dialog(self):
        log_debug("Showing License Dialog")
        msg = QMessageBox()
        msg.setWindowTitle("License Agreement")
        msg.setText(f"{APP_NAME}\n\n{APP_COPYRIGHT}\n\nLicensed under MIT License.")
        msg.setInformativeText("By clicking 'Accept', you agree to the terms of the MIT License.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.button(QMessageBox.StandardButton.Ok).setText("Accept")
        
        if msg.exec() == QMessageBox.StandardButton.Cancel:
            sys.exit(0)
        else:
            self.settings["license_accepted"] = True
            try:
                log_debug("User accepted license. Saving settings...")
                self.settings_mgr.save(self.settings)
                log_debug("Settings saved successfully. License accepted.")
            except Exception as e:
                log_debug(f"Error saving settings during license accept: {e}")
                QMessageBox.critical(self, "Error", f"Could not save settings:\n{e}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save settings:\n{e}")

    def closeEvent(self, event):
        # Guarantee a hard exit after 1.0 seconds if graceful sequence blocks
        import threading, os
        t = threading.Timer(1.0, lambda os_module=os: os_module._exit(0))
        t.daemon = True
        t.start()

        # Save current widths
        if self.active_pane:
            widths = []
            for i in range(self.active_pane.tree_view.header().count()):
                widths.append(self.active_pane.tree_view.columnWidth(i))
            self.settings["column_widths"] = widths
            
        self.settings_mgr.save(self.settings)
        if hasattr(self, 'fs_watcher') and self.fs_watcher:
            self.fs_watcher.stop()
        if hasattr(self, 'indexer') and self.indexer and self.indexer.isRunning():
            self.indexer.stop()
            self.indexer.wait()
        event.accept()

    def add_favorite_item(self, path):
         # Add to favorites tree
         if not os.path.exists(path): return
         
         # Avoid duplicates?
         root = self.dock_favorites.widget().invisibleRootItem()
         for i in range(root.childCount()):
             child = root.child(i)
             if child.data(0, Qt.ItemDataRole.UserRole) == path:
                 return
                 
         name = os.path.basename(path)
         if not name: name = path
         
         item = QTreeWidgetItem(root)
         item.setText(0, name)
         item.setData(0, Qt.ItemDataRole.UserRole, path)
         item.setIcon(0, QFileIconProvider().icon(QFileInfo(path)))
         
         # Save logic needed? We should probably persist favorites in settings
         
    def add_bookmark_item(self, name, path):
        root = self.dock_bookmarks.widget().invisibleRootItem()
        # Find "Bookmarks" section or create?
        # Assuming structure is predefined or simple list
        
        # We can just add to root for now
        item = QTreeWidgetItem(root)
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        item.setExpanded(True)
        return item
            
    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0,0,0,0)
        
        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Last Scan Label (Left)
        last_scan_time = self.settings.get("last_scan_time", "Never")
        self.lbl_last_scan = QLabel(f"Last Scan: {last_scan_time}")
        self.status_bar.addWidget(self.lbl_last_scan)
        
        self.status_bar.addWidget(QLabel(" | "))
        
        # Rescan Link (Left)
        self.lbl_rescan = QLabel("<a href='#'>Scan Now</a>")
        self.lbl_rescan.setOpenExternalLinks(False)
        self.lbl_rescan.linkActivated.connect(self.start_rescan)
        self.status_bar.addWidget(self.lbl_rescan)
        
        # Permanent Message (Right)
        self.lbl_perm_status = QLabel("Ready")
        self.status_bar.addPermanentWidget(self.lbl_perm_status)
        
        # --- Menu Bar ---
        self.create_menus()
        
        # --- Toolbar ---
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        self.toolbar.setMovable(False)
        
        act_back = self.toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "Back")
        act_back.triggered.connect(self.on_back)
        
        act_fwd = self.toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward), "Forward")
        act_fwd.triggered.connect(self.on_forward)
        
        act_up = self.toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp), "Up")
        act_up.triggered.connect(self.on_up)
        
        self.toolbar.addSeparator()
        
        # Path Bar
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self.on_path_entered)
        self.toolbar.addWidget(self.path_edit)
        
        # Search Bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.returnPressed.connect(self.on_search)
        self.search_edit.setFixedWidth(200)
        self.toolbar.addWidget(self.search_edit)
        
        btn_search_help = QPushButton("?")
        btn_search_help.setFixedWidth(30)
        btn_search_help.clicked.connect(lambda: SearchHelpDialog(self).exec())
        self.toolbar.addWidget(btn_search_help)
        
        # --- Sort & View Options ---
        self.toolbar.addSeparator()
        
        btn_sort = QPushButton("Sort")
        menu_sort = QMenu(self)
        self.grp_sort = QActionGroup(self)
        
        opts = ["Name", "Date Modified", "Size", "Type"]
        for opt in opts:
            a = menu_sort.addAction(opt)
            a.setCheckable(True)
            a.setActionGroup(self.grp_sort)
            a.triggered.connect(lambda checked, o=opt: self.set_sort_column(o))
            if opt == "Name": a.setChecked(True)
            
        btn_sort.setMenu(menu_sort)
        self.toolbar.addWidget(btn_sort)
        
        # Profile Combo
        self.combo_profiles = QComboBox()
        self.combo_profiles.addItem("Default")
        self.combo_profiles.addItems(list(self.settings["profiles"].keys()))
        self.combo_profiles.currentIndexChanged.connect(self.on_profile_changed)
        self.toolbar.addWidget(self.combo_profiles)

        # --- Docks ---
        self.load_docks()
        
        # --- Splitter (Dual Pane) ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)
        
        # Pane 1
        self.left_pane = FilePane("Pane 1", "C:\\", self)
        self.splitter.addWidget(self.left_pane)
        
        # Pane 2
        self.right_pane = FilePane("Pane 2", os.path.expanduser("~"), self)
        self.splitter.addWidget(self.right_pane)
        
        self.active_pane = self.left_pane
        self.left_pane.set_active()
        
        # --- Properties Pane (Bottom Dock) ---
        self.dock_props = QDockWidget("Properties", self)
        self.dock_props.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.props_pane = PropertiesPane()
        self.dock_props.setWidget(self.props_pane)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_props)
        # self.dock_props.hide() # Initially hidden? 

    def load_docks(self):
        # Bookmarks
        self.dock_bookmarks = QDockWidget("Bookmarks", self)
        self.dock_bookmarks.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        self.tree_bookmarks = BookmarkTree(self)
        self.dock_bookmarks.setWidget(self.tree_bookmarks)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_bookmarks)
        
        # Favorites
        self.dock_favorites = QDockWidget("Favorite Apps", self)
        self.dock_favorites.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        self.tree_favorites = FavoritesTree(self)
        self.dock_favorites.setWidget(self.tree_favorites)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_favorites)
        
        # Load Defaults
        self.load_default_bookmarks()

    def load_default_bookmarks(self):
        # Load from file later, for now hardcoded structure
        
        data = [
            {"name": "This PC", "type": "folder", "children": [
                {"name": "Desktop", "path": QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)},
                {"name": "Documents", "path": QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)},
                {"name": "Downloads", "path": QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)}, 
                {"name": "Pictures", "path": QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)},
                {"name": "Videos", "path": QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)},
                {"name": "Music", "path": QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)},
                {"name": "OneDrive", "path": os.environ.get("OneDrive", "")},
                {"name": "Dropbox", "path": os.path.expanduser("~/Dropbox")},
            ]},
            {"name": "System", "type": "folder", "children": [
                 {"name": "Recycle Bin", "path": "::{645FF040-5081-101B-9F08-00AA002F954E}"}
            ]}
        ]
        
        # Also add fixed Drives
        drives = QDir.drives()
        drive_children = []
        for d in drives:
            drive_children.append({"name": d.absoluteFilePath(), "path": d.absoluteFilePath()})
        data[0]["children"].extend(drive_children) # Add to This PC
        
        root = self.tree_bookmarks.invisibleRootItem()
        self.load_bookmarks_recursive(data, root)

    def load_bookmarks_recursive(self, data_list, parent_item):
        for entry in data_list:
            item = QTreeWidgetItem(parent_item)
            item.setText(0, entry["name"])
            if entry.get("type") == "folder":
                 item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                 
                 # [FIX] Collapse "System", expand others by default
                 if entry["name"] == "System":
                     item.setExpanded(False)
                 else:
                     item.setExpanded(True)
                     
                 if "children" in entry: self.load_bookmarks_recursive(entry["children"], item)
            else:
                 path = entry.get("path", "")
                 item.setData(0, Qt.ItemDataRole.UserRole, path)
                 item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))

    def create_menus(self):
        bar = self.menuBar()
        
        file_menu = bar.addMenu("File")
        file_menu.addAction("New Window").triggered.connect(lambda: subprocess.Popen([sys.executable, __file__]))
        file_menu.addAction("Exit").triggered.connect(self.close)
        
        edit_menu = bar.addMenu("Edit")
        # Global Edit actions usually delegated to active pane
        act_copy = edit_menu.addAction("Copy")
        act_copy.setShortcut("Ctrl+C")
        act_copy.triggered.connect(self.on_copy)
        
        act_cut = edit_menu.addAction("Cut")
        act_cut.setShortcut("Ctrl+X")
        act_cut.triggered.connect(self.on_cut)
        
        act_paste = edit_menu.addAction("Paste")
        act_paste.setShortcut("Ctrl+V")
        act_paste.triggered.connect(self.on_paste)
        
        act_del = edit_menu.addAction("Delete")
        act_del.setShortcut("Del")
        act_del.triggered.connect(self.on_delete)
        
        edit_menu.addSeparator()
        self.act_undo = edit_menu.addAction("Undo")
        self.act_undo.setShortcut("Ctrl+Z")
        self.act_undo.triggered.connect(self.undo)
        
        self.act_redo = edit_menu.addAction("Redo")
        self.act_redo.setShortcut("Ctrl+Y")
        self.act_redo.triggered.connect(self.redo)
        
        view_menu = bar.addMenu("View")
        self.view_group = QActionGroup(self) # Create exclusive group
        
        self.act_narrow = view_menu.addAction("Narrow")
        self.act_narrow.setCheckable(True)
        self.act_narrow.setActionGroup(self.view_group)
        self.act_narrow.triggered.connect(lambda: self.set_active_pane_view("Narrow"))
        
        self.act_detail = view_menu.addAction("Detailed")
        self.act_detail.setCheckable(True)
        self.act_detail.setActionGroup(self.view_group)
        self.act_detail.triggered.connect(lambda: self.set_active_pane_view("Detailed"))
        
        self.act_detail.setChecked(True) # Default
        
        opts_menu = bar.addMenu("Options")
        opts_menu.addAction("Settings...").triggered.connect(self.open_settings_dialog)
        
        tools_menu = bar.addMenu("Tools")
        tools_menu.addAction("Generate File Stats Report").triggered.connect(self.on_generate_stats)
        tools_menu.addAction("Export Database to CSV").triggered.connect(self.on_export_csv)
        
        help_menu = bar.addMenu("Help")
        help_menu.addAction("Search Syntax").triggered.connect(lambda: SearchHelpDialog(self).exec())
        help_menu.addAction("Change Log").triggered.connect(lambda: ChangeLogDialog(self).exec())
        help_menu.addAction("About").triggered.connect(lambda: AboutDialog(self).exec())

    def on_export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Database", "file_index.csv", "CSV Files (*.csv)")
        if not path: return

        # Default to 70MB if not set
        max_size = self.settings.get("max_dump_size", 73400320)
        ignore_recycle = self.settings.get("ignore_recycle_bin", True)
        
        self.export_progress = QProgressDialog("Exporting Database...", "Cancel", 0, 0, self)
        self.export_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.export_progress.show()
        
        self.export_worker = ExportWorker(self.settings_mgr.db_path, path, max_size, ignore_recycle)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_progress.canceled.connect(self.export_worker.stop)
        self.export_worker.start()

    def on_export_finished(self, success, msg):
        self.export_progress.close()
        if success: QMessageBox.information(self, "Export Complete", msg)
        else: QMessageBox.critical(self, "Export Failed", msg)
        self.export_worker = None

    def on_generate_stats(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Report", "file_stats.txt", "Text Files (*.txt)")
        if path:
            success, msg = self.report_mgr.generate_stats(path)
            if success: QMessageBox.information(self, "Report Generated", msg)
            else: QMessageBox.critical(self, "Report Failed", msg)

    def set_active_pane_view(self, mode):
        if self.active_pane:
            self.active_pane.set_view_mode(mode)

    def on_open_with(self, path):
        log_debug(f"on_open_with called for: {path}")
        if not path or not os.path.exists(path): return
        # Open the Windows "Open With" dialog
        # quote path for shell
        path = os.path.abspath(path)
        try:
            # rundll32 invocation is tricky with spaces. 
            # The most reliable way is often to use the bare command string with shell=True
            cmd = f'rundll32.exe shell32.dll,OpenAs_RunDLL "{path}"'
            log_debug(f"Executing: {cmd}")
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            log_debug(f"Failed to open dialog: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open 'Open With' dialog: {e}")

    def on_open_with_app(self, path, app_path):
        if not path or not os.path.exists(path): return
        try:
            subprocess.Popen([app_path, path])
            log_debug(f"Opened {path} with {app_path}")
        except Exception as e:
            log_debug(f"Failed to open app: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open with selected app: {e}")



# --- NEW Helper: Resolve Windows Shortcut ---
def resolve_windows_shortcut(lnk_path):
    """Resolves a .lnk file to its target path using PowerShell."""
    try:
        lnk_path = os.path.abspath(lnk_path).replace("'", "''")
        cmd = f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{lnk_path}');$s.TargetPath"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.strip()
    except Exception:
        return None

# --- NEW Helper: Get LNK Properties ---
def get_lnk_properties(lnk_path):
    """Retrieves TargetPath and WorkingDirectory from a .lnk file using PowerShell."""
    try:
        lnk_path = os.path.abspath(lnk_path).replace("'", "''")
        # Use a pipe delimiter, as | is illegal in Windows paths
        cmd = f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{lnk_path}');Write-Output ($s.TargetPath + '|' + $s.WorkingDirectory)"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        output = result.stdout.strip()
        if '|' in output:
            parts = output.split('|', 1)
            return parts[0], parts[1]
        return output, ""
    except Exception:
        return None, None

# --- Helper: Get Startup Shortcut Path ---
def get_startup_shortcut_path():
    """Returns the path to the shortcut in the Windows Startup folder."""
    startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    return os.path.join(startup_folder, f"{APP_SHORT_NAME}.lnk")

# --- Helper: Settings Manager ---
# --- Helper: Settings Manager ---
class SettingsManager:
    def __init__(self):
        # [FIX] Do not use QStandardPaths.AppDataLocation because it appends APP_NAME (which has a colon).
        # Instead, get the root Roaming folder and manually append the safe APP_SHORT_NAME.
        if sys.platform == "win32":
            app_data = os.getenv('APPDATA') # C:\Users\Name\AppData\Roaming
        else:
            # Fallback for non-Windows (Linux/Mac)
            app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)

        self.base_dir = os.path.join(app_data, APP_SHORT_NAME)
        self.path = os.path.join(self.base_dir, "prefs.json")
        self.shortcuts_dir = os.path.join(self.base_dir, "shortcuts")
        self.trash_dir = os.path.join(self.base_dir, "trash_staging") 
        self.db_path = os.path.join(self.base_dir, "file_index.db") 
        
        try:
            os.makedirs(self.base_dir, exist_ok=True)
            os.makedirs(self.shortcuts_dir, exist_ok=True)
            os.makedirs(self.trash_dir, exist_ok=True)
            log_debug(f"Settings folders created at: {self.base_dir}")
        except Exception as e:
            log_debug(f"CRITICAL: Failed to create settings folders: {e}")
            QMessageBox.critical(None, "Startup Error", f"Failed to create data folders:\n{e}")
        
    def load(self):
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading settings (resetting): {e}")
            return None 

    def save(self, data):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            
    def get_shortcut_path(self, filename):
        return os.path.join(self.shortcuts_dir, filename)

# --- Database Manager ---
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path, timeout=30)

    def init_db(self):
        log_debug("Initializing Database...")
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    folder_path TEXT NOT NULL,
                    extension TEXT,
                    size_bytes INTEGER,
                    modified_ts REAL,
                    created_ts REAL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename ON files(filename)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_extension ON files(extension)')
            conn.commit()
            conn.close()
            log_debug("Database initialized successfully.")
        except Exception as e:
            log_debug(f"CRITICAL: Database initialization failed: {e}")
            QMessageBox.critical(None, "Database Error", f"Failed to initialize database:\n{e}")

class ReportManager:
    def __init__(self, db_path):
        self.db_path = db_path

    def export_csv(self, target_file, max_size_bytes):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files")
            
            base, ext = os.path.splitext(target_file)
            file_index = 1
            current_file_path = target_file
            
            f = open(current_file_path, 'w', newline='', encoding='utf-8')
            writer = csv.writer(f)
            
            header = [d[0] for d in cursor.description]
            writer.writerow(header)
            
            for row in cursor:
                writer.writerow(row)
                if f.tell() >= max_size_bytes:
                    f.close()
                    file_index += 1
                    current_file_path = f"{base}_{file_index}{ext}"
                    f = open(current_file_path, 'w', newline='', encoding='utf-8')
                    writer = csv.writer(f)
                    writer.writerow(header)
                    
            f.close()
            conn.close()
            return True, "Export Successful"
        except Exception as e:
            if 'f' in locals() and not f.closed: f.close()
            return False, str(e)

    def generate_stats(self, target_file):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(f"File System Statistics - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("==================================================\n\n")
                
                # Top extensions by Count
                f.write("Top 10 File Types by Count:\n")
                f.write("-" * 30 + "\n")
                cursor.execute("SELECT extension, COUNT(*) as c FROM files GROUP BY extension ORDER BY c DESC LIMIT 10")
                for row in cursor.fetchall():
                    ext = row[0] if row[0] else "(no extension)"
                    f.write(f"{ext:<15} : {row[1]}\n")
                
                # Top extensions by Size
                f.write("\nTop 10 File Types by Total Size:\n")
                f.write("-" * 30 + "\n")
                cursor.execute("SELECT extension, SUM(size_bytes) as s FROM files GROUP BY extension ORDER BY s DESC LIMIT 10")
                for row in cursor.fetchall():
                    ext = row[0] if row[0] else "(no extension)"
                    size_mb = row[1] / (1024*1024)
                    f.write(f"{ext:<15} : {size_mb:,.2f} MB\n")
                    
                # Largest Files
                f.write("\nTop 10 Largest Files:\n")
                f.write("-" * 30 + "\n")
                cursor.execute("SELECT filename, folder_path, size_bytes FROM files ORDER BY size_bytes DESC LIMIT 10")
                for row in cursor.fetchall():
                    size_mb = row[2] / (1024*1024)
                    path = os.path.join(row[1], row[0])
                    f.write(f"{size_mb:,.2f} MB : {path}\n")

                # Oldest Files
                f.write("\nOldest 10 Files (by modification date):\n")
                f.write("-" * 30 + "\n")
                cursor.execute("SELECT filename, folder_path, modified_ts FROM files ORDER BY modified_ts ASC LIMIT 10")
                for row in cursor.fetchall():
                    try:
                        dt = datetime.fromtimestamp(row[2]).strftime('%Y-%m-%d %H:%M:%S')
                    except: dt = "Unknown"
                    path = os.path.join(row[1], row[0])
                    f.write(f"{dt} : {path}\n")
                    
            conn.close()
            return True, "Report Generated"
        except Exception as e:
            return False, str(e)

class ExportWorker(QThread):
    finished = pyqtSignal(bool, str) # success, message
    progress = pyqtSignal(int) # optional, maybe for row count

    def __init__(self, db_path, target_file, max_size_bytes, ignore_recycle):
        super().__init__()
        self.db_path = db_path
        self.target_file = target_file
        self.max_size_bytes = max_size_bytes
        self.ignore_recycle = ignore_recycle
        self.is_running = True

    def run(self):
        conn = None
        f = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = "SELECT * FROM files"
            if self.ignore_recycle:
                query += " WHERE folder_path NOT LIKE '%$RECYCLE.BIN%'"
                
            cursor.execute(query)
            
            base, ext = os.path.splitext(self.target_file)
            file_index = 1
            current_file_path = self.target_file
            
            f = open(current_file_path, 'w', newline='', encoding='utf-8')
            writer = csv.writer(f)
            
            header = [d[0] for d in cursor.description]
            writer.writerow(header)
            
            count = 0
            for row in cursor:
                if not self.is_running: break
                writer.writerow(row)
                count += 1
                
                if self.max_size_bytes > 0 and f.tell() >= self.max_size_bytes:
                    f.close()
                    file_index += 1
                    current_file_path = f"{base}_{file_index}{ext}"
                    f = open(current_file_path, 'w', newline='', encoding='utf-8')
                    writer = csv.writer(f)
                    writer.writerow(header)
            
            self.finished.emit(True, f"Export Complete. {count} records exported.")
            
        except Exception as e:
            self.finished.emit(False, str(e))
        finally:
            if f and not f.closed: f.close()
            if conn: conn.close()

    def stop(self):
        self.is_running = False

# --- Indexer Worker (With Crash Protection & Restart Fix) ---
class IndexerWorker(QThread):
    progress_signal = pyqtSignal(int) 
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    
    def __init__(self, db_path, ignore_recycle=True):
        super().__init__()
        self.db_path = db_path
        self.is_running = True
        self.exclusions = ['System Volume Information', 'Windows']
        if ignore_recycle:
            self.exclusions.append('$RECYCLE.BIN')

    def run(self):
        # --- FIX: Ensure flag is reset on run ---
        self.is_running = True
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files")
            conn.commit()
            
            count = 0
            batch_data = []
            batch_size = 1000
            drives = QDir.drives()
            for drive in drives:
                root_path = drive.absoluteFilePath()
                for root, dirs, files in os.walk(root_path):
                    if not self.is_running: break
                    
                    # Exclude based on user settings and system folders
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in self.exclusions]
                    
                    for file in files:
                        if not self.is_running: break
                        try:
                            full_path = os.path.join(root, file)
                            stat = os.stat(full_path)
                            batch_data.append((file, root, os.path.splitext(file)[1].lower(), stat.st_size, stat.st_mtime, stat.st_ctime))
                            count += 1
                            if len(batch_data) >= batch_size:
                                cursor.executemany('''INSERT INTO files (filename, folder_path, extension, size_bytes, modified_ts, created_ts) VALUES (?, ?, ?, ?, ?, ?)''', batch_data)
                                conn.commit()
                                batch_data = []
                                self.progress_signal.emit(count)
                        except (PermissionError, OSError):
                            continue
                if not self.is_running: break
            if batch_data:
                cursor.executemany('''INSERT INTO files (filename, folder_path, extension, size_bytes, modified_ts, created_ts) VALUES (?, ?, ?, ?, ?, ?)''', batch_data)
                conn.commit()
            
            self.finished_signal.emit()
            
        except Exception:
            self.error_signal.emit(traceback.format_exc())
        finally:
            if conn:
                conn.close()

    def stop(self):
        self.is_running = False

# --- Watchdog Event Handler ---
if HAS_WATCHDOG:
    class IndexEventHandler(FileSystemEventHandler):
        def __init__(self, db_path):
            self.db_path = db_path

        def _get_conn(self):
            return sqlite3.connect(self.db_path, timeout=30)

        def on_created(self, event):
            if event.is_directory: return
            try:
                conn = self._get_conn()
                cursor = conn.cursor()
                filename = os.path.basename(event.src_path)
                folder = os.path.dirname(event.src_path)
                ext = os.path.splitext(filename)[1].lower()
                stat = os.stat(event.src_path)
                
                cursor.execute('''INSERT INTO files (filename, folder_path, extension, size_bytes, modified_ts, created_ts) 
                                VALUES (?, ?, ?, ?, ?, ?)''', 
                                (filename, folder, ext, stat.st_size, stat.st_mtime, stat.st_ctime))
                conn.commit()
                conn.close()
            except: pass

        def on_deleted(self, event):
            if event.is_directory: return
            try:
                conn = self._get_conn()
                cursor = conn.cursor()
                filename = os.path.basename(event.src_path)
                folder = os.path.dirname(event.src_path)
                cursor.execute("DELETE FROM files WHERE filename=? AND folder_path=?", (filename, folder))
                conn.commit()
                conn.close()
            except: pass



# --- Search Worker (With Advanced Syntax) ---
class SearchWorker(QThread):
    results_ready = pyqtSignal(list)

    def __init__(self, db_path, query, ignore_recycle=True):
        super().__init__()
        self.db_path = db_path
        self.query = query
        self.ignore_recycle = ignore_recycle

    def run(self):
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            
            # Base Query
            sql = "SELECT filename, folder_path, size_bytes, modified_ts FROM files WHERE 1=1"
            
            # [FIX] Apply Recycle Bin Filter during Search Query
            if self.ignore_recycle:
                sql += " AND folder_path NOT LIKE '%$RECYCLE.BIN%'"
            
            params = []
            
            # --- Advanced Parsing ---
            tokens = self.query.split()
            for token in tokens:
                lower_token = token.lower()
                
                # Extension Filter (ext:jpg)
                if lower_token.startswith("ext:"):
                    ext = lower_token.split(":", 1)[1]
                    if not ext.startswith("."): ext = "." + ext
                    sql += " AND extension = ?"
                    params.append(ext)
                
                # Name Force (name:report)
                elif lower_token.startswith("name:"):
                    name = token.split(":", 1)[1]
                    sql += " AND filename LIKE ?"
                    params.append(f"%{name}%")
                    
                # Size Filter (size:>10MB, size:<500KB)
                elif lower_token.startswith("size:"):
                    val_str = lower_token.split(":", 1)[1]
                    operator = "="
                    if val_str.startswith(">"): 
                        operator = ">"
                        val_str = val_str[1:]
                    elif val_str.startswith("<"): 
                        operator = "<"
                        val_str = val_str[1:]
                    
                    # Convert units
                    multiplier = 1
                    if val_str.endswith("gb"): multiplier = 1024**3; val_str = val_str[:-2]
                    elif val_str.endswith("mb"): multiplier = 1024**2; val_str = val_str[:-2]
                    elif val_str.endswith("kb"): multiplier = 1024; val_str = val_str[:-2]
                    elif val_str.endswith("b"): val_str = val_str[:-1]
                    
                    try:
                        size_val = float(val_str) * multiplier
                        sql += f" AND size_bytes {operator} ?"
                        params.append(size_val)
                    except ValueError:
                        pass # Ignore invalid size

                # Date Filter (modified:2023-01-01, created:>2022-01-01)
                elif lower_token.startswith("modified:") or lower_token.startswith("created:"):
                    is_created = lower_token.startswith("created:")
                    col = "created_ts" if is_created else "modified_ts"
                    val_str = token.split(":", 1)[1]
                    
                    operator = "="
                    if val_str.startswith(">"): 
                        operator = ">"
                        val_str = val_str[1:]
                    elif val_str.startswith("<"): 
                        operator = "<"
                        val_str = val_str[1:]
                        
                    try:
                        dt = datetime.strptime(val_str, "%Y-%m-%d")
                        ts = dt.timestamp()
                        
                        if operator == ">":
                            # > Date means after the END of that date
                            sql += f" AND {col} > ?"
                            params.append(ts + 86400)
                        elif operator == "<":
                            # < Date means before the START of that date
                            sql += f" AND {col} < ?"
                            params.append(ts)
                        else:
                            # = Date means WITHIN that day
                            sql += f" AND {col} >= ? AND {col} < ?"
                            params.append(ts)
                            params.append(ts + 86400)
                    except ValueError:
                        pass 
                
                # Default: Partial Name Match
                else:
                    sql += " AND filename LIKE ?"
                    params.append(f"%{token}%")
            
            sql += " LIMIT 500"
            cursor.execute(sql, params)
            results = cursor.fetchall()
            conn.close()
            self.results_ready.emit(results)
        except Exception as e:
            print(f"Search Error: {e}")
            self.results_ready.emit([])

# --- Dialogs ---
class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("License Agreement")
        self.setModal(True)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        layout = QVBoxLayout(self)
        lbl = QLabel(f"{APP_NAME}\n\n{APP_COPYRIGHT}\n\nLicensed under MIT License.\n\nDo you accept the license?")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        link = QLabel("<a href='https://opensource.org/licenses/MIT'>View License</a>")
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        layout = QVBoxLayout(self)
        icon_label = QLabel()
        if os.path.exists(ICON_PATH):
            icon_label.setPixmap(QPixmap(ICON_PATH).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            icon_label.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon).pixmap(64, 64))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        layout.addWidget(QLabel(APP_NAME, alignment=Qt.AlignmentFlag.AlignCenter))
        layout.addWidget(QLabel(APP_VERSION, alignment=Qt.AlignmentFlag.AlignCenter))
        layout.addWidget(QLabel(APP_COPYRIGHT, alignment=Qt.AlignmentFlag.AlignCenter))
        
        # --- UPDATED LINK ---
        link_label = QLabel("<a href='https://sites.google.com/view/getproductivefast/file-manager'>About File Manager</a>")
        link_label.setOpenExternalLinks(True)
        link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(link_label)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)
        
class UpdateChecker(QThread):
    result_ready = pyqtSignal(bool, str, str, str) # success, version, url, notes

    def run(self):
        url = "https://api.github.com/repos/markstout/GPF-File-Manager/releases/latest"
        try:
            req = urllib.request.Request(url)
            # Add User-Agent header which is often required by GitHub API
            req.add_header('User-Agent', 'File-Mgr-Ongoing-Updater')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                
                tag_name = data.get("tag_name", "").strip()
                # Assuming tag format like "v0.8" or "0.8"
                remote_ver_str = tag_name.lstrip("v")
                
                current_ver_str = APP_VERSION.split()[1] # "Version 0.7 1/5/2026" -> "0.7"
                
                # Simple version comparison
                remote_parts = [int(x) for x in remote_ver_str.split(".")]
                current_parts = [int(x) for x in current_ver_str.split(".")]
                
                is_newer = remote_parts > current_parts
                
                assets = data.get("assets", [])
                download_url = ""
                # Prefer .exe asset if available
                for asset in assets:
                    if asset["name"].endswith(".exe"):
                        download_url = asset["browser_download_url"]
                        break
                # Fallback to first asset if no exe found, or empty if no assets
                if not download_url and assets:
                    download_url = assets[0]["browser_download_url"]
                
                notes = data.get("body", "No release notes available.")
                
                self.result_ready.emit(is_newer, tag_name, download_url, notes)
                
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.result_ready.emit(False, "", "", "No releases found (or repository is private/missing).")
            elif e.code == 403:
                self.result_ready.emit(False, "", "", "API Rate Limit Exceeded or Access Denied.")
            else:
                self.result_ready.emit(False, "", "", f"HTTP Error {e.code}: {e.reason}")
        except Exception as e:
            self.result_ready.emit(False, "", "", str(e))

class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str) # success, file_path

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.is_running = True

    def run(self):
        try:
            # Get filename from URL
            filename = self.url.split("/")[-1]
            temp_dir = os.environ.get("TEMP", os.getcwd())
            save_path = os.path.join(temp_dir, filename)
            
            req = urllib.request.Request(self.url)
            req.add_header('User-Agent', 'File-Mgr-Ongoing-Updater')
             
            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                block_size = 8192
                downloaded = 0
                
                with open(save_path, 'wb') as f:
                    while self.is_running:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        f.write(buffer)
                        downloaded += len(buffer)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress.emit(percent)
                            
            if self.is_running:
                self.finished.emit(True, save_path)
            else:
                if os.path.exists(save_path): os.remove(save_path)
                self.finished.emit(False, "Cancelled")
                
        except Exception as e:
            self.finished.emit(False, str(e))

    def stop(self):
        self.is_running = False

class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Check for Updates")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300) # Increased height per user request
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        layout = QVBoxLayout(self)

        # Version Info
        lbl_ver = QLabel(f"Current version: {APP_VERSION}")
        lbl_ver.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_ver)
        
        self.lbl_status = QLabel("Checking for updates...")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        
        self.txt_notes = QTextEdit()
        self.txt_notes.setReadOnly(True)
        self.txt_notes.hide()
        layout.addWidget(self.txt_notes)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        layout.addSpacing(10)
        
        # Buttons
        self.btns = QDialogButtonBox()
        self.btn_update = self.btns.addButton("Update Now", QDialogButtonBox.ButtonRole.ActionRole)
        self.btn_update.setEnabled(False)
        self.btn_update.hide()
        self.btn_update.clicked.connect(self.start_update)
        
        self.btn_close = self.btns.addButton(QDialogButtonBox.StandardButton.Close)
        self.btn_close.clicked.connect(self.close)
        
        layout.addWidget(self.btns)
        
        self.check_thread = UpdateChecker()
        self.check_thread.result_ready.connect(self.on_check_finished)
        self.check_thread.start()
        
        self.download_url = ""
        self.download_worker = None

    def on_check_finished(self, is_newer, version, url, notes):
        if is_newer:
            self.lbl_status.setText(f"A new version is available: {version}")
            self.txt_notes.setMarkdown(notes)
            self.txt_notes.show()
            self.download_url = url
            if url:
                self.btn_update.show()
                self.btn_update.setEnabled(True)
            else:
                self.lbl_status.setText(f"A new version ({version}) is available, but no download URL was found.")
        elif version:
            self.lbl_status.setText(f"You are up to date! (Latest: {version})")
        else:
            self.lbl_status.setText(f"Error checking for updates: {notes}") # notes contains error msg here

    def start_update(self):
        if not self.download_url: return
        
        self.btn_update.setEnabled(False)
        self.lbl_status.setText("Downloading update...")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        
        self.download_worker = DownloadWorker(self.download_url)
        self.download_worker.progress.connect(self.progress_bar.setValue)
        self.download_worker.finished.connect(self.on_download_finished)
        self.download_worker.start()
        
    def on_download_finished(self, success, path_or_msg):
        self.progress_bar.hide()
        if success:
            self.lbl_status.setText("Download complete. Launching installer...")
            try:
                os.startfile(path_or_msg)
                QApplication.quit()
            except Exception as e:
                QMessageBox.critical(self, "Update Error", f"Could not launch installer:\n{e}")
                self.lbl_status.setText(f"Installer saved to: {path_or_msg}")
                self.btn_update.setEnabled(True)
        else:
            QMessageBox.critical(self, "Download Error", f"Download failed:\n{path_or_msg}")
            self.lbl_status.setText("Download failed.")
            self.btn_update.setEnabled(True)

    def closeEvent(self, event):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.stop()
            self.download_worker.wait()
        super().closeEvent(event)

# --- NEW: Search Help Dialog ---
class SearchHelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Syntax Cheat Sheet")
        self.resize(600, 500)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        layout = QVBoxLayout(self)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml("""
            <h3>🔍 Search Syntax Cheat Sheet</h3>
            <p><b>Logic:</b> Terms are combined with <b>AND</b> logic (e.g., <code>report ext:pdf</code>).</p>
            <table border="1" cellpadding="4" cellspacing="0" width="100%">
              <tr><th align="left">Filter</th><th align="left">Syntax</th><th align="left">Description</th></tr>
              <tr><td><b>Extension</b></td><td>ext:jpg</td><td>Finds files with specific extensions.</td></tr>
              <tr><td><b>Size</b></td><td>size:>500MB</td><td>Units: B, KB, MB, GB. Operators: &gt; (greater), &lt; (less).</td></tr>
              <tr><td><b>Modified</b></td><td>modified:2025-11-22</td><td>Format: YYYY-MM-DD. Operators: &gt;, &lt;.</td></tr>
              <tr><td><b>Created</b></td><td>created:2025-01-01</td><td>Format: YYYY-MM-DD. Operators: &gt;, &lt;.</td></tr>
              <tr><td><b>Exact Name</b></td><td>name:filename</td><td>Forces a filename match (useful for colons).</td></tr>
            </table>
            <h3>💡 Examples</h3>
            <ul>
            <li><b>Large Videos:</b> <code>ext:mp4 size:>1GB</code></li>
            <li><b>Cleanup Temp:</b> <code>ext:tmp size:<1KB</code></li>
            <li><b>Recent Images:</b> <code>ext:jpg modified:>2025-01-01</code></li>
            </ul>
        """)
        layout.addWidget(text_edit)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.close)
        layout.addWidget(btns)

class FieldsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fields & Profiles")
        self.resize(1000, 600)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        
        self.parent_ref = parent
        
        # --- Data Init ---
        if "profiles" not in self.parent_ref.settings:
            self.parent_ref.settings["profiles"] = {
                "Default": {
                    "display": ["Name", "Size", "Type", "Date Modified"],
                    "props": ["Name", "Size", "Type", "Date Modified", "Date Created"]
                }
            }
        
        self.profiles_data = self.parent_ref.settings["profiles"]
        
        main_layout = QVBoxLayout(self)
        
        # --- TOP: Profile Management ---
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Profile:"))
        
        self.combo_profile = QComboBox()
        self.combo_profile.addItems(sorted(self.profiles_data.keys()))
        self.combo_profile.currentTextChanged.connect(self.load_profile)
        profile_layout.addWidget(self.combo_profile)
        
        btn_new = QPushButton("New Profile")
        btn_new.clicked.connect(self.new_profile)
        profile_layout.addWidget(btn_new)
        
        btn_del = QPushButton("Delete Profile")
        btn_del.clicked.connect(self.delete_profile)
        profile_layout.addWidget(btn_del)
        
        main_layout.addLayout(profile_layout)
        
        # --- CONTENT: 3 Columns ---
        content_layout = QHBoxLayout()
        
        # 1. Left: Available
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Available Fields"))
        self.tree_avail = QTreeWidget()
        self.tree_avail.setHeaderHidden(True)
        self.tree_avail.setDragEnabled(True)
        self.tree_avail.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        
        for category, fields in FIELD_DEFINITIONS.items():
            cat_item = QTreeWidgetItem(self.tree_avail)
            cat_item.setText(0, category)
            cat_item.setExpanded(True)
            for f in fields:
                field_item = QTreeWidgetItem(cat_item)
                field_item.setText(0, f)
        left_layout.addWidget(self.tree_avail)
        content_layout.addLayout(left_layout)
        
        # 2. Middle: Display Columns
        mid_layout = QVBoxLayout()
        mid_layout.addWidget(QLabel("Columns (Display View)"))
        self.list_display = QListWidget()
        self.list_display.setDragEnabled(True)
        self.list_display.setAcceptDrops(True)
        self.list_display.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.list_display.setDefaultDropAction(Qt.DropAction.MoveAction)
        mid_layout.addWidget(self.list_display)
        content_layout.addLayout(mid_layout)
        
        # 3. Right: Properties Pane
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Properties Pane Fields"))
        self.list_props = QListWidget()
        self.list_props.setDragEnabled(True)
        self.list_props.setAcceptDrops(True)
        self.list_props.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.list_props.setDefaultDropAction(Qt.DropAction.MoveAction)
        right_layout.addWidget(self.list_props)
        content_layout.addLayout(right_layout)
        
        main_layout.addLayout(content_layout)
        
        # Hint & Remove Button
        lbl_hint = QLabel("Drag fields from Left to Center/Right lists. Drag within lists to re-order.")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_hint.setStyleSheet("color: gray; font-style: italic;")
        main_layout.addWidget(lbl_hint)
        
        del_btn = QPushButton("Remove Selected Field from Lists")
        del_btn.clicked.connect(self.delete_field)
        main_layout.addWidget(del_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Dialog Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.save_current_and_accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)
        
        # Initial Load
        current_profile_name = "Default"
        # If pane is active, try to select its profile
        if self.parent_ref.active_pane:
            current_profile_name = self.parent_ref.active_pane.current_profile
            
        if current_profile_name in self.profiles_data:
            self.combo_profile.setCurrentText(current_profile_name)
        else:
            self.combo_profile.setCurrentIndex(0)
            
        # [FIX] Explicitly load the profile data to populate lists immediately
        self.load_profile(self.combo_profile.currentText())
            
    def load_profile(self, name):
        if not name: return
        data = self.profiles_data.get(name, {})
        
        self.list_display.clear()
        self.list_display.addItems(data.get("display", []))
        
        self.list_props.clear()
        self.list_props.addItems(data.get("props", []))

    def save_current_to_memory(self):
        name = self.combo_profile.currentText()
        if not name: return
        
        display_items = [self.list_display.item(i).text() for i in range(self.list_display.count())]
        props_items = [self.list_props.item(i).text() for i in range(self.list_props.count())]
        
        # Remove duplicates
        display_items = list(dict.fromkeys(display_items))
        props_items = list(dict.fromkeys(props_items))
        
        self.profiles_data[name] = {
            "display": display_items,
            "props": props_items
        }
        
    def new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Profile Name:")
        if ok and name:
            if name in self.profiles_data:
                QMessageBox.warning(self, "Error", "Profile name already exists.")
                return
            # Inherit from Default if possible
            default_data = self.profiles_data.get("Default", {"display":[], "props":[]})
            self.profiles_data[name] = {
                "display": list(default_data["display"]),
                "props": list(default_data["props"])
            }
            self.combo_profile.addItem(name)
            self.combo_profile.setCurrentText(name)

    def delete_profile(self):
        name = self.combo_profile.currentText()
        if name == "Default":
            QMessageBox.warning(self, "Error", "Cannot delete Default profile.")
            return
        
        del self.profiles_data[name]
        self.combo_profile.removeItem(self.combo_profile.currentIndex())
        
    def delete_field(self):
        for lst in [self.list_display, self.list_props]:
            for item in lst.selectedItems():
                lst.takeItem(lst.row(item))

    def save_current_and_accept(self):
        self.save_current_to_memory()
        self.parent_ref.settings["profiles"] = self.profiles_data
        
        # Refresh all panes to reflect changes (update their combo boxes)
        for pane in self.parent_ref.panes:
            pane.refresh_profiles()
            pane.apply_column_settings()
            
        self.accept()

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        
        # --- FIX: robustly get current settings ---
        self.settings = parent.settings if parent else {}
        current_theme = self.settings.get("theme", "light").lower()
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark"])
        self.theme_combo.setCurrentText(current_theme) 
        form.addRow("Theme:", self.theme_combo)
        
        # Font Size
        self.font_combo = QComboBox()
        self.font_combo.addItems([str(i) for i in range(8, 21)])
        self.font_combo.setCurrentText(str(self.settings.get("font_size", 10)))
        form.addRow("Font Size (pt):", self.font_combo)
        
        # Startup
        self.startup_check = QCheckBox("Launch at Startup")
        self.startup_check.setChecked(self.settings.get("launch_at_startup", False))
        if os.path.exists(get_startup_shortcut_path()):
             self.startup_check.setChecked(True)
        form.addRow(self.startup_check)
        
        # Max Dump Size
        self.dump_size = QSpinBox()
        self.dump_size.setRange(1, 10000) # 1MB to 10GB
        self.dump_size.setSuffix(" MB")
        # Convert stored bytes to MB for display (default 70MB)
        current_bytes = self.settings.get("max_dump_size", 73400320) # 70MB
        mb_val = int(current_bytes / (1024 * 1024))
        if mb_val < 10: mb_val = 70 # Sanity check / Fix for user
        self.dump_size.setValue(mb_val)
        form.addRow("Max File Size for Export:", self.dump_size)
        
        # Ignore Recycle Bin
        self.recycle_check = QCheckBox("Ignore Recycle Bin during Search and Export")
        self.recycle_check.setChecked(self.settings.get("ignore_recycle_bin", True))
        form.addRow(self.recycle_check)
        
        # Show Hidden Files
        self.hidden_check = QCheckBox("See Hidden Folderr")
        self.hidden_check.setChecked(self.settings.get("show_hidden", False))
        form.addRow(self.hidden_check)
        
        # Custom Editor
        self.editor_path = QLineEdit()
        self.editor_path.setPlaceholderText("No custom editor selected")
        self.editor_path.setText(self.settings.get("custom_editor_path", ""))
        # self.editor_path.setReadOnly(True) # User can type or paste if they want
        
        btn_browse_editor = QPushButton("Browse...")
        btn_browse_editor.clicked.connect(self.browse_editor)
        
        editor_layout = QHBoxLayout()
        editor_layout.addWidget(self.editor_path)
        editor_layout.addWidget(btn_browse_editor)
        form.addRow("Custom Editor:", editor_layout)
        
        # Use Internal Markdown Viewer/Editor
        self.internal_md_check = QCheckBox("Use Internal Markdown Viewer/Editor")
        self.internal_md_check.setChecked(self.settings.get("use_internal_md", False))
        form.addRow(self.internal_md_check)
        
        # Use Internal Text Editor
        self.internal_txt_check = QCheckBox("Use Internal Text Editor")
        self.internal_txt_check.setChecked(self.settings.get("use_internal_txt", True))
        form.addRow(self.internal_txt_check)
        
        # Include HTML files
        self.include_html_check = QCheckBox("Include HTML files")
        self.include_html_check.setChecked(self.settings.get("include_html", False))
        self.include_html_check.setEnabled(self.internal_txt_check.isChecked())
        form.addRow("   ", self.include_html_check)
        
        # Connect toggling to enable/disable Include HTML files option
        self.internal_txt_check.toggled.connect(self.include_html_check.setEnabled)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
    def browse_editor(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Editor Application", "", "Executables (*.exe);;All Files (*.*)")
        if path:
            self.editor_path.setText(path)
        
    def get_data(self):
        return {
            "theme": self.theme_combo.currentText(),
            "font_size": int(self.font_combo.currentText()),
            "launch_at_startup": self.startup_check.isChecked(),
            "max_dump_size": self.dump_size.value() * 1024 * 1024,
            "ignore_recycle_bin": self.recycle_check.isChecked(),
            "show_hidden": self.hidden_check.isChecked(),
            "custom_editor_path": self.editor_path.text(),
            "use_internal_md": self.internal_md_check.isChecked(),
            "use_internal_txt": self.internal_txt_check.isChecked(),
            "include_html": self.include_html_check.isChecked()
        }

class PropertiesDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Properties")
        self.setMinimumWidth(350)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        info = QFileInfo(path)
        settings = {}
        if parent and hasattr(parent.window(), 'settings'):
            settings = parent.window().settings
        
        # Profile Logic for Dialog? Default to Default profile for now or use passed logic
        fields = ["Name", "Size", "Type", "Date Modified"]
        if "profiles" in settings and "Default" in settings["profiles"]:
            fields = settings["profiles"]["Default"]["props"]

        top_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_prov = QFileIconProvider()
        icon_label.setPixmap(icon_prov.icon(info).pixmap(48, 48))
        top_layout.addWidget(icon_label)
        name_label = QLabel(info.fileName())
        name_label.setStyleSheet("font-weight: bold;")
        name_label.setWordWrap(True)
        top_layout.addWidget(name_label)
        top_layout.addStretch()
        layout.addLayout(top_layout)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # Metadata loading for dialog
        meta = MetadataLoader.get_metadata(path)
        
        for field in fields:
            value = ""
            if field == "Name": value = info.fileName()
            elif field == "Size":
                size = info.size()
                if size < 1024: value = f"{size} B"
                elif size < 1024**2: value = f"{size/1024:.1f} KB"
                else: value = f"{size/1024**2:.1f} MB"
                if info.isDir(): value = "--"
            elif field == "Type": value = "Folder" if info.isDir() else info.suffix().upper() + " File"
            elif field == "Date Modified": value = info.lastModified().toString("yyyy-MM-dd HH:mm")
            elif field == "Date Created": value = info.birthTime().toString("yyyy-MM-dd HH:mm") # FIX
            elif field == "Date Accessed": value = info.lastRead().toString("yyyy-MM-dd HH:mm") # FIX
            elif field == "Owner": value = info.owner()
            elif field == "Permissions":
                perms = []
                p = info.permissions()
                if p & QFileInfo.Permission.ReadUser: perms.append("R")
                if p & QFileInfo.Permission.WriteUser: perms.append("W")
                if p & QFileInfo.Permission.ExeUser: perms.append("X")
                value = "".join(perms)
            
            # Extended Metadata Check
            elif field in meta:
                value = str(meta[field])
                
            if value:
                lbl_val = QLabel(value)
                lbl_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                form.addRow(f"{field}:", lbl_val)
                
        # --- NEW: Shortcut Properties ---
        if info.suffix().lower() == 'lnk':
            target, start_in = get_lnk_properties(path)
            if target:
                lbl_target = QLabel(target)
                lbl_target.setWordWrap(True)
                lbl_target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                form.addRow("Target:", lbl_target)
            if start_in:
                lbl_start = QLabel(start_in)
                lbl_start.setWordWrap(True)
                lbl_start.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                form.addRow("Start In:", lbl_start)
                
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.close)
        layout.addWidget(btns)

class MarkdownViewerDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.is_modified = False
        
        # Extract settings and font size
        settings = {}
        if parent and hasattr(parent.window(), 'settings'):
            settings = parent.window().settings
        font_size = settings.get("font_size", 10)
        
        self.setWindowTitle(f"Markdown Viewer - {os.path.basename(path)}")
        self.setMinimumSize(950, 680)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # --- 1. TOOLBAR ---
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setStyleSheet("QToolBar { spacing: 10px; padding: 2px; }")
        
        self.act_edit = self.toolbar.addAction("Edit")
        self.act_edit.setCheckable(True)
        self.act_edit.triggered.connect(self.toggle_edit_mode)
        
        self.act_search = self.toolbar.addAction("Search")
        self.act_search.setCheckable(True)
        self.act_search.triggered.connect(self.toggle_search_panel)
        
        layout.addWidget(self.toolbar)
        
        # --- 2. SEARCH PANEL ---
        self.search_panel = QFrame()
        self.search_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.search_panel.setStyleSheet("QFrame { background-color: rgba(128, 128, 128, 0.1); border-radius: 4px; padding: 4px; }")
        self.search_panel.hide()
        
        search_layout = QHBoxLayout(self.search_panel)
        search_layout.setContentsMargins(6, 4, 6, 4)
        search_layout.setSpacing(8)
        
        lbl_search = QLabel("Find:")
        search_layout.addWidget(lbl_search)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.find_text_next)
        search_layout.addWidget(self.search_input)
        
        self.btn_find_prev = QPushButton("Previous")
        self.btn_find_prev.clicked.connect(self.find_text_prev)
        search_layout.addWidget(self.btn_find_prev)
        
        self.btn_find_next = QPushButton("Next")
        self.btn_find_next.clicked.connect(self.find_text_next)
        search_layout.addWidget(self.btn_find_next)
        
        self.lbl_search_status = QLabel("")
        self.lbl_search_status.setMinimumWidth(80)
        search_layout.addWidget(self.lbl_search_status)
        
        btn_search_close = QPushButton("X")
        btn_search_close.setFlat(True)
        btn_search_close.setFixedWidth(20)
        btn_search_close.clicked.connect(self.hide_search_panel)
        search_layout.addWidget(btn_search_close)
        
        layout.addWidget(self.search_panel)
        
        # --- 3. SPLITTER (DUAL PANE) ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Pane (Rendered)
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.splitter.addWidget(self.text_browser)
        
        # Right Pane (Edit)
        self.text_editor = QTextEdit()
        
        # Clean monospaced font
        editor_font = QFont("Consolas")
        if not editor_font.fromString("Consolas"):
            editor_font = QFont("Monospace")
        editor_font.setStyleHint(QFont.StyleHint.Monospace)
        editor_font.setPointSize(font_size)
        self.text_editor.setFont(editor_font)
        
        # Standard tab size (4 spaces instead of huge tab stops)
        try:
            self.text_editor.setTabStopDistance(QFontMetrics(editor_font).horizontalAdvance(' ') * 4)
        except AttributeError:
            self.text_editor.setTabStopWidth(QFontMetrics(editor_font).width(' ') * 4)
            
        self.text_editor.hide()
        self.text_editor.textChanged.connect(self.on_text_edited)
        self.splitter.addWidget(self.text_editor)
        
        # Splitter sizing
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        
        layout.addWidget(self.splitter)
        
        # --- 4. THEME STYLING ---
        theme = settings.get("theme", "light").lower()
        
        if theme == "dark":
            css = """
                body {
                    color: #e0e0e0;
                    background-color: #1e1e1e;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11pt;
                    line-height: 1.5;
                    margin: 16px;
                }
                h1 {
                    color: #4fc3f7;
                    font-size: 20pt;
                    font-weight: bold;
                    margin-top: 18px;
                    margin-bottom: 10px;
                    border-bottom: 1px solid #444;
                    padding-bottom: 5px;
                }
                h2 {
                    color: #e0e0e0;
                    font-size: 16pt;
                    font-weight: bold;
                    margin-top: 16px;
                    margin-bottom: 8px;
                    border-bottom: 1px solid #333;
                    padding-bottom: 3px;
                }
                h3 {
                    color: #cccccc;
                    font-size: 13pt;
                    font-weight: bold;
                    margin-top: 14px;
                    margin-bottom: 6px;
                }
                h4, h5, h6 {
                    color: #b0b0b0;
                    font-size: 11pt;
                    font-weight: bold;
                    margin-top: 12px;
                    margin-bottom: 4px;
                }
                p, li {
                    margin-top: 0px;
                    margin-bottom: 8px;
                }
                ul, ol {
                    margin-top: 0px;
                    margin-bottom: 8px;
                    padding-left: 20px;
                }
                code {
                    font-family: 'Consolas', 'Courier New', monospace;
                    background-color: #333333;
                    color: #f48fb1;
                    padding: 2px 4px;
                    border-radius: 3px;
                }
                pre {
                    font-family: 'Consolas', 'Courier New', monospace;
                    background-color: #333333;
                    border: 1px solid #444;
                    padding: 10px;
                    margin: 12px 0px;
                    border-radius: 4px;
                }
                pre code {
                    background-color: transparent;
                    color: #e0e0e0;
                    padding: 0px;
                }
                blockquote {
                    border-left: 4px solid #4fc3f7;
                    background-color: #2b2b2b;
                    padding: 8px 12px;
                    color: #aaaaaa;
                    font-style: italic;
                    margin: 12px 0px;
                }
                a {
                    color: #4fc3f7;
                    text-decoration: none;
                }
                table {
                    border-collapse: collapse;
                    width: 100%;
                    margin: 12px 0px;
                }
                th, td {
                    border: 1px solid #444;
                    padding: 8px;
                    text-align: left;
                }
                th {
                    background-color: #333333;
                    font-weight: bold;
                }
            """
        else:
            css = """
                body {
                    color: #333333;
                    background-color: white;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    font-size: 11pt;
                    line-height: 1.5;
                    margin: 16px;
                }
                h1 {
                    color: #0078d7;
                    font-size: 20pt;
                    font-weight: bold;
                    margin-top: 18px;
                    margin-bottom: 10px;
                    border-bottom: 1px solid #eee;
                    padding-bottom: 5px;
                }
                h2 {
                    color: #111111;
                    font-size: 16pt;
                    font-weight: bold;
                    margin-top: 16px;
                    margin-bottom: 8px;
                    border-bottom: 1px solid #f0f0f0;
                    padding-bottom: 3px;
                }
                h3 {
                    color: #444444;
                    font-size: 13pt;
                    font-weight: bold;
                    margin-top: 14px;
                    margin-bottom: 6px;
                }
                h4, h5, h6 {
                    color: #555555;
                    font-size: 11pt;
                    font-weight: bold;
                    margin-top: 12px;
                    margin-bottom: 4px;
                }
                p, li {
                    margin-top: 0px;
                    margin-bottom: 8px;
                }
                ul, ol {
                    margin-top: 0px;
                    margin-bottom: 8px;
                    padding-left: 20px;
                }
                code {
                    font-family: 'Consolas', 'Courier New', monospace;
                    background-color: #f4f4f4;
                    color: #c7254e;
                    padding: 2px 4px;
                    border-radius: 3px;
                }
                pre {
                    font-family: 'Consolas', 'Courier New', monospace;
                    background-color: #f4f4f4;
                    border: 1px solid #ddd;
                    padding: 10px;
                    margin: 12px 0px;
                    border-radius: 4px;
                }
                pre code {
                    background-color: transparent;
                    color: #333333;
                    padding: 0px;
                }
                blockquote {
                    border-left: 4px solid #0078d7;
                    background-color: #f9f9f9;
                    padding: 8px 12px;
                    color: #555555;
                    font-style: italic;
                    margin: 12px 0px;
                }
                a {
                    color: #0078d7;
                    text-decoration: none;
                }
                table {
                    border-collapse: collapse;
                    width: 100%;
                    margin: 12px 0px;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }
                th {
                    background-color: #f4f4f4;
                    font-weight: bold;
                }
            """
        
        # Scale headers proportionally based on base font size
        h1_size = int(font_size * 1.8)
        h2_size = int(font_size * 1.45)
        h3_size = int(font_size * 1.18)
        
        css = css.replace("font-size: 11pt;", f"font-size: {font_size}pt;")
        css = css.replace("font-size: 20pt;", f"font-size: {h1_size}pt;")
        css = css.replace("font-size: 16pt;", f"font-size: {h2_size}pt;")
        css = css.replace("font-size: 13pt;", f"font-size: {h3_size}pt;")
        
        self.text_browser.document().setDefaultStyleSheet(css)
        
        # Load and render markdown file
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.text_editor.setPlainText(content)
            self.text_browser.setMarkdown(content)
            self.is_modified = False
        except Exception as e:
            self.text_browser.setHtml(f"<h3>Error loading file</h3><p>{str(e)}</p>")
            
        # --- 5. BOTTOM ACTIONS ROW ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(4, 4, 4, 4)
        
        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_file)
        bottom_layout.addWidget(self.btn_save)
        
        self.btn_save_as = QPushButton("Save As...")
        self.btn_save_as.clicked.connect(self.save_file_as)
        bottom_layout.addWidget(self.btn_save_as)
        
        self.btn_help = QPushButton("Help")
        self.btn_help.clicked.connect(self.show_markdown_help)
        bottom_layout.addWidget(self.btn_help)
        
        bottom_layout.addStretch()
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        bottom_layout.addWidget(self.btn_close)
        
        # Hide editing action buttons initially (only shown in Edit Mode)
        self.btn_save.hide()
        self.btn_save_as.hide()
        self.btn_help.hide()
        
        layout.addLayout(bottom_layout)

    def show_markdown_help(self):
        MarkdownHelpDialog(self).exec()

    def toggle_edit_mode(self, checked):
        if checked:
            self.text_editor.show()
            self.splitter.setSizes([450, 450])
            self.text_editor.setFocus()
            self.btn_save.show()
            self.btn_save_as.show()
            self.btn_help.show()
        else:
            self.text_editor.hide()
            self.btn_save.hide()
            self.btn_save_as.hide()
            self.btn_help.hide()

    def toggle_search_panel(self, checked):
        if checked:
            self.search_panel.show()
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            self.search_panel.hide()
            self.lbl_search_status.setText("")

    def hide_search_panel(self):
        self.search_panel.hide()
        self.act_search.setChecked(False)
        self.lbl_search_status.setText("")

    def on_text_edited(self):
        self.is_modified = True
        scroll_bar = self.text_browser.verticalScrollBar()
        scroll_pos = scroll_bar.value()
        
        content = self.text_editor.toPlainText()
        self.text_browser.setMarkdown(content)
        
        # Restore scrollbar position after layout resolves
        QTimer.singleShot(0, lambda: scroll_bar.setValue(scroll_pos))

    def on_search_text_changed(self, text):
        if not text:
            self.lbl_search_status.setText("")
            return
        self.find_text(forward=True, is_incremental=True)

    def find_text_next(self):
        self.find_text(forward=True)

    def find_text_prev(self):
        self.find_text(forward=False)

    def find_text(self, forward=True, is_incremental=False):
        text = self.search_input.text()
        if not text:
            self.lbl_search_status.setText("")
            return
            
        widget = self.text_editor if self.text_editor.isVisible() else self.text_browser
        
        from PyQt6.QtGui import QTextDocument, QTextCursor
        flags = QTextDocument.FindFlag(0)
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
            
        found = widget.find(text, flags)
        if found:
            self.lbl_search_status.setText("Found")
            self.lbl_search_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            # Skip wrap-around prompts for typing incrementally
            if is_incremental:
                self.lbl_search_status.setText("Not found")
                self.lbl_search_status.setStyleSheet("color: red;")
                return
                
            # Wrap around search
            cursor = widget.textCursor()
            if forward:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            widget.setTextCursor(cursor)
            
            found = widget.find(text, flags)
            if found:
                self.lbl_search_status.setText("Wrapped")
                self.lbl_search_status.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.lbl_search_status.setText("Not found")
                self.lbl_search_status.setStyleSheet("color: red;")

    def save_file(self):
        content = self.text_editor.toPlainText()
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.is_modified = False
            QMessageBox.information(self, "Saved", "File saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file: {e}")

    def save_file_as(self):
        default_name = self.path
        new_path, _ = QFileDialog.getSaveFileName(
            self, "Save File As", default_name, "Markdown Files (*.md);;All Files (*)"
        )
        if new_path:
            content = self.text_editor.toPlainText()
            try:
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.path = new_path
                self.setWindowTitle(f"Markdown Viewer - {os.path.basename(new_path)}")
                self.is_modified = False
                self.text_browser.setMarkdown(content)
                QMessageBox.information(self, "Saved", "File saved successfully as new file.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file: {e}")

    def closeEvent(self, event):
        if self.is_modified:
            reply = QMessageBox.question(
                self, 
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_file()
                event.accept()
            elif reply == QMessageBox.StandardButton.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# --- Helper: Is Text File ---
def is_text_file(path):
    if not path or not os.path.isfile(path):
        return False
    # Standard text extensions
    text_extensions = {
        '.txt', '.py', '.json', '.csv', '.ini', '.cfg', '.bat', '.cmd', 
        '.md', '.html', '.xml', '.css', '.js', '.yaml', '.yml', '.sh', 
        '.log', '.sql', '.c', '.cpp', '.h', '.hpp', '.java', '.cs', 
        '.go', '.rs', '.ts', '.properties', '.conf'
    }
    ext = os.path.splitext(path)[1].lower()
    if ext in text_extensions:
        return True
    # Fallback content check
    try:
        if os.path.getsize(path) > 10 * 1024 * 1024: # Avoid huge files
            return False
        with open(path, 'rb') as f:
            chunk = f.read(4096)
            if b'\x00' in chunk:
                return False
            try:
                chunk.decode('utf-8')
                return True
            except UnicodeDecodeError:
                return False
    except Exception:
        return False

# --- Helper: Custom Text Editor Dialog ---
# --- Helper: Custom Text Editor Dialog ---
class TextEditorDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.is_modified = False
        
        self.setWindowTitle(f"Text Editor - {os.path.basename(path)}")
        self.setMinimumSize(850, 620)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # --- 1. TOP COMMAND BAR ---
        self.toolbar_layout = QHBoxLayout()
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_layout.setSpacing(6)
        
        self.btn_cut = QPushButton("Cut")
        self.btn_copy = QPushButton("Copy")
        self.btn_paste = QPushButton("Paste")
        self.btn_delete = QPushButton("Delete")
        self.btn_select_all = QPushButton("Select All")
        self.btn_find = QPushButton("Find")
        
        # Set shortcut keys
        self.btn_cut.setShortcut(QKeySequence("Ctrl+X"))
        self.btn_copy.setShortcut(QKeySequence("Ctrl+C"))
        self.btn_paste.setShortcut(QKeySequence("Ctrl+V"))
        self.btn_delete.setShortcut(QKeySequence("Del"))
        self.btn_select_all.setShortcut(QKeySequence("Ctrl+A"))
        self.btn_find.setShortcut(QKeySequence("Ctrl+F"))
        
        # Tooltips to inform the user about the shortcuts
        self.btn_cut.setToolTip("Cut selected text (Ctrl+X)")
        self.btn_copy.setToolTip("Copy selected text (Ctrl+C)")
        self.btn_paste.setToolTip("Paste from clipboard (Ctrl+V)")
        self.btn_delete.setToolTip("Delete selected text or character (Del)")
        self.btn_select_all.setToolTip("Select all text (Ctrl+A)")
        self.btn_find.setToolTip("Find text (Ctrl+F)")
        
        # Ensure buttons have clean style and dynamic widths
        for btn in [self.btn_cut, self.btn_copy, self.btn_paste, self.btn_delete, self.btn_select_all, self.btn_find]:
            self.toolbar_layout.addWidget(btn)
            
        self.toolbar_layout.addStretch()
        layout.addLayout(self.toolbar_layout)
        
        # --- 2. SEARCH PANEL ---
        self.search_panel = QFrame()
        self.search_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.search_panel.hide()
        
        search_layout = QHBoxLayout(self.search_panel)
        search_layout.setContentsMargins(6, 4, 6, 4)
        search_layout.setSpacing(8)
        
        lbl_search = QLabel("Find:")
        search_layout.addWidget(lbl_search)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.find_text_next)
        search_layout.addWidget(self.search_input)
        
        self.btn_find_prev = QPushButton("Previous")
        self.btn_find_prev.clicked.connect(self.find_text_prev)
        self.btn_find_prev.setShortcut(QKeySequence("Shift+F3"))
        self.btn_find_prev.setToolTip("Find previous occurrence (Shift+F3)")
        search_layout.addWidget(self.btn_find_prev)
        
        self.btn_find_next = QPushButton("Next")
        self.btn_find_next.clicked.connect(self.find_text_next)
        self.btn_find_next.setShortcut(QKeySequence("F3"))
        self.btn_find_next.setToolTip("Find next occurrence (F3)")
        search_layout.addWidget(self.btn_find_next)
        
        self.lbl_search_status = QLabel("")
        self.lbl_search_status.setMinimumWidth(80)
        search_layout.addWidget(self.lbl_search_status)
        
        btn_search_close = QPushButton("X")
        btn_search_close.setFlat(True)
        btn_search_close.setFixedWidth(20)
        btn_search_close.clicked.connect(self.hide_search_panel)
        search_layout.addWidget(btn_search_close)
        
        layout.addWidget(self.search_panel)
        
        # --- 3. TEXT EDITOR ---
        self.text_editor = QTextEdit()
        # Clean monospaced font
        font = QFont("Consolas")
        if not font.fromString("Consolas"):
            font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        
        # Extract font size from settings
        settings = {}
        if parent and hasattr(parent.window(), 'settings'):
            settings = parent.window().settings
        font_size = settings.get("font_size", 10)
        font.setPointSize(font_size)
        self.text_editor.setFont(font)
        
        # Standard tab size (4 spaces instead of huge tab stops)
        try:
            self.text_editor.setTabStopDistance(QFontMetrics(font).horizontalAdvance(' ') * 4)
        except AttributeError:
            self.text_editor.setTabStopWidth(QFontMetrics(font).width(' ') * 4)
        
        layout.addWidget(self.text_editor)
        
        # --- 4. BOTTOM ACTIONS BAR ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(8)
        
        self.btn_save = QPushButton("Save")
        self.btn_save_as = QPushButton("Save As...")
        
        self.btn_save.setShortcut(QKeySequence("Ctrl+S"))
        self.btn_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        
        self.btn_save.setToolTip("Save changes (Ctrl+S)")
        self.btn_save_as.setToolTip("Save as a new file (Ctrl+Shift+S)")
        
        bottom_layout.addWidget(self.btn_save)
        bottom_layout.addWidget(self.btn_save_as)
        
        bottom_layout.addStretch()
        
        self.btn_close = QPushButton("Close")
        self.btn_close.setShortcut(QKeySequence("Escape"))
        self.btn_close.setToolTip("Close editor (Esc)")
        bottom_layout.addWidget(self.btn_close)
        
        layout.addLayout(bottom_layout)
        
        # --- CONNECT SIGNALS ---
        self.btn_cut.clicked.connect(self.text_editor.cut)
        self.btn_copy.clicked.connect(self.text_editor.copy)
        self.btn_paste.clicked.connect(self.text_editor.paste)
        self.btn_delete.clicked.connect(self.delete_action)
        self.btn_select_all.clicked.connect(self.text_editor.selectAll)
        self.btn_find.clicked.connect(self.toggle_search_panel)
        
        self.btn_save.clicked.connect(self.save_file)
        self.btn_save_as.clicked.connect(self.save_file_as)
        self.btn_close.clicked.connect(self.close)
        
        self.text_editor.textChanged.connect(self.on_text_changed)
        
        # --- EXPLICIT PREMIUM THEMING ---
        theme = settings.get("theme", "light").lower()
        if theme == "dark":
            self.setStyleSheet(f"""
                QDialog {{ background-color: #2b2b2b; color: white; }}
                QPushButton {{ 
                    background-color: #3c3c3c; 
                    color: white; 
                    border: 1px solid #555; 
                    padding: 6px 12px; 
                    border-radius: 4px; 
                    font-weight: bold;
                }}
                QPushButton:hover {{ background-color: #505050; border-color: #777; }}
                QPushButton:pressed {{ background-color: #2c2c2c; }}
                QTextEdit {{ 
                    background-color: #1e1e1e; 
                    color: #e0e0e0; 
                    border: 1px solid #444; 
                    border-radius: 4px;
                    padding: 6px;
                }}
                QFrame {{
                    background-color: #3c3c3c;
                    border: 1px solid #555;
                    border-radius: 4px;
                }}
                QLabel {{ color: white; }}
                QLineEdit {{
                    background-color: #1e1e1e;
                    color: white;
                    border: 1px solid #555;
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QDialog {{ background-color: #f0f0f0; color: black; }}
                QPushButton {{ 
                    background-color: #e0e0e0; 
                    color: black; 
                    border: 1px solid #ccc; 
                    padding: 6px 12px; 
                    border-radius: 4px; 
                    font-weight: bold;
                }}
                QPushButton:hover {{ background-color: #d0d0d0; border-color: #bbb; }}
                QPushButton:pressed {{ background-color: #c0c0c0; }}
                QTextEdit {{ 
                    background-color: white; 
                    color: #333333; 
                    border: 1px solid #ccc; 
                    border-radius: 4px;
                    padding: 6px;
                }}
                QFrame {{
                    background-color: #e0e0e0;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                }}
                QLabel {{ color: black; }}
                QLineEdit {{
                    background-color: white;
                    color: black;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
            
        # Load content
        self.load_file()
        
    def toggle_search_panel(self):
        if self.search_panel.isVisible():
            self.hide_search_panel()
        else:
            self.search_panel.show()
            self.search_input.setFocus()
            self.search_input.selectAll()
            
    def hide_search_panel(self):
        self.search_panel.hide()
        self.lbl_search_status.setText("")
        self.text_editor.setFocus()
        
    def on_search_text_changed(self, text):
        if not text:
            self.lbl_search_status.setText("")
            return
        self.find_text(forward=True, is_incremental=True)
        
    def find_text_next(self):
        self.find_text(forward=True)
        
    def find_text_prev(self):
        self.find_text(forward=False)
        
    def find_text(self, forward=True, is_incremental=False):
        text = self.search_input.text()
        if not text:
            self.lbl_search_status.setText("")
            return
            
        from PyQt6.QtGui import QTextDocument, QTextCursor
        flags = QTextDocument.FindFlag(0)
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
            
        found = self.text_editor.find(text, flags)
        if found:
            self.lbl_search_status.setText("Found")
            self.lbl_search_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            if is_incremental:
                self.lbl_search_status.setText("Not found")
                self.lbl_search_status.setStyleSheet("color: red;")
                return
                
            # Wrap around
            cursor = self.text_editor.textCursor()
            if forward:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_editor.setTextCursor(cursor)
            
            found = self.text_editor.find(text, flags)
            if found:
                self.lbl_search_status.setText("Wrapped")
                self.lbl_search_status.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.lbl_search_status.setText("Not found")
                self.lbl_search_status.setStyleSheet("color: red;")

    def delete_action(self):
        cursor = self.text_editor.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()
        else:
            cursor.deleteChar()
            
    def load_file(self):
        try:
            with open(self.path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.text_editor.setPlainText(content)
            self.is_modified = False
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load file: {e}")
            
    def on_text_changed(self):
        self.is_modified = True
        
    def save_file(self):
        content = self.text_editor.toPlainText()
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.is_modified = False
            QMessageBox.information(self, "Saved", "File saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file: {e}")
            
    def save_file_as(self):
        default_name = self.path
        new_path, _ = QFileDialog.getSaveFileName(
            self, "Save File As", default_name, "All Files (*)"
        )
        if new_path:
            content = self.text_editor.toPlainText()
            try:
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.path = new_path
                self.setWindowTitle(f"Text Editor - {os.path.basename(new_path)}")
                self.is_modified = False
                QMessageBox.information(self, "Saved", "File saved successfully as new file.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file: {e}")
                
    def closeEvent(self, event):
        if self.is_modified:
            reply = QMessageBox.question(
                self, 
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_file()
                event.accept()
            elif reply == QMessageBox.StandardButton.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

class ChangeLogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Log")
        self.setMinimumSize(500, 400)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        lbl_title = QLabel("Application Change Log")
        lbl_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #0078d7;")
        layout.addWidget(lbl_title)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("QTextEdit { font-family: 'Segoe UI', Arial; font-size: 10pt; line-height: 1.4; }")
        
        changelog_path = get_resource_path("ChangeLog.md")
        changelog_text = ""
        if os.path.exists(changelog_path):
            try:
                with open(changelog_path, 'r', encoding='utf-8', errors='replace') as f:
                    changelog_text = f.read()
            except Exception as e:
                changelog_text = f"# Error\nCould not load Change Log file: {e}"
        else:
            changelog_text = """# GPF File Manager - Change Log

### Version 1.7.1 (06-13-2026)
- Add folder to Bookmarks
- Added "Open" to the right-click context menu to open files per their default system association or internal viewer/editor.

### Version 1.7.0 (6-5-2026)
- Font size in two editors match main app
- Add "Copy Filename to Clipboard"
- Add "Copy File Contents to Clipboard" to right click menu for text files

### Version 1.6 (5-28-2026)
- Added Text Editing

### Version 1.5 (5-27-2026)
Added Markdown Viewing and Editing.
"""
        
        self.text_edit.setMarkdown(changelog_text)
        layout.addWidget(self.text_edit)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.close)
        layout.addWidget(btns)

class MarkdownHelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Markdown Help")
        self.setMinimumSize(750, 500)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        splitter.addWidget(text_browser)
        
        text_editor = QTextEdit()
        text_editor.setReadOnly(True)
        splitter.addWidget(text_editor)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        
        settings = {}
        if parent and hasattr(parent.window(), 'settings'):
            settings = parent.window().settings
        theme = settings.get("theme", "light").lower()
        
        if theme == "dark":
            css = """
                body { color: #e0e0e0; background-color: #1e1e1e; font-family: 'Segoe UI', Arial; font-size: 10pt; line-height: 1.4; margin: 10px; }
                h1 { color: #4fc3f7; font-size: 16pt; font-weight: bold; border-bottom: 1px solid #444; padding-bottom: 3px; }
                h2 { color: #e0e0e0; font-size: 13pt; font-weight: bold; border-bottom: 1px solid #333; }
                code { font-family: monospace; background-color: #333; color: #f48fb1; padding: 2px; }
                pre { font-family: monospace; background-color: #333; border: 1px solid #444; padding: 6px; }
                blockquote { border-left: 3px solid #4fc3f7; background-color: #2b2b2b; padding-left: 8px; color: #aaa; }
                a { color: #4fc3f7; }
            """
        else:
            css = """
                body { color: #333333; background-color: white; font-family: 'Segoe UI', Arial; font-size: 10pt; line-height: 1.4; margin: 10px; }
                h1 { color: #0078d7; font-size: 16pt; font-weight: bold; border-bottom: 1px solid #eee; padding-bottom: 3px; }
                h2 { color: #111111; font-size: 13pt; font-weight: bold; border-bottom: 1px solid #f0f0f0; }
                code { font-family: monospace; background-color: #f4f4f4; color: #c7254e; padding: 2px; }
                pre { font-family: monospace; background-color: #f4f4f4; border: 1px solid #ddd; padding: 6px; }
                blockquote { border-left: 3px solid #0078d7; background-color: #f9f9f9; padding-left: 8px; color: #555; }
                a { color: #0078d7; }
            """
        text_browser.document().setDefaultStyleSheet(css)
        
        help_path = get_resource_path("markdowdownhelp.md")
        help_content = ""
        if os.path.exists(help_path):
            try:
                with open(help_path, 'r', encoding='utf-8', errors='replace') as f:
                    help_content = f.read()
            except Exception as e:
                help_content = f"# Error\nCould not load help file: {e}"
        else:
            help_content = """# Markdown Syntax Help

Welcome to the internal Markdown Editor! Markdown is a lightweight markup language with plain text formatting syntax.

## Headers
Use `#` symbols followed by a space for headers:
# Heading 1
## Heading 2
### Heading 3

## Emphasis
* *Italic text* (wrap with asterisks)
* **Bold text** (wrap with double asterisks)
* ***Bold & Italic*** (wrap with triple asterisks)

## Lists
### Unordered List:
- Item A
- Item B

### Ordered List:
1. First item
2. Second item

## Blockquotes
Use `>` for blockquotes:
> This is a quote block.

## Links & Tables
[Click here](https://sites.google.com) for a link.
"""
        
        text_editor.setPlainText(help_content)
        text_browser.setMarkdown(help_content)
        splitter.setSizes([350, 350])
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.close)
        layout.addWidget(btns)

class PropertiesPane(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        
        # --- FIX: Clean single layout initialization ---
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.content_widget = QWidget()
        self.form_layout = QFormLayout(self.content_widget)
        self.form_layout.setContentsMargins(10, 10, 10, 10)
        self.form_layout.setSpacing(10)
        
        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)
        
        self.clear_data()
        
    def clear_data(self):
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.form_layout.addRow(QLabel("<i>Select a file...</i>"), QLabel(""))
        
    def update_data(self, path):
        if not path or not os.path.exists(path):
            self.clear_data()
            return
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        info = QFileInfo(path)
        
        # [FIX] Fetch fields from ACTIVE PANE profile
        fields = ["Name", "Size", "Type", "Date Modified"]
        if self.main.active_pane:
            prof = self.main.active_pane.current_profile
            if "profiles" in self.main.settings and prof in self.main.settings["profiles"]:
                fields = self.main.settings["profiles"][prof]["props"]
        
        meta = MetadataLoader.get_metadata(path)
        
        for field in fields:
            value = ""
            if field == "Name": value = info.fileName()
            elif field == "Size":
                size = info.size()
                if size < 1024: value = f"{size} B"
                elif size < 1024**2: value = f"{size/1024:.1f} KB"
                else: value = f"{size/1024**2:.1f} MB"
                if info.isDir(): value = "--"
            elif field == "Type": value = "Folder" if info.isDir() else info.suffix().upper() + " File"
            elif field == "Date Modified": value = info.lastModified().toString("yyyy-MM-dd HH:mm")
            elif field == "Date Created": value = info.birthTime().toString("yyyy-MM-dd HH:mm") # FIX
            elif field == "Date Accessed": value = info.lastRead().toString("yyyy-MM-dd HH:mm") # FIX
            elif field == "Owner": value = info.owner()
            elif field == "Permissions":
                perms = []
                p = info.permissions()
                if p & QFileInfo.Permission.ReadUser: perms.append("R")
                if p & QFileInfo.Permission.WriteUser: perms.append("W")
                if p & QFileInfo.Permission.ExeUser: perms.append("X")
                value = "".join(perms)
            
            # Extended Metadata
            elif field in meta:
                value = str(meta[field])
                
            if value:
                lbl_key = QLabel(f"<b>{field}:</b>")
                lbl_val = QLabel(value)
                lbl_val.setWordWrap(True)
                lbl_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.form_layout.addRow(lbl_key, lbl_val)

        # --- NEW: Shortcut Properties (Pane) ---
        if info.suffix().lower() == 'lnk':
            target, start_in = get_lnk_properties(path)
            if target:
                lbl_t_key = QLabel("<b>Target:</b>")
                lbl_t_val = QLabel(target)
                lbl_t_val.setWordWrap(True)
                lbl_t_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.form_layout.addRow(lbl_t_key, lbl_t_val)
            if start_in:
                lbl_s_key = QLabel("<b>Start In:</b>")
                lbl_s_val = QLabel(start_in)
                lbl_s_val.setWordWrap(True)
                lbl_s_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.form_layout.addRow(lbl_s_key, lbl_s_val)
        if info.suffix().lower() in ['png', 'jpg', 'jpeg', 'gif', 'bmp']:
             reader = QImageReader(path)
             reader.setScaledSize(QSize(200, 200))
             img = reader.read()
             if not img.isNull():
                 pix = QPixmap.fromImage(img)
                 lbl_img = QLabel()
                 lbl_img.setPixmap(pix)
                 lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
                 self.form_layout.addRow(lbl_img)

# --- ROBUST IMAGE LOADING FIX ---

class ThumbnailLoaderSignals(QObject):
    result = pyqtSignal(QPersistentModelIndex, QImage)

class ThumbnailLoader(QRunnable):
    def __init__(self, index, path, size):
        super().__init__()
        self.index = index
        self.path = path
        self.size = size
        self.signals = ThumbnailLoaderSignals()
        
    def run(self):
        try:
            if not os.path.exists(self.path):
                return

            img = QImage()
            
            # --- STRATEGY 1: Use Pillow (Safest/Fastest) ---
            if HAS_PILLOW:
                try:
                    with Image.open(self.path) as pil_img:
                        # Handle orientation from EXIF
                        try:
                            exif = pil_img._getexif()
                            if exif:
                                orientation = exif.get(274)
                                if orientation == 3: pil_img = pil_img.rotate(180, expand=True)
                                elif orientation == 6: pil_img = pil_img.rotate(270, expand=True)
                                elif orientation == 8: pil_img = pil_img.rotate(90, expand=True)
                        except Exception: 
                            pass # Ignore EXIF errors

                        # Efficient thumbnail generation
                        # Use LANCZOS if available, otherwise just rely on thumbnail() defaults
                        try:
                            resample = Image.Resampling.LANCZOS
                        except AttributeError:
                            resample = Image.LANCZOS

                        pil_img.thumbnail((self.size.width(), self.size.height()), resample)
                        
                        # Convert to QImage compatible format
                        if pil_img.mode != "RGBA":
                            pil_img = pil_img.convert("RGBA")
                            
                        data = pil_img.tobytes("raw", "RGBA")
                        img = QImage(data, pil_img.size[0], pil_img.size[1], QImage.Format.Format_RGBA8888).copy()
                except Exception:
                    # If PIL fails, fall through to Strategy 2
                    pass

            # --- STRATEGY 2: Fallback to Qt (Buffered) ---
            # If PIL failed or is missing, read bytes to python memory first.
            # This prevents QImageReader from crashing on direct file access to bad headers.
            if img.isNull():
                with open(self.path, "rb") as f:
                    data = f.read()
                    img = QImage.fromData(data)
                    if not img.isNull():
                        # Scale it down here to save RAM
                        img = img.scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

            if not img.isNull():
                self.signals.result.emit(self.index, img)

        except Exception:
            pass

class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache = {} 
        self.loading = set() 
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(4) 
        self.icon_size = QSize(120, 120)
        self.view = None

    def set_view(self, view):
        self.view = view

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)

    def paint(self, painter, option, index):
        # 1. Get Path
        path = None
        if hasattr(index.model(), 'filePath'): 
            path = index.model().filePath(index)
        else: 
            path = index.data(Qt.ItemDataRole.UserRole)

        # 2. Setup the Style Option
        # We create a copy of the option so we can modify it without breaking other things
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # 3. Logic: Cache Hit vs Miss
        if path and path in self.cache:
            # --- CACHE HIT ---
            # The Magic Fix: Replace the default system icon with our Thumbnail.
            # This ensures Qt draws ONLY the thumbnail, scaling it correctly.
            opt.icon = QIcon(self.cache[path])
            
            # Force the decoration size to match our thumbnail settings
            opt.decorationSize = self.icon_size
            
        else:
            # --- CACHE MISS ---
            # Trigger load if we haven't already
            if path and path not in self.loading:
                ext = os.path.splitext(path)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff']:
                    self.loading.add(path)
                    loader = ThumbnailLoader(QPersistentModelIndex(index), path, self.icon_size)
                    loader.signals.result.connect(self.on_loaded)
                    self.thread_pool.start(loader)

        # 4. Draw the Control
        # We use the underlying style engine to draw the item using our modified 'opt'.
        # This handles selection highlights, text alignment, and focus automatically.
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

    def on_loaded(self, index, image):
        try:
            if not index.isValid(): return
            if not self.view or not self.view.isVisible(): return

            pixmap = QPixmap.fromImage(image)
            path = None
            if hasattr(index.model(), 'filePath'): 
                path = index.model().filePath(QModelIndex(index))
            else: 
                path = index.data(Qt.ItemDataRole.UserRole)

            if path:
                self.cache[path] = pixmap
                if path in self.loading: self.loading.remove(path)
            
            self.view.update(QModelIndex(index))
        except Exception:
            pass

class FileWorker(QThread):
    action_recorded = pyqtSignal(str, str, str)
    error_occurred = pyqtSignal(str)
    finished_all = pyqtSignal()
    def __init__(self, operation, src_list, target_dir):
        super().__init__()
        self.operation = operation 
        self.src_list = src_list
        self.target_dir = target_dir
        self._is_running = True
    def run(self):
        if self.operation == "zip":
            zip_path = self.target_dir
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for src in self.src_list:
                        if not self._is_running: break
                        if os.path.isdir(src):
                            parent_dir = os.path.dirname(src)
                            for root, dirs, files in os.walk(src):
                                for file in files:
                                    if not self._is_running: break
                                    filepath = os.path.join(root, file)
                                    arcname = os.path.relpath(filepath, parent_dir)
                                    zipf.write(filepath, arcname)
                        else:
                            arcname = os.path.basename(src)
                            zipf.write(src, arcname)
                self.finished_all.emit()
            except Exception as e:
                self.error_occurred.emit(f"Zip Error: {str(e)}")
            return
        for src in self.src_list:
            if not self._is_running: break
            if not os.path.exists(src): continue
            fname = os.path.basename(src)
            
            # [FIX] Logic for delete operation: Move to Trash folder
            if self.operation == "delete":
                # Ensure trash dir exists
                if not os.path.exists(self.target_dir):
                    os.makedirs(self.target_dir)
                    
                fname = os.path.basename(src)
                dst = os.path.join(self.target_dir, fname)
                
                # Handle collision in trash
                if os.path.exists(dst):
                    name, ext = os.path.splitext(fname)
                    timestamp = int(time.time())
                    new_name = f"{name}_{timestamp}{ext}"
                    dst = os.path.join(self.target_dir, new_name)
            
            elif self.operation == "unzip": 
                pass
                
            else:
                # Standard copy/move collision handling
                dst = os.path.join(self.target_dir, fname)
                if self.operation == "copy" and os.path.abspath(src) == os.path.abspath(dst):
                    new_name = f"Copy of {fname}"
                    dst = os.path.join(self.target_dir, new_name)
                    while os.path.exists(dst):
                          new_name = f"Copy of {new_name}" 
                          dst = os.path.join(self.target_dir, new_name)
            
            if self.operation != "unzip" and os.path.abspath(src) == os.path.abspath(dst): continue
            
            try:
                if self.operation == "move":
                    shutil.move(src, dst)
                    self.action_recorded.emit("move", src, dst)
                elif self.operation == "copy":
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            self.error_occurred.emit(f"Skipped '{src}': Destination exists.")
                            continue
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    self.action_recorded.emit("copy", src, dst)
                elif self.operation == "delete":
                    # [FIX] Ensure write permissions before moving (fixes WinError 5 for read-only files like .gradle)
                    try:
                        if os.path.isdir(src):
                            # Make root writable
                            try: os.chmod(src, stat.S_IWRITE)
                            except: pass
                            
                            for root, dirs, files in os.walk(src):
                                try: os.chmod(root, stat.S_IWRITE)
                                except: pass
                                for f in files:
                                    try: os.chmod(os.path.join(root, f), stat.S_IWRITE)
                                    except: pass
                        else:
                            try: os.chmod(src, stat.S_IWRITE)
                            except: pass
                    except Exception as e:
                        print(f"Warning: Failed to reset permissions on {src}: {e}")

                    # Move to trash (which is just a move operation to a specific folder)
                    shutil.move(src, dst)
                    self.action_recorded.emit("delete", src, dst)
                elif self.operation == "unzip":
                    if not os.path.exists(self.target_dir): os.makedirs(self.target_dir)
                    with zipfile.ZipFile(src, 'r') as zip_ref: zip_ref.extractall(self.target_dir)
                    self.action_recorded.emit("unzip", src, self.target_dir)
            except Exception as e:
                self.error_occurred.emit(f"Error processing {src}: {str(e)}")
        self.finished_all.emit()
    def stop(self): self._is_running = False

# --- NEW: Zip Exploration Model ---
class ZipExplorationModel(QStandardItemModel):
    def __init__(self, zip_path):
        super().__init__()
        self.zip_path = zip_path
        self.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.current_subpath = "" # Path inside zip, e.g. "folder/subfolder/"
        self.load_zip_contents()

    def set_subpath(self, subpath):
        self.current_subpath = subpath
        self.load_zip_contents()

    def load_zip_contents(self):
        self.clear()
        self.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
        
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                infolist = zf.infolist()
                
                # Filter items in current subpath
                # Standardize current subpath to ensure trailing slash if not empty
                prefix = self.current_subpath
                if prefix and not prefix.endswith('/'): prefix += "/"
                
                # Collect direct children
                # Use a set to avoid duplicates (directories in zip are sometimes implicit)
                entries = {}
                
                for info in infolist:
                    filename = info.filename
                    if not filename.startswith(prefix): continue
                    
                    # Remove prefix
                    rel_path = filename[len(prefix):]
                    if not rel_path: continue
                    
                    # Check if it's a file or folder in this level
                    if '/' in rel_path.rstrip('/'):
                        # It's in a subfolder, add the folder name
                        folder_name = rel_path.split('/')[0]
                        entries[folder_name] = {"type": "Folder", "size": 0, "dt": ""}
                    else:
                        # It's a file or a direct directory entry
                        is_dir = info.is_dir() or filename.endswith('/')
                        name = rel_path.rstrip('/')
                        
                        dt = datetime(*info.date_time).strftime('%Y-%m-%d %H:%M')
                        size = info.file_size
                        
                        entries[name] = {"type": "Folder" if is_dir else "File", "size": size, "dt": dt}
                
                # Add to model
                for name, data in sorted(entries.items(), key=lambda x: (x[1]['type'] != 'Folder', x[0].lower())):
                    item_name = QStandardItem(name)
                    # Store full 'virtual' path in UserRole
                    full_in_zip = prefix + name 
                    if data['type'] == 'Folder': full_in_zip += "/"
                    
                    # Store special path format: zip_path|subpath
                    virtual_path = f"{self.zip_path}|{full_in_zip}"
                    item_name.setData(virtual_path, Qt.ItemDataRole.UserRole)
                    
                    if data['type'] == 'Folder':
                         item_name.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                    else:
                         item_name.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
                    
                    item_type = QStandardItem(data['type'])
                    item_size = QStandardItem(str(data['size']) if data['type'] == 'File' else "")
                    item_mod = QStandardItem(data['dt'])
                    
                    self.appendRow([item_name, item_type, item_size, item_mod])
                    
        except Exception as e:
            print(f"Error loading zip: {e}")

# --- NEW: Bookmark Tree with Drag & Drop ---
# --- NEW: Bookmark Tree with Drag & Drop ---
class BookmarkTree(QTreeWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.setHeaderLabel("Bookmarks")
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)
        self.itemClicked.connect(self.on_item_click)
        
        # Enable Drag & Drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dragEnterEvent(self, event):
        # Accept external files or title bar drags
        
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-filemanager-pane-path"):
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-filemanager-pane-path"):
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        # Handle External Drops (Files/Folders)
        if event.mimeData().hasUrls():
            target_item = self.itemAt(event.position().toPoint())
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.exists(path):
                    self.main.add_bookmark_item(os.path.basename(path), path, target_item)
            event.accept()
            
        # Handle Title Bar Drop
        
        elif event.mimeData().hasFormat("application/x-filemanager-pane-path"):
            path_bytes = event.mimeData().data("application/x-filemanager-pane-path")
            path = str(path_bytes, 'utf-8')
            target_item = self.itemAt(event.position().toPoint())
            if os.path.exists(path):
                self.main.add_bookmark_item(os.path.basename(path), path, target_item)
            event.accept()
            
        # Handle Internal Reordering
        else:
            super().dropEvent(event)
            self.main.save_settings()

    def on_item_click(self, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and self.main.active_pane:
            self.main.active_pane.navigate(path)

    # [FIX] Missing method added here
    def open_context_menu(self, point):
        item = self.itemAt(point)
        menu = QMenu()
        act_add = menu.addAction("Add current folder")
        act_new_folder = menu.addAction("New bookmark folder")
        act_del = menu.addAction("Delete") if item else None
        
        res = menu.exec(self.mapToGlobal(point))
        
        if res == act_add and self.main.active_pane:
             self.main.add_bookmark_item(os.path.basename(self.main.active_pane.current_path), self.main.active_pane.current_path)
        elif res == act_new_folder:
             name, ok = QInputDialog.getText(self, "New Bookmark Folder", "Folder Name:")
             if ok and name:
                 parent = self.invisibleRootItem()
                 if item:
                     path = item.data(0, Qt.ItemDataRole.UserRole)
                     if not path:
                         parent = item
                     else:
                         parent = item.parent() or self.invisibleRootItem()
                 
                 folder_item = QTreeWidgetItem(parent)
                 folder_item.setText(0, name)
                 folder_item.setData(0, Qt.ItemDataRole.UserRole, None)
                 folder_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                 folder_item.setExpanded(True)
                 self.main.save_settings()
        elif res == act_del and item:
             (item.parent() or self.invisibleRootItem()).removeChild(item)
             self.main.save_settings()

class FavoritesTree(QTreeWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.setHeaderLabel("Favorite Apps")
        self.setHeaderHidden(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)
        self.itemDoubleClicked.connect(self.on_item_dbl_click)
        
        # Enable Drag & Drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def on_item_dbl_click(self, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not launch app: {e}")

    def open_context_menu(self, point):
        item = self.itemAt(point)
        menu = QMenu()
        act_add_folder = menu.addAction("Add folder")
        act_rename = menu.addAction("Rename") if item else None
        act_open_with = menu.addAction("Open with...") if item else None
        act_props = menu.addAction("Properties") if item else None
        act_del = menu.addAction("Delete") if item else None
        
        res = menu.exec(self.mapToGlobal(point))
        
        if res == act_add_folder:
            name, ok = QInputDialog.getText(self, "New Folder", "Folder Name:")
            if ok and name:
                self.main.add_favorite_group(name, item)
        elif res == act_rename and item:
            old_name = item.text(0)
            new_name, ok = QInputDialog.getText(self, "Rename Favorite", "Name:", text=old_name)
            if ok and new_name:
                item.setText(0, new_name)
                self.main.save_settings()
        elif res == act_open_with and item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path and os.path.exists(path):
                self.main.on_open_with(path)
        elif res == act_props and item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path and os.path.exists(path):
                dlg = PropertiesDialog(path, self)
                dlg.exec()
        elif res == act_del and item:
             for i in self.selectedItems():
                 (i.parent() or self.invisibleRootItem()).removeChild(i)
             self.main.save_settings()

    def dragEnterEvent(self, event):
        
        if event.mimeData().hasFormat("application/x-filemanager-pane-path"): event.accept()
        elif event.mimeData().hasUrls(): event.accept()
        else: super().dragEnterEvent(event)
    def dragMoveEvent(self, event):
        
        if event.mimeData().hasFormat("application/x-filemanager-pane-path"): event.accept()
        elif event.mimeData().hasUrls(): event.accept()
        else: super().dragMoveEvent(event)
    def dropEvent(self, event):
        
        if event.mimeData().hasFormat("application/x-filemanager-pane-path"):
            path_bytes = event.mimeData().data("application/x-filemanager-pane-path")
            path = str(path_bytes, 'utf-8')
            if os.path.exists(path): self.main.add_favorite_item(path)
            event.accept()
            return
        if event.mimeData().hasUrls():
            target_item = self.itemAt(event.position().toPoint())
            parent = target_item if target_item else None
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.exists(path): self.main.add_favorite_item(path, parent)
            event.accept()
            return
        super().dropEvent(event)
        self.main.save_settings()

class BreadcrumbBar(QWidget):
    def __init__(self, parent_pane):
        super().__init__()
        self.pane = parent_pane
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)

    def set_path(self, path):
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        
        # --- FIX: Handle UNC (Network) Paths correctly ---
        is_unc = path.startswith('//') or path.startswith('\\\\')
        clean_path = path.replace('\\', '/')
        
        if is_unc:
            # Remove leading slashes for splitting, but keep flag to rebuild correctly
            parts = clean_path.lstrip('/').split('/')
            # Prepend the UNC root as the first "part" so it behaves like a drive letter
            if parts:
                parts[0] = f"//{parts[0]}"
        else:
            parts = clean_path.split('/')

        built_path = ""
        for i, part in enumerate(parts):
            if not part: continue 
            
            if i == 0:
                # If it's UNC, the first part is //Server. If local, it's C:
                built_path = part + ("/" if is_unc or ':' in part else "")
            else:
                built_path = os.path.join(built_path, part)
            
            btn = QPushButton(part)
            btn.setFlat(True)
            btn.setStyleSheet("text-align: left; padding: 2px;")
            btn.clicked.connect(lambda checked, p=built_path: self.pane.navigate(p))
            self.layout.addWidget(btn)
            
            if i < len(parts) - 1:
                self.layout.addWidget(QLabel(">"))
                
        self.layout.addStretch()
        edit_btn = QPushButton("...")
        edit_btn.setFixedWidth(30)
        edit_btn.clicked.connect(lambda: self.pane.toggle_path_edit())
        self.layout.addWidget(edit_btn)

class PaneTitleLabel(QLabel):
    def __init__(self, parent_pane):
        super().__init__()
        self.pane = parent_pane
        self.drag_start_pos = None
        self.setAcceptDrops(True)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.pane.set_active()
        super().mousePressEvent(event)
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton): return
        if not self.drag_start_pos: return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance(): return
        drag = QDrag(self)
        mime = QMimeData()
        path_data = self.pane.current_path.encode('utf-8')
        
        mime.setData("application/x-filemanager-pane-path", path_data)
        drag.setMimeData(mime)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        drag.exec(Qt.DropAction.CopyAction)
        
    def dragEnterEvent(self, event):
        
        if event.mimeData().hasFormat("application/x-filemanager-pane-path"): event.accept()
        else: event.ignore()
    def dragMoveEvent(self, event):
        
        if event.mimeData().hasFormat("application/x-filemanager-pane-path"): event.accept()
        else: event.ignore()
    def dropEvent(self, event):
        
        if event.mimeData().hasFormat("application/x-filemanager-pane-path"):
            path_bytes = event.mimeData().data("application/x-filemanager-pane-path")
            path = str(path_bytes, 'utf-8')
            if os.path.exists(path) and path != self.pane.current_path: self.pane.navigate(path)
            event.accept()

class PathEdit(QLineEdit):
    def __init__(self, parent_pane):
        super().__init__()
        self.pane = parent_pane
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.pane.toggle_path_edit()
        else: super().keyPressEvent(event)
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self.isVisible(): self.pane.toggle_path_edit()

class FilePane(QWidget):
    def __init__(self, name, default_path, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(50, 50) 
        self.pane_name = name
        self.current_path = default_path
        self.active = False
        self.current_view_mode = "Detailed"
        self.active = False
        self.current_view_mode = "Detailed"
        self.current_profile = "Default" # Default profile
        self.this_pc_model = None # [FIX] Persist This PC model to prevent GC crash
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(2)
        self.title_bar = QFrame()
        self.title_bar.setObjectName("PaneTitleBar") 
        self.title_layout = QHBoxLayout(self.title_bar)
        self.title_layout.setContentsMargins(5, 2, 5, 2)
        self.title_label = PaneTitleLabel(self)
        self.title_label.setText(f"{name} - {os.path.basename(default_path)}")
        self.title_label.setAcceptDrops(True) 
        self.title_layout.addWidget(self.title_label, 1)
        self.btn_ps = QPushButton("PS")
        self.btn_ps.setToolTip("Open PowerShell")
        self.btn_ps.clicked.connect(self.open_powershell)
        self.btn_cmd = QPushButton("CMD")
        self.btn_cmd.setToolTip("Open Command Window")
        self.btn_cmd.clicked.connect(self.open_cmd)
        
        # Initial button sizing based on font size in settings
        initial_font_size = 10
        if parent and hasattr(parent, 'settings'):
            initial_font_size = parent.settings.get("font_size", 10)
        self.update_button_widths(initial_font_size)
        
        self.title_layout.addWidget(self.btn_ps)
        self.title_layout.addSpacing(8)
        self.title_layout.addWidget(self.btn_cmd)
        self.layout.addWidget(self.title_bar)
        nav_frame = QFrame()
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(0,0,0,0)
        self.btn_up = QPushButton()
        self.btn_up.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.btn_up.clicked.connect(self.go_up)
        nav_layout.addWidget(self.btn_up)
        self.drive_combo = QComboBox()
        self.refresh_drives()
        self.drive_combo.activated.connect(self.change_drive)
        nav_layout.addWidget(self.drive_combo)
        self.breadcrumbs = BreadcrumbBar(self)
        nav_layout.addWidget(self.breadcrumbs)
        self.path_edit = PathEdit(self)
        self.path_edit.returnPressed.connect(self.on_path_entered)
        self.path_edit.hide()
        nav_layout.addWidget(self.path_edit)
        
        # --- Search Bar ---
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(150)
        self.search_edit.returnPressed.connect(self.on_search_submit)
        self.search_edit.textChanged.connect(self.on_search_text_changed)
        
        self.search_model = QStandardItemModel()
        self.search_model.setHorizontalHeaderLabels(["Name", "Path", "Size", "Modified"])
        
        self.btn_search_help = QPushButton("?")
        self.btn_search_help.setFixedWidth(25)
        self.btn_search_help.setToolTip("Search Syntax Help")
        self.btn_search_help.clicked.connect(self.show_search_help)
        
        nav_layout.addWidget(self.search_edit)
        nav_layout.addWidget(self.btn_search_help)
        
        # --- Sort Button ---
        self.btn_sort = QPushButton("Sort")
        self.btn_sort.setFixedWidth(40)
        self.btn_sort.setStyleSheet("padding: 3px;")
        self.btn_sort.clicked.connect(self.show_sort_menu)
        nav_layout.addWidget(self.btn_sort)
        
        # --- Profile Selector ---
        self.combo_profile = QComboBox()
        self.combo_profile.setFixedWidth(100)
        self.combo_profile.setToolTip("Field Profile")
        # Profiles loaded in refresh_profiles() called later
        self.combo_profile.currentTextChanged.connect(self.on_profile_changed)
        nav_layout.addWidget(self.combo_profile)

        self.layout.addWidget(nav_frame)
        self.model = DetailedFileSystemModel() 
        self.model.setRootPath("")
        self.model.setReadOnly(False) 
        
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(default_path))
        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.doubleClicked.connect(self.on_double_click)
        self.tree_view.clicked.connect(self.on_click) 
        self.tree_view.dragEnterEvent = self.dragEnterEvent
        self.tree_view.dragMoveEvent = self.dragMoveEvent
        self.tree_view.dropEvent = self.dropEvent
        self.tree_view.customContextMenuRequested.connect(self.open_context_menu)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        if parent and hasattr(parent, 'settings'):
            saved_widths = parent.settings.get("column_widths", [])
            if saved_widths:
                for i, w in enumerate(saved_widths):
                    self.tree_view.setColumnWidth(i, w)
                    
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setRootIndex(self.model.index(default_path))
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setGridSize(QSize(140, 140))
        self.list_view.setIconSize(QSize(120, 120))
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setDragEnabled(True)
        self.list_view.setAcceptDrops(True)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.doubleClicked.connect(self.on_double_click)
        self.list_view.clicked.connect(self.on_click)
        self.list_view.customContextMenuRequested.connect(self.open_context_menu)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumbnail_delegate = ThumbnailDelegate(self.list_view)
        self.thumbnail_delegate.set_view(self.list_view)
        self.list_view.setItemDelegate(self.thumbnail_delegate)
        
        self.stack.addWidget(self.tree_view) # Index 0
        self.stack.addWidget(self.list_view) # Index 1
        
        # Initialize Profiles
        self.refresh_profiles()
        
        self.apply_hidden_filter()
        self.navigate(default_path)
        self.set_color_mode(False)
        self.apply_column_settings()

    # --- Sort Menu Logic ---
    def show_sort_menu(self):
        menu = QMenu(self)
        
        # Column mappings: 0=Name, 1=Size, 2=Type, 3=Modified
        header = self.tree_view.header()
        curr_col = header.sortIndicatorSection()
        curr_order = header.sortIndicatorOrder()
        
        col_group = QActionGroup(menu)
        col_group.setExclusive(True)

        def add_col_action(text, col_idx):
            act = menu.addAction(text)
            act.setCheckable(True)
            act.setChecked(curr_col == col_idx)
            act.setActionGroup(col_group)
            act.triggered.connect(lambda: self.apply_sort(col_idx))
            return act

        add_col_action("Name", 0)
        add_col_action("Size", 1)
        add_col_action("Type", 2)
        add_col_action("Date Updated", 3)
        
        act_created = menu.addAction("Date Created")
        act_created.setCheckable(True)
        act_created.setChecked(curr_col == 3) 
        act_created.setActionGroup(col_group)
        act_created.triggered.connect(lambda: self.apply_sort(3))
        
        menu.addSeparator()
        
        order_group = QActionGroup(menu)
        order_group.setExclusive(True)
        
        a_asc = menu.addAction("Ascending")
        a_asc.setCheckable(True)
        a_asc.setChecked(curr_order == Qt.SortOrder.AscendingOrder)
        a_asc.setActionGroup(order_group)
        a_asc.triggered.connect(lambda: self.apply_sort(None, Qt.SortOrder.AscendingOrder))
        
        a_desc = menu.addAction("Descending")
        a_desc.setCheckable(True)
        a_desc.setChecked(curr_order == Qt.SortOrder.DescendingOrder)
        a_desc.setActionGroup(order_group)
        a_desc.triggered.connect(lambda: self.apply_sort(None, Qt.SortOrder.DescendingOrder))
        
        menu.exec(QCursor.pos())

    def apply_sort(self, column=None, order=None):
        header = self.tree_view.header()
        current_col = header.sortIndicatorSection()
        current_order = header.sortIndicatorOrder()
        
        target_col = current_col if column is None else column
        target_order = current_order if order is None else order
        
        self.tree_view.sortByColumn(target_col, target_order)
        self.list_view.model().sort(target_col, target_order)

    def apply_sort_settings(self, column, order_int):
        order = Qt.SortOrder(order_int)
        self.tree_view.sortByColumn(column, order)

    def apply_hidden_filter(self):
        show = False
        window = self.window()
        if window and hasattr(window, 'settings'):
            show = window.settings.get("show_hidden", False)
        
        # Base filter: Dirs, Files, Drives, and hide . and ..
        filters = QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot
        if show:
            filters |= QDir.Filter.Hidden | QDir.Filter.System
            
        self.model.setFilter(filters)
        
    def refresh_profiles(self):
        if self.window() and hasattr(self.window(), 'settings'):
             profs = self.window().settings.get("profiles", {})
             self.combo_profile.blockSignals(True)
             self.combo_profile.clear()
             self.combo_profile.addItems(sorted(profs.keys()))
             
             if self.current_profile in profs:
                 self.combo_profile.setCurrentText(self.current_profile)
             else:
                 self.combo_profile.setCurrentText("Default")
                 self.current_profile = "Default"
             self.combo_profile.blockSignals(False)

    def on_profile_changed(self, text):
        if not text: return
        self.current_profile = text
        self.apply_column_settings()
        if self.active:
            self.window().update_properties(self.current_path)

    def show_search_help(self):
        SearchHelpDialog(self.window()).exec()

    def on_search_submit(self):
        query = self.search_edit.text().strip()
        if not query:
            self.switch_to_normal_mode()
            return

        # [NEW] Update Title to "Search: [First 20 chars]"
        display_query = query[:20] + "..." if len(query) > 20 else query
        self.title_label.setText(f"Search: {display_query}")
        
        self.window().start_search(query, self)

    def on_search_text_changed(self, text):
        if not text:
            self.switch_to_normal_mode()

    def display_search_results(self, results):
        self.search_model.clear()
        self.search_model.setHorizontalHeaderLabels(["Name", "Path", "Size", "Modified"])
        for row in results:
            name, folder, size, mod_ts = row
            full_path = os.path.join(folder, name)
            item_name = QStandardItem(name)
            item_name.setData(full_path, Qt.ItemDataRole.UserRole)
            item_path = QStandardItem(folder)
            item_size = QStandardItem(str(size))
            try:
                mod_date = datetime.fromtimestamp(mod_ts).strftime('%Y-%m-%d %H:%M')
            except:
                mod_date = "Unknown"

            item_mod = QStandardItem(mod_date)

            self.search_model.appendRow([item_name, item_path, item_size, item_mod])
        
        self.switch_to_search_mode()

    def switch_to_search_mode(self):
        # In search mode, we might want to switch to the stack index 0 (Table View) 
        # or we might want to ensure the model is set to the search/custom model.
        # IF we previously set self.tree_view.setModel(some_custom_model),
        # we need to make sure we don't accidentally reset it to self.model (the file system model).
        
        self.stack.setCurrentIndex(0) 
        # [FIX] Do NOT reset the model here if we are showing "This PC"
        if self.current_path != "sys:this_pc":
            self.tree_view.setModel(self.search_model)
            
    def switch_to_normal_mode(self):
        # [NEW] Reset Title
        folder_name = os.path.basename(self.current_path)
        if not folder_name and ':' in self.current_path: folder_name = self.current_path
        self.title_label.setText(f"{self.pane_name} - {folder_name}")

        self.tree_view.setModel(self.model)
        self.list_view.setModel(self.model) 
        self.tree_view.setRootIndex(self.model.index(self.current_path))
        self.list_view.setRootIndex(self.model.index(self.current_path))
        
        # [FIX] Restore Delegate for Normal View
        if self.list_view.itemDelegate() != self.thumbnail_delegate:
             self.list_view.setItemDelegate(self.thumbnail_delegate)
        
        if self.current_view_mode == "Images":
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)

    def set_color_mode(self, active):
        self.active = active
        color = "#0078d7" if active else "#555555"
        self.title_bar.setStyleSheet(f"background-color: {color}; color: white;")

    def on_click(self, index):
        self.set_active()
        
        # [FIX] Handle This PC click (prevent invalid index crash)
        if self.current_path == "sys:this_pc":
            path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
            # log_debug(f"Clicked This PC item: {path}")
        elif self.tree_view.model() == self.search_model:
            path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        # [NEW] Handle Zip Model Click
        elif '|' in self.current_path or isinstance(self.tree_view.model(), ZipExplorationModel):
             path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        elif self.tree_view.model() == self.model:
            path = self.model.filePath(index)
        else:
            return
            
        self.window().update_properties(path)

    def set_active(self):
        window = self.window()
        if isinstance(window, MainWindow): window.set_active_pane(self)

    # --- NEW: Show This PC ---
    def show_this_pc(self):
        self.current_path = "sys:this_pc"
        self.breadcrumbs.set_path("This PC")
        self.title_label.setText(f"{self.pane_name} - This PC")
        self.path_edit.setText("This PC")
        
        # Create model for drives
        # Create model for drives
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Name", "Type", "File System", "Used Space", "Free Space", "Capacity", "% Free"])
        
        for vol in QStorageInfo.mountedVolumes():
            if not vol.isValid(): continue
            
            # Helper to safely decode strings/bytes
            def safe_str(v):
                if isinstance(v, (bytes, bytearray)):
                    return v.decode('utf-8', errors='ignore')
                return str(v)

            vol_name = safe_str(vol.name())
            vol_root = safe_str(vol.rootPath())
            
            display_name = f"{vol_root} ({vol_name})" if vol_name else vol_root
            name_item = QStandardItem(display_name)
            name_item.setData(vol_root, Qt.ItemDataRole.UserRole)
            name_item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon))
            
            type_str = "Read-Only" if vol.isReadOnly() else "Read-Write"
            fs_type = safe_str(vol.fileSystemType())
            
            # Calculate sizes
            total = vol.bytesTotal()
            free = vol.bytesFree()
            used = total - free
            
            pct_free = 0
            if total > 0:
                pct_free = (free / total) * 100
            
            def fmt_size(b):
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if b < 1024: return f"{b:.2f} {unit}"
                    b /= 1024
                return f"{b:.2f} PB"

            model.appendRow([
                name_item,
                QStandardItem(type_str),
                QStandardItem(fs_type),
                QStandardItem(fmt_size(used)),
                QStandardItem(fmt_size(free)),
                QStandardItem(fmt_size(total)),
                QStandardItem(f"{pct_free:.1f}%")
            ])
            

            
        self.this_pc_model = model # [FIX] Keep reference
        self.tree_view.setModel(self.this_pc_model)
        self.list_view.setModel(self.this_pc_model)
        
        # [FIX] Disable Thumbnail Delegate for This PC (prevents crash on paint)
        self.list_view.setItemDelegate(None)
        
        # Adjust columns
        for i in range(7): self.tree_view.resizeColumnToContents(i)
        
        self.switch_to_search_mode() # Reuse the "custom model" view mode logic (stack index 0)

    def refresh_drives(self):
        self.drive_combo.clear()
        for drive in QDir.drives(): self.drive_combo.addItem(drive.absoluteFilePath())
        
        # [NEW] Refresh "This PC" if active
        if self.current_path == "sys:this_pc":
            self.show_this_pc()

    def change_drive(self): self.navigate(self.drive_combo.currentText())

    def on_path_entered(self):
        self.navigate(self.path_edit.text())
        if self.path_edit.isVisible(): self.toggle_path_edit()

    def navigate(self, path):
        try:
            log_debug(f"Navigate called for: {path}")

            # [NEW] Handle Shell Commands
            if path.startswith("shell:"):
                resolved = self.window().resolve_shell_path(path)
                if resolved and os.path.exists(resolved):
                    path = resolved
                else:
                    # If it's a virtual folder like shell:appsfolder
                    try:
                        os.startfile(path)
                    except Exception as e:
                        log_debug(f"Failed to start shell command {path}: {e}")
                    return
            
            # [NEW] Handle Zip Browsing
            # Check if path is a zip file OR inside a zip (format: zip_path|subpath)
            if '|' in path: 
                # Internal zip navigation
                zip_path, subpath = path.split('|', 1)
                
                if not os.path.exists(zip_path): 
                     log_debug(f"Zip path not found: {zip_path}")
                     return

                log_debug(f"Navigating inside zip: {zip_path} -> {subpath}")
                
                # Create or Reuse Model
                if not isinstance(self.tree_view.model(), ZipExplorationModel) or self.tree_view.model().zip_path != zip_path:
                     self.zip_model = ZipExplorationModel(zip_path)
                     self.tree_view.setModel(self.zip_model)
                     # self.list_view.setModel(self.zip_model) # List View not fully supported for zip yet?
                
                self.tree_view.model().set_subpath(subpath)
                
                # Switch Stack to Table View (Index 0) forcefully as it's a "custom" model
                self.stack.setCurrentIndex(0)
                
                self.current_path = path 
                self.breadcrumbs.set_path(f"{os.path.basename(zip_path)}/{subpath}")
                self.title_label.setText(f"{self.pane_name} - {os.path.basename(zip_path)}/{subpath}")
                self.path_edit.setText(path)
                return
            
            # Check if entering a zip file from standard view
            if os.path.isfile(path) and path.lower().endswith('.zip'):
                log_debug(f"Entering zip file: {path}")
                self.zip_model = ZipExplorationModel(path)
                self.tree_view.setModel(self.zip_model)
                
                # Switch Stack
                self.stack.setCurrentIndex(0)
                
                self.current_path = f"{path}|" # Root of zip
                self.breadcrumbs.set_path(f"{os.path.basename(path)}/")
                self.title_label.setText(f"{self.pane_name} - {os.path.basename(path)}")
                self.path_edit.setText(self.current_path)
                return

            # [NEW] Handle "This PC"
            if path == "sys:this_pc":
                log_debug("Switching to This PC View")
                self.show_this_pc()
                return

            if not os.path.exists(path): 
                log_debug(f"Path does not exist: {path}")
                return

            # [FIX] Set Root Path BEFORE switching models to ensure validity
            log_debug(f"Setting root path on QFileSystemModel: {path}")
            self.model.setRootPath(path)

            self.current_path = path
            self.breadcrumbs.set_path(path)
            self.switch_to_normal_mode()
            
            # self.model.setRootPath(path) # Moved up
            
            idx = self.model.index(path)
            if idx.isValid():
                self.tree_view.setRootIndex(idx)
                self.list_view.setRootIndex(idx)
            
            folder_name = os.path.basename(path)
            if not folder_name and ':' in path: folder_name = path 
            self.title_label.setText(f"{self.pane_name} - {folder_name}")
        except Exception as e:
            print(f"CRASH PREVENTION: Error navigating to {path}: {e}")
            traceback.print_exc()

    def go_up(self):
        # [NEW] Handle Zip Up
        if '|' in self.current_path:
            zip_path, subpath = self.current_path.split('|', 1)
            if not subpath: # At root of zip
                self.navigate(os.path.dirname(zip_path))
            else:
                # Go up one level in zip
                # Remove trailing slash for reliable dirname
                subpath = subpath.rstrip('/')
                new_sub = os.path.dirname(subpath)
                if not new_sub: # We were at toplevel folder
                     self.navigate(f"{zip_path}|")
                else:
                     self.navigate(f"{zip_path}|{new_sub}/")
            return

        parent = os.path.dirname(self.current_path)
        if self.current_path == "sys:this_pc": return # Up from This PC? Default behavior is fine or disable
        
        if parent and parent != self.current_path: 
            self.navigate(parent)
        elif len(self.current_path) == 3 and self.current_path.endswith(":/"): 
            self.navigate("sys:this_pc") # From C:/ go to This PC

    def toggle_path_edit(self):
        if self.path_edit.isVisible():
            self.path_edit.hide()
            self.breadcrumbs.show()
        else:
            self.path_edit.setText(self.current_path)
            self.breadcrumbs.hide()
            self.path_edit.show()
            self.path_edit.setFocus()
    
    def on_double_click(self, index):
        # [NEW] Handle My PC click
        if self.current_path == "sys:this_pc":
            path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
            if path: 
                log_debug(f"Double-click on THIS PC drive: {path}")
                # Use singleShot to defer navigation, preventing crash when model changes
                # [FIX - ATTEMPT 2] Restore singleShot + keep persistence
                QTimer.singleShot(0, lambda: self.navigate(path))
            return

        # [NEW] Handle Zip Browsing
        if '|' in self.current_path or isinstance(self.tree_view.model(), ZipExplorationModel):
             try:
                 virtual_path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
                 if virtual_path:
                     # Check if it's a folder inside zip
                     if virtual_path.endswith('/'):
                         self.navigate(virtual_path)
                     else:
                         # It's a file inside a zip
                         pass
             except Exception as e:
                 print(f"Error handling zip double-click: {e}")
             return

        if self.tree_view.model() == self.search_model:
            full_path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
            if full_path and os.path.exists(full_path):
                if os.path.isdir(full_path):
                    self.navigate(full_path)
                    return
                else:
                    path = full_path
            else:
                return
        elif self.tree_view.model() == self.model: # Explicitly check for FS model
            path = self.model.filePath(index)
        else:
            return # Unknown model, ignore to prevent crash
    
        if os.path.isdir(path):
            self.navigate(path)
        else:
            # [NEW] Check if zip file
            if path.lower().endswith('.zip'):
                self.navigate(path)
                return

            # Check if executable file
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.exe', '.bat', '.cmd', '.ps1', '.com']:
                try:
                    work_dir = os.path.dirname(path)
                    safe_launch(path, cwd=work_dir, shell=(ext == '.bat' or ext == '.cmd'))
                    return
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not launch executable:\n{e}")
                    return

            # Check if internal markdown viewer/editor is enabled
            use_internal = False
            if self.window() and hasattr(self.window(), 'settings'):
                use_internal = self.window().settings.get("use_internal_md", False)
            if use_internal and path.lower().endswith('.md'):
                MarkdownViewerDialog(path, self.window()).exec()
                return

            # Check if internal text editor is enabled
            use_internal_txt = False
            include_html = False
            if self.window() and hasattr(self.window(), 'settings'):
                use_internal_txt = self.window().settings.get("use_internal_txt", True)
                include_html = self.window().settings.get("include_html", False)
            
            is_txt = is_text_file(path)
            if is_txt:
                if ext in ['.html', '.htm'] and not include_html:
                    is_txt = False
                    
            if use_internal_txt and is_txt:
                TextEditorDialog(path, self.window()).exec()
                return

            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def apply_column_settings(self):
        # 1. Load columns from the ACTIVE PROFILE
        fields = ["Name", "Size", "Type", "Date Modified"]
        
        if self.window() and hasattr(self.window(), 'settings'):
            profs = self.window().settings.get("profiles", {})
            if self.current_profile in profs:
                fields = profs[self.current_profile].get("display", fields)
        
        # 2. Update model structure
        self.model.set_custom_columns(fields)
        
        # 3. Determine Logical Indices for the requested fields
        # Standard Mapping:
        # 0: Name
        # 1: Size
        # 2: Type
        # 3: Date Modified
        # 4+: Custom Columns (in order of appearance in 'fields', minus standard ones)
        
        custom_cols_in_model = self.model.custom_columns # This list matches indices 4, 5, 6...
        
        target_logical_order = []
        
        for f in fields:
            if f == "Name": target_logical_order.append(0)
            elif f == "Size": target_logical_order.append(1)
            elif f == "Type": target_logical_order.append(2)
            elif f == "Date Modified": target_logical_order.append(3)
            elif f in custom_cols_in_model:
                # Calculate index: 4 + position in the custom list
                target_logical_order.append(4 + custom_cols_in_model.index(f))
                
        # 4. Move Sections in Header to match Target Order
        header = self.tree_view.header()
        
        for visual_pos, logical_idx in enumerate(target_logical_order):
            current_visual_pos = header.visualIndex(logical_idx)
            header.moveSection(current_visual_pos, visual_pos)
            
        # 5. Set Visibility
        # First hide everything to be safe, or just selectively show/hide
        total_cols = self.model.columnCount()
        for i in range(total_cols):
            if i in target_logical_order:
                self.tree_view.setColumnHidden(i, False)
                if self.tree_view.columnWidth(i) < 20:
                    self.tree_view.setColumnWidth(i, 120)
            else:
                self.tree_view.setColumnHidden(i, True)

    def set_view_mode(self, mode):
        self.current_view_mode = mode 
        if mode == "Images":
            self.stack.setCurrentIndex(1) # List/Images
            self.navigate(self.current_path)
            self.tree_view.setRootIndex(self.model.index(self.current_path))
        else:
            self.stack.setCurrentIndex(0) # Tree/Details/Narrow
            if mode == "Narrow":
                for i in range(1, self.model.columnCount()): self.tree_view.setColumnHidden(i, True)
            elif mode == "Detailed":
                self.apply_column_settings()
                self.tree_view.viewport().update()
                self.tree_view.update()
            self.navigate(self.current_path)

    def get_valid_local_path(self):
        path = self.current_path
        if not path:
            return os.path.expanduser("~")
        if path.startswith("sys:") or path.startswith("shell:") or not os.path.exists(path):
            return os.path.expanduser("~")
        return os.path.normpath(path)

    def open_powershell(self):
        local_path = self.get_valid_local_path()
        try:
            subprocess.Popen(["powershell.exe"], cwd=local_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open PowerShell:\n{e}")

    def open_cmd(self):
        local_path = self.get_valid_local_path()
        try:
            subprocess.Popen(["cmd.exe"], cwd=local_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open CMD:\n{e}")
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()
            
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()
            
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls: return
        
        target_dir = self.current_path
        index = QModelIndex()
        view = self.tree_view if self.tree_view.isVisible() else self.list_view
        index = view.indexAt(event.position().toPoint())
            
        if index.isValid():
            if view.model() == self.search_model:
                path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
                if path and os.path.isdir(path):
                    target_dir = path
            elif self.model.isDir(index):
                target_dir = self.model.filePath(index)

        menu = QMenu(self)
        action_copy = menu.addAction(f"Copy to {os.path.basename(target_dir)}")
        action_move = menu.addAction(f"Move to {os.path.basename(target_dir)}")
        
        # [NEW] Check for Zip Files
        src_paths = [u.toLocalFile() for u in urls if os.path.exists(u.toLocalFile())]
        zip_files = [p for p in src_paths if p.lower().endswith('.zip')]
        
        action_extract = None
        if zip_files:
             action_extract = menu.addAction("Extract here")
             
        action_cancel = menu.addAction("Cancel")
        res = menu.exec(QCursor.pos())
        
        if res == action_cancel or not res: return
            
        if action_extract and res == action_extract:
            if isinstance(self.window(), MainWindow):
                self.window().run_threaded_io("unzip", zip_files, target_dir)
            event.accept()
            return

        op_type = "move" if res == action_move else "copy"
        # src_paths already calculated above
        
        if isinstance(self.window(), MainWindow):
            self.window().run_threaded_io(op_type, src_paths, target_dir)
        event.accept()
        
    def get_selected_paths(self):
        paths = []
        view = self.tree_view if self.tree_view.isVisible() else self.list_view
        model = view.model()

        indexes = []
        if self.tree_view.isVisible():
            indexes = view.selectionModel().selectedRows()
        else:
            indexes = view.selectionModel().selectedIndexes()
            
        for idx in indexes:
            if model == self.search_model:
                p = idx.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
                if p: paths.append(p)
            else:
                paths.append(self.model.filePath(idx))
        
        return list(set(paths))

    def copy_selection(self):
        paths = self.get_selected_paths()
        if not paths: return
        mime = QMimeData()
        urls = [QUrl.fromLocalFile(p) for p in paths]
        mime.setUrls(urls)
        QApplication.clipboard().setMimeData(mime)

    def paste_selection(self, is_cut_operation):
        mime = QApplication.clipboard().mimeData()
        if not mime.hasUrls(): return
        urls = mime.urls()
        target_dir = self.current_path
        src_paths = [u.toLocalFile() for u in urls if os.path.exists(u.toLocalFile())]
        if not src_paths: return

        op_type = "move" if is_cut_operation else "copy"
        if isinstance(self.window(), MainWindow):
            self.window().run_threaded_io(op_type, src_paths, target_dir)
    
    def delete_selection(self):
        paths = self.get_selected_paths()
        if not paths: return
        window = self.window()
        if not isinstance(window, MainWindow): return

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText(f"Delete {len(paths)} items?")
        msg.setInformativeText("Items will be moved to the Trash folder and can be undone.")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg.exec() != QMessageBox.StandardButton.Yes: return

        trash_dir = window.settings_mgr.trash_dir
        window.run_threaded_io("delete", paths, trash_dir)

    def open_context_menu(self, point):
        view = self.sender()
        if not isinstance(view, QAbstractItemView):
            view = self.tree_view if self.tree_view.isVisible() else self.list_view
        index = view.indexAt(point)
        if not index.isValid(): return
        
        if view.model() == self.search_model:
            path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        else:
            path = self.model.filePath(index)
            
        is_txt = is_text_file(path)
        if is_txt:
            include_html = self.window().settings.get("include_html", False)
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.html', '.htm'] and not include_html:
                is_txt = False

        menu = QMenu()
        act_open = menu.addAction("Open")
        menu.addSeparator()
        
        # [NEW] Jump to Folder for Search Results
        if view.model() == self.search_model:
            act_jump = menu.addAction("Jump to this folder")
            act_jump.triggered.connect(lambda: self.navigate(os.path.dirname(path)))
            menu.addSeparator()
        
        # Open With Submenu [DISABLED]
        # open_with_menu = menu.addMenu("Open With")
        # 
        # # 1. Associated Apps
        # ext = os.path.splitext(path)[1].lower()
        # assoc_apps = get_associated_apps(ext)
        # for app_name, app_path in assoc_apps:
        #     a = open_with_menu.addAction(app_name)
        #     a.triggered.connect(lambda checked, p=path, ap=app_path: self.window().on_open_with_app(p, ap))
        #     
        # if assoc_apps:
        #     open_with_menu.addSeparator()
        #     
        # # 2. Choose another app
        # act_choose_app = open_with_menu.addAction("Choose another app")
        # act_choose_app.triggered.connect(lambda: self.window().on_open_with(path))
        # menu.addSeparator()
        
        act_cut = menu.addAction("Cut")
        act_copy = menu.addAction("Copy")
        act_paste = menu.addAction("Paste")
        act_del = menu.addAction("Delete")
        menu.addSeparator()
        act_rename = menu.addAction("Rename")
        act_copy_path = menu.addAction("Copy path to clipboard")
        act_copy_filename = menu.addAction("Copy filename to clipboard")
        act_copy_contents = None
        if is_txt:
            act_copy_contents = menu.addAction("Copy contents to clipboard")
        menu.addSeparator()
        act_bookmark = menu.addAction("Add to bookmarks") 
        act_fav = menu.addAction("Add to favorite apps")
        menu.addSeparator()
        act_compress = menu.addAction("Compress to zip")
        
        act_unzip_here = None
        act_unzip_folder = None
        if path.lower().endswith('.zip'):
            act_unzip_here = menu.addAction("Extract here")
            act_unzip_folder = menu.addAction(f"Extract to {os.path.splitext(os.path.basename(path))[0]}/")
            
        act_view_md = None
        if path.lower().endswith('.md'):
            act_view_md = menu.addAction("View markdown file")
            
        use_internal_txt = self.window().settings.get("use_internal_txt", True)
                
        act_edit = None
        if use_internal_txt and is_txt:
            act_edit = menu.addAction("Edit")
        
        menu.addSeparator()

        send_to_menu = menu.addMenu("Send to")
        act_send_desktop = send_to_menu.addAction("Desktop (create shortcut)")
        act_send_docs = send_to_menu.addAction("Documents")
        sendto_dir = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'SendTo')
        if os.path.exists(sendto_dir):
            send_to_menu.addSeparator()
            items = []
            try: items = sorted(os.listdir(sendto_dir), key=lambda x: x.lower())
            except: pass
            for item_name in items:
                if "Desktop (create shortcut)" in item_name: continue
                full_path = os.path.join(sendto_dir, item_name)
                display_name = os.path.splitext(item_name)[0]
                action = send_to_menu.addAction(display_name)
                action.triggered.connect(lambda checked, p=full_path, s=path: self.window().on_custom_sendto(s, p))
        act_sendto_here = menu.addAction("Create sendto destination to here")
        menu.addSeparator()
        
        act_custom_edit = None
        custom_editor = self.window().settings.get("custom_editor_path")
        if custom_editor and os.path.exists(custom_editor):
            app_name = os.path.splitext(os.path.basename(custom_editor))[0].title()
            act_custom_edit = menu.addAction(f"Edit in {app_name}")
        
        act_notepad = menu.addAction("Edit in notepad")
        act_notepad_plus = menu.addAction("Edit in notepad++")
        menu.addSeparator()
        act_props = menu.addAction("Properties")

        action = menu.exec(view.viewport().mapToGlobal(point))
        if not action: return
        
        if action == act_open:
            self.on_double_click(index)
        elif action == act_rename: self.tree_view.edit(index)

        elif action == act_copy_path: QApplication.clipboard().setText(path)
        elif action == act_copy_filename: QApplication.clipboard().setText(os.path.basename(path))
        elif act_copy_contents and action == act_copy_contents:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                QApplication.clipboard().setText(content)
            except Exception as e:
                QMessageBox.critical(self.window(), "Error", f"Failed to copy file contents: {e}")
        elif action == act_fav:
             paths = self.get_selected_paths()
             if not paths: paths = [path]
             for p in paths: self.window().add_favorite_item(p)
        elif action == act_cut: self.window().on_cut()
        elif action == act_copy: self.window().on_copy()
        elif action == act_paste: self.window().on_paste()
        elif action == act_del: self.delete_selection() # [FIX]
        elif action == act_props: PropertiesDialog(path, self.window()).exec()
        elif action == act_bookmark: self.window().add_bookmark_item(os.path.basename(path), path)
        elif action == act_compress: self.window().on_compress_selection()
        elif action == act_view_md:
             MarkdownViewerDialog(path, self.window()).exec()
        elif act_edit and action == act_edit:
             TextEditorDialog(path, self.window()).exec()
        elif action == act_unzip_here: self.window().run_threaded_io("unzip", [path], os.path.dirname(path))
        elif action == act_unzip_folder:
             folder_name = os.path.splitext(os.path.basename(path))[0]
             target_path = os.path.join(os.path.dirname(path), folder_name)
             self.window().run_threaded_io("unzip", [path], target_path)
        elif action == act_send_desktop: self.window().on_send_to_desktop(path)
        elif action == act_send_docs: self.window().on_send_to_documents(path)
        elif action == act_sendto_here: self.window().on_create_sendto_destination(path)
        elif act_custom_edit and action == act_custom_edit: safe_launch(custom_editor, arguments=[path])
        elif action == act_notepad: safe_launch('notepad.exe', arguments=[path])
        elif action == act_notepad_plus:
             npp_paths = [
                 r"C:\Program Files\Notepad++\notepad++.exe",
                 r"C:\Program Files (x86)\Notepad++\notepad++.exe"
             ]
             found = False
             for npp in npp_paths:
                 if os.path.exists(npp):
                     safe_launch(npp, arguments=[path])
                     found = True
                     break
             if not found:
                 QMessageBox.warning(self, "Error", "Notepad++ executable not found in standard locations.")
                  
    def update_button_widths(self, font_size):
        # Create QFont matching settings font size and apply to buttons directly
        font = self.btn_ps.font()
        font.setPointSize(font_size)
        self.btn_ps.setFont(font)
        self.btn_cmd.setFont(font)
        
        # Measure text width using QFontMetrics for highly robust fitting
        metrics = QFontMetrics(font)
        try:
            w_ps = metrics.horizontalAdvance("PS")
            w_cmd = metrics.horizontalAdvance("CMD")
        except AttributeError:
            w_ps = metrics.width("PS")
            w_cmd = metrics.width("CMD")
            
        # Compute proper sizes combining minimum base scaling with text dimensions, then make them 50% wider
        width_ps = int(max(w_ps + 16, int(24 * (font_size / 10.0))) * 1.5)
        width_cmd = int(max(w_cmd + 16, int(45 * (font_size / 10.0))) * 1.5)
        height = max(metrics.height() + 8, int(24 * (font_size / 10.0)))
        
        # Reset maximum size to allow dynamic expansion, then set minimum size
        self.btn_ps.setMaximumSize(16777215, 16777215)
        self.btn_cmd.setMaximumSize(16777215, 16777215)
        
        self.btn_ps.setMinimumSize(width_ps, height)
        self.btn_cmd.setMinimumSize(width_cmd, height)
        
        self.btn_ps.updateGeometry()
        self.btn_cmd.updateGeometry()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        self.settings_mgr = SettingsManager()
        
        # --- FIX: Check if file exists BEFORE loading so we can show license ---
        loaded_data = self.settings_mgr.load()
        is_first_run = loaded_data is None 
        # is_first_run = False # [DEBUG] SKIP LICENSE
        self.settings = loaded_data or {}
        
        # Ensure profiles dict exists
        if "profiles" not in self.settings:
            self.settings["profiles"] = {
                "Default": {
                    "display": ["Name", "Size", "Type", "Date Modified"],
                    "props": ["Name", "Size", "Type", "Date Modified", "Date Created"]
                }
            }
        
        # --- NEW: Show License if first run ---
        if is_first_run:
            lic = LicenseDialog(self)
            if lic.exec() != QDialog.DialogCode.Accepted:
                sys.exit()
            self.move(self.screen().geometry().center() - self.rect().center())
        else:
             if "geometry" in self.settings:
                 self.restoreGeometry(bytes.fromhex(self.settings["geometry"]))

        # --- NEW: Enforce Default Fields if Empty ---
        default_fields = ["Name", "Type", "Date Modified"]
        
        # Check Display Column Set
        if not self.settings.get("fields_display"):
            self.settings["fields_display"] = default_fields
            
        # Check Properties Pane Set
        if not self.settings.get("fields_props"):
            self.settings["fields_props"] = default_fields
        # --------------------------------------------
        
        self.undo_stack = []
        self.redo_stack = []
        self.current_batch = [] 
        self.clipboard_pending_move = False 

        self.panes = []
        self.active_pane = None
        self.bookmark_dock = None 
        self.fav_tree = None 
        self.props_pane = None 
        
        self.setup_ui()
        self.setup_menus()
        self.setup_sidebar() 
        
        # [NEW] Apply theme and font size on startup
        self.set_theme(self.settings.get("theme", "light"))
        
        self.resize(800, 600)
        
        self.set_layout_mode(self.settings.get("layout_mode", "2-vert"))

        if self.bookmark_dock:
             bm_width = self.settings.get("bookmark_width", 150)
             self.resizeDocks([self.bookmark_dock], [bm_width], Qt.Orientation.Horizontal)

        # --- Start Indexer and Watcher ---
        if HAS_WATCHDOG:
            self.watcher = QFileSystemModel(self) # Dummy
            self.fs_watcher = FileSystemWatcher(self.settings_mgr.db_path)
            try:
                self.fs_watcher.start()
            except Exception as e:
                log_debug(f"CRITICAL: Failed to start FileSystemWatcher: {e}") 
            
        # --- Initialize Indexer ---
        self.indexer = IndexerWorker(self.settings_mgr.db_path, self.settings.get("ignore_recycle_bin", True))
        self.indexer.progress_signal.connect(self.on_scan_progress)
        self.indexer.finished_signal.connect(self.on_scan_finished)
        
        self.start_drive_monitoring()
    def get_special_folder(self, csidl):
        try:
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
                return buf.value
        except:
            pass
        return None

    def resolve_shell_path(self, path):
        if not path or not path.startswith("shell:"): return path
        
        cmd = path.lower()
        if cmd == "shell:sendto": return self.get_special_folder(9)
        if cmd == "shell:startup": return self.get_special_folder(7)
        if cmd == "shell:personal": return self.get_special_folder(5) # Documents
        if cmd == "shell:downloads": 
            # Downloads is not a standard CSIDL, but we can try 
            # FOLDERID_Downloads = {374DE290-123F-4565-9164-39C4925E467B}
            # Or use QStandardPaths
            return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        return path # shell:appsfolder etc. remains as is

    def add_bookmark_item(self, name, path, parent=None):
        if not path: return
        # Allow shell: paths even if they don't exist on disk (virtual folders)
        if not os.path.exists(path) and not path.startswith("shell:"): return
        # --- FIX: Use QTreeWidgetItem instead of QListWidgetItem ---
        root = parent if parent else self.bookmark_tree.invisibleRootItem()
        item = QTreeWidgetItem(root)
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.save_settings()
        return item

    def ensure_system_bookmarks(self):
        root = self.bookmark_tree.invisibleRootItem()
        system_item = None
        for i in range(root.childCount()):
            if root.child(i).text(0) == "System":
                system_item = root.child(i)
                # Ensure it's at the very top (index 0)
                if i > 0:
                    item = root.takeChild(i)
                    root.insertChild(0, item)
                    system_item = item
                break
        
        system_defaults = [
            ("SendTo", "shell:sendto"),
            ("Startup", "shell:startup"),
            ("Apps", "shell:appsfolder"),
            ("Downloads", "shell:downloads"),
            ("Personal", "shell:personal"),
            ("Control Panel", "shell:ControlPanelFolder")
        ]
        
        if system_item is not None:
            # Check existing children to avoid duplicates
            existing_names = []
            for j in range(system_item.childCount()):
                existing_names.append(system_item.child(j).text(0))
            
            for name, path in system_defaults:
                if name not in existing_names:
                    sub_item = QTreeWidgetItem(system_item)
                    sub_item.setText(0, name)
                    sub_item.setData(0, Qt.ItemDataRole.UserRole, path)
                    sub_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            return
        
        # Not found, create it at the top
        system_item = QTreeWidgetItem()
        system_item.setText(0, "System")
        system_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        # No UserRole data means it's a structural folder
        
        for name, path in system_defaults:
            sub_item = QTreeWidgetItem(system_item)
            sub_item.setText(0, name)
            sub_item.setData(0, Qt.ItemDataRole.UserRole, path)
            sub_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        
        system_item.setExpanded(False)
        root.insertChild(0, system_item)

    def add_favorite_item(self, path, parent_item=None):
        if not self.fav_tree: return
        name = os.path.basename(path)
        root = parent_item if parent_item else self.fav_tree.invisibleRootItem()
        item = QTreeWidgetItem(root)
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        
        if os.path.isdir(path):
            item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        else:
            item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.save_settings()

    def add_favorite_group(self, name, parent_item=None):
        if not self.fav_tree: return
        root = parent_item if parent_item else self.fav_tree.invisibleRootItem()
        item = QTreeWidgetItem(root)
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole, None)
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        item.setExpanded(True)
        self.save_settings()
        return item
            
    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0,0,0,0)
        
        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Last Scan Label (Left)
        last_scan_time = self.settings.get("last_scan_time", "Never")
        self.lbl_last_scan = QLabel(f"Last Scan: {last_scan_time}")
        self.status_bar.addWidget(self.lbl_last_scan)
        
        self.status_bar.addWidget(QLabel(" | "))
        
        # Rescan Link (Left)
        self.lbl_rescan = QLabel("<a href='#'>Scan Now</a>")
        self.lbl_rescan.setOpenExternalLinks(False)
        self.lbl_rescan.linkActivated.connect(self.start_rescan)
        self.status_bar.addWidget(self.lbl_rescan)

    def start_rescan(self):
        if not self.indexer.isRunning():
            self.lbl_last_scan.setText("Scanning...")
            self.indexer.start()

    def on_scan_progress(self, count):
        self.lbl_last_scan.setText(f"Scanning... ({count} indexed)")

    def on_scan_finished(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.lbl_last_scan.setText(f"Last Scan: {now}")
        self.settings["last_scan_time"] = now
        self.settings_mgr.save(self.settings)

    def setup_sidebar(self):
        dock = QDockWidget("Bookmarks", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.bookmark_dock = dock 
        
        # --- FIX: Define self.sidebar_splitter properly as a class member ---
        self.sidebar_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # --- FIX: Switch to QTreeWidget to match load_bookmarks_recursive logic ---
        self.bookmark_tree = BookmarkTree(self) 
        
        self.sidebar_splitter.addWidget(self.bookmark_tree)
        
        # Favorites Tree
        self.fav_tree = FavoritesTree(self)
        self.fav_tree.setHeaderLabel("Favorite Apps")
        self.fav_tree.setHeaderHidden(False)

        self.sidebar_splitter.addWidget(self.fav_tree)
        
        # [FIX] Restore Sidebar Splitter Sizes (Bookmarks vs Favorites)
        saved_sizes = self.settings.get("sidebar_split_sizes", [200, 400])
        self.sidebar_splitter.setSizes(saved_sizes)
        
        # Load Bookmarks
        saved_bm = self.settings.get("bookmarks")
        if saved_bm:
            if isinstance(saved_bm, dict):
                 # Handle legacy dict format if necessary
                 for name, path in saved_bm.items(): self.add_bookmark_item(name, path)
            else: 
                # Correctly load recursive list
                self.load_bookmarks_recursive(saved_bm, self.bookmark_tree.invisibleRootItem())
        else: 
            self.create_default_bookmarks()
            
        # [NEW] Always ensure "System" folder is at the top, even for existing users
        self.ensure_system_bookmarks()
            
        # Load Favorites
        saved_favs = self.settings.get("favorites", [])
        self.load_favorites_recursive(saved_favs, self.fav_tree.invisibleRootItem())
        
        dock.setWidget(self.sidebar_splitter)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def create_default_bookmarks(self):
        # [NEW] Add "This PC"
        pc_item = QTreeWidgetItem(self.bookmark_tree)
        pc_item.setText(0, "This PC")
        pc_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon))
        pc_item.setData(0, Qt.ItemDataRole.UserRole, "sys:this_pc")

        defaults = [
            ("Desktop", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)),
            ("Documents", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)),
            ("Downloads", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)),
            ("Pictures", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)),
            ("Videos", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)),
            ("Music", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation))
        ]
        for name, path in defaults: self.add_bookmark_item(name, path)
        
        # Removed OneDrive, Dropbox, and System folder as per user request (System added back via ensure_system_bookmarks)

    def load_bookmarks_recursive(self, data_list, parent_item):
        for entry in data_list:
            item = QTreeWidgetItem(parent_item)
            item.setText(0, entry["name"])
            if entry.get("type") == "folder":
                 item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                 
                 # [FIX] Collapse "System", expand others by default
                 if entry["name"] == "System":
                     item.setExpanded(False)
                 else:
                     item.setExpanded(True)
                     
                 if "children" in entry: self.load_bookmarks_recursive(entry["children"], item)
            else:
                 path = entry.get("path", "")
                 item.setData(0, Qt.ItemDataRole.UserRole, path)
                 item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))

    def load_favorites_recursive(self, data_list, parent_item):
        for entry in data_list:
            item = QTreeWidgetItem(parent_item)
            item.setText(0, entry["name"])
            if entry["type"] == "folder":
                item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                item.setExpanded(False) # Collapsed on startup
                if "children" in entry: self.load_favorites_recursive(entry["children"], item)
            else:
                path = entry.get("path", "")
                item.setData(0, Qt.ItemDataRole.UserRole, path)
                info = QFileInfo(path)
                if info.exists():
                    if info.isDir():
                        QTreeWidgetItem(item)
                        icon_prov = QFileIconProvider()
                        item.setIcon(0, icon_prov.icon(info))
                    else:
                        icon_prov = QFileIconProvider()
                        item.setIcon(0, icon_prov.icon(info))
                else: item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))

    # --- NEW: Direct Action for Menu ---
    def action_add_bookmark(self):
        if self.active_pane and self.active_pane.current_path:
            path = self.active_pane.current_path
            name = os.path.basename(path)
            if not name: name = path # Drive root case
            self.add_bookmark_item(name, path)
            
    def on_bookmark_click(self, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and self.active_pane:
            self.active_pane.navigate(path)

    def setup_menus(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("File")
        
        act_new_file = file_menu.addAction("New File")
        act_new_file.setShortcut("Ctrl+N")
        act_new_file.triggered.connect(self.new_file)
        
        act_new_folder = file_menu.addAction("New Folder")
        act_new_folder.setShortcut("Ctrl+Shift+N")
        act_new_folder.triggered.connect(self.new_folder)
        
        file_menu.addSeparator()
        file_menu.addAction("Add Bookmark").triggered.connect(self.action_add_bookmark) 
        file_menu.addAction("Exit").triggered.connect(self.close)
        
        edit_menu = bar.addMenu("Edit")
        act_cut = edit_menu.addAction("Cut")
        act_cut.setShortcut("Ctrl+X")
        act_cut.triggered.connect(self.on_cut)

        act_copy = edit_menu.addAction("Copy")
        act_copy.setShortcut("Ctrl+C")
        act_copy.triggered.connect(self.on_copy)

        act_paste = edit_menu.addAction("Paste")
        act_paste.setShortcut("Ctrl+V")
        act_paste.triggered.connect(self.on_paste)

        act_del = edit_menu.addAction("Delete")
        act_del.setShortcut("Del")
        act_del.triggered.connect(self.on_delete)

        edit_menu.addSeparator()
        self.act_undo = edit_menu.addAction("Undo")
        self.act_undo.setShortcut("Ctrl+Z")
        self.act_undo.triggered.connect(self.undo)
        
        self.act_redo = edit_menu.addAction("Redo")
        self.act_redo.setShortcut("Ctrl+Y")
        self.act_redo.triggered.connect(self.redo)
        
        view_menu = bar.addMenu("View")
        self.view_group = QActionGroup(self) # Create exclusive group
        
        self.act_narrow = view_menu.addAction("Narrow")
        self.act_narrow.setCheckable(True)
        self.act_narrow.setActionGroup(self.view_group)
        self.act_narrow.triggered.connect(lambda: self.set_active_pane_view("Narrow"))
        
        self.act_detail = view_menu.addAction("Detailed")
        self.act_detail.setCheckable(True)
        self.act_detail.setActionGroup(self.view_group)
        self.act_detail.triggered.connect(lambda: self.set_active_pane_view("Detailed"))
        
        self.act_img = view_menu.addAction("Images")
        self.act_img.setCheckable(True)
        self.act_img.setActionGroup(self.view_group)
        self.act_img.triggered.connect(lambda: self.set_active_pane_view("Images"))
        
        layout_menu = bar.addMenu("Layouts")
        layout_menu.addAction("1 Pane").triggered.connect(lambda: self.set_layout_mode("1"))
        layout_menu.addAction("1 Pane + Props").triggered.connect(lambda: self.set_layout_mode("1-prop"))
        layout_menu.addAction("2 Vertical").triggered.connect(lambda: self.set_layout_mode("2-vert"))
        layout_menu.addAction("2 Vertical + Props").triggered.connect(lambda: self.set_layout_mode("2-prop"))
        layout_menu.addAction("3 Vertical").triggered.connect(lambda: self.set_layout_mode("3-vert"))
        layout_menu.addAction("3 (2 Left, 1 Right)").triggered.connect(lambda: self.set_layout_mode("3-2L1R"))
        layout_menu.addAction("3 (1 Left, 2 Right)").triggered.connect(lambda: self.set_layout_mode("3-1L2R"))
        layout_menu.addAction("4 Vertical").triggered.connect(lambda: self.set_layout_mode("4-vert"))
        layout_menu.addAction("4 Grid").triggered.connect(lambda: self.set_layout_mode("4-grid"))
        
        opt_menu = bar.addMenu("Options")
        opt_menu.addAction("Settings...").triggered.connect(self.open_settings_dialog) # NEW: Settings Dialog
        opt_menu.addAction("Fields...").triggered.connect(self.open_fields_dialog)
        
        tools_menu = bar.addMenu("Tools")
        tools_menu.addAction("Export Database to CSV...").triggered.connect(self.on_export_csv)
        tools_menu.addAction("Generate Statistics Report...").triggered.connect(self.on_generate_stats)

        help_menu = bar.addMenu("Help")
        # --- UPDATED LINK ---
        help_menu.addAction("Documentation").triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://sites.google.com/view/getproductivefast/file-manager/documentation")))
        help_menu.addAction("Check for Updates").triggered.connect(lambda: UpdateDialog(self).exec())
        help_menu.addAction("Change Log").triggered.connect(lambda: ChangeLogDialog(self).exec())
        help_menu.addAction("About").triggered.connect(lambda: AboutDialog(self).exec())

    def on_export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Database", "file_index.csv", "CSV Files (*.csv)")
        if not path: return

        # Default to 70MB if not set
        max_size = self.settings.get("max_dump_size", 73400320)
        ignore_recycle = self.settings.get("ignore_recycle_bin", True)
        
        self.export_progress = QProgressDialog("Exporting Database...", "Cancel", 0, 0, self)
        self.export_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.export_progress.show()
        
        self.export_worker = ExportWorker(self.settings_mgr.db_path, path, max_size, ignore_recycle)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_progress.canceled.connect(self.export_worker.stop)
        self.export_worker.start()

    def on_export_finished(self, success, msg):
        self.export_progress.close()
        if success: QMessageBox.information(self, "Export Complete", msg)
        else: QMessageBox.critical(self, "Export Failed", msg)
        self.export_worker = None

    def on_generate_stats(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Report", "file_stats.txt", "Text Files (*.txt)")
        if path:
            success, msg = self.report_mgr.generate_stats(path)
            if success: QMessageBox.information(self, "Report Generated", msg)
            else: QMessageBox.critical(self, "Report Failed", msg)

    def set_active_pane_view(self, mode):
        if self.active_pane:
            self.active_pane.set_view_mode(mode)

    def on_open_with(self, path):
        if not path or not os.path.exists(path): return
        # Open the Windows "Open With" dialog
        # quote path for shell
        path = os.path.abspath(path)
        try:
            # rundll32 invocation is tricky with spaces. 
            # The most reliable way is often to use the bare command string with shell=True
            cmd = f'rundll32.exe shell32.dll,OpenAs_RunDLL "{path}"'
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open 'Open With' dialog: {e}")

    def on_open_with_app(self, path, app_path):
        if not path or not os.path.exists(path): return
        try:
            safe_launch(app_path, arguments=[path])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open with selected app: {e}")
        
    def on_open_with(self, path):
        if not path or not os.path.exists(path): return
        
        # Use Windows ShellExecuteW directly to trigger "openas"
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "openas", path, None, None, 1)
            
            # Error 31 = SE_ERR_NOASSOC (No file association)
            # This paradoxically happens when "Open With" is most needed.
            # Fallback to forcing the dialog via rundll32.
            if ret == 31:
                log_debug(f"Open With: Error 31 (No Association) for {path}. Forcing dialog...")
                # Use list-based Popen to avoid shell quoting issues
                subprocess.Popen(["rundll32", "shell32.dll,OpenAs_RunDLL", path])
                return

            if ret <= 32:
                # Other error codes: 2=File not found, 5=Access denied, etc.
                QMessageBox.warning(self, "Open With Error", 
                                   f"Failed to open dialog.\nError Code: {ret}\nPath: {path}")
            else:
                log_debug(f"Open With triggered successfully for: {path}")

        except Exception as e:
            log_debug(f"Open With ShellExecute exception: {e}")
            QMessageBox.warning(self, "Open With Error", f"Exception: {e}")

    def on_cut(self):
        self.clipboard_pending_move = True
        if self.active_pane: self.active_pane.copy_selection()

    def on_copy(self):
        self.clipboard_pending_move = False
        if self.active_pane: self.active_pane.copy_selection()

    def on_paste(self):
        if self.active_pane: 
            self.active_pane.paste_selection(self.clipboard_pending_move)
            if self.clipboard_pending_move:
                self.clipboard_pending_move = False

    def on_delete(self):
        if self.active_pane: self.active_pane.delete_selection()

    def set_theme(self, mode):
        # [NEW] Get Font Size from settings
        font_size = self.settings.get("font_size", 10)
        
        # Common styling
        base_style = f"""
            * {{ font-size: {font_size}pt; }}
            QLineEdit, QComboBox, QSpinBox {{ 
                padding: 4px; 
                border: 1px solid #ccc; 
                border-radius: 4px; 
            }}
            QMenu::separator {{ height: 1px; background: #ccc; margin: 5px; }}
        """
        
        if mode == "light":
            # Light Theme - Explicitly style Menu Bar to ensure visibility
            self.setStyleSheet(f"""
                QMainWindow, QDialog, QDockWidget {{ background-color: #f0f0f0; color: black; }}
                QFrame {{ background-color: #f0f0f0; color: black; }}
                
                /* Menus */
                QMenuBar {{ background-color: #f0f0f0; color: black; }}
                QMenuBar::item {{ background-color: transparent; color: black; }}
                QMenuBar::item:selected {{ background-color: #e0e0e0; color: black; }}
                
                QMenu {{ background-color: white; color: black; border: 1px solid #ccc; }}
                QMenu::item:selected {{ background-color: #0078d7; color: white; }}
                
                /* Lists/Trees */
                QTreeView, QListView, QListWidget, QTextEdit {{ background-color: white; color: black; border: 1px solid #ccc; }}
                QHeaderView::section {{ background-color: #e0e0e0; color: black; border: 1px solid #ccc; }}
                
                /* Controls */
                QLabel, QCheckBox, QRadioButton {{ color: black; }}
                QPushButton {{ background-color: #e0e0e0; color: black; border: 1px solid #ccc; padding: 4px; }}
                QPushButton:hover {{ background-color: #d0d0d0; }}
                
                {base_style}
                QLineEdit, QComboBox, QSpinBox {{ background-color: white; color: black; }}
                QStatusBar {{ background: #e0e0e0; color: black; }}
            """)
        else:
            # Dark Theme
            self.setStyleSheet(f"""
                QMainWindow, QDialog, QDockWidget {{ background-color: #2b2b2b; color: white; }}
                QFrame {{ background-color: #2b2b2b; color: white; }}
                
                /* Menus */
                QMenuBar {{ background-color: #2b2b2b; color: white; }}
                QMenuBar::item {{ background-color: transparent; color: white; }}
                QMenuBar::item:selected {{ background-color: #444; }}
                
                QMenu {{ background-color: #2b2b2b; color: white; border: 1px solid #444; }}
                QMenu::item:selected {{ background-color: #0078d7; color: white; }}
                
                /* Lists/Trees */
                QTreeView, QListView, QListWidget, QTextEdit {{ background-color: #1e1e1e; color: white; border: 1px solid #444; }}
                QHeaderView::section {{ background-color: #333; color: white; border: 1px solid #444; }}
                
                /* Controls */
                QLabel, QCheckBox, QRadioButton {{ color: white; }}
                QPushButton {{ background-color: #444; color: white; border: 1px solid #555; padding: 4px; }}
                QPushButton:hover {{ background-color: #555; }}
                
                {base_style}
                QLineEdit, QComboBox, QSpinBox {{ background-color: #1e1e1e; color: white; border: 1px solid #444; }}
                
                /* Specifically fix Title Bar colors in panes to differ from main bg */
                QFrame#PaneTitleBar {{ background-color: #444; }} 
                QStatusBar {{ background: #333; color: white; }}
            """)
        self.settings["theme"] = mode
        
        # Update PowerShell and CMD button widths in all panes to compensate for font size change
        for p in self.panes:
            if p:
                p.update_button_widths(font_size)

    def open_fields_dialog(self):
        FieldsDialog(self).exec()
        
    def open_settings_dialog(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.settings.update(data)
            
            # [NEW] Apply theme and font size
            self.set_theme(data["theme"])
            
            # Redraw window to fit new font sizes
            self.update()
            
            # Save settings immediately
            self.settings_mgr.save(self.settings)
            
            # [NEW] Apply hidden filter to all panes
            for p in self.panes:
                if p: p.apply_hidden_filter()
                
            # Re-launch behavior handled by OS, but we can update shortcut
            if data["launch_at_startup"]:
                create_windows_shortcut(sys.argv[0], get_startup_shortcut_path())
            else:
                if os.path.exists(get_startup_shortcut_path()):
                    try: os.remove(get_startup_shortcut_path())
                    except: pass

    def set_active_pane(self, pane):
        self.active_pane = pane
        for p in self.panes:
            p.set_color_mode(p == pane)
        
        # Update View Menu Checkmarks based on the active pane's current mode
        if hasattr(self, 'act_narrow'): 
            if pane.current_view_mode == "Narrow":
                self.act_narrow.setChecked(True)
            elif pane.current_view_mode == "Detailed":
                self.act_detail.setChecked(True)
            elif pane.current_view_mode == "Images":
                self.act_img.setChecked(True)

    def update_properties(self, path):
        if not path or '|' in path: return # Skip virtual zip paths
        if self.props_pane and self.props_pane.isVisible():
            self.props_pane.update_data(path)

    def set_all_views(self, mode):
        for p in self.panes:
            p.set_view_mode(mode)

    def record_action(self, type_, src, dst):
        # Instead of pushing to stack immediately, add to the current batch buffer
        self.current_batch.append({"type": type_, "src": src, "dst": dst})

    def undo(self):
        if not self.undo_stack:
            return
        
        # Safely handle single items vs batches
        item = self.undo_stack.pop()
        self.redo_stack.append(item) 
        
        # Normalize to list
        batch = item if isinstance(item, list) else [item]
        
        # Loop reversed to undo last action first
        for action in reversed(batch):
            try:
                # Clean paths to satisfy Windows APIs
                src = os.path.normpath(action["src"])
                dst = os.path.normpath(action["dst"])
                
                # Undo Copy: Delete the destination
                if action["type"] == "copy":
                    if os.path.exists(dst):
                        if HAS_SEND2TRASH:
                            send2trash(dst)
                        else:
                            if os.path.isdir(dst): shutil.rmtree(dst)
                            else: os.remove(dst)
                
                # Undo Move: Move dst back to src
                elif action["type"] == "move":
                    if os.path.exists(dst):
                        shutil.move(dst, src)
                        
                # Undo Delete: Move from Trash (dst) back to Original (src)
                elif action["type"] == "delete":
                    if os.path.exists(dst): 
                        shutil.move(dst, src)
                        
            except Exception as e:
                print(f"Undo Error: {e}")
                # Continue loop to try undoing the rest

    def redo(self):
        if not self.redo_stack: return
        
        item = self.redo_stack.pop()
        self.undo_stack.append(item) 
        
        batch = item if isinstance(item, list) else [item]
        
        for action in batch:
            try:
                src = os.path.normpath(action["src"])
                dst = os.path.normpath(action["dst"])

                if action["type"] == "copy":
                    if os.path.isdir(src): shutil.copytree(src, dst)
                    else: shutil.copy2(src, dst)
                elif action["type"] == "move":
                    shutil.move(src, dst)
                elif action["type"] == "delete":
                    if os.path.exists(src):
                        shutil.move(src, dst)
            except Exception as e:
                print(f"Redo Error: {e}")
            
    def start_search(self, query, pane):
        self.worker_search = SearchWorker(self.settings_mgr.db_path, query, self.settings.get("ignore_recycle_bin", True))
        self.worker_search.results_ready.connect(pane.display_search_results)
        self.worker_search.start()
        
    def on_compress_selection(self):
        if not self.active_pane: return
        paths = self.active_pane.get_selected_paths()
        if not paths: return
        
        # Ask for name
        name, ok = QInputDialog.getText(self, "Compress", "Archive Name:")
        if not ok or not name: return
        if not name.lower().endswith(".zip"): name += ".zip"
        
        target_path = os.path.join(self.active_pane.current_path, name)
        self.run_threaded_io("zip", paths, target_path)

    def on_io_error(self, message):
        self.progress.close() 
        QMessageBox.critical(self, "File Operation Error", message)

    def run_threaded_io(self, operation, src_list, target_dir):
        # [NEW] Check for Overwrite Collisions
        if operation in ["copy", "move"]:
            collisions = []
            for src in src_list:
                fname = os.path.basename(src)
                tgt = os.path.join(target_dir, fname)
                if os.path.exists(tgt):
                    # Ignore collision if copying to same folder (auto-rename logic handles this)
                    if operation == "copy" and os.path.abspath(os.path.dirname(src)) == os.path.abspath(target_dir):
                        continue
                    collisions.append(fname)
            
            if collisions:
                msg = f"The destination already has {len(collisions)} file(s) with the same names:\n\n"
                msg += "\n".join(collisions[:5])
                if len(collisions) > 5: msg += "\n..."
                msg += "\n\nDo you want to overwrite them?"
                
                reply = QMessageBox.question(self, "Confirm Overwrite", msg, 
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
                
                if reply != QMessageBox.StandardButton.Yes:
                    return

        self.progress = QProgressDialog(f"Performing {operation}...", "Cancel", 0, 0, self)
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.setMinimumDuration(0) 
        self.progress.show()

        # [FIX] Reset batch buffer at start of operation
        self.current_batch = []

        self.worker = FileWorker(operation, src_list, target_dir)
        self.worker.action_recorded.connect(self.record_action)
        self.worker.error_occurred.connect(self.on_io_error)
        self.worker.finished_all.connect(self.on_io_finished)
        self.progress.canceled.connect(self.worker.stop)
        self.worker.start()

    def on_io_finished(self):
        self.progress.close()
        self.worker = None
        
        # [FIX] Commit the collected batch to the Undo Stack
        if self.current_batch:
            self.undo_stack.append(self.current_batch)
            self.redo_stack.clear() # Clear redo history on new action
            self.current_batch = [] # Reset buffer

        if self.active_pane:
            self.active_pane.navigate(self.active_pane.current_path)
            
    def empty_trash(self):
        trash_path = self.settings_mgr.trash_dir
        if not os.path.exists(trash_path): return
        try:
            for item in os.listdir(trash_path):
                full_path = os.path.join(trash_path, item)
                if HAS_SEND2TRASH:
                    send2trash(os.path.normpath(full_path))
                else:
                    if os.path.isdir(full_path): shutil.rmtree(full_path)
                    else: os.remove(full_path)
        except Exception as e:
            print(f"Error emptying trash: {e}")
            
    def new_folder(self):
        if not self.active_pane: return
        path = self.active_pane.current_path
        base = "New Folder"
        
        # Calculate unique default name
        default_name = base
        test_path = os.path.join(path, default_name)
        counter = 1
        while os.path.exists(test_path):
            default_name = f"{base} ({counter})"
            test_path = os.path.join(path, default_name)
            counter += 1
            
        # Prompt user
        name, ok = QInputDialog.getText(self, "New Folder", "Folder Name:", text=default_name)
        if ok and name:
            new_path = os.path.join(path, name)
            try:
                os.mkdir(new_path)
                self.active_pane.navigate(path)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def new_file(self):
        if not self.active_pane: return
        path = self.active_pane.current_path
        base = "New Text Document.txt"
        
        # Calculate unique default name
        default_name = base
        test_path = os.path.join(path, default_name)
        counter = 1
        while os.path.exists(test_path):
            default_name = f"New Text Document ({counter}).txt"
            test_path = os.path.join(path, default_name)
            counter += 1
            
        # Prompt user
        name, ok = QInputDialog.getText(self, "New File", "File Name:", text=default_name)
        if ok and name:
            new_path = os.path.join(path, name)
            try:
                with open(new_path, 'w') as f: pass
                self.active_pane.navigate(path)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    # --- NEW: Implement Missing SendTo Handlers ---
    def on_send_to_desktop(self, src_path):
        """Creates a shortcut on the Desktop."""
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        name = os.path.splitext(os.path.basename(src_path))[0]
        shortcut_path = os.path.join(desktop, f"{name}.lnk")
        
        if create_windows_shortcut(src_path, shortcut_path):
            QMessageBox.information(self, "Success", f"Shortcut created on Desktop:\n{shortcut_path}")
        else:
            QMessageBox.warning(self, "Error", "Failed to create shortcut (Powershell error).")

    def on_search(self):
        query = self.search_edit.text().strip()
        if not query: return
        
        # Determine target pane
        pane = self.active_pane if self.active_pane else self.panes[0]
        self.start_search(query, pane)


    def on_send_to_documents(self, src_path):
        """Copies the file to Documents."""
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        self.run_threaded_io("copy", [src_path], docs)

    def on_create_sendto_destination(self, folder_path):
        """Creates a shortcut in the Windows SendTo folder pointing to the selected folder."""
        if not os.path.isdir(folder_path):
            QMessageBox.warning(self, "Error", "Target must be a folder.")
            return
            
        sendto_dir = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'SendTo')
        if not os.path.exists(sendto_dir):
            QMessageBox.warning(self, "Error", "SendTo folder not found.")
            return

        name = os.path.basename(folder_path)
        shortcut_path = os.path.join(sendto_dir, f"{name}.lnk")
        
        if create_windows_shortcut(folder_path, shortcut_path):
            QMessageBox.information(self, "Success", f"Added '{name}' to Send To menu.")
        else:
            QMessageBox.warning(self, "Error", "Failed to create SendTo shortcut.")

    def on_custom_sendto(self, src_path, target_executable_or_folder):
        """
        Handles sending a file to a custom destination found in the SendTo folder.
        If the target is a folder, copy. If it's an app (exe/lnk), open it.
        """
        # Resolve target if it is a shortcut
        real_target = target_executable_or_folder
        if target_executable_or_folder.lower().endswith('.lnk'):
            resolved = resolve_windows_shortcut(target_executable_or_folder)
            if resolved: real_target = resolved

        if os.path.isdir(real_target):
            self.run_threaded_io("copy", [src_path], real_target)
        elif os.path.isfile(real_target):
            # It's an application, try to open the source file with it
            try:
                safe_launch(real_target, arguments=[src_path])
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not launch application:\n{e}")

    def get_pane(self, index):
        while len(self.panes) <= index:
            saved_paths = self.settings.get("pane_paths", [])
            default_path = ""
            if index < len(saved_paths) and os.path.exists(saved_paths[index]):
                default_path = saved_paths[index]
            else:
                paths = [
                    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation),
                    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation),
                    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation),
                    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)
                ]
                default_path = paths[len(self.panes)%4]
                
            p = FilePane(f"Pane {len(self.panes)+1}", default_path, self)
            
            # --- NEW: Restore sort settings ---
            pane_sorts = self.settings.get("pane_sorts", [])
            if index < len(pane_sorts):
                sort_col, sort_order = pane_sorts[index]
                p.apply_sort_settings(sort_col, sort_order)
            
            # --- NEW: Restore View Mode ---
            pane_views = self.settings.get("pane_views", [])
            if index < len(pane_views):
                p.set_view_mode(pane_views[index])
            
            # --- NEW: Restore Pane Profile ---
            pane_profiles = self.settings.get("pane_profiles", [])
            if index < len(pane_profiles):
                p.current_profile = pane_profiles[index]
                p.refresh_profiles()
                p.apply_column_settings()
            # ----------------------------------
            
            self.panes.append(p)
        return self.panes[index]

    def clear_layout(self):
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None) 

    def set_layout_mode(self, mode):
        self.settings["layout_mode"] = mode 
        
        for p in self.panes:
            p.setParent(self.central_widget)
            p.hide() 
            
        if self.props_pane:
            self.props_pane.setParent(None)
            self.props_pane.deleteLater()
            self.props_pane = None

        self.clear_layout()
        
        def create_props_pane():
            self.props_pane = PropertiesPane(self)
            return self.props_pane
        
        # Re-implement splitters carefully
        if mode == "1":
            self.main_layout.addWidget(self.get_pane(0))
            self.get_pane(0).show()
        elif mode == "1-prop":
            s = QSplitter(Qt.Orientation.Horizontal)
            s.addWidget(self.get_pane(0))
            s.addWidget(create_props_pane())
            self.get_pane(0).show()
            self.props_pane.show()
            self.main_layout.addWidget(s)
        elif mode == "2-vert":
            s = QSplitter(Qt.Orientation.Horizontal)
            s.addWidget(self.get_pane(0))
            s.addWidget(self.get_pane(1))
            self.get_pane(0).show()
            self.get_pane(1).show()
            self.main_layout.addWidget(s)
        elif mode == "2-prop":
             s = QSplitter(Qt.Orientation.Horizontal)
             s.addWidget(self.get_pane(0))
             s.addWidget(create_props_pane())
             s.addWidget(self.get_pane(1))
             self.get_pane(0).show()
             self.get_pane(1).show()
             self.props_pane.show()
             self.main_layout.addWidget(s)
        elif mode == "3-vert":
            s = QSplitter(Qt.Orientation.Horizontal)
            s.addWidget(self.get_pane(0))
            s.addWidget(self.get_pane(1))
            s.addWidget(self.get_pane(2))
            self.get_pane(0).show()
            self.get_pane(1).show()
            self.get_pane(2).show()
            self.main_layout.addWidget(s)
        elif mode == "3-2L1R": 
            left = QSplitter(Qt.Orientation.Vertical)
            left.addWidget(self.get_pane(0))
            left.addWidget(self.get_pane(1))
            main = QSplitter(Qt.Orientation.Horizontal)
            main.addWidget(left)
            main.addWidget(self.get_pane(2))
            self.get_pane(0).show()
            self.get_pane(1).show()
            self.get_pane(2).show()
            self.main_layout.addWidget(main)
        elif mode == "3-1L2R": 
            right = QSplitter(Qt.Orientation.Vertical)
            right.addWidget(self.get_pane(1))
            right.addWidget(self.get_pane(2))
            main = QSplitter(Qt.Orientation.Horizontal)
            main.addWidget(self.get_pane(0))
            main.addWidget(right)
            self.get_pane(0).show()
            self.get_pane(1).show()
            self.get_pane(2).show()
            self.main_layout.addWidget(main)
        elif mode == "4-vert":
            s = QSplitter(Qt.Orientation.Horizontal)
            s.addWidget(self.get_pane(0))
            s.addWidget(self.get_pane(1))
            s.addWidget(self.get_pane(2))
            s.addWidget(self.get_pane(3))
            self.get_pane(0).show()
            self.get_pane(1).show()
            self.get_pane(2).show()
            self.get_pane(3).show()
            self.main_layout.addWidget(s)
        elif mode == "4-grid":
            left = QSplitter(Qt.Orientation.Vertical)
            left.addWidget(self.get_pane(0))
            left.addWidget(self.get_pane(1))
            right = QSplitter(Qt.Orientation.Vertical)
            right.addWidget(self.get_pane(2))
            right.addWidget(self.get_pane(3))
            main = QSplitter(Qt.Orientation.Horizontal)
            main.addWidget(left)
            main.addWidget(right)
            self.get_pane(0).show()
            self.get_pane(1).show()
            self.get_pane(2).show()
            self.get_pane(3).show()
            self.main_layout.addWidget(main)
            
        if not self.active_pane:
            self.set_active_pane(self.panes[0])

    def save_settings(self):
        try:
            geo_data = self.saveGeometry()
            geo_hex = bytes(geo_data).hex()
            
            bm_width = 150
            if self.bookmark_dock and self.bookmark_dock.widget():
                bm_width = self.bookmark_dock.widget().width()
            
            pane_paths = [p.current_path for p in self.panes]
            
            # [FIX] Collect view modes from all panes
            pane_views = [p.current_view_mode for p in self.panes]
            
            # [FIX] Collect profiles from all panes
            pane_profiles = [p.current_profile for p in self.panes]
            
            col_widths = []
            if self.active_pane and self.active_pane.tree_view.isVisible():
                header = self.active_pane.tree_view.header()
                for i in range(header.count()):
                    col_widths.append(header.sectionSize(i))
            elif self.panes:
                header = self.panes[0].tree_view.header()
                for i in range(header.count()):
                    col_widths.append(header.sectionSize(i))

            # Helper: Serialize Tree Structure (reused for bookmarks & favorites)
            def serialize_tree(item):
                node = {"name": item.text(0)}
                path = item.data(0, Qt.ItemDataRole.UserRole)
                
                if path:
                    node["type"] = "file"
                    node["path"] = path
                else:
                    node["type"] = "folder"
                    node["children"] = []
                    for i in range(item.childCount()):
                        node["children"].append(serialize_tree(item.child(i)))
                return node

            # Serialize Favorites
            fav_data = []
            root = self.fav_tree.invisibleRootItem()
            for i in range(root.childCount()):
                fav_data.append(serialize_tree(root.child(i)))
            
            # Serialize Bookmarks (New Structure)
            bm_data = []
            bm_root = self.bookmark_tree.invisibleRootItem()
            for i in range(bm_root.childCount()):
                bm_data.append(serialize_tree(bm_root.child(i)))

            data = {
                "geometry": geo_hex,
                "theme": self.settings.get("theme", "light"),
                "font_size": self.settings.get("font_size", 10),
                "layout_mode": self.settings.get("layout_mode", "2-vert"),
                "pane_paths": pane_paths,
                "pane_views": pane_views,  # [FIX] Save the list of view modes
                "pane_profiles": pane_profiles, # [FIX] Save the list of pane profiles
                "column_widths": col_widths,
                "bookmarks": bm_data, # New hierarchical format
                "favorites": fav_data,
                "fields_display": self.settings.get("fields_display", []),
                "fields_props": self.settings.get("fields_props", []),
                "bookmark_width": bm_width,
                "sidebar_split_sizes": self.sidebar_splitter.sizes(),
                # --- NEW: Save pane sorts ---
                "pane_sorts": self.get_all_pane_sorts(),
                # --- NEW: Settings from Dialog ---
                "max_dump_size": self.settings.get("max_dump_size", 73400320),
                "ignore_recycle_bin": self.settings.get("ignore_recycle_bin", True),
                "show_hidden": self.settings.get("show_hidden", False),
                "custom_editor_path": self.settings.get("custom_editor_path", ""),
                "last_scan_time": self.settings.get("last_scan_time", "Never"), # NEW
                "profiles": self.settings.get("profiles", {}), # [NEW] Save Profiles
                "use_internal_md": self.settings.get("use_internal_md", False),
                "use_internal_txt": self.settings.get("use_internal_txt", True),
                "include_html": self.settings.get("include_html", False)
            }
            
            self.settings_mgr.save(data)
            self.settings = data
            
        except Exception as e:
            print(f"Error saving settings: {e}")
            QMessageBox.critical(self, "Error Saving Settings", f"Could not save preferences:\n{e}")

    def get_all_pane_sorts(self):
        sorts = []
        for p in self.panes:
            if p.tree_view.isVisible():
                header = p.tree_view.header()
                sorts.append((header.sortIndicatorSection(), header.sortIndicatorOrder().value))
            else:
                # Default if view not active or something else
                sorts.append((0, 0)) 
        return sorts

    def start_drive_monitoring(self):
        # Use polling instead of nativeEvent for stability
        self.drive_timer = QTimer(self)
        self.drive_timer.timeout.connect(self.check_drives)
        self.drive_timer.start(2000) # Check every 2 seconds
        self.known_drives = set(v.rootPath() for v in QStorageInfo.mountedVolumes() if v.isValid())

    def check_drives(self):
        current_drives = set(v.rootPath() for v in QStorageInfo.mountedVolumes() if v.isValid())
        if current_drives != self.known_drives:
            self.known_drives = current_drives
            self.refresh_all_drives()

    def refresh_all_drives(self):
        # Refresh all panes
        for p in self.panes: 
            if p: p.refresh_drives()

    def closeEvent(self, event):
        # Guarantee a hard exit after 1.0 seconds if graceful sequence blocks
        import threading, os
        t = threading.Timer(1.0, lambda os_module=os: os_module._exit(0))
        t.daemon = True
        t.start()

        # Stop background threads
        try:
            if hasattr(self, 'fs_watcher') and self.fs_watcher:
                # Wrap in thread to prevent blocking main thread if it hangs
                threading.Thread(target=self.fs_watcher.stop, daemon=True).start()
        except Exception:
            pass
            
        for worker_name in ['indexer', 'worker_search', 'worker', 'export_worker', 'download_worker', 'check_thread']:
            if hasattr(self, worker_name):
                w = getattr(self, worker_name)
                try:
                    if w and w.isRunning():
                        if hasattr(w, 'stop'):
                            w.stop()
                        w.wait(200) # Reduced from 500ms to allow quicker exit
                except Exception:
                    pass
                    
        try:
            self.save_settings()
        except Exception:
            pass
            
        try:
            self.empty_trash()
        except Exception:
            pass
        
        try:
            from PyQt6.QtCore import QThreadPool
            QThreadPool.globalInstance().clear()
        except:
            pass
            
        super().closeEvent(event)
        event.accept()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # --- Ensure QFileIconProvider is imported to prevent NameError ---
    from PyQt6.QtWidgets import QFileIconProvider 
    # from PyQt6.QtCore import QStorageInfo # Already imported at top

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    
    # [NEW] Single Instance Lock
    lock_file = QLockFile(os.path.join(QDir.tempPath(), 'GPFFileManager.lock'))
    if not lock_file.tryLock(100):
        # Already running
        sys.exit(0)
    
    try:
        window = MainWindow()
        log_debug("MainWindow initialized. Showing window...")
        window.show()
        log_debug("window.show() called.")
    except Exception as e:
        log_debug(f"CRITICAL MAIN LOOP ERROR: {e}")
        traceback.print_exc()
    
    sys.exit(app.exec())
