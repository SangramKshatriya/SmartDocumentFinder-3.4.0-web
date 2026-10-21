from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton,
    QVBoxLayout, QApplication, QStyle,
)

from language.languages import LANGUAGES


class SearchWidget(QFrame):
    search_requested = Signal(str)
    voice_requested = Signal()
    recent_requested = Signal()
    history_requested = Signal()
    language_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.setup_ui()

    def _icon(self, standard_icon):
        return QApplication.style().standardIcon(standard_icon)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 0)
        layout.setSpacing(12)

        header = QHBoxLayout()
        brand = QLabel("SD")
        brand.setObjectName("brandMark")
        brand.setAlignment(Qt.AlignCenter)
        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)
        title = QLabel("Smart Document Finder")
        title.setObjectName("appName")
        subtitle = QLabel("Search your documents in English and Indian languages")
        subtitle.setObjectName("appSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header.addWidget(brand)
        header.addLayout(title_layout)
        header.addStretch()
        header.addWidget(QLabel("Language"))
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        self.language_combo.addItem("Auto Detect", "")
        for language in LANGUAGES:
            self.language_combo.addItem(
                f"{language.name} • {language.native_name}",
                language.code,
            )
        self.language_combo.currentIndexChanged.connect(
            lambda _: self.language_changed.emit(self.language_combo.currentData() or "")
        )
        header.addWidget(self.language_combo)
        layout.addLayout(header)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        container = QFrame()
        container.setObjectName("searchContainer")
        search_layout = QHBoxLayout(container)
        search_layout.setContentsMargins(16, 6, 8, 6)
        self.search_box = QLineEdit()
        self.search_box.setObjectName("searchBox")
        self.search_box.setPlaceholderText(
            'Search: “show my 12th marksheet” • “मेरा पैन कार्ड दिखाओ”'
        )
        self.search_box.setMinimumHeight(50)
        self.voice_input_button = QToolButton()
        self.voice_input_button.setObjectName("iconButton")
        self.voice_input_button.setIcon(self._icon(QStyle.SP_MediaVolume))
        self.voice_input_button.setToolTip("Voice search")
        self.voice_input_button.clicked.connect(self.voice_requested.emit)
        self.clear_button = QToolButton()
        self.clear_button.setObjectName("iconButton")
        self.clear_button.setIcon(self._icon(QStyle.SP_DialogCloseButton))
        self.clear_button.setToolTip("Clear search")
        self.clear_button.clicked.connect(self.search_box.clear)
        search_layout.addWidget(self.search_box, 1)
        search_layout.addWidget(self.voice_input_button)
        search_layout.addWidget(self.clear_button)
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("searchButton")
        self.search_button.setIcon(self._icon(QStyle.SP_FileDialogContentsView))
        self.search_button.setMinimumHeight(52)
        self.search_button.setCursor(Qt.PointingHandCursor)
        search_row.addWidget(container, 1)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch()
        self.recent_button = self._action_button("Recent", QStyle.SP_FileDialogInfoView)
        self.recent_button.setCheckable(True)
        self.recent_button.setToolTip("Show or hide recently opened documents")
        self.recent_button.setMinimumWidth(150)
        self.history_button = self._action_button("History", QStyle.SP_FileDialogDetailedView)
        self.history_button.setToolTip("View your timestamped search and document history")
        self.history_button.setMinimumWidth(150)
        actions.addWidget(self.recent_button)
        actions.addWidget(self.history_button)
        layout.addLayout(actions)

        self.search_button.clicked.connect(self.emit_search)
        self.search_box.returnPressed.connect(self.emit_search)
        self.recent_button.clicked.connect(self.recent_requested.emit)
        self.history_button.clicked.connect(self.history_requested.emit)

    def _action_button(self, text, standard_icon):
        button = QPushButton(text)
        button.setObjectName("actionButton")
        button.setIcon(self._icon(standard_icon))
        button.setMinimumHeight(44)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def emit_search(self):
        self.search_requested.emit(self.search_box.text().strip())

    def selected_language(self):
        return self.language_combo.currentData() or ""

    def set_recent_checked(self, checked: bool):
        self.recent_button.blockSignals(True)
        self.recent_button.setChecked(checked)
        self.recent_button.blockSignals(False)

    def set_busy(self, busy: bool):
        for widget in (
            self.search_box, self.search_button, self.voice_input_button,
            self.clear_button, self.recent_button, self.history_button, self.language_combo,
        ):
            widget.setEnabled(not busy)
