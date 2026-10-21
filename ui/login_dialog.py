from PySide6.QtCore import Qt

from database import record_login_attempt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout


class LoginDialog(QDialog):
    """Lightweight local identity dialog for activity tracking.

    This is intentionally an identity/session layer, not a security boundary.
    It records who used this local desktop application without changing access
    to the existing document search/index pipeline.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Smart Document Finder — User Login")
        self.setMinimumWidth(440)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(12)

        title = QLabel("Welcome to Smart Document Finder")
        title.setObjectName("loginTitle")
        subtitle = QLabel("Enter your local user identity so searches and document activity can be timestamped.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("loginSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(10)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("e.g. anshul")
        self.username_edit.setMaxLength(80)
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setPlaceholderText("e.g. Anshul Chaudhary")
        self.display_name_edit.setMaxLength(120)
        form.addRow("Username", self.username_edit)
        form.addRow("Display name", self.display_name_edit)
        root.addLayout(form)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setObjectName("loginMessage")
        root.addWidget(self.message)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Login")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.username_edit.returnPressed.connect(self._accept)
        self.display_name_edit.returnPressed.connect(self._accept)

    def _accept(self):
        username = self.username_edit.text().strip()
        display_name = self.display_name_edit.text().strip() or username
        if not username:
            record_login_attempt(
                username="",
                display_name=display_name,
                status="FAIL",
                reason="username_required",
            )
            self.message.setText("Username is required.")
            self.username_edit.setFocus()
            return
        self.username = username
        self.display_name = display_name
        self.accept()
