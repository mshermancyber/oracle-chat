"""Qt stylesheet — dark-navy aesthetic inspired by Claude.ai."""
from __future__ import annotations

STYLESHEET = """
* {
    font-family: -apple-system, "Segoe UI", "Inter", "Roboto", sans-serif;
    color: #E5ECF7;
}

QMainWindow, QDialog, QWidget {
    background: #0B1220;
}

/* Sidebar ---------------------------------------------------------------- */
#sidebar {
    background: #111A2E;
    border-right: 1px solid #1E2A45;
}

#sidebar QPushButton#newChatButton {
    background: #1E2A45;
    border: 1px solid #2A3A5A;
    border-radius: 8px;
    padding: 10px 12px;
    margin: 12px;
    font-weight: 600;
    text-align: left;
}
#sidebar QPushButton#newChatButton:hover {
    background: #2A3A5A;
}

QListWidget#chatList {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget#chatList::item {
    padding: 10px 12px;
    margin: 2px 8px;
    border-radius: 6px;
}
QListWidget#chatList::item:hover {
    background: #17223B;
}
QListWidget#chatList::item:selected {
    background: #1E2A45;
    color: #E5ECF7;
}

/* Top bar ---------------------------------------------------------------- */
#topBar {
    background: #0B1220;
    border-bottom: 1px solid #1E2A45;
    padding: 8px 16px;
}
QLabel#chatTitle {
    font-size: 14px;
    font-weight: 600;
    color: #E5ECF7;
}
QComboBox#modelPicker {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 6px;
    padding: 6px 10px;
    min-width: 180px;
}
QComboBox#modelPicker::drop-down {
    border: none;
    width: 18px;
}
QComboBox QAbstractItemView {
    background: #17223B;
    border: 1px solid #2A3A5A;
    selection-background-color: #1E2A45;
}

/* Chat view -------------------------------------------------------------- */
QTextBrowser#chatView {
    background: #0B1220;
    border: none;
    padding: 20px;
    font-size: 14px;
    selection-background-color: #1E2A45;
}

/* Input area ------------------------------------------------------------- */
#inputArea {
    background: #0B1220;
    border-top: 1px solid #1E2A45;
}
QPlainTextEdit#inputBox {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 10px;
    padding: 12px 14px;
    font-size: 14px;
    color: #E5ECF7;
}
QPlainTextEdit#inputBox:focus {
    border: 1px solid #60A5FA;
}
QPushButton#sendButton {
    background: #2563EB;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
    color: white;
}
QPushButton#sendButton:hover {
    background: #1D4ED8;
}
QPushButton#sendButton:disabled {
    background: #1E2A45;
    color: #64748B;
}
QPushButton#stopButton {
    background: #B91C1C;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
    color: white;
}
QPushButton#stopButton:hover {
    background: #991B1B;
}
QPushButton#attachButton {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 8px;
    padding: 10px 14px;
    font-weight: 500;
    color: #CBD5E1;
}
QPushButton#attachButton:hover {
    background: #1E2A45;
    color: #E5ECF7;
}

/* Pending-attachment chips ----------------------------------------------- */
QFrame#attachChip {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 14px;
}
QFrame#attachChip QLabel {
    color: #CBD5E1;
    font-size: 12px;
}
QPushButton#chipClose {
    background: transparent;
    border: none;
    color: #94A3B8;
    font-size: 13px;
    padding: 0;
}
QPushButton#chipClose:hover {
    color: #F87171;
}

/* Token counter --------------------------------------------------------- */
QLabel#tokenLabel {
    color: #64748B;
    font-size: 11px;
    padding: 0 2px;
}

/* Sidebar search -------------------------------------------------------- */
QLineEdit#sidebarSearch {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 6px;
    padding: 8px 10px;
    margin: 8px 12px 4px 12px;
    color: #E5ECF7;
    font-size: 13px;
}
QLineEdit#sidebarSearch:focus {
    border: 1px solid #60A5FA;
}

/* In-conversation search bar -------------------------------------------- */
#searchBar {
    background: #111A2E;
    border-bottom: 1px solid #1E2A45;
}
QLineEdit#searchInput {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 6px;
    padding: 6px 10px;
    color: #E5ECF7;
    font-size: 13px;
}
QLineEdit#searchInput:focus {
    border: 1px solid #60A5FA;
}
QPushButton#searchNavButton {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    color: #CBD5E1;
}
QPushButton#searchNavButton:hover {
    background: #1E2A45;
    color: #E5ECF7;
}

/* Pin indicator in chat list -------------------------------------------- */
QListWidget#chatList::item[pinned="true"] {
    font-weight: 600;
}

/* Export button ---------------------------------------------------------- */
QPushButton#exportButton {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 500;
    color: #CBD5E1;
    font-size: 12px;
}
QPushButton#exportButton:hover {
    background: #1E2A45;
    color: #E5ECF7;
}

/* Setup dialog ----------------------------------------------------------- */
QDialog QLabel {
    color: #E5ECF7;
}
QDialog QLineEdit {
    background: #17223B;
    border: 1px solid #2A3A5A;
    border-radius: 6px;
    padding: 8px 10px;
    color: #E5ECF7;
}
QDialog QLineEdit:focus {
    border: 1px solid #60A5FA;
}

/* Scrollbar -------------------------------------------------------------- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2A3A5A;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

STYLESHEET_LIGHT = """
* {
    font-family: -apple-system, "Segoe UI", "Inter", "Roboto", sans-serif;
    color: #1E293B;
}
QMainWindow, QDialog, QWidget { background: #FFFFFF; }
#sidebar { background: #F8FAFC; border-right: 1px solid #E2E8F0; }
#sidebar QPushButton#newChatButton {
    background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 8px;
    padding: 10px 12px; margin: 12px; font-weight: 600; text-align: left;
}
#sidebar QPushButton#newChatButton:hover { background: #E2E8F0; }
QListWidget#chatList { background: transparent; border: none; outline: none; }
QListWidget#chatList::item { padding: 10px 12px; margin: 2px 8px; border-radius: 6px; }
QListWidget#chatList::item:hover { background: #F1F5F9; }
QListWidget#chatList::item:selected { background: #E2E8F0; color: #1E293B; }
#topBar { background: #FFFFFF; border-bottom: 1px solid #E2E8F0; padding: 8px 16px; }
QLabel#chatTitle { font-size: 14px; font-weight: 600; color: #1E293B; }
QComboBox#modelPicker {
    background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px;
    padding: 6px 10px; min-width: 180px; color: #1E293B;
}
QComboBox#modelPicker::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #F1F5F9; border: 1px solid #E2E8F0; selection-background-color: #E2E8F0; }
QTextBrowser#chatView {
    background: #FFFFFF; border: none; padding: 20px; font-size: 14px;
    selection-background-color: #BFDBFE;
}
#inputArea { background: #FFFFFF; border-top: 1px solid #E2E8F0; }
QPlainTextEdit#inputBox {
    background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px;
    padding: 12px 14px; font-size: 14px; color: #1E293B;
}
QPlainTextEdit#inputBox:focus { border: 1px solid #3B82F6; }
QPushButton#sendButton {
    background: #3B82F6; border: none; border-radius: 8px;
    padding: 10px 18px; font-weight: 600; color: white;
}
QPushButton#sendButton:hover { background: #2563EB; }
QPushButton#sendButton:disabled { background: #E2E8F0; color: #94A3B8; }
QPushButton#stopButton {
    background: #DC2626; border: none; border-radius: 8px;
    padding: 10px 18px; font-weight: 600; color: white;
}
QPushButton#stopButton:hover { background: #B91C1C; }
QPushButton#attachButton {
    background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 8px;
    padding: 10px 14px; font-weight: 500; color: #64748B;
}
QPushButton#attachButton:hover { background: #E2E8F0; color: #1E293B; }
QFrame#attachChip { background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 14px; }
QFrame#attachChip QLabel { color: #64748B; font-size: 12px; }
QPushButton#chipClose { background: transparent; border: none; color: #94A3B8; font-size: 13px; padding: 0; }
QPushButton#chipClose:hover { color: #EF4444; }
QLabel#tokenLabel { color: #94A3B8; font-size: 11px; padding: 0 2px; }
QLineEdit#sidebarSearch {
    background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px;
    padding: 8px 10px; margin: 8px 12px 4px 12px; color: #1E293B; font-size: 13px;
}
QLineEdit#sidebarSearch:focus { border: 1px solid #3B82F6; }
#searchBar { background: #F8FAFC; border-bottom: 1px solid #E2E8F0; }
QLineEdit#searchInput {
    background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px;
    padding: 6px 10px; color: #1E293B; font-size: 13px;
}
QLineEdit#searchInput:focus { border: 1px solid #3B82F6; }
QPushButton#searchNavButton {
    background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px;
    padding: 6px 10px; font-size: 12px; color: #64748B;
}
QPushButton#searchNavButton:hover { background: #E2E8F0; color: #1E293B; }
QPushButton#exportButton {
    background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px;
    padding: 6px 10px; font-weight: 500; color: #64748B; font-size: 12px;
}
QPushButton#exportButton:hover { background: #E2E8F0; color: #1E293B; }
QDialog QLabel { color: #1E293B; }
QDialog QLineEdit {
    background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px;
    padding: 8px 10px; color: #1E293B;
}
QDialog QLineEdit:focus { border: 1px solid #3B82F6; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
