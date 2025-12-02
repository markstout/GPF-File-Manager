# Get Productive Fast:  File Manager
# Version 0.5.2 12/2/2025
# Copyright 2025 Mark A. Stout
# Licensed under MIT License
# For more information see : https://sites.google.com/view/getproductivefast/file-manager


import sys
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
from datetime import datetime
from pathlib import Path

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
                             QTreeWidget, QTreeWidgetItem, QFileIconProvider, QTextEdit, 
                             QFileDialog, QSpinBox, QStackedWidget, QStatusBar)

from PyQt6.QtCore import (Qt, QSize, QDir, QUrl, QMimeData, QSettings, 
                          QStandardPaths, QPoint, QFileInfo, qInstallMessageHandler,
                          QThread, pyqtSignal, QObject, QRunnable, QThreadPool, 
                          QPersistentModelIndex, QModelIndex, QTimer)

from PyQt6.QtGui import (QAction, QIcon, QDesktopServices, QDrag, QActionGroup, 
                         QColor, QPalette, QPixmap, QFileSystemModel, QImageReader, 
                         QKeySequence, QCursor, QPainter, QImage, QStandardItemModel, 
                         QStandardItem, QTextDocument)

# --- PDF Support ---
try:
    from PyQt6.QtPrintSupport import QPrinter
    HAS_PRINTER = True
except ImportError:
    HAS_PRINTER = False

# Variables near start
APP_NAME = "Get Productive Fast:  File Manager"
APP_COPYRIGHT = "Copyright 2025 Mark A. Stout"
APP_VERSION = "Version 0.5.1 11/28/2025"
APP_SHORT_NAME = "GPFFileManager"

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
                    audio = MP3(path)
                    data["Duration"] = time.strftime('%M:%S', time.gmtime(audio.info.length))
                    data["Bit Rate"] = f"{int(audio.info.bitrate / 1000)} kbps"
                    
            except Exception:
                pass

        MetadataLoader._cache[path] = data
        return data

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
        if index.column() < 4:
            return super().data(index, role)
        
        if role == Qt.ItemDataRole.DisplayRole:
            col_name = self.custom_columns[index.column() - 4]
            file_path = self.filePath(index.siblingAtColumn(0))
            
            # Handle Standard Extended Fields (Dates)
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

            # Handle Metadata (Images/Audio)
            meta = MetadataLoader.get_metadata(file_path)
            return meta.get(col_name, "")
            
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
                except Exception as e:
                    print(f"Could not watch {path}: {e}")
            self.observer.start()

        def stop(self):
            self.observer.stop()
            self.observer.join()

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
        
class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Check for Updates")
        self.setMinimumWidth(400)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            
        layout = QVBoxLayout(self)

        # Version Info
        lbl_ver = QLabel(f"The current version is: {APP_VERSION}")
        lbl_ver.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl_ver)
        
        # Explanation
        msg = ("There is no automatic update capability. "
               "Check this version and date against the web page "
               "to see if you need to download a new version.")
        lbl_msg = QLabel(msg)
        lbl_msg.setWordWrap(True)
        layout.addWidget(lbl_msg)
        
        layout.addSpacing(10)
        
        # Link
        link_url = "https://sites.google.com/view/getproductivefast/file-manager/download-and-updates"
        link_lbl = QLabel(f"<a href='{link_url}'>Check for Updates</a>")
        link_lbl.setOpenExternalLinks(True)
        layout.addWidget(link_lbl)
        
        layout.addStretch()
        
        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)

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
            "launch_at_startup": self.startup_check.isChecked(),
            "max_dump_size": self.dump_size.value() * 1024 * 1024,
            "ignore_recycle_bin": self.recycle_check.isChecked(),
            "custom_editor_path": self.editor_path.text()
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
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
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
                
        layout.addLayout(form)
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

    def on_item_click(self, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and self.main.active_pane:
            self.main.active_pane.navigate(path)

    # [FIX] Missing method added here
    def open_context_menu(self, point):
        item = self.itemAt(point)
        menu = QMenu()
        act_add = menu.addAction("Add Current Folder")
        act_del = menu.addAction("Delete") if item else None
        
        res = menu.exec(self.mapToGlobal(point))
        
        if res == act_add and self.main.active_pane:
             self.main.add_bookmark_item(os.path.basename(self.main.active_pane.current_path), self.main.active_pane.current_path)
        elif res == act_del and item:
             (item.parent() or self.invisibleRootItem()).removeChild(item)

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
        act_add_folder = menu.addAction("Add Folder")
        act_rename = menu.addAction("Rename") if item else None
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
        elif res == act_del and item:
             for i in self.selectedItems():
                 (i.parent() or self.invisibleRootItem()).removeChild(i)

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
        self.current_profile = "Default" # Default profile
        
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
        self.btn_ps.setFixedSize(24, 24)
        self.btn_ps.clicked.connect(self.open_powershell)
        self.btn_cmd = QPushButton("CMD")
        self.btn_cmd.setToolTip("Open Command Window")
        self.btn_cmd.setFixedSize(45, 24) 
        self.btn_cmd.clicked.connect(self.open_cmd)
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
            item_mod = QStandardItem(datetime.fromtimestamp(mod_ts).strftime('%Y-%m-%d %H:%M'))
            self.search_model.appendRow([item_name, item_path, item_size, item_mod])
        self.switch_to_search_mode()

    def switch_to_search_mode(self):
        self.tree_view.setModel(self.search_model)
        if self.list_view.isVisible():
            self.stack.setCurrentIndex(0) 

    def switch_to_normal_mode(self):
        self.tree_view.setModel(self.model)
        self.list_view.setModel(self.model) 
        self.tree_view.setRootIndex(self.model.index(self.current_path))
        self.list_view.setRootIndex(self.model.index(self.current_path))
        
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
        if self.tree_view.model() == self.search_model:
            path = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        else:
            path = self.model.filePath(index)
        self.window().update_properties(path)

    def set_active(self):
        window = self.window()
        if isinstance(window, MainWindow): window.set_active_pane(self)

    def refresh_drives(self):
        self.drive_combo.clear()
        for drive in QDir.drives(): self.drive_combo.addItem(drive.absoluteFilePath())

    def change_drive(self): self.navigate(self.drive_combo.currentText())

    def on_path_entered(self):
        self.navigate(self.path_edit.text())
        if self.path_edit.isVisible(): self.toggle_path_edit()

    def navigate(self, path):
        if not os.path.exists(path): return
        self.current_path = path
        self.breadcrumbs.set_path(path)
        self.switch_to_normal_mode()
        
        self.model.setRootPath(path)
        
        idx = self.model.index(path)
        if idx.isValid():
            self.tree_view.setRootIndex(idx)
            self.list_view.setRootIndex(idx)
        
        folder_name = os.path.basename(path)
        if not folder_name and ':' in path: folder_name = path 
        self.title_label.setText(f"{self.pane_name} - {folder_name}")

    def go_up(self):
        parent = os.path.dirname(self.current_path)
        if parent and parent != self.current_path: self.navigate(parent)
        elif len(self.current_path) == 3 and self.current_path.endswith(":/"): pass 

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
        else:
            path = self.model.filePath(index)
    
        if os.path.isdir(path):
            self.navigate(path)
        else:
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.exe', '.bat', '.cmd', '.ps1', '.com']:
                try:
                    work_dir = os.path.dirname(path)
                    subprocess.Popen([path], cwd=work_dir, shell=(ext == '.bat' or ext == '.cmd'))
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not launch executable:\n{e}")
            else:
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

    def open_powershell(self): subprocess.Popen(["powershell.exe", "-NoExit", "-Command", f"cd '{self.current_path}'"])
    def open_cmd(self): subprocess.Popen(["cmd.exe", "/K", f"cd /d {self.current_path}"])
    
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
        action_cancel = menu.addAction("Cancel")
        res = menu.exec(QCursor.pos())
        
        if res == action_cancel or not res: return
            
        op_type = "move" if res == action_move else "copy"
        src_paths = [u.toLocalFile() for u in urls if os.path.exists(u.toLocalFile())]
        
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
            
        menu = QMenu()
        
        act_cut = menu.addAction("Cut")
        act_copy = menu.addAction("Copy")
        act_paste = menu.addAction("Paste")
        act_del = menu.addAction("Delete")
        menu.addSeparator()
        act_rename = menu.addAction("Rename")
        act_copy_path = menu.addAction("Copy Path")
        menu.addSeparator()
        act_bookmark = menu.addAction("Add to Bookmarks") 
        act_fav = menu.addAction("Add to Favorite Apps")
        menu.addSeparator()
        act_compress = menu.addAction("Compress to Zip")
        
        act_unzip_here = None
        act_unzip_folder = None
        if path.lower().endswith('.zip'):
            act_unzip_here = menu.addAction("Extract Here")
            act_unzip_folder = menu.addAction(f"Extract to {os.path.splitext(os.path.basename(path))[0]}/")
        
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
        act_sendto_here = menu.addAction("Create SendTo Destination to here")
        menu.addSeparator()
        
        act_custom_edit = None
        custom_editor = self.window().settings.get("custom_editor_path")
        if custom_editor and os.path.exists(custom_editor):
            app_name = os.path.splitext(os.path.basename(custom_editor))[0].title()
            act_custom_edit = menu.addAction(f"Edit in {app_name}")
        
        act_notepad = menu.addAction("Edit in Notepad")
        act_notepad_plus = menu.addAction("Edit in Notepad++")
        menu.addSeparator()
        act_props = menu.addAction("Properties")

        action = menu.exec(view.viewport().mapToGlobal(point))
        if not action: return
        
        if action == act_rename: self.tree_view.edit(index)
        elif action == act_copy_path: QApplication.clipboard().setText(path)
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
        elif action == act_unzip_here: self.window().run_threaded_io("unzip", [path], os.path.dirname(path))
        elif action == act_unzip_folder:
             folder_name = os.path.splitext(os.path.basename(path))[0]
             target_path = os.path.join(os.path.dirname(path), folder_name)
             self.window().run_threaded_io("unzip", [path], target_path)
        elif action == act_send_desktop: self.window().on_send_to_desktop(path)
        elif action == act_send_docs: self.window().on_send_to_documents(path)
        elif action == act_sendto_here: self.window().on_create_sendto_destination(path)
        elif act_custom_edit and action == act_custom_edit: subprocess.Popen([custom_editor, path])
        elif action == act_notepad: subprocess.Popen(['notepad.exe', path])
        elif action == act_notepad_plus:
             npp_paths = [
                 r"C:\Program Files\Notepad++\notepad++.exe",
                 r"C:\Program Files (x86)\Notepad++\notepad++.exe"
             ]
             found = False
             for npp in npp_paths:
                 if os.path.exists(npp):
                     subprocess.Popen([npp, path])
                     found = True
                     break
             if not found:
                 QMessageBox.warning(self, "Error", "Notepad++ executable not found in standard locations.")

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
        
        self.resize(800, 600)
        
        self.set_layout_mode(self.settings.get("layout_mode", "2-vert"))

        if self.bookmark_dock:
             bm_width = self.settings.get("bookmark_width", 150)
             self.resizeDocks([self.bookmark_dock], [bm_width], Qt.Orientation.Horizontal)

        # --- Start Indexer and Watcher ---
        self.db_mgr = DatabaseManager(self.settings_mgr.db_path)
        self.report_mgr = ReportManager(self.settings_mgr.db_path)
        self.indexer = IndexerWorker(self.settings_mgr.db_path, self.settings.get("ignore_recycle_bin", True))
        self.indexer.finished_signal.connect(self.on_scan_finished) 
        # --- FIX: Connect progress ---
        self.indexer.progress_signal.connect(self.on_scan_progress)
        
        self.indexer.start()
        
        if HAS_WATCHDOG:
            self.watcher = QFileSystemModel(self) # Dummy
            self.fs_watcher = FileSystemWatcher(self.settings_mgr.db_path)
            self.fs_watcher.start()
    def add_bookmark_item(self, name, path, parent=None):
        if not path or not os.path.exists(path): return
        # --- FIX: Use QTreeWidgetItem instead of QListWidgetItem ---
        root = parent if parent else self.bookmark_tree.invisibleRootItem()
        item = QTreeWidgetItem(root)
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        return item

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

    def add_favorite_group(self, name, parent_item=None):
        if not self.fav_tree: return
        root = parent_item if parent_item else self.fav_tree.invisibleRootItem()
        item = QTreeWidgetItem(root)
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole, None)
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
        self.lbl_rescan = QLabel("<a href='#'>Rescan</a>")
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
            
        # Load Favorites
        saved_favs = self.settings.get("favorites", [])
        self.load_favorites_recursive(saved_favs, self.fav_tree.invisibleRootItem())
        
        dock.setWidget(self.sidebar_splitter)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def create_default_bookmarks(self):
        defaults = [
            ("Desktop", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)),
            ("Documents", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)),
            ("Downloads", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)),
            ("Pictures", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)),
            ("Videos", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)),
            ("Music", QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation))
        ]
        for name, path in defaults: self.add_bookmark_item(name, path)
        home = os.path.expanduser("~")
        for cloud in ["OneDrive", "Google Drive", "Dropbox"]:
            p = os.path.join(home, cloud)
            if os.path.exists(p): self.add_bookmark_item(cloud, p)
        
        sys_item = QTreeWidgetItem(self.bookmark_tree)
        sys_item.setText(0, "System")
        sys_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        
        # [FIX] Collapse System folder by default
        sys_item.setExpanded(False)
        
        startup = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        if os.path.exists(startup): self.add_bookmark_item("Startup", startup, sys_item)
        sendto = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'SendTo')
        if os.path.exists(sendto): self.add_bookmark_item("SendTo", sendto, sys_item)
        pf = os.environ.get("ProgramFiles")
        if pf and os.path.exists(pf): self.add_bookmark_item("Program Files", pf, sys_item)
        pfx86 = os.environ.get("ProgramFiles(x86)")
        if pfx86 and os.path.exists(pfx86): self.add_bookmark_item("Program Files (x86)", pfx86, sys_item)
        appdata = os.path.join(home, "AppData")
        if os.path.exists(appdata): self.add_bookmark_item("AppData", appdata, sys_item)

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
        
        act_new_folder = file_menu.addAction("New Folder")
        act_new_folder.setShortcut("Ctrl+Shift+N")
        act_new_folder.triggered.connect(self.new_folder)
        
        act_new_file = file_menu.addAction("New File")
        act_new_file.setShortcut("Ctrl+N")
        act_new_file.triggered.connect(self.new_file)
        
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
        # Common styling
        base_style = """
            QLineEdit, QComboBox, QSpinBox { 
                padding: 4px; 
                border: 1px solid #ccc; 
                border-radius: 4px; 
            }
            QMenu::separator { height: 1px; background: #ccc; margin: 5px; }
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

    def open_fields_dialog(self):
        FieldsDialog(self).exec()
        
    def open_settings_dialog(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.settings.update(data)
            self.set_theme(data["theme"])
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
        new_path = os.path.join(path, base)
        counter = 1
        while os.path.exists(new_path):
            new_path = os.path.join(path, f"{base} ({counter})")
            counter += 1
        try:
            os.mkdir(new_path)
            self.active_pane.navigate(path)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def new_file(self):
        if not self.active_pane: return
        path = self.active_pane.current_path
        base = "New Text Document.txt"
        new_path = os.path.join(path, base)
        counter = 1
        while os.path.exists(new_path):
            new_path = os.path.join(path, f"New Text Document ({counter}).txt")
            counter += 1
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
                subprocess.Popen([real_target, src_path])
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
                "custom_editor_path": self.settings.get("custom_editor_path", ""),
                "last_scan_time": self.settings.get("last_scan_time", "Never"), # NEW
                "profiles": self.settings.get("profiles", {}) # [NEW] Save Profiles
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

    def closeEvent(self, event):
        # Stop watcher thread if it exists
        if hasattr(self, 'watcher'):
            self.fs_watcher.stop()
            
        self.save_settings()
        self.empty_trash()
        super().closeEvent(event)

if __name__ == "__main__":
    # --- Ensure QFileIconProvider is imported to prevent NameError ---
    from PyQt6.QtWidgets import QFileIconProvider 
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    # --- Ensure QFileIconProvider is imported to prevent NameError ---
    from PyQt6.QtWidgets import QFileIconProvider 
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    # --- Ensure QFileIconProvider is imported to prevent NameError ---
    from PyQt6.QtWidgets import QFileIconProvider 
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
    
