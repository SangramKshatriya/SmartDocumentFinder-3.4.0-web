from pathlib import Path

from PySide6.QtCore import QObject, Signal

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # Optional until dependency installation.
    FileSystemEventHandler = object
    Observer = None

from config import SUPPORTED_EXTENSIONS


class _Handler(FileSystemEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def on_created(self, event):
        self.owner._emit(event.src_path)

    def on_modified(self, event):
        self.owner._emit(event.src_path)

    def on_deleted(self, event):
        self.owner._emit_deleted(event.src_path)

    def on_moved(self, event):
        self.owner._emit_deleted(event.src_path)
        self.owner._emit(event.dest_path)


class FolderWatcher(QObject):
    file_changed = Signal(str)
    file_deleted = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.observer = None
        self.folder = None

    @property
    def available(self) -> bool:
        return Observer is not None

    def start(self, folder: str) -> bool:
        self.stop()
        if Observer is None:
            self.error.emit("File watching requires the watchdog package.")
            return False
        try:
            self.folder = str(Path(folder).resolve())
            self.observer = Observer()
            self.observer.schedule(_Handler(self), self.folder, recursive=True)
            self.observer.start()
            return True
        except Exception as error:
            self.observer = None
            self.error.emit(f"Could not start folder watcher: {error}")
            return False

    def stop(self):
        if self.observer is not None:
            try:
                self.observer.stop()
                self.observer.join(timeout=2)
            except Exception:
                pass
        self.observer = None
        self.folder = None

    def _emit(self, path: str):
        path_obj = Path(path)
        if path_obj.is_file() and path_obj.suffix.lower() in SUPPORTED_EXTENSIONS:
            self.file_changed.emit(str(path_obj.resolve()))

    def _emit_deleted(self, path: str):
        path_obj = Path(path)
        if path_obj.suffix.lower() in SUPPORTED_EXTENSIONS:
            self.file_deleted.emit(str(path_obj.resolve()))
