APP_STYLE = """
* { font-family: 'Segoe UI'; }
QWidget { background: #f7f9fc; color: #17233a; }
QFrame#page { background: transparent; }
QLabel#brandMark { background: #146ef5; color: white; border-radius: 12px; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; font-size: 14px; font-weight: 800; }
QLabel#appName { color: #14213a; font-size: 23px; font-weight: 750; }
QLabel#appSubtitle { color: #728096; font-size: 13px; }
QFrame#searchContainer { background: white; border: 1px solid #dce3ee; border-radius: 14px; }
QLineEdit#searchBox { background: transparent; border: none; font-size: 15px; padding: 4px; color: #17233a; }
QLineEdit#searchBox:focus { border: none; }
QComboBox#languageCombo { background: white; border: 1px solid #dfe5ed; border-radius: 9px; padding: 6px 10px; min-height: 30px; color: #24324a; }
QComboBox#languageCombo:hover { border-color: #bcd2f5; }
QToolButton#iconButton { background: transparent; border: none; padding: 7px; }
QToolButton#iconButton:hover { background: #edf3ff; border-radius: 8px; }
QPushButton#searchButton { background: #146ef5; color: white; border: none; border-radius: 12px; padding: 0 20px; font-size: 14px; font-weight: 650; }
QPushButton#searchButton:hover { background: #0e60dc; }
QPushButton#searchButton:disabled { background: #a8bde5; }
QPushButton#actionButton { background: white; color: #24324a; border: 1px solid #e1e7ef; border-radius: 12px; font-size: 13px; font-weight: 600; }
QPushButton#actionButton:hover { background: #f0f5fd; border-color: #c8d7ee; }
QPushButton#actionButton:checked { background: #eaf2ff; color: #146ef5; border-color: #bcd2f5; }
QPushButton#actionButton:disabled { color: #9ca7b8; background: #f7f8fa; }
QFrame#resultsPanel, QFrame#viewerPanel { background: white; border: 1px solid #e0e7f0; border-radius: 16px; }
QLabel#resultsTitle { font-size: 16px; font-weight: 750; color: #1a2840; }
QLabel#resultsCount { background: #eef4ff; color: #146ef5; border-radius: 9px; padding: 2px 8px; font-size: 12px; font-weight: 700; }
QScrollArea#resultsScroll, QScrollArea#documentArea { background: transparent; border: none; }
QFrame#resultCard { background: #fff; border: 1px solid transparent; border-radius: 12px; }
QFrame#resultCard:hover { background: #f6f9fd; border-color: #dfe7f2; }
QFrame#resultCard[selected='true'] { background: #eaf2ff; border-color: #bcd2f5; }
QLabel#resultIcon { background: #eef4ff; color: #146ef5; border-radius: 9px; padding: 4px; font-size: 10px; font-weight: 800; }
QLabel#resultName { color: #1b2940; font-size: 13px; font-weight: 700; }
QLabel#resultPath { color: #77869d; font-size: 11px; }
QLabel#resultMeta { color: #8290a4; font-size: 10px; }
QFrame#viewerHeader { background: #fff; border-bottom: 1px solid #edf0f4; }
QLabel#documentIcon { color: #146ef5; font-size: 12px; font-weight: 800; }
QLabel#documentName { color: #1a2840; font-size: 15px; font-weight: 750; }
QPushButton#viewerTool { background: white; border: 1px solid #dfe5ed; border-radius: 8px; min-width: 34px; min-height: 30px; color: #24324a; }
QPushButton#viewerTool:hover { background: #f4f7fb; }
QPushButton#viewerAction { background: transparent; border: none; color: #2b3a52; font-size: 12px; padding: 5px 7px; }
QPushButton#viewerAction:hover { color: #146ef5; background: #f2f6fd; border-radius: 7px; }
QLabel#viewerZoom { min-width: 46px; color: #526179; font-size: 11px; }
QLabel#pageNumber { min-width: 80px; color: #65748b; font-size: 12px; }
QLabel#emptyTitle { color: #263650; font-size: 20px; font-weight: 750; }
QLabel#emptyMessage { color: #7a889c; font-size: 13px; max-width: 520px; }
QLabel#statusLabel { color: #5e6d84; font-size: 12px; }
QLabel#folderLabel { color: #758298; font-size: 11px; }
QProgressBar#progressBar { height: 10px; border: none; border-radius: 5px; background: #e8edf4; text-visible: false; }
QProgressBar#progressBar::chunk { background: #146ef5; border-radius: 5px; }
QTextBrowser { background: white; border: none; border-radius: 10px; padding: 14px; font-size: 13px; }

QLabel#loginTitle { color: #1a2840; font-size: 19px; font-weight: 750; }
QLabel#loginSubtitle { color: #738198; font-size: 12px; }
QLabel#loginMessage { color: #b04040; font-size: 11px; }
QLabel#historyTitle { color: #1a2840; font-size: 18px; font-weight: 750; }
QLabel#historyStats { color: #65748b; font-size: 11px; }
QLabel#historyHint { color: #8491a5; font-size: 11px; }
"""
