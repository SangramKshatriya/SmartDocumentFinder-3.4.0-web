from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QHeaderView, QMessageBox,
)

from database import (
    export_user_history_json,
    get_document_history,
    get_search_history,
    get_session_history,
    get_user_stats,
)


def format_timestamp(value: str) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d %b %Y  %I:%M:%S %p")
    except Exception:
        return value


class HistoryDialog(QDialog):
    search_again = Signal(str)

    def __init__(self, username: str, display_name: str, parent=None):
        super().__init__(parent)
        self.username = str(username or "").strip()
        self.display_name = display_name
        self.setWindowTitle(f"Activity History — {display_name}")
        self.resize(1050, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Activity History")
        title.setObjectName("historyTitle")
        header.addWidget(title)
        header.addStretch()
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("historyStats")
        header.addWidget(self.stats_label)
        self.export_button = QPushButton("Export JSON")
        self.export_button.clicked.connect(self.export_json)
        header.addWidget(self.export_button)
        root.addLayout(header)

        hint = QLabel("Double-click a search to run it again.")
        hint.setObjectName("historyHint")
        root.addWidget(hint)

        tabs = QTabWidget()
        self.search_table = self._make_table([
            "Time", "Search", "Language", "Mode", "Document", "Results", "Status", "Duration"
        ])
        self.document_table = self._make_table([
            "Time", "Document", "Source", "Action", "Document Type", "Path"
        ])
        self.session_table = self._make_table([
            "Login Time", "Logout Time", "Login Status", "Logout Status", "Session Status", "Reason"
        ])
        tabs.addTab(self.search_table, "Search History")
        tabs.addTab(self.document_table, "Document History")
        tabs.addTab(self.session_table, "Sessions")
        root.addWidget(tabs, 1)

        self.search_table.cellDoubleClicked.connect(self._repeat_search)
        self.refresh()

    @staticmethod
    def _make_table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        return table

    @staticmethod
    def _item(text, user_data=None):
        item = QTableWidgetItem(str(text if text not in (None, "") else "—"))
        if user_data is not None:
            item.setData(Qt.UserRole, user_data)
        return item

    def refresh(self):
        stats = get_user_stats(self.username)
        self.stats_label.setText(
            f"Searches: {stats['searches']}  •  Opens: {stats['document_opens']}  •  Voice: {stats['voice_searches']}  •  Success: {stats['successful_searches']}"
        )

        searches = get_search_history(self.username, 200)
        self.search_table.setRowCount(0)
        for row in searches:
            index = self.search_table.rowCount()
            self.search_table.insertRow(index)
            values = [
                format_timestamp(row["searched_at"]),
                row["original_query"],
                row["detected_language"] or row["preferred_language"] or "auto",
                row["input_mode"],
                row["document_type"] or "—",
                row["results_count"],
                "Found" if str(row["status"] or "").upper() == "PASS" else "No match / failed",
                f"{int(row['duration_ms'] or 0)} ms",
            ]
            for col, value in enumerate(values):
                item = self._item(value, row["original_query"] if col == 1 else None)
                self.search_table.setItem(index, col, item)
            error_message = str(row["error_message"] or "")
            if error_message:
                self.search_table.item(index, 6).setToolTip(error_message)

        documents = get_document_history(self.username, 200)
        self.document_table.setRowCount(0)
        for row in documents:
            index = self.document_table.rowCount()
            self.document_table.insertRow(index)
            timestamp = (
                row["accessed_at"]
                if "accessed_at" in row.keys()
                else row["event_time"]
            )
            values = [
                format_timestamp(timestamp), row["document_name"],
                row["source"], row["action"], row["document_type"] or "—", row["document_path"],
            ]
            for col, value in enumerate(values):
                self.document_table.setItem(index, col, self._item(value))
            self.document_table.item(index, 5).setToolTip(row["document_path"])

        sessions = get_session_history(self.username, 100)
        self.session_table.setRowCount(0)
        for row in sessions:
            index = self.session_table.rowCount()
            self.session_table.insertRow(index)
            values = [
                format_timestamp(row["login_time"]),
                format_timestamp(row["logout_time"]),
                row["login_status"] or "—",
                row["logout_status"] or "—",
                row["session_status"] or "—",
                row["event_reason"] or "—",
            ]
            for col, value in enumerate(values):
                self.session_table.setItem(index, col, self._item(value))

    def _repeat_search(self, row: int, _column: int):
        item = self.search_table.item(row, 1)
        if item:
            query = item.data(Qt.UserRole) or item.text()
            if query:
                self.search_again.emit(str(query))
                self.accept()

    def export_json(self):
        default_name = f"smart_document_finder_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export Activity History", str(Path.home() / default_name), "JSON Files (*.json)"
        )
        if not destination:
            return
        try:
            export_user_history_json(self.username, destination)
            QMessageBox.information(self, "History Exported", f"History exported successfully to:\n{destination}")
        except Exception as error:
            QMessageBox.critical(self, "Export Failed", str(error))
