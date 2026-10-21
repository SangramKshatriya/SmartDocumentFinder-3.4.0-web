import os
import shutil
import subprocess
from pathlib import Path

import pymupdf

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QTextBrowser, QVBoxLayout, QWidget, QStyle,
)

from content_extractor import extract_text


class DocumentViewer(QWidget):
    document_opened = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.file_type = None
        self.pdf_document = None
        self.pdf_page_number = 0
        self.pdf_page_count = 0
        self.pdf_pixmap = None
        self.image_pixmap = None
        self.image_label = None
        self.pdf_page_label = None
        self.text_browser = None
        self.zoom_factor = -1
        self.setup_ui()

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        header = QFrame()
        header.setObjectName("viewerHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 6, 10, 6)
        self.document_icon = QLabel("DOC")
        self.document_icon.setObjectName("documentIcon")
        self.document_name = QLabel("No document selected")
        self.document_name.setObjectName("documentName")
        h.addWidget(self.document_icon)
        h.addWidget(self.document_name, 1)
        self.zoom_out_button = self._tool("−", "Zoom out")
        self.zoom_label = QLabel("Fit")
        self.zoom_label.setObjectName("viewerZoom")
        self.zoom_in_button = self._tool("+", "Zoom in")
        self.fit_button = self._tool("Fit", "Fit to page")
        self.open_button = self._action("Open", self.open_external)
        self.download_button = self._action("Save", self.download_document)
        self.reveal_button = self._action("Reveal", self.reveal_document)
        for widget in (self.zoom_out_button, self.zoom_label, self.zoom_in_button, self.fit_button,
                       self.open_button, self.download_button, self.reveal_button):
            h.addWidget(widget)
        root.addWidget(header)

        canvas = QFrame()
        canvas.setObjectName("documentCanvas")
        c = QVBoxLayout(canvas)
        c.setContentsMargins(8, 8, 8, 8)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("documentArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignCenter)
        self.scroll_area.setWidget(self.content_widget)
        c.addWidget(self.scroll_area)
        root.addWidget(canvas, 1)

        nav = QHBoxLayout()
        nav.setAlignment(Qt.AlignCenter)
        self.previous_button = self._tool("‹", "Previous page")
        self.page_label = QLabel("—")
        self.page_label.setObjectName("pageNumber")
        self.next_button = self._tool("›", "Next page")
        nav.addWidget(self.previous_button)
        nav.addWidget(self.page_label)
        nav.addWidget(self.next_button)
        root.addLayout(nav)

        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.fit_button.clicked.connect(self.fit_page)
        self.previous_button.clicked.connect(self.previous_page)
        self.next_button.clicked.connect(self.next_page)
        self.set_controls_enabled(False)

    def _tool(self, text, tooltip):
        button = QPushButton(text)
        button.setObjectName("viewerTool")
        button.setToolTip(tooltip)
        return button

    def _action(self, text, callback):
        button = QPushButton(text)
        button.setObjectName("viewerAction")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.image_label = None
        self.pdf_page_label = None
        self.text_browser = None

    def clear(self):
        self._clear_content()
        if self.pdf_document is not None:
            try:
                self.pdf_document.close()
            except Exception:
                pass
        self.pdf_document = None
        self.current_file = None
        self.file_type = None
        self.zoom_factor = -1
        self.page_label.setText("—")
        self.set_controls_enabled(False)

    def show_empty_state(self, title: str, message: str):
        self.clear()
        box = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("emptyTitle")
        title_label.setAlignment(Qt.AlignCenter)
        message_label = QLabel(message)
        message_label.setObjectName("emptyMessage")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignCenter)
        box.addStretch()
        box.addWidget(title_label)
        box.addWidget(message_label)
        box.addStretch()
        holder = QWidget()
        holder.setLayout(box)
        self.content_layout.addWidget(holder)
        self.document_name.setText("No document selected")

    def open_file(self, file_path: str, content: str = "") -> bool:
        self.clear()
        path = Path(file_path)
        if not path.is_file():
            self.show_empty_state("Document not found", "The indexed file no longer exists.")
            return False
        self.current_file = str(path.resolve())
        self.document_name.setText(path.name)
        extension = path.suffix.lower()
        try:
            if extension == ".pdf":
                self.file_type = "pdf"
                success = self._open_pdf()
            elif extension in {".jpg", ".jpeg", ".png"}:
                self.file_type = "image"
                success = self._open_image()
            else:
                self.file_type = "text"
                success = self._open_text_preview(content)
            if success:
                self.document_opened.emit(self.current_file)
            return success
        except Exception as error:
            self.show_empty_state("Unable to preview document", str(error))
            return False

    def _open_image(self) -> bool:
        pixmap = QPixmap(self.current_file)
        if pixmap.isNull():
            raise RuntimeError("The image could not be decoded by Qt.")
        self.image_pixmap = pixmap
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.image_label)
        self.zoom_factor = -1
        self.set_controls_enabled(True)
        self.display_image()
        return True

    def display_image(self):
        if self.image_pixmap is None:
            return
        viewport = self.scroll_area.viewport()
        if self.zoom_factor < 0:
            scaled = self.image_pixmap.scaled(
                max(100, viewport.width() - 30), max(100, viewport.height() - 30),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        else:
            scaled = self.image_pixmap.scaled(
                int(self.image_pixmap.width() * self.zoom_factor),
                int(self.image_pixmap.height() * self.zoom_factor),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        self.image_label.setPixmap(scaled)
        self.update_zoom_label()

    def _open_pdf(self) -> bool:
        self.pdf_document = pymupdf.open(self.current_file)
        self.pdf_page_count = len(self.pdf_document)
        if self.pdf_page_count == 0:
            raise RuntimeError("This PDF has no pages.")
        self.pdf_page_number = 0
        self.pdf_page_label = QLabel()
        self.pdf_page_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.pdf_page_label)
        self.zoom_factor = -1
        self.set_controls_enabled(True)
        self.display_pdf_page()
        return True

    def display_pdf_page(self):
        if self.pdf_document is None:
            return
        page = self.pdf_document[self.pdf_page_number]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        image = QPixmap()
        image.loadFromData(pixmap.tobytes("png"))
        self.pdf_pixmap = image
        viewport = self.scroll_area.viewport()
        if self.zoom_factor < 0:
            scaled = image.scaled(
                max(100, viewport.width() - 40), max(100, viewport.height() - 40),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        else:
            scaled = image.scaled(
                int(image.width() * self.zoom_factor), int(image.height() * self.zoom_factor),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        self.pdf_page_label.setPixmap(scaled)
        self.page_label.setText(f"{self.pdf_page_number + 1} / {self.pdf_page_count}")
        self.previous_button.setEnabled(self.pdf_page_number > 0)
        self.next_button.setEnabled(self.pdf_page_number < self.pdf_page_count - 1)
        self.update_zoom_label()

    def _open_text_preview(self, content: str) -> bool:
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(False)
        if not content:
            content = extract_text(self.current_file)
        if not content:
            content = "No extracted text is available for preview.\n\nUse Open to view this file in its default application."
        self.text_browser.setPlainText(content)
        self.content_layout.addWidget(self.text_browser)
        self.page_label.setText("Text")
        self.set_controls_enabled(True)
        return True

    def set_controls_enabled(self, enabled: bool):
        for button in (self.zoom_out_button, self.zoom_in_button, self.fit_button,
                       self.open_button, self.download_button, self.reveal_button):
            button.setEnabled(enabled)
        self.previous_button.setEnabled(enabled and self.file_type == "pdf" and self.pdf_page_number > 0)
        self.next_button.setEnabled(enabled and self.file_type == "pdf" and self.pdf_page_number < self.pdf_page_count - 1)

    def zoom_in(self):
        if self.file_type not in {"pdf", "image"}:
            return
        self.zoom_factor = 1.0 if self.zoom_factor < 0 else self.zoom_factor
        self.zoom_factor = min(5.0, self.zoom_factor + 0.25)
        self.refresh()

    def zoom_out(self):
        if self.file_type not in {"pdf", "image"}:
            return
        self.zoom_factor = 1.0 if self.zoom_factor < 0 else self.zoom_factor
        self.zoom_factor = max(0.25, self.zoom_factor - 0.25)
        self.refresh()

    def fit_page(self):
        self.zoom_factor = -1
        self.refresh()

    def refresh(self):
        if self.file_type == "pdf":
            self.display_pdf_page()
        elif self.file_type == "image":
            self.display_image()

    def update_zoom_label(self):
        self.zoom_label.setText("Fit" if self.zoom_factor < 0 else f"{int(self.zoom_factor * 100)}%")

    def previous_page(self):
        if self.file_type == "pdf" and self.pdf_page_number > 0:
            self.pdf_page_number -= 1
            self.display_pdf_page()

    def next_page(self):
        if self.file_type == "pdf" and self.pdf_page_number < self.pdf_page_count - 1:
            self.pdf_page_number += 1
            self.display_pdf_page()

    def open_external(self):
        if not self.current_file:
            return
        try:
            os.startfile(self.current_file)  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["xdg-open", self.current_file])
        except Exception as error:
            QMessageBox.warning(self, "Open Failed", str(error))

    def reveal_document(self):
        if not self.current_file:
            return
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", self.current_file])
            else:
                subprocess.Popen(["xdg-open", str(Path(self.current_file).parent)])
        except Exception as error:
            QMessageBox.warning(self, "Reveal Failed", str(error))

    def download_document(self):
        if not self.current_file:
            return
        destination, _ = QFileDialog.getSaveFileName(self, "Save Document", Path(self.current_file).name, "All Files (*)")
        if not destination:
            return
        try:
            shutil.copy2(self.current_file, destination)
            QMessageBox.information(self, "Saved", "Document saved successfully.")
        except Exception as error:
            QMessageBox.critical(self, "Save Failed", str(error))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom_factor < 0 and self.file_type in {"pdf", "image"}:
            self.refresh()
