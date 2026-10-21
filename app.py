import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from PySide6.QtWidgets import QApplication, QMessageBox

from config import APP_VERSION
from database import end_session, get_or_create_user, initialize_database, start_session, get_database_backend
from ui.login_dialog import LoginDialog
from ui.main_window import MainWindow
from ui.styles import APP_STYLE


def resolve_folder(folder_arg: str | None) -> str:
    """Resolve the document folder from CLI argument, environment, or terminal prompt."""
    import os

    folder = (folder_arg or os.getenv("DOCUMENT_FOLDER", "")).strip().strip('"')

    while True:
        if not folder:
            print("\nSmart Document Finder")
            print("Enter the folder containing the documents you want to search.")
            print(r'Example: C:\Users\YourName\Documents')
            try:
                folder = input("\nDocument folder: ").strip().strip('"')
            except EOFError as exc:
                raise RuntimeError(
                    "No document folder was provided. Run `python app.py \"C:\\path\\to\\documents\"` "
                    "or run it from an interactive terminal."
                ) from exc

        path = Path(folder).expanduser()
        if path.is_dir():
            return str(path.resolve())

        print(f"Folder not found: {path}")
        folder = ""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Search your documents from a simple desktop interface."
    )
    parser.add_argument(
        "folder", nargs="?",
        help="Document folder. If omitted, the terminal will ask for it."
    )
    parser.add_argument(
        "--reindex", action="store_true",
        help="Force a full reindex when the application starts."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    folder = resolve_folder(args.folder)

    print(f"\nDocument folder: {folder}")
    print("Starting Smart Document Finder…")
    print("You can search from the application window now.\n")

    app = QApplication(sys.argv)
    app.setApplicationName("Smart Document Finder")
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(APP_STYLE)

    # Initialize the document index and configured activity backend before the
    # login dialog. A PostgreSQL configuration problem should be shown as a
    # clear setup error instead of appearing later as a history/session crash.
    try:
        initialize_database()
        print(f"Activity database backend: {get_database_backend()}")
    except Exception as error:
        QMessageBox.critical(
            None,
            "Database Setup Error",
            f"Smart Document Finder could not initialize its database backend.\n\n{error}",
        )
        return

    login_dialog = LoginDialog()
    if login_dialog.exec() != login_dialog.DialogCode.Accepted:
        return

    user = get_or_create_user(login_dialog.username, login_dialog.display_name)
    session_id = start_session(user["username"], user["display_name"])

    window = MainWindow(
        folder, force_index=args.reindex,
        username=user["username"], display_name=user["display_name"], session_id=session_id,
    )
    app.aboutToQuit.connect(lambda: end_session(session_id, "application_closed"))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
