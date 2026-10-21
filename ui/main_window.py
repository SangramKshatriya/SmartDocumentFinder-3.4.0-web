from datetime import datetime, timezone
from pathlib import Path
import os
from time import perf_counter

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from database import (
    get_document_count, get_recent_documents, get_setting, initialize_database,
    log_audit_event, mark_opened, record_document_access, record_search_history,
    set_setting,
)
from file_watcher import FolderWatcher
from indexer import index_folder
from search_engine import search_documents_multilingual
from query_processor import extract_constraints
from ui.document_viewer import DocumentViewer
from ui.history_dialog import HistoryDialog
from ui.search_widget import SearchWidget
from ui.voice_assistant import VoiceAssistant
from language.manager import LanguageManager
from services.provider_factory import build_provider
from services.digilocker_provider import DigiLockerClient
from config import DATA_DIR


class IndexWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, folder: str, force: bool):
        super().__init__()
        self.folder = folder
        self.force = force
        self.stop_requested = False

    def run(self):
        try:
            stats = index_folder(
                self.folder,
                force=self.force,
                progress_callback=lambda current, total, name: self.progress.emit(current, total, name),
                should_stop=lambda: self.stop_requested,
            )
            self.finished.emit(stats)
        except Exception as error:
            self.failed.emit(str(error))

    def stop(self):
        self.stop_requested = True


class SearchWorker(QObject):
    finished = Signal(object, object, object)
    failed = Signal(str)

    def __init__(self, query: str, preferred_language: str, language_manager: LanguageManager, digilocker=None, input_mode: str = "text"):
        super().__init__()
        self.query = query
        self.preferred_language = preferred_language
        self.language_manager = language_manager
        self.digilocker = digilocker
        self.input_mode = input_mode or "text"

    def run(self):
        started_at = datetime.now(timezone.utc)
        started_perf = perf_counter()
        try:
            prepared = self.language_manager.prepare_query(
                self.query,
                preferred_language=self.preferred_language or None,
            )
            results = search_documents_multilingual(
                prepared.original,
                canonical_query=prepared.canonical_english,
                transliterated_query=prepared.transliterated,
                document_type=prepared.document_type,
                constraints=extract_constraints(prepared.canonical_english or prepared.original),
                limit=5,
            )

            # Optional DigiLocker source: only the matching issued document is
            # downloaded, never the whole locker.
            if self.digilocker and (prepared.document_type or prepared.canonical_english):
                try:
                    remote = self.digilocker.search_issued_documents(
                        prepared.document_type, prepared.document_name or prepared.canonical_english, limit=1
                    )
                    if remote:
                        item = remote[0]
                        cache_dir = DATA_DIR / "digilocker"
                        downloaded = self.digilocker.fetch_file(
                            item["uri"], str(cache_dir),
                            suggested_name=prepared.document_name.replace(" ", "_") or item.get("name", "document"),
                        )
                        remote_result = {
                            "id": "digilocker:" + str(item.get("uri")),
                            "name": item.get("name") or prepared.document_name,
                            "path": downloaded,
                            "extension": Path(downloaded).suffix,
                            "size": Path(downloaded).stat().st_size,
                            "modified_time": 0,
                            "content": "",
                            "document_type": prepared.document_type,
                            "language": "en-IN",
                            "score": int(item.get("score", 0)) + 1000,
                            "extraction_status": "remote",
                            "extraction_error": "",
                            "source": "digilocker",
                            "issuer": item.get("issuer", ""),
                        }
                        results = [remote_result] + results
                except Exception as error:
                    # Remote fetch must never make local search unusable; surface
                    # the reason so a missing token/authorization is actionable.
                    from dataclasses import replace
                    message = f"DigiLocker: {error}"
                    combined = f"{prepared.provider_error}; {message}" if prepared.provider_error else message
                    prepared = replace(prepared, provider_error=combined)
            duration_ms = int((perf_counter() - started_perf) * 1000)
            telemetry = {
                "searched_at": started_at.replace(tzinfo=None).isoformat(timespec="seconds") + "Z",
                "duration_ms": duration_ms,
                "input_mode": self.input_mode,
            }
            self.finished.emit(results[:5], prepared, telemetry)
        except Exception as error:
            duration_ms = int((perf_counter() - started_perf) * 1000)
            self.failed.emit(f"{duration_ms}|{error}")


class ResultCard(QFrame):
    clicked = Signal(object)

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self.setObjectName("resultCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)

        extension = Path(result["path"]).suffix.lower()
        icon_text = "PDF" if extension == ".pdf" else "IMG" if extension in {".jpg", ".jpeg", ".png"} else "DOC"
        icon = QLabel(icon_text)
        icon.setObjectName("resultIcon")
        icon.setFixedWidth(38)
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        body = QVBoxLayout()
        body.setSpacing(3)
        name = QLabel(result["name"])
        name.setObjectName("resultName")
        name.setWordWrap(False)
        path_label = QLabel(self._compact_parent(result["path"]))
        path_label.setObjectName("resultPath")
        path_label.setWordWrap(False)
        modified = "Unknown"
        try:
            modified = datetime.fromtimestamp(result["modified_time"]).strftime("%d %b %Y")
        except Exception:
            pass
        meta = QLabel(f"{modified}  •  {result.get('document_type') or 'Document'}  •  score {result['score']}")
        meta.setObjectName("resultMeta")
        for label in (name, path_label, meta):
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            body.addWidget(label)
        layout.addLayout(body, 1)

    @staticmethod
    def _compact_parent(path: str) -> str:
        p = Path(path)
        parent = p.parent.name or str(p.parent)
        return f"…/{parent}"

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.result)
        super().mouseReleaseEvent(event)


class MainWindow(QWidget):
    def __init__(self, folder: str, force_index: bool = False, parent=None, *, username: str = "local_user", display_name: str = "Local User", session_id: int | None = None):
        super().__init__(parent)
        initialize_database()
        self.setWindowTitle("Smart Document Finder")
        self.resize(1440, 880)
        self.setMinimumSize(980, 650)
        self.username = str(username or "local_user").strip()
        self.display_name = display_name or "Local User"
        self.session_id = int(session_id) if session_id is not None else None
        self.active_search_history_id = None
        self.pending_open_result = None
        self.current_input_mode = "text"
        self.current_results = []
        self.selected_card = None
        self.index_thread = None
        self.index_worker = None
        self.search_thread = None
        self.search_worker = None
        self.language_provider_error = ""
        try:
            provider = build_provider()
        except Exception as error:
            provider = None
            self.language_provider_error = f"Language provider setup failed: {error}"

        # Missing provider credentials used to silently downgrade the app to
        # local-only mode. Keep the local fallback, but make the configuration
        # problem visible so multilingual failures are actionable.
        configured_provider = os.getenv("LANGUAGE_PROVIDER", "sarvam").strip().lower()
        if not provider and not self.language_provider_error and configured_provider == "sarvam" and not os.getenv("SARVAM_API_KEY", "").strip():
            self.language_provider_error = "Sarvam API key is not configured; multilingual translation uses local fallback."
        elif not provider and not self.language_provider_error and configured_provider == "bhashini" and not os.getenv("BHASHINI_API_KEY", "").strip():
            self.language_provider_error = "BHASHINI API key is not configured; multilingual translation uses local fallback."

        self.language_manager = LanguageManager(provider)
        self.digilocker = DigiLockerClient.from_env()
        self.watcher = FolderWatcher(self)
        self.pending_refresh_timer = QTimer(self)
        self.pending_refresh_timer.setSingleShot(True)
        self.pending_refresh_timer.setInterval(900)
        self.pending_refresh_timer.timeout.connect(self._refresh_current_index)
        self.voice_assistant_engine = VoiceAssistant(self)
        self._connect_background_services()
        self.setup_ui()
        self._set_folder(folder, start_watcher=False)
        self.start_indexing(folder, force=force_index)

    def _connect_background_services(self):
        self.watcher.file_changed.connect(self._on_file_changed)
        self.watcher.file_deleted.connect(self._on_file_changed)
        self.watcher.error.connect(self._set_status_error)
        self.voice_assistant_engine.text_received.connect(self.handle_voice_text)
        self.voice_assistant_engine.status_changed.connect(self.handle_voice_status)
        self.voice_assistant_engine.error_occurred.connect(self.handle_voice_error)
        self.voice_assistant_engine.language_detected.connect(self.handle_voice_language)

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)
        self.search_widget = SearchWidget()
        root.addWidget(self.search_widget)

        content = QHBoxLayout()
        content.setSpacing(12)
        self.results_panel = QFrame()
        self.results_panel.setObjectName("resultsPanel")
        self.results_panel.setMinimumWidth(330)
        self.results_panel.setMaximumWidth(470)
        results_layout = QVBoxLayout(self.results_panel)
        results_layout.setContentsMargins(6, 8, 6, 8)
        results_header = QHBoxLayout()
        self.results_title = QLabel("Search Results")
        self.results_title.setObjectName("resultsTitle")
        self.results_count = QLabel("0")
        self.results_count.setObjectName("resultsCount")
        results_header.addWidget(self.results_title)
        results_header.addWidget(self.results_count)
        results_header.addStretch()
        results_layout.addLayout(results_header)
        self.results_scroll = QScrollArea()
        self.results_scroll.setObjectName("resultsScroll")
        self.results_scroll.setWidgetResizable(True)
        self.results_container = QWidget()
        self.results_container_layout = QVBoxLayout(self.results_container)
        self.results_container_layout.setContentsMargins(3, 3, 3, 3)
        self.results_container_layout.setSpacing(6)
        self.results_container_layout.addStretch()
        self.results_scroll.setWidget(self.results_container)
        results_layout.addWidget(self.results_scroll, 1)
        content.addWidget(self.results_panel)
        self.results_panel.hide()

        viewer_panel = QFrame()
        viewer_panel.setObjectName("viewerPanel")
        viewer_layout = QVBoxLayout(viewer_panel)
        viewer_layout.setContentsMargins(2, 2, 2, 2)
        self.document_viewer = DocumentViewer()
        viewer_layout.addWidget(self.document_viewer)
        content.addWidget(viewer_panel, 1)
        root.addLayout(content, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        self.progress = QProgressBar()
        self.progress.setObjectName("progressBar")
        self.progress.setFixedWidth(220)
        self.progress.hide()
        self.indexed_label = QLabel("0 documents indexed")
        self.indexed_label.setObjectName("folderLabel")
        footer.addWidget(self.status_label)
        footer.addWidget(self.progress)
        footer.addStretch()
        footer.addWidget(self.indexed_label)
        root.addLayout(footer)

        self.search_widget.search_requested.connect(self.perform_search)
        self.search_widget.language_changed.connect(self._language_changed)
        self.search_widget.voice_requested.connect(self.voice_assistant)
        self.search_widget.recent_requested.connect(self.show_recent_documents)
        self.search_widget.history_requested.connect(self.show_history)
        self.document_viewer.document_opened.connect(self._document_was_opened)
        self.document_viewer.show_empty_state(
            "Search for a document",
            'Try “show my PAN card” or “show my 12th marksheet”.',
        )

    def _set_folder(self, folder: str, start_watcher: bool = True):
        folder = str(Path(folder).resolve())
        set_setting("document_folder", folder)
        self.indexed_label.setText("Indexing…")
        if start_watcher:
            self.watcher.start(folder)

    def start_indexing(self, folder: str, force: bool = False):
        if self.index_thread is not None and self.index_thread.isRunning():
            return
        self.search_widget.set_busy(True)
        self.progress.setValue(0)
        self.progress.show()
        self.status_label.setText("Indexing documents…")
        self.index_thread = QThread(self)
        self.index_worker = IndexWorker(folder, force)
        self.index_worker.moveToThread(self.index_thread)
        self.index_thread.started.connect(self.index_worker.run)
        self.index_worker.progress.connect(self._index_progress)
        self.index_worker.finished.connect(self._index_finished)
        self.index_worker.failed.connect(self._index_failed)
        self.index_worker.finished.connect(self.index_thread.quit)
        self.index_worker.failed.connect(self.index_thread.quit)
        self.index_thread.finished.connect(self._index_cleanup)
        self.index_thread.start()

    def _index_progress(self, current: int, total: int, name: str):
        if total:
            self.progress.setValue(int(current * 100 / total))
        self.status_label.setText(f"Indexing {current}/{total}: {name}")

    def _index_finished(self, stats: dict):
        folder = get_setting("document_folder", "")
        self.progress.hide()
        self.search_widget.set_busy(False)
        self.indexed_label.setText(f"{get_document_count()} documents indexed")
        if folder:
            self.watcher.start(folder)
        log_audit_event(
            "INDEX_COMPLETED", username=self.username, display_name=self.display_name, session_id=self.session_id,
            details={"folder": folder, "total": stats.get("total", 0), "changed": stats.get("changed", 0), "skipped": stats.get("skipped", 0)},
        )
        self.status_label.setText(
            f"Index ready • {stats['total']} files • {stats['changed']} updated • {stats['skipped']} unchanged"
        )

    def _index_failed(self, message: str):
        self.progress.hide()
        self.search_widget.set_busy(False)
        log_audit_event(
            "INDEX_FAILED", username=self.username, display_name=self.display_name, session_id=self.session_id,
            details={"error": message},
        )
        self.status_label.setText("Indexing failed")
        QMessageBox.critical(self, "Indexing Error", message)

    def _index_cleanup(self):
        if self.index_worker is not None:
            self.index_worker.deleteLater()
        if self.index_thread is not None:
            self.index_thread.deleteLater()
        self.index_worker = None
        self.index_thread = None

    def _refresh_current_index(self):
        folder = get_setting("document_folder", "")
        if folder and Path(folder).is_dir() and not (self.index_thread and self.index_thread.isRunning()):
            self.start_indexing(folder, force=False)

    def perform_search(self, query: str, input_mode: str = "text"):
        query = (query or "").strip()
        if not query:
            self.status_label.setText("Enter a document request.")
            return
        if self.search_thread is not None and self.search_thread.isRunning():
            return
        self.search_widget.set_busy(True)
        self.current_input_mode = input_mode or "text"
        self.status_label.setText("Understanding language and searching…")
        self.search_thread = QThread(self)
        self.search_worker = SearchWorker(
            query,
            self.search_widget.selected_language(),
            self.language_manager,
            self.digilocker,
            input_mode=self.current_input_mode,
        )
        self.search_worker.moveToThread(self.search_thread)
        self.search_thread.started.connect(self.search_worker.run)
        self.search_worker.finished.connect(self._search_finished)
        self.search_worker.failed.connect(self._search_failed)
        self.search_worker.finished.connect(self.search_thread.quit)
        self.search_worker.failed.connect(self.search_thread.quit)
        self.search_thread.finished.connect(self._search_cleanup)
        self.search_thread.start()

    def _search_finished(self, results, prepared, telemetry):
        self.search_widget.set_busy(False)
        self.search_widget.search_box.setFocus()
        self.current_results = results
        self._show_results_panel("Search Results")
        self.search_widget.set_recent_checked(False)
        self.populate_results(results)
        language_label = prepared.language_code or "auto"
        provider_label = prepared.provider_used or "local"
        detail_messages = [x for x in (self.language_provider_error, prepared.provider_error) if x]
        detail = f" • {'; '.join(detail_messages)}" if detail_messages else ""
        document_type = prepared.document_type or ""
        canonical_query = prepared.canonical_english or ""
        history_error = "; ".join(detail_messages)
        self.active_search_history_id = record_search_history(
            username=self.username, display_name=self.display_name,
            session_id=self.session_id,
            original_query=prepared.original or self.search_widget.search_box.text(),
            canonical_query=canonical_query,
            transliterated_query=prepared.transliterated or "",
            detected_language=language_label,
            preferred_language=self.search_widget.selected_language(),
            input_mode=telemetry.get("input_mode", self.current_input_mode),
            provider=provider_label,
            document_type=document_type,
            searched_at=telemetry.get("searched_at"),
            duration_ms=telemetry.get("duration_ms", 0),
            results_count=len(results),
            success=bool(results),
            error_message=history_error,
        )
        log_audit_event(
            "SEARCH", username=self.username, display_name=self.display_name, session_id=self.session_id,
            details={
                "query": prepared.original,
                "canonical_query": canonical_query,
                "language": language_label,
                "input_mode": telemetry.get("input_mode", self.current_input_mode),
                "provider": provider_label,
                "results_count": len(results),
                "duration_ms": telemetry.get("duration_ms", 0),
                "success": bool(results),
            },
        )
        if not results:
            self.document_viewer.show_empty_state(
                "No matching document",
                "Try a more specific document name, class, semester or year.",
            )
            self.status_label.setText(f"No match • {prepared.document_name or prepared.canonical_english} • {language_label} • {provider_label}{detail}")
            return
        self.open_result(results[0])
        source_label = "DigiLocker" if results[0].get("source") == "digilocker" else "Local"
        self.status_label.setText(
            f"Found {prepared.document_name or prepared.canonical_english} • {source_label} • {language_label} • {provider_label}{detail}"
        )

    def _search_failed(self, message: str):
        self.search_widget.set_busy(False)
        duration_text, _, clean_message = str(message).partition("|")
        try:
            duration_ms = int(duration_text)
        except ValueError:
            duration_ms = 0
            clean_message = str(message)
        query = self.search_widget.search_box.text().strip()
        if query:
            self.active_search_history_id = record_search_history(
                username=self.username, display_name=self.display_name,
                session_id=self.session_id,
                original_query=query,
                preferred_language=self.search_widget.selected_language(),
                input_mode=self.current_input_mode,
                provider="",
                searched_at=None,
                duration_ms=duration_ms,
                results_count=0,
                success=False,
                error_message=clean_message,
            )
            log_audit_event(
                "SEARCH_FAILED", username=self.username, display_name=self.display_name, session_id=self.session_id,
                details={"query": query, "duration_ms": duration_ms, "error": clean_message},
            )
        self.status_label.setText("Search failed")
        QMessageBox.critical(self, "Search Error", clean_message)

    def _search_cleanup(self):
        if self.search_worker is not None:
            self.search_worker.deleteLater()
        if self.search_thread is not None:
            self.search_thread.deleteLater()
        self.search_worker = None
        self.search_thread = None

    def _language_changed(self, language_code: str):
        self.voice_assistant_engine.set_language_code(language_code or None)
        if language_code:
            self.status_label.setText(f"Language selected: {language_code}")
        else:
            self.status_label.setText("Language: Auto Detect")


    def populate_results(self, results):
        while self.results_container_layout.count() > 1:
            item = self.results_container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.selected_card = None
        self.results_count.setText(str(len(results)))
        for index, result in enumerate(results):
            card = ResultCard(result)
            card.clicked.connect(self.open_result)
            self.results_container_layout.insertWidget(index, card)

    def open_result(self, result, announce: bool = True):
        self.pending_open_result = result
        success = self.document_viewer.open_file(result["path"], content=result.get("content", ""))
        if success:
            for i in range(self.results_container_layout.count() - 1):
                widget = self.results_container_layout.itemAt(i).widget()
                if isinstance(widget, ResultCard):
                    widget.set_selected(widget.result.get("id") == result.get("id"))
                    if widget.result.get("id") == result.get("id"):
                        self.selected_card = widget
            if announce:
                self.status_label.setText(f"Opened {result['name']}")

    def show_recent_documents(self):
        if self.results_panel.isVisible() and self.search_widget.recent_button.isChecked():
            # The recent button acts as a simple results drawer toggle.
            self.results_panel.hide()
            self.search_widget.set_recent_checked(False)
            return

        self.results_panel.show()
        self.results_title.setText("Recent Documents")
        self.search_widget.set_recent_checked(True)
        self.active_search_history_id = None
        rows = get_recent_documents(10)
        results = []
        for row in rows:
            path = row["path"]
            if not Path(path).is_file():
                continue
            results.append({
                "id": int(row["id"]), "name": row["name"], "path": path,
                "extension": row["extension"], "size": int(row["size"] or 0),
                "modified_time": float(row["modified_time"] or 0),
                "content": row["content"] or "", "document_type": row["document_type"] or None,
                "language": row["language"] or "", "score": 0,
            })
        self.current_results = results
        self.populate_results(results)
        if results:
            self.open_result(results[0], announce=False)
            self.status_label.setText("Recently opened documents")
        else:
            self.document_viewer.show_empty_state("No recent documents", "Open a document and it will appear here.")
            self.status_label.setText("No recent documents yet")

    def _show_results_panel(self, title: str):
        self.results_panel.show()
        self.results_title.setText(title)

    def show_history(self):
        dialog = HistoryDialog(self.username, self.display_name, self)
        dialog.search_again.connect(lambda query: self.perform_search(query, input_mode="history_replay"))
        dialog.exec()

    def voice_assistant(self):
        self.search_widget.set_busy(True)
        self.status_label.setText("Starting voice search…")
        self.voice_assistant_engine.start()

    def handle_voice_status(self, message: str):
        self.status_label.setText(message)

    def handle_voice_language(self, language_code: str):
        if language_code:
            self.status_label.setText(f"Detected speech language: {language_code}")

    def handle_voice_text(self, text: str):
        self.search_widget.search_box.setText(text)
        self.status_label.setText(f'Heard: “{text}”')
        self.search_widget.set_busy(False)
        self.perform_search(text, input_mode="voice")

    def handle_voice_error(self, message: str):
        self.search_widget.set_busy(False)
        self._set_status_error(message)
        QMessageBox.warning(self, "Voice Search", message)

    def _on_file_changed(self, _path: str):
        self.pending_refresh_timer.start()

    def _set_status_error(self, message: str):
        self.status_label.setText(message)

    def _document_was_opened(self, path: str):
        mark_opened(path)
        result = self.pending_open_result or {}
        source = result.get("source", "local") or "local"
        document_id = result.get("id")
        if isinstance(document_id, str) and ":" in document_id:
            document_id = None
        record_document_access(
            username=self.username, display_name=self.display_name,
            session_id=self.session_id,
            document_id=document_id,
            document_name=result.get("name") or Path(path).name,
            document_path=path,
            source=source,
            action="open",
            search_history_id=self.active_search_history_id,
        )
        self.pending_open_result = None
        self.indexed_label.setText(f"{get_document_count()} documents indexed")

    def closeEvent(self, event):
        self.watcher.stop()
        if self.index_worker:
            self.index_worker.stop()
        if self.index_thread and self.index_thread.isRunning():
            self.index_thread.quit()
            self.index_thread.wait(2000)
        super().closeEvent(event)
