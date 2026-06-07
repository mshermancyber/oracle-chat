"""Oracle main window — sidebar + chat view + input."""
from __future__ import annotations

import html
import os
import re
import json as _json
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from pathlib import Path

from PySide6.QtCore import Qt, QMimeData, QSize, QUrl, Signal
from PySide6.QtGui import (
    QAction, QDesktopServices, QIcon, QImage, QKeySequence,
    QShortcut, QTextCursor, QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSplitter,
    QTextBrowser, QVBoxLayout, QWidget, QMenu,
)

from . import db
from . import attachments as att
from .api import StreamWorker
from .bridge_api import BridgeWorker, CustomGatewayWorker
from .claude_code_api import ClaudeCodeWorker, claude_binary_available, cleanup_relay_attachments
from .config import (
    MODELS, Settings, DATA_DIR, load as load_settings, save as save_settings,
    model_display_name, load_prompts, save_prompts, find_prompt,
    load_templates, save_templates, load_recent_files, add_recent_file,
    load_snippets, save_snippets, MODEL_PRICING, PERSONAS,
    load_macros, save_macros, load_filters, save_filters,
    load_memory, save_memory, add_memory,
    load_project, save_project, list_projects, delete_project,
    AUTH_API, AUTH_BRIDGE, AUTH_CLAUDE_CODE, AUTH_CUSTOM,
)
from .markdown_renderer import render as render_markdown, get_code_blocks, set_citation_sources

# Provider presets for Custom Gateway
_GATEWAY_PRESETS = {
    "Custom (localhost)": {"url": "http://localhost:11434", "key": "", "model": "deepseek-r1"},
    "Ollama": {"url": "http://localhost:11434", "key": "", "model": "llama3.1"},
    "OpenAI / ChatGPT": {"url": "https://api.openai.com", "key": "", "model": "gpt-4o"},
    "Anthropic": {"url": "https://api.anthropic.com", "key": "", "model": "claude-sonnet-4-6"},
    "Google Gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai", "key": "", "model": "gemini-2.5-flash"},
    "Grok (xAI)": {"url": "https://api.x.ai", "key": "", "model": "grok-3"},
    "DeepSeek": {"url": "https://api.deepseek.com", "key": "", "model": "deepseek-chat"},
    "Together AI": {"url": "https://api.together.xyz", "key": "", "model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"},
    "Groq": {"url": "https://api.groq.com/openai", "key": "", "model": "llama-3.3-70b-versatile"},
    "OpenRouter": {"url": "https://openrouter.ai/api", "key": "", "model": "anthropic/claude-sonnet-4"},
    "LM Studio": {"url": "http://localhost:1234", "key": "", "model": "local-model"},
}

_AT_FILE_RE = re.compile(r'@(/\S+)')
_MAX_FILE_INLINE_BYTES = 1_024_000  # 1 MB


# ─────────────────────────────────────────────────────────────────────────────
# First-run / settings dialog
# ─────────────────────────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    """Tabbed settings dialog with Auth, Model, Behavior, Display, and About tabs."""

    def __init__(self, settings: Settings, first_run: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Oracle — Settings" if not first_run else "Welcome to Oracle")
        self.setMinimumWidth(580)
        self.setMinimumHeight(500)
        self._settings = settings

        from PySide6.QtWidgets import QTabWidget, QCheckBox, QSpinBox
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        if first_run:
            intro = QLabel("Oracle is a native Linux chat client for Anthropic Claude.\n"
                           "Configure your authentication below to get started.")
            intro.setWordWrap(True)
            layout.addWidget(intro)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ── Auth tab ──
        auth_tab = QWidget()
        al = QVBoxLayout(auth_tab)
        al.addWidget(QLabel("Authentication mode:"))
        self.auth_picker = QComboBox()
        self.auth_picker.addItem("Anthropic API key (direct — recommended)", AUTH_API)
        cc_label = "Relay through Claude Code (experimental)"
        if not claude_binary_available(settings.claude_binary or "claude"):
            cc_label += " — `claude` not found"
        self.auth_picker.addItem(cc_label, AUTH_CLAUDE_CODE)
        self.auth_picker.addItem("Bridge (OpenAI-compatible gateway — text only)", AUTH_BRIDGE)
        self.auth_picker.addItem("Custom Gateway (Ollama, Grok, Gemini, ChatGPT, etc.)", AUTH_CUSTOM)
        idx = self.auth_picker.findData(settings.auth_mode or AUTH_API)
        if idx >= 0:
            self.auth_picker.setCurrentIndex(idx)
        self.auth_picker.currentIndexChanged.connect(self._on_auth_changed)
        al.addWidget(self.auth_picker)
        self.relay_warning = QLabel("⚠  Relay modes are experimental. See README for details.")
        self.relay_warning.setWordWrap(True)
        self.relay_warning.setStyleSheet(
            "background:#3F2A06;color:#FCD34D;border:1px solid #92400E;"
            "border-radius:6px;padding:8px 10px;font-size:12px;")
        al.addWidget(self.relay_warning)
        self.key_label = QLabel("Anthropic API key:")
        al.addWidget(self.key_label)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setText(settings.api_key or "")
        self.key_edit.setPlaceholderText("sk-ant-…")
        al.addWidget(self.key_edit)
        self.binary_label = QLabel("`claude` binary path:")
        al.addWidget(self.binary_label)
        self.binary_edit = QLineEdit()
        self.binary_edit.setText(settings.claude_binary or "claude")
        al.addWidget(self.binary_edit)
        self.bridge_label = QLabel("Bridge IP address:")
        al.addWidget(self.bridge_label)
        self.bridge_edit = QLineEdit()
        self.bridge_edit.setText(settings.bridge_ip or "127.0.0.1")
        al.addWidget(self.bridge_edit)
        self.bridge_key_label = QLabel("Bridge API key (if bridge uses --api-key):")
        al.addWidget(self.bridge_key_label)
        self.bridge_key_edit = QLineEdit()
        self.bridge_key_edit.setEchoMode(QLineEdit.Password)
        self.bridge_key_edit.setText(settings.bridge_api_key or "")
        self.bridge_key_edit.setPlaceholderText("Leave blank if bridge has no --api-key")
        al.addWidget(self.bridge_key_edit)
        al.addWidget(QLabel("SearXNG URL (for /web search):"))
        self.searxng_edit = QLineEdit()
        self.searxng_edit.setText(settings.searxng_url or "")
        self.searxng_edit.setPlaceholderText("http://localhost:8888")
        al.addWidget(self.searxng_edit)
        # Custom gateway fields
        self.custom_provider_label = QLabel("Gateway provider:")
        al.addWidget(self.custom_provider_label)
        self.custom_provider_picker = QComboBox()
        for name in _GATEWAY_PRESETS:
            self.custom_provider_picker.addItem(name)
        self.custom_provider_picker.currentTextChanged.connect(self._on_provider_changed)
        al.addWidget(self.custom_provider_picker)
        self.custom_url_label = QLabel("API base URL:")
        al.addWidget(self.custom_url_label)
        self.custom_url_edit = QLineEdit()
        self.custom_url_edit.setText(settings.custom_api_url or "http://localhost:11434")
        self.custom_url_edit.setPlaceholderText("http://localhost:11434")
        al.addWidget(self.custom_url_edit)
        self.custom_key_label = QLabel("API key (leave blank if not needed):")
        al.addWidget(self.custom_key_label)
        self.custom_key_edit = QLineEdit()
        self.custom_key_edit.setEchoMode(QLineEdit.Password)
        self.custom_key_edit.setText(settings.custom_api_key or "")
        al.addWidget(self.custom_key_edit)
        self.custom_model_label = QLabel("Model name:")
        al.addWidget(self.custom_model_label)
        self.custom_model_edit = QLineEdit()
        self.custom_model_edit.setText(settings.custom_model or "deepseek-r1")
        self.custom_model_edit.setPlaceholderText("deepseek-r1")
        al.addWidget(self.custom_model_edit)
        al.addStretch()
        self._refresh_auth_visibility()
        tabs.addTab(auth_tab, "Auth")

        # ── Model tab ──
        model_tab = QWidget()
        ml = QVBoxLayout(model_tab)
        ml.addWidget(QLabel("Default model:"))
        self.model_picker = QComboBox()
        for display, mid in MODELS.items():
            self.model_picker.addItem(display, mid)
        idx = self.model_picker.findData(settings.default_model)
        if idx >= 0:
            self.model_picker.setCurrentIndex(idx)
        ml.addWidget(self.model_picker)
        ml.addWidget(QLabel("Max tokens per response:"))
        self.max_tokens_edit = QLineEdit(str(settings.max_tokens))
        ml.addWidget(self.max_tokens_edit)
        ml.addWidget(QLabel("System prompt (sent with every conversation):"))
        self.system_edit = QPlainTextEdit()
        self.system_edit.setPlainText(settings.system_prompt or "")
        self.system_edit.setFixedHeight(80)
        ml.addWidget(self.system_edit)
        ml.addStretch()
        tabs.addTab(model_tab, "Model")

        # ── Behavior tab ──
        behav_tab = QWidget()
        bl = QVBoxLayout(behav_tab)
        self.auto_continue_cb = QCheckBox("Auto-continue when response is cut off")
        self.auto_continue_cb.setChecked(settings.auto_continue)
        bl.addWidget(self.auto_continue_cb)
        self.auto_retry_cb = QCheckBox("Auto-retry on rate limit (5s delay)")
        self.auto_retry_cb.setChecked(settings.auto_retry)
        bl.addWidget(self.auto_retry_cb)
        self.auto_title_cb = QCheckBox("Auto-title chats after first exchange")
        self.auto_title_cb.setChecked(settings.auto_title)
        bl.addWidget(self.auto_title_cb)
        self.auto_model_cb = QCheckBox("Auto-switch model by message complexity")
        self.auto_model_cb.setChecked(settings.auto_model)
        bl.addWidget(self.auto_model_cb)
        self.notify_cb = QCheckBox("Play notification sound when response completes")
        self.notify_cb.setChecked(settings.notify_sound)
        bl.addWidget(self.notify_cb)
        self.show_thinking_cb = QCheckBox("Show extended thinking blocks")
        self.show_thinking_cb.setChecked(settings.show_thinking)
        bl.addWidget(self.show_thinking_cb)
        bl.addStretch()
        tabs.addTab(behav_tab, "Behavior")

        # ── Display tab ──
        disp_tab = QWidget()
        dl = QVBoxLayout(disp_tab)
        self.compact_cb = QCheckBox("Compact mode (denser message layout)")
        self.compact_cb.setChecked(settings.compact_mode)
        dl.addWidget(self.compact_cb)
        self.typewriter_cb = QCheckBox("Typewriter scroll (center during streaming)")
        self.typewriter_cb.setChecked(settings.typewriter_mode)
        dl.addWidget(self.typewriter_cb)
        self.rawmd_cb = QCheckBox("Show raw markdown (no rendering)")
        self.rawmd_cb.setChecked(settings.show_raw_md)
        dl.addWidget(self.rawmd_cb)
        dl.addWidget(QLabel("Theme:"))
        self.theme_picker = QComboBox()
        self.theme_picker.addItems(["dark", "light"])
        self.theme_picker.setCurrentText(settings.theme or "dark")
        dl.addWidget(self.theme_picker)
        dl.addWidget(QLabel("Font size:"))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(10, 24)
        self.font_spin.setValue(settings.font_size)
        dl.addWidget(self.font_spin)
        dl.addWidget(QLabel("Sidebar sort:"))
        self.sort_picker = QComboBox()
        self.sort_picker.addItems(["recent", "alpha", "model"])
        self.sort_picker.setCurrentText(settings.sidebar_sort or "recent")
        dl.addWidget(self.sort_picker)
        dl.addStretch()
        tabs.addTab(disp_tab, "Display")

        # ── About tab ──
        about_tab = QWidget()
        abl = QVBoxLayout(about_tab)
        abl.setAlignment(Qt.AlignCenter)
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        src_dir = Path(__file__).resolve().parent.parent
        icon_path = src_dir / "assets" / "oracle.svg"
        if icon_path.exists():
            logo_label.setPixmap(QIcon(str(icon_path)).pixmap(QSize(80, 80)))
        abl.addWidget(logo_label)
        name_label = QLabel("Oracle")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-size:20px;font-weight:700;")
        abl.addWidget(name_label)
        ver_label = QLabel("v1.1.0 — Native Linux AI chat client")
        ver_label.setAlignment(Qt.AlignCenter)
        ver_label.setStyleSheet("color:#94A3B8;font-size:13px;")
        abl.addWidget(ver_label)
        link = QLabel('<a href="https://github.com/mshermancyber/oracle-chat" '
                      'style="color:#60A5FA;">github.com/mshermancyber/oracle-chat</a>')
        link.setAlignment(Qt.AlignCenter)
        link.setOpenExternalLinks(True)
        abl.addWidget(link)
        author = QLabel("github.com/mshermancyber/oracle-chat")
        author.setAlignment(Qt.AlignCenter)
        author.setStyleSheet("color:#64748B;font-size:12px;margin-top:8px;")
        abl.addWidget(author)
        desc = QLabel(
            "Multi-provider AI chat client with 130+ features.\n"
            "Connects to Claude, ChatGPT, Gemini, Grok, Ollama, DeepSeek, and more.\n\n"
            "Streaming, file uploads, code execution, voice I/O, web search,\n"
            "research agent, memory, projects, personas, and much more.\n\n"
            "Built with PySide6 (Qt6). MIT License."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#94A3B8;font-size:12px;margin-top:12px;")
        abl.addWidget(desc)
        abl.addStretch()
        tabs.addTab(about_tab, "About")

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_auth_changed(self) -> None:
        self._refresh_auth_visibility()

    def _on_provider_changed(self, name: str) -> None:
        preset = _GATEWAY_PRESETS.get(name, {})
        if preset:
            self.custom_url_edit.setText(preset.get("url", ""))
            self.custom_model_edit.setText(preset.get("model", ""))

    def _refresh_auth_visibility(self) -> None:
        mode = self.auth_picker.currentData()
        is_api = mode == AUTH_API
        is_cc = mode == AUTH_CLAUDE_CODE
        is_bridge = mode == AUTH_BRIDGE
        is_custom = mode == AUTH_CUSTOM
        self.key_label.setVisible(is_api)
        self.key_edit.setVisible(is_api)
        self.binary_label.setVisible(is_cc)
        self.binary_edit.setVisible(is_cc)
        self.bridge_label.setVisible(is_bridge)
        self.bridge_edit.setVisible(is_bridge)
        self.bridge_key_label.setVisible(is_bridge)
        self.bridge_key_edit.setVisible(is_bridge)
        self.relay_warning.setVisible(is_cc or is_bridge)
        for w in (self.custom_provider_label, self.custom_provider_picker,
                  self.custom_url_label, self.custom_url_edit,
                  self.custom_key_label, self.custom_key_edit,
                  self.custom_model_label, self.custom_model_edit):
            w.setVisible(is_custom)

    def result_settings(self) -> Settings:
        try:
            max_tokens = max(1, min(64_000, int(self.max_tokens_edit.text().strip() or "4096")))
        except ValueError:
            max_tokens = 4096
        s = Settings(
            api_key=self.key_edit.text().strip() or None,
            default_model=self.model_picker.currentData() or self._settings.default_model,
            system_prompt=self.system_edit.toPlainText().strip(),
            max_tokens=max_tokens,
            auth_mode=self.auth_picker.currentData() or AUTH_API,
            claude_binary=self.binary_edit.text().strip() or "claude",
            bridge_ip=self.bridge_edit.text().strip() or "127.0.0.1",
            bridge_api_key=self.bridge_key_edit.text().strip(),
        )
        s.auto_continue = self.auto_continue_cb.isChecked()
        s.auto_retry = self.auto_retry_cb.isChecked()
        s.auto_title = self.auto_title_cb.isChecked()
        s.auto_model = self.auto_model_cb.isChecked()
        s.notify_sound = self.notify_cb.isChecked()
        s.show_thinking = self.show_thinking_cb.isChecked()
        s.compact_mode = self.compact_cb.isChecked()
        s.typewriter_mode = self.typewriter_cb.isChecked()
        s.show_raw_md = self.rawmd_cb.isChecked()
        s.theme = self.theme_picker.currentText()
        s.font_size = self.font_spin.value()
        s.sidebar_sort = self.sort_picker.currentText()
        s.response_length = self._settings.response_length
        s.response_format = self._settings.response_format
        s.persona = self._settings.persona
        s.focus_mode = self._settings.focus_mode
        s.favorite_models = self._settings.favorite_models
        s.thinking_effort = self._settings.thinking_effort
        s.active_project = self._settings.active_project
        s.searxng_url = self.searxng_edit.text().strip()
        s.custom_api_url = self.custom_url_edit.text().strip()
        s.custom_api_key = self.custom_key_edit.text().strip()
        s.custom_model = self.custom_model_edit.text().strip()
        return s


# ─────────────────────────────────────────────────────────────────────────────
# Custom input widget — Enter to send, @file mentions, drag-and-drop
# ─────────────────────────────────────────────────────────────────────────────
_ATTACHMENT_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.docx'}

class ChatInput(QPlainTextEdit):
    """Input box: Enter sends, Shift+Enter inserts newline, @ opens file picker."""

    send_requested = Signal()
    at_mention_requested = Signal()
    files_dropped = Signal(list, str)  # (paths, "text"|"attachment")
    image_pasted = Signal(object)      # QImage from clipboard
    history_prev = Signal()
    history_next = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def insertFromMimeData(self, source):
        if source.hasImage():
            image = QImage(source.imageData())
            if not image.isNull():
                self.image_pasted.emit(image)
                return
        if source.hasText():
            text = source.text()
            if self._looks_like_code(text):
                lang = self._detect_lang(text)
                cursor = self.textCursor()
                cursor.insertText(f"```{lang}\n{text}\n```")
                self.setTextCursor(cursor)
                return
        super().insertFromMimeData(source)

    @staticmethod
    def _looks_like_code(text: str) -> bool:
        lines = text.strip().split("\n")
        if len(lines) < 4:
            return False
        indicators = [
            "def ", "class ", "import ", "from ", "function ", "const ", "let ", "var ",
            "if (", "for (", "while (", "Traceback (", "  File \"",
            "};", "=>", "#!/",
        ]
        matches = sum(1 for ind in indicators if ind in text)
        return matches >= 2 or text.strip().startswith("{")

    _SLASH_COMMANDS = [
        "/archive", "/archived", "/automodel", "/autotitle", "/bookmarks", "/budget",
        "/chatprompt", "/clear", "/compact", "/compare", "/context", "/cost",
        "/delete", "/ephemeral", "/export", "/favorite", "/focus", "/format",
        "/grep", "/heatmap", "/help", "/history", "/import", "/length", "/link",
        "/merge", "/model", "/notes", "/notify", "/persona", "/prompt",
        "/replace", "/restore", "/checkpoint", "/schedule", "/search", "/snippet",
        "/split", "/stats", "/summary", "/system", "/tag", "/tags",
        "/template", "/theme", "/timeline", "/unarchive", "/unfavorite",
        "/untag", "/wc", "/workspace",
    ]

    def _complete_slash(self) -> None:
        text = self.toPlainText().strip()
        matches = [c for c in self._SLASH_COMMANDS if c.startswith(text)]
        if len(matches) == 1:
            self.setPlainText(matches[0] + " ")
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)
        elif matches:
            prefix = os.path.commonprefix(matches)
            if len(prefix) > len(text):
                self.setPlainText(prefix)
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.setTextCursor(cursor)

    @staticmethod
    def _detect_lang(text: str) -> str:
        if "Traceback (" in text or "  File \"" in text:
            return "python"
        if "def " in text or "import " in text:
            return "python"
        if "function " in text or "const " in text or "=>" in text:
            return "javascript"
        if text.strip().startswith("{") and text.strip().endswith("}"):
            return "json"
        if "#!/bin/" in text:
            return "bash"
        return ""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_requested.emit()
        elif event.text() == "@":
            self.at_mention_requested.emit()
        elif event.key() == Qt.Key_Tab and self.toPlainText().startswith("/"):
            self._complete_slash()
        elif event.key() == Qt.Key_Up and not self.toPlainText().strip():
            self.history_prev.emit()
        elif event.key() == Qt.Key_Down and not self.toPlainText().strip():
            self.history_next.emit()
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return
        text_paths, attach_paths = [], []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            ext = Path(path).suffix.lower()
            if ext in _ATTACHMENT_EXTS:
                attach_paths.append(path)
            else:
                text_paths.append(path)
        if text_paths:
            self.files_dropped.emit(text_paths, "text")
        if attach_paths:
            self.files_dropped.emit(attach_paths, "attachment")
        event.acceptProposedAction()


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    """Single-window Oracle app: sidebar chat list + main chat view + input."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Oracle")
        self.resize(1180, 820)

        self.settings: Settings = load_settings()
        db.init()
        cleanup_relay_attachments()

        self._current_chat_id: Optional[int] = None
        self._streaming_chat_id: Optional[int] = None
        self._streaming_worker: Optional[StreamWorker] = None
        self._stream_buffer: List[str] = []
        self._pending_attachments: List[att.AttachmentSpec] = []
        self._stream_start_time: Optional[float] = None
        self._compact: bool = self.settings.compact_mode
        self._quick_replies: List[str] = []
        self._show_quick_replies: bool = False
        self._last_regen_old_text: Optional[str] = None
        self._session_start: float = time.monotonic()
        self._undo_stack: List[tuple] = []  # (chat_id, action, data)
        self._input_history: List[str] = []
        self._input_history_idx: int = -1
        self._recording: bool = False
        self._record_proc: Optional[subprocess.Popen] = None
        self._record_file: Optional[str] = None

        self._build_ui()
        self._wire_shortcuts()
        self._refresh_chat_list()
        self._update_custom_model_in_picker()

        if not self.settings.configured:
            self._first_run_setup()

    # ── UI construction ───────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self._splitter = QSplitter(Qt.Horizontal, self)
        self._splitter.setHandleWidth(1)

        self._sidebar_widget = self._build_sidebar()
        self._splitter.addWidget(self._sidebar_widget)
        self._splitter.addWidget(self._build_chat_pane())
        self._splitter.setSizes([280, 900])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self._splitter)
        if self.settings.focus_mode:
            self._sidebar_widget.setVisible(False)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(420)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # "+ New chat" button
        new_btn = QPushButton("＋  New chat")
        new_btn.setObjectName("newChatButton")
        new_btn.clicked.connect(self._on_new_chat)
        layout.addWidget(new_btn)

        self.chat_count_label = QLabel("0 chats")
        self.chat_count_label.setObjectName("tokenLabel")
        self.chat_count_label.setContentsMargins(12, 4, 12, 4)
        layout.addWidget(self.chat_count_label)

        # Sidebar search
        self.sidebar_search = QLineEdit()
        self.sidebar_search.setObjectName("sidebarSearch")
        self.sidebar_search.setPlaceholderText("Search chats...")
        self.sidebar_search.setClearButtonEnabled(True)
        self.sidebar_search.textChanged.connect(self._on_sidebar_search_changed)
        layout.addWidget(self.sidebar_search)

        # Chat list
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("chatList")
        self.chat_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._show_chat_context_menu)
        self.chat_list.currentItemChanged.connect(self._on_chat_selected)
        layout.addWidget(self.chat_list, 1)

        # Footer — settings
        settings_btn = QPushButton("⚙  Settings")
        settings_btn.setObjectName("newChatButton")  # reuse styling
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        return sidebar

    def _build_chat_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar — chat title + model picker
        top = QWidget()
        top.setObjectName("topBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 8, 16, 8)
        self.chat_title_label = QLabel("Start a new chat")
        self.chat_title_label.setObjectName("chatTitle")
        top_layout.addWidget(self.chat_title_label, 1)

        self.model_picker = QComboBox()
        self.model_picker.setObjectName("modelPicker")
        for display, mid in MODELS.items():
            self.model_picker.addItem(display, mid)
        idx = self.model_picker.findData(self.settings.default_model)
        if idx >= 0:
            self.model_picker.setCurrentIndex(idx)
        self.model_picker.currentIndexChanged.connect(self._on_model_picker_changed)
        top_layout.addWidget(self.model_picker)

        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("exportButton")
        self.export_btn.setToolTip("Export conversation as Markdown")
        self.export_btn.clicked.connect(self._on_export)
        top_layout.addWidget(self.export_btn)

        self.cmds_btn = QPushButton("Commands")
        self.cmds_btn.setObjectName("exportButton")
        self.cmds_btn.setToolTip("Show all available commands")
        self.cmds_btn.clicked.connect(self._show_commands_menu)
        top_layout.addWidget(self.cmds_btn)

        layout.addWidget(top)

        # In-conversation search bar (hidden by default)
        self.search_bar = QWidget()
        self.search_bar.setObjectName("searchBar")
        self.search_bar.setVisible(False)
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(16, 6, 16, 6)
        search_layout.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Find in conversation...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._on_search_next)
        search_layout.addWidget(self.search_input, 1)
        prev_btn = QPushButton("Prev")
        prev_btn.setObjectName("searchNavButton")
        prev_btn.clicked.connect(self._on_search_prev)
        search_layout.addWidget(prev_btn)
        next_btn = QPushButton("Next")
        next_btn.setObjectName("searchNavButton")
        next_btn.clicked.connect(self._on_search_next)
        search_layout.addWidget(next_btn)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("searchNavButton")
        close_btn.clicked.connect(self._toggle_search_bar)
        search_layout.addWidget(close_btn)
        layout.addWidget(self.search_bar)

        # Chat views — main + optional split
        chat_splitter = QSplitter(Qt.Horizontal)
        chat_splitter.setHandleWidth(1)
        self.chat_view = QTextBrowser()
        self.chat_view.setObjectName("chatView")
        self.chat_view.setOpenExternalLinks(False)
        self.chat_view.anchorClicked.connect(self._on_link_clicked)
        chat_splitter.addWidget(self.chat_view)
        self.split_view = QTextBrowser()
        self.split_view.setObjectName("chatView")
        self.split_view.setOpenExternalLinks(False)
        self.split_view.setVisible(False)
        chat_splitter.addWidget(self.split_view)
        layout.addWidget(chat_splitter, 1)

        # Input area
        input_area = QWidget()
        input_area.setObjectName("inputArea")
        input_layout = QVBoxLayout(input_area)
        input_layout.setContentsMargins(16, 12, 16, 16)
        input_layout.setSpacing(8)

        # Pending-attachment chip row (hidden when empty)
        self.attach_row = QWidget()
        self.attach_row.setObjectName("attachRow")
        self.attach_row_layout = QHBoxLayout(self.attach_row)
        self.attach_row_layout.setContentsMargins(0, 0, 0, 0)
        self.attach_row_layout.setSpacing(6)
        self.attach_row.setVisible(False)
        input_layout.addWidget(self.attach_row)

        self.input_box = ChatInput()
        self.input_box.setObjectName("inputBox")
        self.input_box.setPlaceholderText("Enter to send, Shift+Enter for new line. Type @ to attach a file.")
        self.input_box.setMinimumHeight(72)
        self.input_box.setMaximumHeight(220)
        self.input_box.send_requested.connect(self._on_send)
        self.input_box.at_mention_requested.connect(self._on_at_mention)
        self.input_box.files_dropped.connect(self._on_files_dropped)
        self.input_box.image_pasted.connect(self._on_image_pasted)
        self.input_box.history_prev.connect(self._on_history_prev)
        self.input_box.history_next.connect(self._on_history_next)
        self.input_box.textChanged.connect(self._update_token_count)
        input_layout.addWidget(self.input_box)

        self.token_label = QLabel("~0 tokens")
        self.token_label.setObjectName("tokenLabel")
        input_layout.addWidget(self.token_label)

        row = QHBoxLayout()

        self.attach_btn = QPushButton("📎  Attach")
        self.attach_btn.setObjectName("attachButton")
        self.attach_btn.setToolTip("Attach images or .docx / .pdf documents")
        self.attach_btn.clicked.connect(self._on_attach)
        row.addWidget(self.attach_btn)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setObjectName("attachButton")
        self.mic_btn.setToolTip("Voice input (requires arecord + whisper)")
        self.mic_btn.clicked.connect(self._on_mic_toggle)
        row.addWidget(self.mic_btn)

        self.web_btn = QPushButton("🌐 Web")
        self.web_btn.setObjectName("attachButton")
        self.web_btn.setToolTip("Search the web via SearXNG")
        self.web_btn.clicked.connect(self._on_web_search_btn)
        row.addWidget(self.web_btn)

        row.addStretch(1)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._on_stop)
        row.addWidget(self.stop_btn)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("sendButton")
        self.send_btn.clicked.connect(self._on_send)
        row.addWidget(self.send_btn)
        input_layout.addLayout(row)

        layout.addWidget(input_area)
        return pane

    # ── Attachments ───────────────────────────────────────────────────────
    def _on_attach(self) -> None:
        """Open a file dialog to pick one or more attachments."""
        filt = (
            "Supported (*.png *.jpg *.jpeg *.gif *.webp *.pdf *.docx);;"
            "Images (*.png *.jpg *.jpeg *.gif *.webp);;"
            "Documents (*.pdf *.docx);;"
            "All files (*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach files", "", filt)
        if not paths:
            return
        added = 0
        for p in paths:
            try:
                spec = att.classify(Path(p))
            except att.UnsupportedAttachment as e:
                QMessageBox.warning(self, "Unsupported file", str(e))
                continue
            self._pending_attachments.append(spec)
            added += 1
        if added:
            self._refresh_attach_row()

    def _refresh_attach_row(self) -> None:
        """Rebuild the chip row from self._pending_attachments."""
        # Clear existing chips
        while self.attach_row_layout.count():
            it = self.attach_row_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        if not self._pending_attachments:
            self.attach_row.setVisible(False)
            return
        for idx, spec in enumerate(self._pending_attachments):
            chip = self._make_chip(spec, idx)
            self.attach_row_layout.addWidget(chip)
        self.attach_row_layout.addStretch(1)
        self.attach_row.setVisible(True)

    def _make_chip(self, spec: att.AttachmentSpec, idx: int) -> QWidget:
        chip = QFrame()
        chip.setObjectName("attachChip")
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(8, 4, 4, 4)
        lay.setSpacing(6)
        icon = {"image": "🖼", "pdf": "📄", "docx": "📝"}.get(spec.kind, "📎")
        lbl = QLabel(f"{icon}  {spec.display_name}")
        lbl.setToolTip(str(spec.path))
        lay.addWidget(lbl)
        close = QPushButton("✕")
        close.setObjectName("chipClose")
        close.setFixedSize(QSize(20, 20))
        close.setToolTip("Remove this attachment")
        close.clicked.connect(lambda _=False, i=idx: self._remove_pending(i))
        lay.addWidget(close)
        return chip

    def _remove_pending(self, idx: int) -> None:
        if 0 <= idx < len(self._pending_attachments):
            self._pending_attachments.pop(idx)
        self._refresh_attach_row()

    def _wire_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._on_new_chat)
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(self._open_settings)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._toggle_search_bar)
        QShortcut(QKeySequence("Alt+Up"), self).activated.connect(self._select_prev_chat)
        QShortcut(QKeySequence("Alt+Down"), self).activated.connect(self._select_next_chat)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self).activated.connect(self._paste_as_code)
        QShortcut(QKeySequence("Alt+J"), self).activated.connect(self._nav_next_message)
        QShortcut(QKeySequence("Alt+K"), self).activated.connect(self._nav_prev_message)
        QShortcut(QKeySequence("Ctrl+M"), self).activated.connect(self._quick_model_switch)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._undo_last)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self._zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self._zoom_out)
        QShortcut(QKeySequence("Ctrl+/"), self).activated.connect(self._show_shortcut_overlay)
        for i in range(1, 10):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda idx=i - 1: self._select_chat_by_index(idx))

    def _select_prev_chat(self) -> None:
        row = max(0, self.chat_list.currentRow() - 1)
        self.chat_list.setCurrentRow(row)

    def _select_next_chat(self) -> None:
        row = min(self.chat_list.count() - 1, self.chat_list.currentRow() + 1)
        self.chat_list.setCurrentRow(row)

    def _select_chat_by_index(self, idx: int) -> None:
        if 0 <= idx < self.chat_list.count():
            self.chat_list.setCurrentRow(idx)

    def _paste_as_code(self) -> None:
        text = QApplication.clipboard().text()
        if not text:
            return
        cursor = self.input_box.textCursor()
        cursor.insertText(f"```\n{text}\n```")
        self.input_box.setTextCursor(cursor)

    def _zoom_in(self) -> None:
        self.settings.font_size = min(24, self.settings.font_size + 1)
        save_settings(self.settings)
        self._apply_font_size()

    def _zoom_out(self) -> None:
        self.settings.font_size = max(10, self.settings.font_size - 1)
        save_settings(self.settings)
        self._apply_font_size()

    def _apply_font_size(self) -> None:
        fs = self.settings.font_size
        self.chat_view.setStyleSheet(f"font-size:{fs}px;")
        self.input_box.setStyleSheet(f"font-size:{fs}px;")

    def _show_shortcut_overlay(self) -> None:
        shortcuts = (
            "Keyboard Shortcuts:\n\n"
            "Enter — Send message\n"
            "Shift+Enter — New line\n"
            "@ — Attach file reference\n"
            "Tab — Autocomplete slash command\n"
            "Up/Down — Input history (when empty)\n"
            "Ctrl+N — New chat\n"
            "Ctrl+F — Search in conversation\n"
            "Ctrl+M — Quick model switch\n"
            "Ctrl+Z — Undo last action\n"
            "Ctrl+V — Paste (images auto-detected)\n"
            "Ctrl+Shift+V — Paste as code block\n"
            "Ctrl++/- — Zoom in/out\n"
            "Ctrl+, — Settings\n"
            "Ctrl+/ — This overlay\n"
            "Ctrl+1-9 — Jump to chat by position\n"
            "Alt+Up/Down — Navigate chats\n"
            "Alt+J/K — Navigate messages"
        )
        QMessageBox.information(self, "Oracle — Shortcuts", shortcuts)

    def _nav_next_message(self) -> None:
        self.chat_view.find("Claude", QTextDocument.FindFlag(0))
        if not self.chat_view.find("You", QTextDocument.FindFlag(0)):
            self.chat_view.find("Claude", QTextDocument.FindFlag(0))

    def _nav_prev_message(self) -> None:
        self.chat_view.find("You", QTextDocument.FindFlag.FindBackward)
        if not self.chat_view.find("Claude", QTextDocument.FindFlag.FindBackward):
            self.chat_view.find("You", QTextDocument.FindFlag.FindBackward)

    # ── First-run / settings ──────────────────────────────────────────────
    def _first_run_setup(self) -> None:
        dlg = SettingsDialog(self.settings, first_run=True, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.result_settings()
            save_settings(self.settings)
            self._sync_model_picker_to_settings()
        if not self.settings.configured:
            QMessageBox.warning(self, "Oracle",
                "No API key was provided. Open Settings (Ctrl+,) to add one before sending messages.")

    def _open_settings(self) -> None:
        old_auth = self.settings.auth_mode
        old_custom_model = self.settings.custom_model
        dlg = SettingsDialog(self.settings, first_run=False, parent=self)
        if dlg.exec() == QDialog.Accepted:
            old_theme = self.settings.theme
            self.settings = dlg.result_settings()
            save_settings(self.settings)
            # Restart if auth mode or custom model changed for a clean state
            auth_changed = (self.settings.auth_mode != old_auth or
                            (self.settings.auth_mode == AUTH_CUSTOM and
                             self.settings.custom_model != old_custom_model))
            if auth_changed:
                self._restart_app()
                return
            self._sync_model_picker_to_settings()
            self._update_custom_model_in_picker()
            self._compact = self.settings.compact_mode
            self._apply_font_size()
            if self.settings.theme != old_theme:
                from .styles import STYLESHEET, STYLESHEET_LIGHT
                QApplication.instance().setStyleSheet(
                    STYLESHEET_LIGHT if self.settings.theme == "light" else STYLESHEET)
            if self._current_chat_id:
                self._render_messages(db.get_messages(self._current_chat_id))
            self._refresh_chat_list()

    def _restart_app(self) -> None:
        """Save state and restart the application."""
        if self._current_chat_id is not None:
            db.set_draft(self._current_chat_id, self.input_box.toPlainText())
        db.delete_ephemeral_chats()
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._streaming_worker.cancel()
            self._streaming_worker.wait(2000)
        exe = sys.executable
        if not exe or not os.path.isfile(exe):
            QMessageBox.warning(self, "Restart", "Cannot determine Python executable. Please restart manually.")
            return
        args = [exe] + sys.argv
        app = QApplication.instance()
        app.quit()
        app.processEvents()
        try:
            os.execv(exe, args)
        except OSError:
            pass

    def _update_custom_model_in_picker(self) -> None:
        if self.settings.auth_mode == AUTH_CUSTOM and self.settings.custom_model:
            mid = self.settings.custom_model
            # Remove stale [Custom] entries
            for i in range(self.model_picker.count() - 1, -1, -1):
                if self.model_picker.itemText(i).startswith("[Custom]"):
                    self.model_picker.removeItem(i)
            self.model_picker.addItem(f"[Custom] {mid}", mid)
            idx = self.model_picker.findData(mid)
            if idx >= 0:
                self.model_picker.blockSignals(True)
                self.model_picker.setCurrentIndex(idx)
                self.model_picker.blockSignals(False)

    def _sync_model_picker_to_settings(self) -> None:
        idx = self.model_picker.findData(self.settings.default_model)
        if idx >= 0:
            self.model_picker.blockSignals(True)
            self.model_picker.setCurrentIndex(idx)
            self.model_picker.blockSignals(False)

    # ── Chat list ─────────────────────────────────────────────────────────
    def _refresh_chat_list(self) -> None:
        self.chat_list.clear()
        chats = db.list_chats()
        msg_counts = db.message_counts_bulk()
        sort = self.settings.sidebar_sort
        if sort == "alpha":
            chats.sort(key=lambda c: (not c.pinned, c.title.lower()))
        elif sort == "model":
            chats.sort(key=lambda c: (not c.pinned, c.model, c.title.lower()))
        for c in chats:
            color_dot = {"#EF4444": "🔴", "#FBBF24": "🟡", "#22C55E": "🟢",
                         "#3B82F6": "🔵", "#A855F7": "🟣"}.get(c.color, "")
            prefix = "📌 " if c.pinned else ""
            mc = msg_counts.get(c.id, 0)
            label = f"{prefix}{color_dot}{c.title}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, c.id)
            tip = f"{c.title}\nModel: {model_display_name(c.model)}\n{mc} messages\nUpdated: {c.updated_at}"
            if c.tags:
                tip += f"\nTags: {c.tags}"
            item.setToolTip(tip)
            self.chat_list.addItem(item)
        self.chat_count_label.setText(f"{len(chats)} chats")
        if self.chat_list.count() and self._current_chat_id is None:
            self.chat_list.setCurrentRow(0)
        self._on_sidebar_search_changed(self.sidebar_search.text())

    def _on_chat_selected(self, current: QListWidgetItem, _previous) -> None:
        # Save draft from previous chat
        if self._current_chat_id is not None:
            db.set_draft(self._current_chat_id, self.input_box.toPlainText())
        self._input_history = []
        self._input_history_idx = -1
        if not current:
            self._current_chat_id = None
            self._render_messages([])
            self.chat_title_label.setText("Start a new chat")
            self.input_box.clear()
            return
        chat_id = current.data(Qt.UserRole)
        self._current_chat_id = chat_id
        chat_title = current.text().removeprefix("📌 ").lstrip("🔴🟡🟢🔵🟣 ")
        self.chat_title_label.setText(chat_title)
        self.setWindowTitle(f"Oracle — {chat_title}")
        chat = db.get_chat(chat_id)
        if chat:
            idx = self.model_picker.findData(chat.model)
            if idx >= 0:
                self.model_picker.blockSignals(True)
                self.model_picker.setCurrentIndex(idx)
                self.model_picker.blockSignals(False)
        self._render_messages(db.get_messages(chat_id))
        # Scroll to first unread
        unread_id = db.get_first_unread_id(chat_id)
        if unread_id:
            self.chat_view.scrollToAnchor(f"msg_{unread_id}")
        db.mark_messages_read(chat_id)
        # Restore draft
        chat = db.get_chat(chat_id)
        if chat and chat.draft:
            self.input_box.setPlainText(chat.draft)
            cursor = self.input_box.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.input_box.setTextCursor(cursor)
        else:
            self.input_box.clear()

    def _on_new_chat(self) -> None:
        title = "New chat"
        model = self.model_picker.currentData() or self.settings.default_model
        c = db.create_chat(title=title, model=model)
        self._current_chat_id = c.id
        self._refresh_chat_list()
        # Select the new chat we just created
        for i in range(self.chat_list.count()):
            it = self.chat_list.item(i)
            if it.data(Qt.UserRole) == c.id:
                self.chat_list.setCurrentItem(it)
                break
        self.input_box.setFocus()

    def _show_chat_context_menu(self, pos) -> None:
        item = self.chat_list.itemAt(pos)
        if not item:
            return
        chat_id = item.data(Qt.UserRole)
        chat = db.get_chat(chat_id)
        menu = QMenu(self.chat_list)
        pin_act = menu.addAction("Unpin" if (chat and chat.pinned) else "Pin")
        dup_act = menu.addAction("Duplicate")
        rename_act = menu.addAction("Rename")
        archive_act = menu.addAction("Archive")
        delete_act = menu.addAction("Delete")
        chosen = menu.exec(self.chat_list.viewport().mapToGlobal(pos))
        if chosen == pin_act:
            db.toggle_pin(chat_id)
            self._refresh_chat_list()
        elif chosen == dup_act:
            new_chat = db.duplicate_chat(chat_id)
            if new_chat:
                self._current_chat_id = new_chat.id
                self._refresh_chat_list()
                for i in range(self.chat_list.count()):
                    it = self.chat_list.item(i)
                    if it.data(Qt.UserRole) == new_chat.id:
                        self.chat_list.setCurrentItem(it)
                        break
        elif chosen == archive_act:
            db.set_archived(chat_id, 1)
            if self._current_chat_id == chat_id:
                self._current_chat_id = None
            self._refresh_chat_list()
        elif chosen == rename_act:
            self._rename_chat(chat_id, item.text().removeprefix("📌 ").lstrip("🔴🟡🟢🔵🟣 "))
        elif chosen == delete_act:
            self._delete_chat(chat_id)

    def _rename_chat(self, chat_id: int, current_title: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        new_title, ok = QInputDialog.getText(self, "Rename chat",
                                              "New title:", text=current_title)
        if ok and new_title.strip():
            db.rename_chat(chat_id, new_title.strip())
            self._refresh_chat_list()

    def _delete_chat(self, chat_id: int) -> None:
        if QMessageBox.question(self, "Delete chat",
                                 "Delete this chat? This cannot be undone.",
                                 QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_chat(chat_id)
        if self._current_chat_id == chat_id:
            self._current_chat_id = None
        self._refresh_chat_list()

    def _on_model_picker_changed(self) -> None:
        """If the user is on a saved chat, update its stored model."""
        if self._current_chat_id is None:
            return
        # Re-record chat model — we update via a fresh row insert is unnecessary;
        # the model column on `chats` is informational only. We just keep using
        # the picker for new turns. (Could persist via a dedicated UPDATE later.)

    # ── Message rendering ────────────────────────────────────────────────
    _STARTER_PROMPTS = [
        "Explain this code to me",
        "Help me debug an error",
        "Write a function that...",
        "What's the difference between...",
    ]

    def _render_messages(self, messages: List[db.Message]) -> None:
        if not getattr(self, '_citation_sources', None):
            set_citation_sources([])
        html_parts = ['<div style="max-width:780px;margin:0 auto;">']
        if not messages:
            html_parts.append(
                '<div style="text-align:center;padding:60px 20px;color:#64748B;">'
                '<div style="font-size:28px;font-weight:700;color:#60A5FA;margin-bottom:8px;">Oracle</div>'
                '<div style="font-size:13px;margin-bottom:24px;">Native Linux chat client for Claude</div>'
                '<div style="font-size:12px;color:#475569;">Try asking:</div>'
            )
            for i, p in enumerate(self._STARTER_PROMPTS):
                html_parts.append(
                    f'<div style="margin:6px auto;max-width:300px;">'
                    f'<a href="oracle://starter/{i}" style="color:#60A5FA;text-decoration:none;'
                    f'font-size:13px;">{html.escape(p)}</a></div>'
                )
            html_parts.append('</div>')
            html_parts.append("</div>")
            self.chat_view.setHtml("".join(html_parts))
            return
        self._all_code_blocks: List[str] = []
        code_block_offset = 0
        # Pinned messages section
        pinned = [m for m in messages if m.pinned_in_chat]
        if pinned:
            html_parts.append(
                '<div style="background:#1A1A2E;border:1px solid #2A3A5A;border-radius:8px;'
                'padding:8px 12px;margin:8px 0 14px 0;">'
                '<div style="font-size:10px;color:#FBBF24;margin-bottom:6px;font-weight:600;">PINNED</div>'
            )
            for m in pinned:
                role_label = "You" if m.role == "user" else "Claude"
                preview = html.escape((m.content or "")[:120]).replace("\n", " ")
                html_parts.append(
                    f'<div style="font-size:12px;color:#CBD5E1;margin:2px 0;">'
                    f'<b>{role_label}:</b> {preview}{"..." if len(m.content or "") > 120 else ""}</div>'
                )
            html_parts.append('</div>')
        for m in messages:
            html_parts.append(f'<a name="msg_{m.id}"></a>')
            html_parts.append(
                self._render_message_html(
                    m.role, m.content, m.attachments,
                    code_block_offset=code_block_offset,
                    message_id=m.id, created_at=m.created_at,
                    bookmarked=m.bookmarked, compact=self._compact,
                    reaction=m.reaction, pinned_in_chat=m.pinned_in_chat,
                    collapsed=m.collapsed, annotation=m.annotation,
                    highlight=m.highlight, response_time=m.response_time,
                    show_raw=self.settings.show_raw_md, stop_reason=m.stop_reason,
                )
            )
            if m.role == "assistant":
                new_blocks = get_code_blocks()
                self._all_code_blocks.extend(new_blocks)
                code_block_offset += len(new_blocks)
        if self._show_quick_replies and messages:
            html_parts.append(self._render_quick_replies_html())
            self._show_quick_replies = False
        html_parts.append("</div>")
        self.chat_view.setHtml("".join(html_parts))
        self._scroll_to_bottom()

    @staticmethod
    def _render_message_html(role: str, content: str,
                             attachments: Optional[List[db.Attachment]] = None,
                             code_block_offset: int = 0,
                             message_id: Optional[int] = None,
                             created_at: str = "",
                             bookmarked: int = 0,
                             compact: bool = False,
                             reaction: str = "",
                             pinned_in_chat: int = 0,
                             collapsed: int = 0,
                             annotation: str = "",
                             highlight: str = "",
                             response_time: float = 0.0,
                             show_raw: bool = False,
                             stop_reason: str = "") -> str:
        attachments = attachments or []
        ts = ""
        if created_at and len(created_at) >= 16:
            ts = f'<span style="color:#475569;font-size:10px;font-weight:400;margin-left:8px;">{created_at[11:16]}</span>'

        margin = "6px" if compact else "14px"
        pad = "8px 10px" if compact else "12px 14px"
        link_style = 'style="color:#64748B;font-size:11px;text-decoration:none;"'
        bm_style = 'style="color:#FBBF24;font-size:11px;text-decoration:none;"' if bookmarked else link_style
        bm_label = "Bookmarked" if bookmarked else "Bookmark"

        if role == "user":
            safe = html.escape(content or "").replace("\n", "<br/>")
            safe = _AT_FILE_RE.sub(
                r'<span style="color:#60A5FA;font-weight:500;">@\1</span>', safe
            )
            atts_html = ""
            if attachments:
                parts = []
                for a in attachments:
                    if a.kind == "image" and Path(a.stored_path).exists():
                        url = QUrl.fromLocalFile(a.stored_path).toString()
                        parts.append(
                            f'<img src="{url}" alt="{html.escape(a.original_name)}" '
                            f'style="max-width:480px;max-height:320px;'
                            f'border:1px solid #1E2A45;border-radius:8px;margin:4px 6px 0 0;"/>'
                        )
                    else:
                        icon = {"pdf": "📄", "docx": "📝"}.get(a.kind, "📎")
                        parts.append(
                            f'<span style="display:inline-block;background:#0F1A35;'
                            f'border:1px solid #1E2A45;border-radius:6px;padding:4px 8px;'
                            f'margin:4px 6px 0 0;color:#CBD5E1;font-size:12px;">'
                            f'{icon}&nbsp;{html.escape(a.original_name)}</span>'
                        )
                atts_html = '<div style="margin-top:8px;">' + "".join(parts) + '</div>'
            body = safe if safe else ('<span style="color:#94A3B8;font-style:italic;">'
                                       '(attachment only)</span>' if attachments else "")
            pin_label = "Unpin" if pinned_in_chat else "Pin"
            pin_style = 'style="color:#FBBF24;font-size:11px;text-decoration:none;"' if pinned_in_chat else link_style
            actions = ""
            if message_id is not None:
                actions = (
                    f'<div style="margin-top:4px;text-align:right;">'
                    f'<a href="oracle://copymsg/{message_id}" {link_style}>Copy</a>'
                    f'&nbsp;&nbsp;<a href="oracle://pinmsg/{message_id}" {pin_style}>{pin_label}</a>'
                    f'&nbsp;&nbsp;<a href="oracle://reply/{message_id}" {link_style}>Reply</a>'
                    f'&nbsp;&nbsp;<a href="oracle://bookmark/{message_id}" {bm_style}>{bm_label}</a>'
                    f'&nbsp;&nbsp;<a href="oracle://edit/{message_id}" {link_style}>Edit</a>'
                    f'&nbsp;&nbsp;<a href="oracle://branch/{message_id}" {link_style}>Branch</a>'
                    f'&nbsp;&nbsp;<a href="oracle://annotate/{message_id}" {link_style}>Note</a>'
                    f'&nbsp;&nbsp;<a href="oracle://highlight/{message_id}" {link_style}>Color</a>'
                    f'</div>'
                )
            hl_border = f"border-left:3px solid {html.escape(highlight)};" if highlight else ""
            annotation_html = ""
            if annotation:
                annotation_html = (
                    f'<div style="background:#3F2A06;border:1px solid #92400E;border-radius:6px;'
                    f'padding:4px 8px;margin-top:4px;font-size:11px;color:#FCD34D;">'
                    f'{html.escape(annotation)}</div>'
                )
            if compact:
                return (
                    f'<div style="margin:{margin} 0;border-left:3px solid #94A3B8;padding-left:10px;{hl_border}">'
                    f'<div style="background:#17223B;border:1px solid #1E2A45;border-radius:6px;padding:{pad};color:#E5ECF7;">{body}{atts_html}</div>'
                    f'{annotation_html}{actions}</div>'
                )
            return (
                f'<div style="margin:{margin} 0;display:block;">'
                f'<div style="font-size:11px;color:#94A3B8;margin-bottom:4px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;">You{ts}</div>'
                f'<div style="background:#17223B;border:1px solid #1E2A45;border-radius:10px;padding:{pad};color:#E5ECF7;">{body}{atts_html}</div>'
                f'{annotation_html}{actions}</div>'
            )
        elif role == "assistant":
            if collapsed and content and len(content) > 200:
                truncated = html.escape(content[:150]).replace("\n", "<br/>") + '<br/><i style="color:#64748B;">... collapsed ...</i>'
                body = truncated
            elif show_raw:
                body = '<pre style="white-space:pre-wrap;color:#E5ECF7;">' + html.escape(content or "") + '</pre>'
            else:
                body = render_markdown(content or "", block_offset=code_block_offset)
            # Highlight border
            hl_border = f"border-left:3px solid {html.escape(highlight)};" if highlight else ""
            # Response time + confidence
            meta_parts = []
            if response_time > 0:
                meta_parts.append(f"{response_time:.1f}s")
            if stop_reason == "max_tokens":
                meta_parts.append("truncated")
            if content:
                hedges = sum(1 for w in ("might", "possibly", "perhaps", "I think", "not sure", "could be")
                             if w in (content or "").lower()[:500])
                if hedges == 0:
                    meta_parts.append("confident")
                elif hedges >= 3:
                    meta_parts.append("uncertain")
            meta_html = ""
            if meta_parts:
                meta_html = f'<span style="color:#475569;font-size:10px;margin-left:8px;">({", ".join(meta_parts)})</span>'
            collapse_label = "Expand" if collapsed else "Collapse"
            pin_label = "Unpin" if pinned_in_chat else "Pin"
            pin_style = 'style="color:#FBBF24;font-size:11px;text-decoration:none;"' if pinned_in_chat else link_style
            actions = ""
            if message_id is not None:
                up_style = 'style="color:#22C55E;font-size:11px;text-decoration:none;"' if reaction == "up" else link_style
                dn_style = 'style="color:#EF4444;font-size:11px;text-decoration:none;"' if reaction == "down" else link_style
                actions = (
                    f'<div style="margin-top:4px;text-align:right;">'
                    f'<a href="oracle://react-up/{message_id}" {up_style}>+1</a>'
                    f'&nbsp;<a href="oracle://react-down/{message_id}" {dn_style}>-1</a>'
                    f'&nbsp;&nbsp;<a href="oracle://copymsg/{message_id}" {link_style}>Copy</a>'
                    f'&nbsp;&nbsp;<a href="oracle://pinmsg/{message_id}" {pin_style}>{pin_label}</a>'
                    f'&nbsp;&nbsp;<a href="oracle://reply/{message_id}" {link_style}>Reply</a>'
                    f'&nbsp;&nbsp;<a href="oracle://bookmark/{message_id}" {bm_style}>{bm_label}</a>'
                    f'&nbsp;&nbsp;<a href="oracle://collapse/{message_id}" {link_style}>{collapse_label}</a>'
                    f'&nbsp;&nbsp;<a href="oracle://regen/{message_id}" {link_style}>Regenerate</a>'
                    f'&nbsp;&nbsp;<a href="oracle://branch/{message_id}" {link_style}>Branch</a>'
                    f'&nbsp;&nbsp;<a href="oracle://annotate/{message_id}" {link_style}>Note</a>'
                    f'&nbsp;&nbsp;<a href="oracle://highlight/{message_id}" {link_style}>Color</a>'
                    f'&nbsp;&nbsp;<a href="oracle://speak/{message_id}" {link_style}>Speak</a>'
                    f'</div>'
                )
            annotation_html = ""
            if annotation:
                annotation_html = (
                    f'<div style="background:#3F2A06;border:1px solid #92400E;border-radius:6px;'
                    f'padding:4px 8px;margin-top:4px;font-size:11px;color:#FCD34D;">'
                    f'{html.escape(annotation)}</div>'
                )
            if compact:
                return (
                    f'<div style="margin:{margin} 0;border-left:3px solid #60A5FA;padding-left:10px;{hl_border}">'
                    f'<div style="background:#0B1220;border:1px solid #1E2A45;border-radius:6px;padding:{pad};color:#E5ECF7;">{body}</div>'
                    f'{annotation_html}{actions}</div>'
                )
            return (
                f'<div style="margin:{margin} 0;display:block;{hl_border}">'
                f'<div style="font-size:11px;color:#60A5FA;margin-bottom:4px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;">Claude{ts}{meta_html}</div>'
                f'<div style="background:#0B1220;border:1px solid #1E2A45;border-radius:10px;padding:{pad};color:#E5ECF7;">{body}</div>'
                f'{annotation_html}{actions}</div>'
            )
        else:
            safe = html.escape(content or "").replace("\n", "<br/>")
            return (
                f'<div style="margin:{margin} 0;display:block;color:#94A3B8;font-style:italic;">'
                f'{safe}</div>'
            )

    def _append_chunk_to_last(self, chunk: str) -> None:
        """Streaming render: append a chunk to the current assistant bubble."""
        self._stream_buffer.append(chunk)
        cid = self._streaming_chat_id
        if self._stream_start_time is not None:
            elapsed = time.monotonic() - self._stream_start_time
            if elapsed > 0.5:
                tps = len("".join(self._stream_buffer)) / 4 / elapsed
                self.token_label.setText(f"~{tps:.0f} tok/s")
        if cid != self._current_chat_id:
            return
        messages = db.get_messages(cid) if cid else []
        if messages and messages[-1].role == "assistant":
            messages[-1].content = "".join(self._stream_buffer) + " █"
        self._render_messages(messages)
        if self.settings.typewriter_mode:
            sb = self.chat_view.verticalScrollBar()
            if sb:
                sb.setValue(max(0, sb.maximum() - self.chat_view.height() // 2))

    def _is_scrolled_to_bottom(self) -> bool:
        sb = self.chat_view.verticalScrollBar()
        if sb is None:
            return True
        return sb.value() >= sb.maximum() - 30

    def _scroll_to_bottom(self, force: bool = False) -> None:
        if not force and self._streaming_worker and not self._is_scrolled_to_bottom():
            return
        self.chat_view.moveCursor(QTextCursor.End)
        sb = self.chat_view.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    # ── @file mentions ──────────────────────────────────────────────────
    _TEXT_FILE_FILTER = (
        "Code & Text (*.py *.js *.ts *.tsx *.jsx *.c *.cpp *.h *.hpp *.rs *.go "
        "*.java *.rb *.sh *.fish *.bash *.zsh *.yaml *.yml *.json *.toml *.md "
        "*.txt *.html *.css *.scss *.sql *.xml *.csv *.ini *.cfg *.conf *.lua "
        "*.pl *.swift *.kt *.scala *.r *.R *.m *.el *.vim);;"
        "All files (*)"
    )

    def _on_at_mention(self) -> None:
        recent = load_recent_files()
        if recent:
            menu = QMenu(self)
            for rp in recent:
                act = menu.addAction(Path(rp).name)
                act.setData(rp)
                act.setToolTip(rp)
            menu.addSeparator()
            browse_act = menu.addAction("Browse...")
            chosen = menu.exec(self.input_box.mapToGlobal(self.input_box.cursorRect().bottomRight()))
            if chosen is None:
                return
            if chosen == browse_act:
                paths, _ = QFileDialog.getOpenFileNames(
                    self, "Select file to reference", "", self._TEXT_FILE_FILTER
                )
            elif chosen.data():
                paths = [chosen.data()]
            else:
                return
        else:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Select file to reference", "", self._TEXT_FILE_FILTER
            )
        if not paths:
            return
        cursor = self.input_box.textCursor()
        for p in paths:
            cursor.insertText(f"@{p} ")
            add_recent_file(p)
        self.input_box.setTextCursor(cursor)

    # ── Drag-and-drop files ──────────────────────────────────────────────
    def _on_files_dropped(self, paths: list, kind: str) -> None:
        if kind == "text":
            cursor = self.input_box.textCursor()
            for p in paths:
                cursor.insertText(f"@{p} ")
            self.input_box.setTextCursor(cursor)
        elif kind == "attachment":
            for p in paths:
                try:
                    spec = att.classify(Path(p))
                except att.UnsupportedAttachment as e:
                    QMessageBox.warning(self, "Unsupported file", str(e))
                    continue
                self._pending_attachments.append(spec)
            self._refresh_attach_row()

    # ── Link clicks (code block Copy/Apply, regen, edit, external) ──────
    def _on_link_clicked(self, url: QUrl) -> None:
        if url.scheme() == "oracle":
            action = url.host()
            try:
                index = int(url.path().lstrip("/"))
            except (ValueError, TypeError):
                return
            if action == "copy":
                blocks = getattr(self, "_all_code_blocks", [])
                if 0 <= index < len(blocks):
                    QApplication.clipboard().setText(blocks[index])
            elif action == "apply":
                blocks = getattr(self, "_all_code_blocks", [])
                if 0 <= index < len(blocks):
                    path, _ = QFileDialog.getSaveFileName(self, "Apply code to file", "", "All files (*)")
                    if path:
                        try:
                            Path(path).write_text(blocks[index] + "\n", encoding="utf-8")
                        except OSError as e:
                            QMessageBox.warning(self, "Write error", f"Could not write file: {e}")
            elif action == "regen":
                self._on_regenerate(index)
            elif action == "edit":
                self._on_edit_message(index)
            elif action == "bookmark":
                db.toggle_bookmark(index)
                if self._current_chat_id:
                    self._render_messages(db.get_messages(self._current_chat_id))
            elif action == "branch":
                self._on_branch(index)
            elif action == "copymsg":
                self._on_copy_message(index)
            elif action == "pinmsg":
                db.toggle_pin_message(index)
                if self._current_chat_id:
                    self._render_messages(db.get_messages(self._current_chat_id))
            elif action == "reply":
                self._on_reply(index)
            elif action == "annotate":
                self._on_annotate(index)
            elif action == "highlight":
                self._on_highlight(index)
            elif action == "speak":
                self._on_speak(index)
            elif action == "preview":
                self._on_preview_html(index)
            elif action == "citation":
                self._on_citation(index)
            elif action == "collapse":
                db.toggle_collapsed(index)
                if self._current_chat_id:
                    self._render_messages(db.get_messages(self._current_chat_id))
            elif action == "run":
                self._on_run_code(index)
            elif action in ("react-up", "react-down"):
                new_reaction = "up" if action == "react-up" else "down"
                msgs = db.get_messages(self._current_chat_id) if self._current_chat_id else []
                current = ""
                for m in msgs:
                    if m.id == index:
                        current = m.reaction
                        break
                db.set_reaction(index, "" if current == new_reaction else new_reaction)
                if self._current_chat_id:
                    self._render_messages(db.get_messages(self._current_chat_id))
            elif action == "quickreply":
                if 0 <= index < len(self._quick_replies):
                    self.input_box.setPlainText(self._quick_replies[index])
                    self._on_send()
            elif action == "starter":
                if 0 <= index < len(self._STARTER_PROMPTS):
                    self.input_box.setPlainText(self._STARTER_PROMPTS[index])
                    self.input_box.setFocus()
        elif url.scheme() == "file" and url.toLocalFile().lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")):
            self._show_image_lightbox(url.toLocalFile())
        elif url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)

    # ── Text-to-speech (voice response) ─────────────────────────────────
    _tts_proc: Optional[subprocess.Popen] = None

    def _on_speak(self, message_id: int) -> None:
        import shutil
        if not self._current_chat_id:
            return
        if self._tts_proc and self._tts_proc.poll() is None:
            self._tts_proc.terminate()
            self._tts_proc = None
            return
        content = ""
        for m in db.get_messages(self._current_chat_id):
            if m.id == message_id:
                content = m.content or ""
                break
        if not content:
            return
        for cmd in ("espeak-ng", "espeak", "festival"):
            if shutil.which(cmd):
                try:
                    if cmd == "festival":
                        self._tts_proc = subprocess.Popen(
                            ["festival", "--tts"],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                        self._tts_proc.communicate(input=content[:2000].encode(), timeout=30)
                    else:
                        self._tts_proc = subprocess.Popen(
                            [cmd, "--", content[:2000]],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                    return
                except (OSError, subprocess.TimeoutExpired):
                    continue
        self._show_system_message("Voice output requires espeak-ng, espeak, or festival.")

    # ── Copy message ─────────────────────────────────────────────────────
    def _on_copy_message(self, message_id: int) -> None:
        if not self._current_chat_id:
            return
        for m in db.get_messages(self._current_chat_id):
            if m.id == message_id:
                QApplication.clipboard().setText(m.content or "")
                return

    # ── Commands menu ──────────────────────────────────────────────────
    _COMMANDS_HELP = [
        ("Chat", [
            ("/clear", "Clear conversation"),
            ("/delete <N>", "Delete last N messages"),
            ("/replace old -> new", "Find & replace in messages"),
            ("/merge <chat>", "Merge another chat into this one"),
            ("/link <chat>", "Pull context from another chat"),
            ("/summary", "AI-generated conversation summary"),
            ("/autotitle", "AI-generated chat title"),
        ]),
        ("Model", [
            ("/model <name>", "Switch model"),
            ("/compare <model>", "Compare with another model"),
            ("/automodel", "Toggle auto model switching"),
            ("/favorite <model>", "Pin model to top of picker"),
            ("/unfavorite <model>", "Remove from favorites"),
        ]),
        ("Prompt", [
            ("/system <text>", "Set global system prompt"),
            ("/chatprompt <text>", "Per-chat system prompt"),
            ("/persona <name>", "Load persona (reviewer/tutor/etc)"),
            ("/format <type>", "Response format (code/prose/bullets/table)"),
            ("/length <level>", "Response length (brief/normal/detailed)"),
            ("/prompt save|load|list|delete", "Prompt presets"),
            ("/template save|load|list|delete", "Conversation templates"),
            ("/systempromptpreview", "Show effective prompt"),
        ]),
        ("View", [
            ("/compact", "Toggle compact mode"),
            ("/focus", "Toggle sidebar"),
            ("/theme dark|light", "Switch theme"),
            ("/rawmd", "Toggle raw markdown view"),
            ("/typewriter", "Toggle typewriter scroll"),
            ("/split [chat]", "Toggle split view"),
        ]),
        ("Organize", [
            ("/tag <name>", "Tag current chat"),
            ("/untag <name>", "Remove tag"),
            ("/tags", "List tags"),
            ("/chatcolor <color>", "Color-code chat"),
            ("/archive", "Archive chat"),
            ("/archived", "List archived chats"),
            ("/unarchive <name>", "Restore from archive"),
            ("/autoclean <N>d", "Archive stale chats"),
            ("/filter save|load|list|delete", "Saved sidebar filters"),
        ]),
        ("Search", [
            ("/search [role] <q>", "Search messages"),
            ("/searchall <q>", "Search across all chats"),
            ("/grep <regex>", "Regex search"),
            ("/bookmarks", "List bookmarked messages"),
            ("/notes", "List all annotations"),
        ]),
        ("Export & Stats", [
            ("/export", "Export as Markdown"),
            ("/exporthtml", "Export as styled HTML"),
            ("/import", "Import Markdown conversation"),
            ("/stats", "Chat statistics"),
            ("/wc", "Word count"),
            ("/cost", "Estimated API cost"),
            ("/context", "Context window usage"),
            ("/heatmap", "Activity by hour"),
            ("/timeline", "Chronological chat list"),
            ("/dashboard", "Aggregate statistics"),
            ("/timer", "Session duration"),
        ]),
        ("Tools", [
            ("/snippet save|paste|list|delete", "Snippet library"),
            ("/macro save|list|delete <name>", "Input macros (!!name)"),
            ("/workspace <dir>", "Add directory listing as context"),
            ("/schedule <Ns|m|h> <msg>", "Delayed send"),
            ("/budget <N>", "Token budget per chat"),
            ("/checkpoint <name>", "Save conversation state"),
            ("/restore <name>", "Restore checkpoint"),
            ("/history", "View edit history"),
            ("/tree", "Show conversation branches"),
            ("/diff <file>", "Preview code block diff"),
            ("/ephemeral", "Temporary chat (auto-deletes)"),
            ("/notify", "Toggle notification sound"),
            ("/gallery", "List images in chat"),
        ]),
    ]

    def _show_commands_menu(self) -> None:
        menu = QMenu(self)
        for group_name, commands in self._COMMANDS_HELP:
            sub = menu.addMenu(group_name)
            for cmd, desc in commands:
                act = sub.addAction(f"{cmd}  —  {desc}")
                act.setData(cmd.split()[0])
        chosen = menu.exec(self.cmds_btn.mapToGlobal(self.cmds_btn.rect().bottomLeft()))
        if chosen and chosen.data():
            self.input_box.setPlainText(chosen.data() + " ")
            self.input_box.setFocus()
            cursor = self.input_box.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.input_box.setTextCursor(cursor)

    # ── Image lightbox ────────────────────────────────────────────────────
    def _show_image_lightbox(self, path: str) -> None:
        from PySide6.QtWidgets import QDialog as _QDialog
        dlg = _QDialog(self)
        dlg.setWindowTitle("Image Preview")
        dlg.resize(800, 600)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        browser = QTextBrowser(dlg)
        img_url = QUrl.fromLocalFile(path).toString()
        browser.setHtml(
            f'<div style="text-align:center;padding:10px;">'
            f'<img src="{img_url}" style="max-width:100%;max-height:100%;"/></div>'
        )
        layout.addWidget(browser)
        dlg.exec()

    # ── Highlight message color ──────────────────────────────────────────
    def _on_highlight(self, message_id: int) -> None:
        colors = {"Red": "#EF4444", "Yellow": "#FBBF24", "Green": "#22C55E",
                  "Blue": "#3B82F6", "Clear": ""}
        menu = QMenu(self)
        for name, val in colors.items():
            act = menu.addAction(name)
            act.setData(val)
        chosen = menu.exec(self.chat_view.mapToGlobal(self.chat_view.cursorRect().center()))
        if chosen:
            db.set_highlight(message_id, chosen.data())
            if self._current_chat_id:
                self._render_messages(db.get_messages(self._current_chat_id))

    # ── Quick model switch (Ctrl+M) ─────────────────────────────────────
    def _quick_model_switch(self) -> None:
        menu = QMenu(self)
        for display, mid in MODELS.items():
            act = menu.addAction(display)
            act.setData(mid)
        chosen = menu.exec(self.input_box.mapToGlobal(self.input_box.cursorRect().center()))
        if chosen:
            idx = self.model_picker.findData(chosen.data())
            if idx >= 0:
                self.model_picker.setCurrentIndex(idx)

    # ── Undo (Ctrl+Z) ───────────────────────────────────────────────────
    def _undo_last(self) -> None:
        if not self._undo_stack:
            self._show_system_message("Nothing to undo.")
            return
        chat_id, action, data = self._undo_stack.pop()
        if action == "delete" and chat_id == self._current_chat_id:
            for role, content in data:
                db.add_message(chat_id, role, content)
            self._render_messages(db.get_messages(chat_id))
            self._show_system_message(f"Undone: restored {len(data)} message(s).")
        else:
            self._show_system_message("Cannot undo this action.")

    # ── Annotate message ────────────────────────────────────────────────
    def _on_annotate(self, message_id: int) -> None:
        from PySide6.QtWidgets import QInputDialog
        current = ""
        if self._current_chat_id:
            for m in db.get_messages(self._current_chat_id):
                if m.id == message_id:
                    current = m.annotation
                    break
        text, ok = QInputDialog.getText(self, "Add note", "Note:", text=current)
        if ok:
            db.set_annotation(message_id, text.strip())
            if self._current_chat_id:
                self._render_messages(db.get_messages(self._current_chat_id))

    # ── Reply (quote message) ────────────────────────────────────────────
    def _on_reply(self, message_id: int) -> None:
        if not self._current_chat_id:
            return
        for m in db.get_messages(self._current_chat_id):
            if m.id == message_id:
                quoted = "\n".join(f"> {line}" for line in (m.content or "").split("\n")[:5])
                if len((m.content or "").split("\n")) > 5:
                    quoted += "\n> ..."
                self.input_box.setPlainText(f"{quoted}\n\n")
                cursor = self.input_box.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.input_box.setTextCursor(cursor)
                self.input_box.setFocus()
                return

    # ── Run code block ───────────────────────────────────────────────────
    def _on_run_code(self, index: int) -> None:
        blocks = getattr(self, "_all_code_blocks", [])
        if index < 0 or index >= len(blocks):
            return
        code = blocks[index]
        preview = code[:500] + ("..." if len(code) > 500 else "")
        if QMessageBox.question(
            self, "Run code?",
            f"Execute this code as Python?\n\n{preview}\n\n"
            f"[{len(code)} chars total] This runs with your full user permissions.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        try:
            result = subprocess.run(
                ["python3", "-c", code],
                capture_output=True, text=True, timeout=30,
                cwd=str(Path.home()),
            )
            output = result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if not output.strip():
                output = "(no output)"
        except subprocess.TimeoutExpired:
            output = "[Timed out after 30s]"
        except FileNotFoundError:
            output = "[python3 not found]"
        except OSError as e:
            output = f"[Error: {e}]"
        self._show_system_message(f"Output:\n{output.strip()}")

    # ── Voice input ──────────────────────────────────────────────────────
    def _on_mic_toggle(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        import shutil
        if not shutil.which("arecord"):
            self._show_system_message("Voice input requires `arecord` (alsa-utils). Install it first.")
            return
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self._record_file = tmp.name
        tmp.close()
        try:
            self._record_proc = subprocess.Popen(
                ["arecord", "-f", "cd", "-t", "wav", self._record_file],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._recording = True
            self.mic_btn.setText("⏹")
            self.mic_btn.setToolTip("Click to stop recording")
        except OSError as e:
            self._show_system_message(f"Could not start recording: {e}")
            if self._record_file:
                Path(self._record_file).unlink(missing_ok=True)
                self._record_file = None

    def _stop_recording(self) -> None:
        import shutil
        self._recording = False
        self.mic_btn.setText("🎤")
        self.mic_btn.setToolTip("Voice input (requires arecord + whisper)")
        if self._record_proc:
            self._record_proc.terminate()
            try:
                self._record_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._record_proc.kill()
            self._record_proc = None
        if not self._record_file or not Path(self._record_file).exists():
            return
        whisper_cmd = shutil.which("whisper")
        if not whisper_cmd:
            self._show_system_message("Transcription requires `whisper` CLI. Install: pip install openai-whisper")
            return
        try:
            result = subprocess.run(
                [whisper_cmd, self._record_file, "--model", "base", "--output_format", "txt",
                 "--output_dir", str(Path(self._record_file).parent)],
                capture_output=True, text=True, timeout=60,
            )
            txt_path = Path(self._record_file).with_suffix(".txt")
            if txt_path.exists():
                text = txt_path.read_text(encoding="utf-8").strip()
                if text:
                    cursor = self.input_box.textCursor()
                    cursor.insertText(text)
                    self.input_box.setTextCursor(cursor)
                txt_path.unlink(missing_ok=True)
            else:
                self._show_system_message("Transcription produced no output.")
        except subprocess.TimeoutExpired:
            self._show_system_message("Transcription timed out.")
        except OSError as e:
            self._show_system_message(f"Transcription error: {e}")
        Path(self._record_file).unlink(missing_ok=True)
        self._record_file = None

    # ── Clipboard image paste ────────────────────────────────────────────
    def _on_image_pasted(self, image) -> None:
        dest_dir = DATA_DIR / "clipboard-paste"
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = f"paste_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        dest = dest_dir / fname
        QImage(image).save(str(dest), "PNG")
        try:
            spec = att.classify(dest)
            self._pending_attachments.append(spec)
            self._refresh_attach_row()
        except att.UnsupportedAttachment:
            pass

    # ── Token counter ────────────────────────────────────────────────────
    def _update_token_count(self) -> None:
        text = self.input_box.toPlainText()
        count = max(1, len(text) // 4) if text.strip() else 0
        if "@/" in text:
            for fpath in _AT_FILE_RE.findall(text):
                try:
                    count += Path(fpath).stat().st_size // 4
                except OSError:
                    pass
        if count >= 1000:
            self.token_label.setText(f"~{count / 1000:.1f}k tokens")
        else:
            self.token_label.setText(f"~{count} tokens")

    # ── Search ───────────────────────────────────────────────────────────
    def _on_sidebar_search_changed(self, text: str) -> None:
        query = text.lower()
        if not query:
            for i in range(self.chat_list.count()):
                self.chat_list.item(i).setHidden(False)
            return
        chats_by_id = {c.id: c for c in db.list_chats()}
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            chat_id = item.data(Qt.UserRole)
            chat = chats_by_id.get(chat_id)
            title_match = query in item.text().lower()
            tag_match = chat and query in (chat.tags or "").lower()
            item.setHidden(not (title_match or tag_match))

    def _toggle_search_bar(self) -> None:
        visible = not self.search_bar.isVisible()
        self.search_bar.setVisible(visible)
        if visible:
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            self.chat_view.setFocus()

    def _on_search_text_changed(self, text: str) -> None:
        if not text:
            return
        self.chat_view.moveCursor(QTextCursor.Start)
        self.chat_view.find(text)

    def _on_search_next(self) -> None:
        text = self.search_input.text()
        if not text:
            return
        if not self.chat_view.find(text):
            self.chat_view.moveCursor(QTextCursor.Start)
            self.chat_view.find(text)

    def _on_search_prev(self) -> None:
        text = self.search_input.text()
        if not text:
            return
        if not self.chat_view.find(text, QTextDocument.FindFlag.FindBackward):
            self.chat_view.moveCursor(QTextCursor.End)
            self.chat_view.find(text, QTextDocument.FindFlag.FindBackward)

    # ── Regenerate + Edit ────────────────────────────────────────────────
    def _on_regenerate(self, message_id: int) -> None:
        if self._current_chat_id is None:
            return
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._show_system_message("Cannot regenerate while a response is streaming.")
            return
        # Save old response for diff
        for m in db.get_messages(self._current_chat_id):
            if m.id == message_id and m.role == "assistant":
                self._last_regen_old_text = m.content
                db.save_edit_history(self._current_chat_id, m.role, m.content)
                break
        db.delete_messages_from(self._current_chat_id, message_id)
        db.add_message(self._current_chat_id, "assistant", "")
        self._stream_buffer = []
        self._render_messages(db.get_messages(self._current_chat_id))
        self._start_streaming_from_current_history()

    def _on_edit_message(self, message_id: int) -> None:
        if self._current_chat_id is None:
            return
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._show_system_message("Cannot edit while a response is streaming.")
            return
        messages = db.get_messages(self._current_chat_id)
        target = None
        for m in messages:
            if m.id == message_id:
                target = m
                break
        if target is None:
            return
        db.save_edit_history(self._current_chat_id, target.role, target.content)
        db.delete_messages_from(self._current_chat_id, message_id)
        self.input_box.setPlainText(target.content)
        self.input_box.setFocus()
        cursor = self.input_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.input_box.setTextCursor(cursor)
        self._render_messages(db.get_messages(self._current_chat_id))

    # ── Branch ────────────────────────────────────────────────────────────
    def _on_branch(self, message_id: int) -> None:
        if self._current_chat_id is None:
            return
        title = f"Branch of {self.chat_title_label.text().strip()}"
        model = self.model_picker.currentData() or self.settings.default_model
        new_chat = db.create_chat(title=title, model=model)
        db.copy_messages_up_to(self._current_chat_id, message_id, new_chat.id)
        self._current_chat_id = new_chat.id
        self._refresh_chat_list()
        for i in range(self.chat_list.count()):
            it = self.chat_list.item(i)
            if it.data(Qt.UserRole) == new_chat.id:
                self.chat_list.setCurrentItem(it)
                break
        self.input_box.setFocus()

    # ── Quick-reply suggestions ──────────────────────────────────────────
    def _render_quick_replies_html(self) -> str:
        chip = (
            'display:inline-block;background:#17223B;border:1px solid #2A3A5A;'
            'border-radius:14px;padding:8px 18px;margin:6px 10px;color:#CBD5E1;'
            'font-size:12px;text-decoration:none;'
        )
        parts = []
        for i, text in enumerate(self._quick_replies):
            parts.append(f'<a href="oracle://quickreply/{i}" style="{chip}">{html.escape(text)}</a>')
        return f'<div style="margin:14px 0;text-align:center;">{"&nbsp;&nbsp;&nbsp;".join(parts)}</div>'

    # ── Export conversation ──────────────────────────────────────────────
    def _on_export(self) -> None:
        if self._current_chat_id is None:
            QMessageBox.information(self, "Export", "No conversation to export.")
            return
        messages = db.get_messages(self._current_chat_id)
        if not messages:
            QMessageBox.information(self, "Export", "This conversation is empty.")
            return
        title = self.chat_title_label.text().strip() or "conversation"
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:60]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export conversation", f"{safe_title}.md",
            "Markdown (*.md);;Text (*.txt);;All files (*)"
        )
        if not path:
            return
        lines = [f"# {title}\n\n"]
        for m in messages:
            if m.role == "user":
                lines.append("## You\n\n")
                lines.append(m.content or "")
                if m.attachments:
                    lines.append("\n")
                    for a in m.attachments:
                        lines.append(f"\n[Attachment: {a.original_name}]")
                lines.append("\n\n")
            elif m.role == "assistant":
                lines.append("## Claude\n\n")
                lines.append(m.content or "")
                lines.append("\n\n")
        try:
            Path(path).write_text("".join(lines), encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Export error", f"Could not write file: {e}")

    # ── Slash commands ───────────────────────────────────────────────────
    def _handle_slash_command(self, text: str) -> None:
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd == "/clear":
            self._slash_clear()
        elif cmd == "/model":
            self._slash_model(arg)
        elif cmd == "/system":
            self._slash_system(arg)
        elif cmd == "/export":
            self._on_export()
        elif cmd == "/prompt":
            self._slash_prompt(arg)
        elif cmd == "/compact":
            self._slash_compact()
        elif cmd == "/length":
            self._slash_length(arg)
        elif cmd == "/stats":
            self._slash_stats()
        elif cmd == "/tag":
            self._slash_tag(arg)
        elif cmd == "/untag":
            self._slash_untag(arg)
        elif cmd == "/tags":
            self._slash_tags()
        elif cmd == "/notify":
            self._slash_notify()
        elif cmd == "/import":
            self._slash_import()
        elif cmd == "/compare":
            self._slash_compare(arg)
        elif cmd == "/bookmarks":
            self._slash_bookmarks()
        elif cmd == "/template":
            self._slash_template(arg)
        elif cmd == "/wc":
            self._slash_wc()
        elif cmd == "/theme":
            self._slash_theme(arg)
        elif cmd == "/chatprompt":
            self._slash_chatprompt(arg)
        elif cmd == "/delete":
            self._slash_delete(arg)
        elif cmd == "/context":
            self._slash_context()
        elif cmd == "/focus":
            self._slash_focus()
        elif cmd == "/archive":
            self._slash_archive()
        elif cmd == "/unarchive":
            self._slash_unarchive(arg)
        elif cmd == "/archived":
            self._slash_archived()
        elif cmd == "/snippet":
            self._slash_snippet(arg)
        elif cmd == "/summary":
            self._slash_summary()
        elif cmd == "/split":
            self._slash_split(arg)
        elif cmd == "/automodel":
            self._slash_automodel()
        elif cmd == "/schedule":
            self._slash_schedule(arg)
        elif cmd == "/link":
            self._slash_link(arg)
        elif cmd == "/history":
            self._slash_history()
        elif cmd == "/help":
            self._slash_help()
        elif cmd == "/replace":
            self._slash_replace(arg)
        elif cmd == "/heatmap":
            self._slash_heatmap()
        elif cmd == "/cost":
            self._slash_cost()
        elif cmd == "/search":
            self._slash_search(arg)
        elif cmd == "/autotitle":
            self._slash_autotitle()
        elif cmd == "/merge":
            self._slash_merge(arg)
        elif cmd == "/grep":
            self._slash_grep(arg)
        elif cmd == "/ephemeral":
            self._slash_ephemeral()
        elif cmd == "/budget":
            self._slash_budget(arg)
        elif cmd == "/favorite":
            self._slash_favorite(arg)
        elif cmd == "/unfavorite":
            self._slash_unfavorite(arg)
        elif cmd == "/timeline":
            self._slash_timeline()
        elif cmd == "/format":
            self._slash_format(arg)
        elif cmd == "/persona":
            self._slash_persona(arg)
        elif cmd == "/workspace":
            self._slash_workspace(arg)
        elif cmd == "/checkpoint":
            self._slash_checkpoint(arg)
        elif cmd == "/restore":
            self._slash_restore(arg)
        elif cmd == "/notes":
            self._slash_notes()
        elif cmd == "/diff":
            self._slash_diff(arg)
        elif cmd == "/searchall":
            self._slash_searchall(arg)
        elif cmd == "/autoclean":
            self._slash_autoclean(arg)
        elif cmd == "/gallery":
            self._slash_gallery()
        elif cmd == "/filter":
            self._slash_filter(arg)
        elif cmd == "/exporthtml":
            self._slash_exporthtml()
        elif cmd == "/systempromptpreview":
            self._slash_systempromptpreview()
        elif cmd == "/typewriter":
            self._slash_typewriter()
        elif cmd == "/rawmd":
            self._slash_rawmd()
        elif cmd == "/chatcolor":
            self._slash_chatcolor(arg)
        elif cmd == "/macro":
            self._slash_macro(arg)
        elif cmd == "/dashboard":
            self._slash_dashboard()
        elif cmd == "/timer":
            self._slash_timer()
        elif cmd == "/tree":
            self._slash_tree()
        elif cmd == "/web":
            self._slash_web(arg)
        elif cmd == "/memory":
            self._slash_memory(arg)
        elif cmd == "/project":
            self._slash_project(arg)
        elif cmd == "/thinking":
            self._slash_thinking(arg)
        elif cmd == "/research":
            self._slash_research(arg)
        elif cmd == "/factcheck":
            self._slash_factcheck()
        else:
            self._show_system_message(f"Unknown command: {cmd}\nType /help for available commands.")
        self.input_box.clear()

    def _slash_clear(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat to clear.")
            return
        db.clear_messages(self._current_chat_id)
        self._render_messages([])
        self._show_system_message("Conversation cleared.")

    def _slash_model(self, name: str) -> None:
        if not name:
            current = self.model_picker.currentData()
            self._show_system_message(
                f"Current model: {model_display_name(current)}\n"
                f"Available: {', '.join(MODELS.keys())}"
            )
            return
        name_lower = name.lower()
        for display, mid in MODELS.items():
            if mid == name or display.lower() == name_lower:
                idx = self.model_picker.findData(mid)
                if idx >= 0:
                    self.model_picker.setCurrentIndex(idx)
                    self._show_system_message(f"Switched to {display}.")
                return
        matches = [(d, m) for d, m in MODELS.items()
                   if name_lower in d.lower() or name_lower in m.lower()]
        if len(matches) == 1:
            display, mid = matches[0]
            idx = self.model_picker.findData(mid)
            if idx >= 0:
                self.model_picker.setCurrentIndex(idx)
                self._show_system_message(f"Switched to {display}.")
            return
        if len(matches) > 1:
            names = ", ".join(d for d, _ in matches)
            self._show_system_message(f"Ambiguous model name. Matches: {names}")
            return
        self._show_system_message(
            f"No model matching '{name}'.\nAvailable: {', '.join(MODELS.keys())}"
        )

    def _slash_system(self, prompt: str) -> None:
        self.settings.system_prompt = prompt
        save_settings(self.settings)
        if prompt:
            preview = prompt[:80] + ("..." if len(prompt) > 80 else "")
            self._show_system_message(f"System prompt updated: {preview}")
        else:
            self._show_system_message("System prompt cleared.")

    def _slash_prompt(self, arg: str) -> None:
        parts = arg.split(None, 1)
        subcmd = parts[0].lower() if parts else ""
        subarg = parts[1].strip() if len(parts) > 1 else ""
        if subcmd == "save":
            if not subarg:
                self._show_system_message("Usage: /prompt save <name>")
                return
            if not self.settings.system_prompt:
                self._show_system_message("No system prompt set. Use /system <prompt> first.")
                return
            prompts = load_prompts()
            prompts = [p for p in prompts if p["name"].lower() != subarg.lower()]
            prompts.append({"name": subarg, "content": self.settings.system_prompt})
            save_prompts(prompts)
            self._show_system_message(f"Saved prompt preset: {subarg}")
        elif subcmd == "load":
            if not subarg:
                self._show_system_message("Usage: /prompt load <name>")
                return
            found = find_prompt(subarg)
            if not found:
                self._show_system_message(f"No preset named '{subarg}'. Use /prompt list.")
                return
            self.settings.system_prompt = found["content"]
            save_settings(self.settings)
            preview = found["content"][:80] + ("..." if len(found["content"]) > 80 else "")
            self._show_system_message(f"Loaded prompt '{found['name']}': {preview}")
        elif subcmd == "list":
            prompts = load_prompts()
            if not prompts:
                self._show_system_message("No saved prompts. Use /prompt save <name>.")
                return
            lines = ["Saved prompts:"]
            for p in prompts:
                preview = p["content"][:60] + ("..." if len(p["content"]) > 60 else "")
                lines.append(f"  {p['name']} — {preview}")
            self._show_system_message("\n".join(lines))
        elif subcmd == "delete":
            if not subarg:
                self._show_system_message("Usage: /prompt delete <name>")
                return
            prompts = load_prompts()
            new_prompts = [p for p in prompts if p["name"].lower() != subarg.lower()]
            if len(new_prompts) == len(prompts):
                self._show_system_message(f"No preset named '{subarg}'.")
                return
            save_prompts(new_prompts)
            self._show_system_message(f"Deleted prompt preset: {subarg}")
        else:
            self._show_system_message(
                "Usage: /prompt <save|load|list|delete> [name]\n"
                "  /prompt save <name> — save current system prompt\n"
                "  /prompt load <name> — load as system prompt\n"
                "  /prompt list — list saved presets\n"
                "  /prompt delete <name> — remove a preset"
            )

    def _slash_compact(self) -> None:
        self._compact = not self._compact
        self.settings.compact_mode = self._compact
        save_settings(self.settings)
        if self._current_chat_id:
            self._render_messages(db.get_messages(self._current_chat_id))
        self._show_system_message(f"Compact mode {'on' if self._compact else 'off'}.")

    def _slash_length(self, arg: str) -> None:
        valid = {"brief", "normal", "detailed"}
        if arg.lower() not in valid:
            self._show_system_message(
                f"Current: {self.settings.response_length}\n"
                f"Usage: /length <{'|'.join(sorted(valid))}>"
            )
            return
        self.settings.response_length = arg.lower()
        save_settings(self.settings)
        self._show_system_message(f"Response length set to: {arg.lower()}")

    def _slash_stats(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        s = db.chat_stats(self._current_chat_id)
        if not s.get("msg_count"):
            self._show_system_message("This conversation is empty.")
            return
        tokens = s["total_chars"] // 4
        tok_str = f"~{tokens / 1000:.1f}k" if tokens >= 1000 else f"~{tokens}"
        first = s.get("first_at", "")[:16].replace("T", " ")
        last = s.get("last_at", "")[:16].replace("T", " ")
        model = model_display_name(self.model_picker.currentData() or "")
        self._show_system_message(
            f"Messages: {s['msg_count']} ({s['user_count']} you, {s['assistant_count']} Claude)\n"
            f"Tokens: {tok_str} estimated\n"
            f"First message: {first}\n"
            f"Last message: {last}\n"
            f"Model: {model}"
        )

    def _slash_tag(self, name: str) -> None:
        if not name:
            self._show_system_message("Usage: /tag <name>")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        chat = db.get_chat(self._current_chat_id)
        if not chat:
            return
        tags = [t.strip() for t in chat.tags.split(",") if t.strip()] if chat.tags else []
        if name.lower() not in [t.lower() for t in tags]:
            tags.append(name)
        db.set_tags(self._current_chat_id, ", ".join(tags))
        self._refresh_chat_list()
        self._show_system_message(f"Tagged: {', '.join(tags)}")

    def _slash_untag(self, name: str) -> None:
        if not name:
            self._show_system_message("Usage: /untag <name>")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        chat = db.get_chat(self._current_chat_id)
        if not chat:
            return
        tags = [t.strip() for t in chat.tags.split(",") if t.strip()] if chat.tags else []
        tags = [t for t in tags if t.lower() != name.lower()]
        db.set_tags(self._current_chat_id, ", ".join(tags))
        self._refresh_chat_list()
        self._show_system_message(f"Tags: {', '.join(tags) if tags else '(none)'}")

    def _slash_tags(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        chat = db.get_chat(self._current_chat_id)
        tags = chat.tags if chat and chat.tags else "(none)"
        self._show_system_message(f"Tags: {tags}")

    def _slash_notify(self) -> None:
        self.settings.notify_sound = not self.settings.notify_sound
        save_settings(self.settings)
        self._show_system_message(
            f"Notification sound {'on' if self.settings.notify_sound else 'off'}."
        )

    def _slash_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import conversation", "",
            "Markdown (*.md);;Text (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as e:
            self._show_system_message(f"Could not read file: {e}")
            return
        title = Path(path).stem
        messages: List[tuple] = []
        current_role = None
        current_lines: List[str] = []
        for line in text.split("\n"):
            if line.strip().startswith("# ") and not messages and not current_role:
                title = line.strip()[2:]
                continue
            if line.strip() in ("## You", "## User"):
                if current_role and current_lines:
                    messages.append((current_role, "\n".join(current_lines).strip()))
                current_role = "user"
                current_lines = []
            elif line.strip() in ("## Claude", "## Assistant"):
                if current_role and current_lines:
                    messages.append((current_role, "\n".join(current_lines).strip()))
                current_role = "assistant"
                current_lines = []
            elif current_role is not None:
                current_lines.append(line)
        if current_role and current_lines:
            messages.append((current_role, "\n".join(current_lines).strip()))
        if not messages:
            self._show_system_message("No messages found. Expected ## You / ## Claude sections.")
            return
        model = self.model_picker.currentData() or self.settings.default_model
        chat = db.create_chat(title=title, model=model)
        for role, content in messages:
            db.add_message(chat.id, role, content)
        self._current_chat_id = chat.id
        self._refresh_chat_list()
        for i in range(self.chat_list.count()):
            it = self.chat_list.item(i)
            if it.data(Qt.UserRole) == chat.id:
                self.chat_list.setCurrentItem(it)
                break
        self._show_system_message(f"Imported {len(messages)} messages from {Path(path).name}")

    def _slash_compare(self, name: str) -> None:
        if not name:
            self._show_system_message("Usage: /compare <model>\nSends the last user message to a different model.")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._show_system_message("Cannot compare while streaming.")
            return
        name_lower = name.lower()
        matched_mid = None
        matched_display = None
        for display, mid in MODELS.items():
            if mid == name or display.lower() == name_lower:
                matched_mid = mid
                matched_display = display
                break
        if not matched_mid:
            for display, mid in MODELS.items():
                if name_lower in display.lower() or name_lower in mid.lower():
                    matched_mid = mid
                    matched_display = display
                    break
        if not matched_mid:
            self._show_system_message(f"No model matching '{name}'.")
            return
        db.add_message(self._current_chat_id, "assistant", "")
        self._stream_buffer = []
        self._render_messages(db.get_messages(self._current_chat_id))
        if self.model_picker.findData(matched_mid) < 0:
            self.model_picker.addItem(f"[Compare] {matched_display}", matched_mid)
        idx = self.model_picker.findData(matched_mid)
        if idx >= 0:
            self.model_picker.blockSignals(True)
            self.model_picker.setCurrentIndex(idx)
            self.model_picker.blockSignals(False)
        self._start_streaming_from_current_history()

    def _slash_template(self, arg: str) -> None:
        parts = arg.split(None, 1)
        subcmd = parts[0].lower() if parts else ""
        subarg = parts[1].strip() if len(parts) > 1 else ""
        if subcmd == "save":
            if not subarg:
                self._show_system_message("Usage: /template save <name>")
                return
            templates = load_templates()
            prompt = self.settings.system_prompt or ""
            templates = [t for t in templates if t["name"].lower() != subarg.lower()]
            templates.append({"name": subarg, "system_prompt": prompt,
                              "first_message": self.input_box.toPlainText().strip()})
            save_templates(templates)
            self._show_system_message(f"Saved template: {subarg}")
        elif subcmd == "load":
            if not subarg:
                self._show_system_message("Usage: /template load <name>")
                return
            templates = load_templates()
            found = None
            for t in templates:
                if t["name"].lower() == subarg.lower():
                    found = t
                    break
            if not found:
                self._show_system_message(f"No template named '{subarg}'.")
                return
            if found.get("system_prompt"):
                self.settings.system_prompt = found["system_prompt"]
                save_settings(self.settings)
            if found.get("first_message"):
                self.input_box.setPlainText(found["first_message"])
            self._show_system_message(f"Loaded template: {found['name']}")
        elif subcmd == "list":
            templates = load_templates()
            if not templates:
                self._show_system_message("No saved templates. Use /template save <name>.")
                return
            lines = ["Saved templates:"]
            for t in templates:
                sp = (t.get("system_prompt") or "")[:40]
                fm = (t.get("first_message") or "")[:40]
                lines.append(f"  {t['name']} — prompt: {sp or '(none)'}, msg: {fm or '(none)'}")
            self._show_system_message("\n".join(lines))
        elif subcmd == "delete":
            if not subarg:
                self._show_system_message("Usage: /template delete <name>")
                return
            templates = load_templates()
            new = [t for t in templates if t["name"].lower() != subarg.lower()]
            if len(new) == len(templates):
                self._show_system_message(f"No template named '{subarg}'.")
                return
            save_templates(new)
            self._show_system_message(f"Deleted template: {subarg}")
        else:
            self._show_system_message(
                "Usage: /template <save|load|list|delete> [name]\n"
                "  save — saves current system prompt + input text\n"
                "  load — restores prompt and pre-fills input"
            )

    def _slash_wc(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        wc = db.word_count(self._current_chat_id)
        self._show_system_message(
            f"Words: {wc['words']:,}\n"
            f"Characters: {wc['chars']:,}\n"
            f"Reading time: ~{wc['reading_min']} min"
        )

    def _slash_theme(self, arg: str) -> None:
        if arg.lower() not in ("dark", "light"):
            self._show_system_message(f"Current: {self.settings.theme}\nUsage: /theme <dark|light>")
            return
        self.settings.theme = arg.lower()
        save_settings(self.settings)
        from .styles import STYLESHEET, STYLESHEET_LIGHT
        sheet = STYLESHEET_LIGHT if arg.lower() == "light" else STYLESHEET
        QApplication.instance().setStyleSheet(sheet)
        self._show_system_message(f"Theme switched to {arg.lower()}.")

    def _slash_chatprompt(self, arg: str) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        db.set_chat_system_prompt(self._current_chat_id, arg)
        if arg:
            preview = arg[:80] + ("..." if len(arg) > 80 else "")
            self._show_system_message(f"Chat-specific prompt set: {preview}")
        else:
            self._show_system_message("Chat-specific prompt cleared (using global).")

    def _slash_delete(self, arg: str) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        try:
            n = int(arg.strip()) if arg.strip() else 0
        except ValueError:
            self._show_system_message("Usage: /delete <N> — delete the last N messages")
            return
        if n <= 0:
            self._show_system_message("Usage: /delete <N> — delete the last N messages")
            return
        msgs = db.get_messages(self._current_chat_id)
        undo_data = [(m.role, m.content) for m in msgs[-n:]]
        self._undo_stack.append((self._current_chat_id, "delete", undo_data))
        deleted = db.delete_last_n_messages(self._current_chat_id, n)
        self._render_messages(db.get_messages(self._current_chat_id))
        self._show_system_message(f"Deleted {deleted} message(s).")

    def _slash_context(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        stats = db.chat_stats(self._current_chat_id)
        total_chars = stats.get("total_chars", 0)
        est_tokens = total_chars // 4
        max_context = 200_000
        pct = min(100, est_tokens * 100 // max_context) if max_context else 0
        bar_len = 20
        filled = pct * bar_len // 100
        bar = "█" * filled + "░" * (bar_len - filled)
        self._show_system_message(
            f"Context usage: ~{est_tokens:,} / {max_context:,} tokens ({pct}%)\n"
            f"[{bar}]"
        )

    def _slash_focus(self) -> None:
        visible = self._sidebar_widget.isVisible()
        self._sidebar_widget.setVisible(not visible)
        self.settings.focus_mode = visible
        save_settings(self.settings)
        self._show_system_message(f"Focus mode {'on' if visible else 'off'}.")

    def _slash_archive(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        db.set_archived(self._current_chat_id, 1)
        self._current_chat_id = None
        self._refresh_chat_list()
        self._render_messages([])
        self.chat_title_label.setText("Start a new chat")

    def _slash_unarchive(self, arg: str) -> None:
        if not arg:
            self._show_system_message("Usage: /unarchive <chat title or id>")
            return
        for c in db.list_archived_chats():
            if arg.lower() in c.title.lower() or arg == str(c.id):
                db.set_archived(c.id, 0)
                self._refresh_chat_list()
                self._show_system_message(f"Unarchived: {c.title}")
                return
        self._show_system_message(f"No archived chat matching '{arg}'.")

    def _slash_archived(self) -> None:
        chats = db.list_archived_chats()
        if not chats:
            self._show_system_message("No archived chats.")
            return
        lines = ["Archived chats:"]
        for c in chats[:20]:
            lines.append(f"  [{c.id}] {c.title}")
        self._show_system_message("\n".join(lines))

    def _slash_snippet(self, arg: str) -> None:
        parts = arg.split(None, 1)
        subcmd = parts[0].lower() if parts else ""
        subarg = parts[1].strip() if len(parts) > 1 else ""
        if subcmd == "save":
            if not subarg:
                self._show_system_message("Usage: /snippet save <name>\nSaves clipboard text.")
                return
            text = QApplication.clipboard().text()
            if not text:
                self._show_system_message("Clipboard is empty.")
                return
            snippets = load_snippets()
            snippets = [s for s in snippets if s["name"].lower() != subarg.lower()]
            snippets.append({"name": subarg, "content": text})
            save_snippets(snippets)
            self._show_system_message(f"Saved snippet: {subarg} ({len(text)} chars)")
        elif subcmd == "paste":
            if not subarg:
                self._show_system_message("Usage: /snippet paste <name>")
                return
            snippets = load_snippets()
            found = None
            for s in snippets:
                if s["name"].lower() == subarg.lower():
                    found = s
                    break
            if not found:
                self._show_system_message(f"No snippet named '{subarg}'.")
                return
            cursor = self.input_box.textCursor()
            cursor.insertText(found["content"])
            self.input_box.setTextCursor(cursor)
        elif subcmd == "list":
            snippets = load_snippets()
            if not snippets:
                self._show_system_message("No saved snippets.")
                return
            lines = ["Saved snippets:"]
            for s in snippets:
                preview = s["content"][:50].replace("\n", " ")
                lines.append(f"  {s['name']} — {preview}...")
            self._show_system_message("\n".join(lines))
        elif subcmd == "delete":
            if not subarg:
                self._show_system_message("Usage: /snippet delete <name>")
                return
            snippets = load_snippets()
            new = [s for s in snippets if s["name"].lower() != subarg.lower()]
            if len(new) == len(snippets):
                self._show_system_message(f"No snippet named '{subarg}'.")
                return
            save_snippets(new)
            self._show_system_message(f"Deleted snippet: {subarg}")
        else:
            self._show_system_message("Usage: /snippet <save|paste|list|delete> [name]")

    def _slash_summary(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._show_system_message("Cannot summarize while streaming.")
            return
        messages = db.get_messages(self._current_chat_id)
        if not messages:
            self._show_system_message("No messages to summarize.")
            return
        summary_text = "\n".join(
            f"{'User' if m.role == 'user' else 'Claude'}: {(m.content or '')[:200]}"
            for m in messages if m.role in ("user", "assistant") and m.content
        )
        db.add_message(self._current_chat_id, "user",
                        f"Summarize this conversation in one paragraph:\n{summary_text}")
        db.add_message(self._current_chat_id, "assistant", "")
        self._stream_buffer = []
        self._render_messages(db.get_messages(self._current_chat_id))
        self._start_streaming_from_current_history()

    def _slash_split(self, arg: str) -> None:
        if not arg:
            self.split_view.setVisible(not self.split_view.isVisible())
            if not self.split_view.isVisible():
                self._show_system_message("Split view closed.")
            return
        for c in db.list_chats(include_archived=True):
            if arg.lower() in c.title.lower():
                msgs = db.get_messages(c.id)
                parts = [f'<div style="max-width:780px;margin:0 auto;">']
                for m in msgs:
                    parts.append(self._render_message_html(
                        m.role, m.content, compact=True,
                    ))
                parts.append("</div>")
                self.split_view.setHtml("".join(parts))
                self.split_view.setVisible(True)
                self._show_system_message(f"Split view: {c.title}")
                return
        self._show_system_message(f"No chat matching '{arg}'.")

    def _slash_automodel(self) -> None:
        self.settings.auto_model = not self.settings.auto_model
        save_settings(self.settings)
        self._show_system_message(
            f"Auto-model switching {'on' if self.settings.auto_model else 'off'}.\n"
            "Short/simple → Haiku, complex/code → Opus, default → current model."
        )

    def _slash_schedule(self, arg: str) -> None:
        import re as _re
        match = _re.match(r'(\d+)([smh])\s+(.*)', arg, _re.DOTALL)
        if not match:
            self._show_system_message("Usage: /schedule <N><s|m|h> <message>\nExample: /schedule 5m check the build")
            return
        num, unit, message = int(match.group(1)), match.group(2), match.group(3).strip()
        ms = num * {"s": 1000, "m": 60_000, "h": 3_600_000}[unit]
        if ms > 86_400_000:
            self._show_system_message("Maximum schedule delay is 24 hours.")
            self.input_box.clear()
            return
        from PySide6.QtCore import QTimer
        QTimer.singleShot(ms, lambda: self._scheduled_send(message))
        self._show_system_message(f"Scheduled in {num}{unit}: {message}")

    def _scheduled_send(self, message: str) -> None:
        if self._current_chat_id is None:
            self._on_new_chat()
        self.input_box.setPlainText(message)
        self._on_send()

    def _slash_link(self, arg: str) -> None:
        if not arg:
            self._show_system_message("Usage: /link <chat title>\nPulls last few messages as context.")
            return
        for c in db.list_chats(include_archived=True):
            if arg.lower() in c.title.lower():
                msgs = db.get_messages(c.id)
                recent = [m for m in msgs if m.role in ("user", "assistant")][-4:]
                if not recent:
                    self._show_system_message(f"Chat '{c.title}' is empty.")
                    return
                context = f"Context from '{c.title}':\n"
                for m in recent:
                    role = "User" if m.role == "user" else "Claude"
                    context += f"{role}: {(m.content or '')[:300]}\n"
                cursor = self.input_box.textCursor()
                cursor.insertText(context + "\n")
                self.input_box.setTextCursor(cursor)
                return
        self._show_system_message(f"No chat matching '{arg}'.")

    def _slash_history(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        edits = db.get_edit_history(self._current_chat_id)
        if not edits:
            self._show_system_message("No edit history for this chat.")
            return
        lines = ["Edit history (most recent first):"]
        for e in edits[:10]:
            preview = (e["original_content"] or "")[:80].replace("\n", " ")
            lines.append(f"  [{e['replaced_at'][:16]}] {e['role']}: {preview}...")
        self._show_system_message("\n".join(lines))

    def _slash_replace(self, arg: str) -> None:
        parts = arg.split(" -> ", 1) if " -> " in arg else arg.split(" => ", 1)
        if len(parts) != 2:
            self._show_system_message("Usage: /replace old text -> new text")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        old, new = parts[0].strip(), parts[1].strip()
        count = db.replace_in_messages(self._current_chat_id, old, new)
        self._render_messages(db.get_messages(self._current_chat_id))
        self._show_system_message(f"Replaced in {count} message(s): '{old}' -> '{new}'")

    def _slash_heatmap(self) -> None:
        chats = db.list_chats(include_archived=True)
        if not chats:
            self._show_system_message("No chats.")
            return
        from collections import Counter
        hours = Counter()
        for c in chats:
            try:
                h = int(c.created_at[11:13])
                hours[h] += 1
            except (ValueError, IndexError):
                pass
        if not hours:
            self._show_system_message("No data for heatmap.")
            return
        max_v = max(hours.values())
        blocks = " ░▒▓█"
        lines = ["Chat activity by hour:"]
        for h in range(24):
            v = hours.get(h, 0)
            level = int(v / max_v * 4) if max_v else 0
            bar = blocks[level] * 3
            lines.append(f"  {h:02d}:00  {bar}  ({v})")
        self._show_system_message("\n".join(lines))

    def _slash_cost(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        stats = db.chat_stats(self._current_chat_id)
        if not stats.get("msg_count"):
            self._show_system_message("Empty chat.")
            return
        model = self.model_picker.currentData() or ""
        pricing = MODEL_PRICING.get(model, (3.0, 15.0))
        user_chars = sum(len(m.content or "") for m in db.get_messages(self._current_chat_id) if m.role == "user")
        asst_chars = sum(len(m.content or "") for m in db.get_messages(self._current_chat_id) if m.role == "assistant")
        in_tokens = user_chars // 4
        out_tokens = asst_chars // 4
        in_cost = in_tokens * pricing[0] / 1_000_000
        out_cost = out_tokens * pricing[1] / 1_000_000
        total = in_cost + out_cost
        self._show_system_message(
            f"Estimated cost ({model_display_name(model)}):\n"
            f"  Input: ~{in_tokens:,} tokens (${in_cost:.4f})\n"
            f"  Output: ~{out_tokens:,} tokens (${out_cost:.4f})\n"
            f"  Total: ${total:.4f}"
        )

    def _slash_search(self, arg: str) -> None:
        parts = arg.split(None, 1)
        role = None
        query = arg
        if len(parts) >= 2 and parts[0].lower() in ("user", "assistant"):
            role = parts[0].lower()
            query = parts[1]
        if not query.strip():
            self._show_system_message("Usage: /search [user|assistant] <query>")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        results = db.search_messages(self._current_chat_id, query.strip(), role)
        if not results:
            self._show_system_message(f"No messages matching '{query.strip()}'.")
            return
        lines = [f"Found {len(results)} match(es):"]
        for r in results[:15]:
            preview = (r["content"] or "")[:80].replace("\n", " ")
            lines.append(f"  [{r['role']}] {preview}")
        self._show_system_message("\n".join(lines))

    def _slash_autotitle(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._show_system_message("Cannot auto-title while streaming.")
            return
        messages = db.get_messages(self._current_chat_id)
        if not messages:
            self._show_system_message("No messages.")
            return
        context = "\n".join(
            f"{'User' if m.role == 'user' else 'Claude'}: {(m.content or '')[:100]}"
            for m in messages[:4] if m.content
        )
        db.add_message(self._current_chat_id, "user",
                        f"Generate a short title (max 6 words) for this conversation. "
                        f"Reply with ONLY the title, nothing else:\n{context}")
        db.add_message(self._current_chat_id, "assistant", "")
        self._stream_buffer = []
        self._render_messages(db.get_messages(self._current_chat_id))
        self._start_streaming_from_current_history()

    def _slash_merge(self, arg: str) -> None:
        if not arg:
            self._show_system_message("Usage: /merge <chat title>")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        for c in db.list_chats(include_archived=True):
            if arg.lower() in c.title.lower() and c.id != self._current_chat_id:
                count = db.merge_chat_into(c.id, self._current_chat_id)
                self._render_messages(db.get_messages(self._current_chat_id))
                self._show_system_message(f"Merged {count} messages from '{c.title}'.")
                return
        self._show_system_message(f"No chat matching '{arg}'.")

    def _slash_grep(self, arg: str) -> None:
        if not arg.strip():
            self._show_system_message("Usage: /grep <regex pattern>")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        if len(arg.strip()) > 200:
            self._show_system_message("Regex too long (max 200 chars).")
            return
        try:
            pattern = re.compile(arg.strip(), re.IGNORECASE)
            _redos_test = pattern.search("a" * 1000)
        except (re.error, RecursionError) as e:
            self._show_system_message(f"Invalid regex: {e}")
            return
        messages = db.get_messages(self._current_chat_id)
        matches = []
        for m in messages:
            for i, line in enumerate((m.content or "").split("\n")):
                if pattern.search(line):
                    role = "You" if m.role == "user" else "Claude"
                    matches.append(f"  [{role} L{i+1}] {line.strip()[:100]}")
        if not matches:
            self._show_system_message(f"No matches for /{arg.strip()}/")
            return
        lines = [f"Grep: {len(matches)} match(es)"] + matches[:30]
        if len(matches) > 30:
            lines.append(f"  ... and {len(matches) - 30} more")
        self._show_system_message("\n".join(lines))

    def _slash_ephemeral(self) -> None:
        model = self.model_picker.currentData() or self.settings.default_model
        c = db.create_chat(title="Ephemeral chat", model=model)
        db.set_ephemeral(c.id, 1)
        self._current_chat_id = c.id
        self._refresh_chat_list()
        for i in range(self.chat_list.count()):
            it = self.chat_list.item(i)
            if it.data(Qt.UserRole) == c.id:
                self.chat_list.setCurrentItem(it)
                break
        self.input_box.setFocus()
        self._show_system_message("Ephemeral chat — will be deleted when you close Oracle.")

    def _slash_budget(self, arg: str) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        if not arg.strip():
            chat = db.get_chat(self._current_chat_id)
            budget = chat.token_budget if chat else 0
            if budget:
                self._show_system_message(f"Token budget: {budget:,}")
            else:
                self._show_system_message("No token budget set. Usage: /budget <N> (e.g. /budget 10000)")
            return
        raw = arg.strip().lower().replace("k", "000").replace(",", "")
        try:
            budget = int(raw)
        except ValueError:
            self._show_system_message("Usage: /budget <N> (e.g. /budget 10k)")
            return
        db.set_token_budget(self._current_chat_id, budget)
        self._show_system_message(f"Token budget set to {budget:,}.")

    def _slash_favorite(self, arg: str) -> None:
        if not arg:
            self._show_system_message("Usage: /favorite <model name>")
            return
        matched = None
        for display, mid in MODELS.items():
            if arg.lower() in display.lower() or arg.lower() in mid.lower():
                matched = mid
                break
        if not matched:
            self._show_system_message(f"No model matching '{arg}'.")
            return
        favs = [f for f in self.settings.favorite_models.split(",") if f.strip()]
        if matched not in favs:
            favs.insert(0, matched)
        self.settings.favorite_models = ",".join(favs)
        save_settings(self.settings)
        self._rebuild_model_picker()
        self._show_system_message(f"Favorited: {model_display_name(matched)}")

    def _slash_unfavorite(self, arg: str) -> None:
        if not arg:
            self._show_system_message("Usage: /unfavorite <model name>")
            return
        matched = None
        for display, mid in MODELS.items():
            if arg.lower() in display.lower() or arg.lower() in mid.lower():
                matched = mid
                break
        if not matched:
            self._show_system_message(f"No model matching '{arg}'.")
            return
        favs = [f for f in self.settings.favorite_models.split(",") if f.strip()]
        favs = [f for f in favs if f != matched]
        self.settings.favorite_models = ",".join(favs)
        save_settings(self.settings)
        self._rebuild_model_picker()
        self._show_system_message(f"Unfavorited: {model_display_name(matched)}")

    def _rebuild_model_picker(self) -> None:
        current = self.model_picker.currentData()
        self.model_picker.blockSignals(True)
        self.model_picker.clear()
        favs = [f.strip() for f in self.settings.favorite_models.split(",") if f.strip()]
        added = set()
        for mid in favs:
            display = model_display_name(mid)
            if display != mid:
                self.model_picker.addItem(f"★ {display}", mid)
                added.add(mid)
        for display, mid in MODELS.items():
            if mid not in added:
                self.model_picker.addItem(display, mid)
                added.add(mid)
        if self.settings.auth_mode == AUTH_CUSTOM and self.settings.custom_model:
            cmid = self.settings.custom_model
            if cmid not in added:
                self.model_picker.addItem(f"[Custom] {cmid}", cmid)
        idx = self.model_picker.findData(current)
        if idx >= 0:
            self.model_picker.setCurrentIndex(idx)
        self.model_picker.blockSignals(False)

    def _slash_timeline(self) -> None:
        timeline = db.get_all_chats_timeline()
        if not timeline:
            self._show_system_message("No chats.")
            return
        lines = ["Chat timeline:"]
        for t in timeline[:30]:
            date = (t["created_at"] or "")[:10]
            msg = (t["first_msg"] or "")[:60].replace("\n", " ")
            lines.append(f"  {date}  {t['title'][:30]}")
            if msg:
                lines.append(f"           {msg}")
        self._show_system_message("\n".join(lines))

    def _slash_format(self, arg: str) -> None:
        valid = {"", "code", "prose", "bullets", "table"}
        if arg.lower() not in valid:
            self._show_system_message(f"Current: {self.settings.response_format or 'none'}\n"
                                       f"Usage: /format <{'|'.join(sorted(valid - {''}))}> (empty to clear)")
            return
        self.settings.response_format = arg.lower()
        save_settings(self.settings)
        if arg:
            self._show_system_message(f"Response format set to: {arg.lower()}")
        else:
            self._show_system_message("Response format cleared.")

    def _slash_persona(self, arg: str) -> None:
        if not arg:
            current = self.settings.persona
            names = ", ".join(PERSONAS.keys())
            self._show_system_message(f"Current: {current or 'none'}\nAvailable: {names}\nUse /persona <name> or /persona off")
            return
        if arg.lower() == "off":
            self.settings.persona = ""
            save_settings(self.settings)
            self._show_system_message("Persona cleared.")
            return
        if arg.lower() not in PERSONAS:
            self._show_system_message(f"Unknown persona. Available: {', '.join(PERSONAS.keys())}")
            return
        self.settings.persona = arg.lower()
        save_settings(self.settings)
        self._show_system_message(f"Persona set to: {arg.lower()}\n{PERSONAS[arg.lower()][:80]}...")

    def _slash_workspace(self, arg: str) -> None:
        if not arg:
            self._show_system_message("Usage: /workspace <directory path>\nAdds file listing as context.")
            return
        p = Path(arg.strip())
        if not p.is_dir():
            self._show_system_message(f"Not a directory: {arg}")
            return
        files = []
        gitignore = set()
        gi_path = p / ".gitignore"
        if gi_path.exists():
            for line in gi_path.read_text(errors="replace").split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    gitignore.add(line.strip("/"))
        for root, dirs, fnames in os.walk(str(p), followlinks=False):
            rel_root = os.path.relpath(root, str(p))
            parts = rel_root.split("/") if rel_root != "." else []
            skip = {"node_modules", "__pycache__", ".git", ".venv", "venv"}
            if any(part in gitignore or part.startswith(".") or part in skip for part in parts):
                dirs.clear()
                continue
            for fn in sorted(fnames):
                rel = os.path.join(rel_root, fn) if rel_root != "." else fn
                files.append(rel)
                if len(files) >= 200:
                    break
            if len(files) >= 200:
                break
        if not files:
            self._show_system_message("No files found.")
            return
        listing = f"Files in {p}:\n" + "\n".join(f"  {f}" for f in files)
        if len(files) >= 200:
            listing += "\n  ... (truncated at 200)"
        cursor = self.input_box.textCursor()
        cursor.insertText(f"[Workspace: {p}]\n{listing}\n\n")
        self.input_box.setTextCursor(cursor)
        self._show_system_message(f"Added {len(files)} files from {p} as context.")

    def _slash_checkpoint(self, arg: str) -> None:
        if not arg.strip():
            if self._current_chat_id:
                names = db.list_checkpoints(self._current_chat_id)
                if names:
                    self._show_system_message(f"Checkpoints: {', '.join(names)}")
                else:
                    self._show_system_message("No checkpoints. Usage: /checkpoint <name>")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        db.save_checkpoint(self._current_chat_id, arg.strip())
        self._show_system_message(f"Checkpoint saved: {arg.strip()}")

    def _slash_restore(self, arg: str) -> None:
        if not arg.strip():
            self._show_system_message("Usage: /restore <checkpoint name>")
            return
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        if db.restore_checkpoint(self._current_chat_id, arg.strip()):
            self._render_messages(db.get_messages(self._current_chat_id))
            self._show_system_message(f"Restored to checkpoint: {arg.strip()}")
        else:
            self._show_system_message(f"No checkpoint named '{arg.strip()}'.")

    def _slash_notes(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        annotations = db.get_annotations(self._current_chat_id)
        if not annotations:
            self._show_system_message("No annotations in this chat.")
            return
        lines = ["Annotations:"]
        for a in annotations:
            role = "You" if a["role"] == "user" else "Claude"
            content_preview = (a["content"] or "")[:40].replace("\n", " ")
            lines.append(f"  [{role}] {content_preview}...")
            lines.append(f"    Note: {a['annotation']}")
        self._show_system_message("\n".join(lines))

    def _slash_searchall(self, arg: str) -> None:
        if not arg.strip():
            self._show_system_message("Usage: /searchall <query>")
            return
        results = db.search_all_chats(arg.strip())
        if not results:
            self._show_system_message(f"No matches for '{arg.strip()}' across chats.")
            return
        by_chat: Dict[str, List] = {}
        for r in results:
            by_chat.setdefault(r["chat_title"], []).append(r)
        lines = [f"Found {len(results)} match(es) across {len(by_chat)} chat(s):"]
        for title, msgs in list(by_chat.items())[:10]:
            lines.append(f"\n  {title}:")
            for m in msgs[:3]:
                preview = (m["content"] or "")[:60].replace("\n", " ")
                lines.append(f"    [{m['role']}] {preview}")
        self._show_system_message("\n".join(lines))

    def _slash_autoclean(self, arg: str) -> None:
        if not arg.strip():
            self._show_system_message("Usage: /autoclean <N>d — archive chats older than N days")
            return
        raw = arg.strip().rstrip("d")
        try:
            days = int(raw)
        except ValueError:
            self._show_system_message("Usage: /autoclean 30d")
            return
        count = db.auto_archive_stale(days)
        self._refresh_chat_list()
        self._show_system_message(f"Archived {count} chat(s) older than {days} days.")

    def _slash_gallery(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        atts = db.get_all_attachments(self._current_chat_id)
        images = [a for a in atts if a["kind"] == "image"]
        if not images:
            self._show_system_message("No images in this chat.")
            return
        lines = [f"Gallery ({len(images)} images):"]
        for a in images:
            lines.append(f"  {a['original_name']} — {a['stored_path']}")
        self._show_system_message("\n".join(lines))

    def _slash_filter(self, arg: str) -> None:
        parts = arg.split(None, 1)
        subcmd = parts[0].lower() if parts else ""
        subarg = parts[1].strip() if len(parts) > 1 else ""
        if subcmd == "save":
            if not subarg:
                self._show_system_message("Usage: /filter save <name>")
                return
            query = self.sidebar_search.text()
            if not query:
                self._show_system_message("Sidebar search is empty — type a search first.")
                return
            filters = load_filters()
            filters[subarg] = query
            save_filters(filters)
            self._show_system_message(f"Saved filter: {subarg} = '{query}'")
        elif subcmd == "load":
            if not subarg:
                self._show_system_message("Usage: /filter load <name>")
                return
            filters = load_filters()
            if subarg not in filters:
                self._show_system_message(f"No filter named '{subarg}'.")
                return
            self.sidebar_search.setText(filters[subarg])
        elif subcmd == "list":
            filters = load_filters()
            if not filters:
                self._show_system_message("No saved filters.")
                return
            lines = ["Saved filters:"]
            for name, query in filters.items():
                lines.append(f"  {name} — '{query}'")
            self._show_system_message("\n".join(lines))
        elif subcmd == "delete":
            filters = load_filters()
            if subarg in filters:
                del filters[subarg]
                save_filters(filters)
                self._show_system_message(f"Deleted filter: {subarg}")
            else:
                self._show_system_message(f"No filter named '{subarg}'.")
        else:
            self._show_system_message("Usage: /filter <save|load|list|delete> [name]")

    def _slash_exporthtml(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        messages = db.get_messages(self._current_chat_id)
        if not messages:
            self._show_system_message("Empty chat.")
            return
        title = self.chat_title_label.text().strip() or "conversation"
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:60]
        path, _ = QFileDialog.getSaveFileName(self, "Export as HTML", f"{safe_title}.html",
                                               "HTML (*.html);;All files (*)")
        if not path:
            return
        parts = [f'<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
                 f'<style>body{{background:#0B1220;color:#E5ECF7;font-family:sans-serif;max-width:800px;margin:0 auto;padding:20px}}'
                 f'.user{{background:#17223B;border-radius:10px;padding:12px;margin:14px 0}}'
                 f'.asst{{background:#0B1220;border:1px solid #1E2A45;border-radius:10px;padding:12px;margin:14px 0}}'
                 f'.role{{font-size:11px;font-weight:600;text-transform:uppercase;margin-bottom:4px}}'
                 f'.you{{color:#94A3B8}}.claude{{color:#60A5FA}}'
                 f'</style></head><body>']
        parts.append(f'<h1>{html.escape(title)}</h1>')
        for m in messages:
            if m.role == "user":
                parts.append(f'<div class="role you">You</div><div class="user">{html.escape(m.content or "")}</div>')
            elif m.role == "assistant":
                parts.append(f'<div class="role claude">Claude</div><div class="asst">{render_markdown(m.content or "")}</div>')
        parts.append('</body></html>')
        try:
            Path(path).write_text("".join(parts), encoding="utf-8")
            self._show_system_message(f"Exported to {path}")
        except OSError as e:
            self._show_system_message(f"Error: {e}")

    def _slash_systempromptpreview(self) -> None:
        parts = []
        if self.settings.persona and self.settings.persona in PERSONAS:
            parts.append(f"Persona ({self.settings.persona}): {PERSONAS[self.settings.persona][:80]}...")
        fmt_hints = {"code": "Code-focused", "prose": "Prose", "bullets": "Bullets", "table": "Tables"}
        if self.settings.response_format in fmt_hints:
            parts.append(f"Format: {fmt_hints[self.settings.response_format]}")
        length_map = {"brief": "Concise", "detailed": "Detailed"}
        if self.settings.response_length in length_map:
            parts.append(f"Length: {length_map[self.settings.response_length]}")
        if self._current_chat_id:
            chat = db.get_chat(self._current_chat_id)
            if chat and chat.chat_system_prompt:
                parts.append(f"Chat prompt: {chat.chat_system_prompt[:80]}...")
        if self.settings.system_prompt:
            parts.append(f"Global prompt: {self.settings.system_prompt[:80]}...")
        if not parts:
            parts.append("(no system prompt configured)")
        self._show_system_message("Effective system prompt:\n  " + "\n  ".join(parts))

    def _slash_typewriter(self) -> None:
        self.settings.typewriter_mode = not self.settings.typewriter_mode
        save_settings(self.settings)
        self._show_system_message(f"Typewriter mode {'on' if self.settings.typewriter_mode else 'off'}.")

    def _slash_rawmd(self) -> None:
        self.settings.show_raw_md = not self.settings.show_raw_md
        save_settings(self.settings)
        if self._current_chat_id:
            self._render_messages(db.get_messages(self._current_chat_id))
        self._show_system_message(f"Raw markdown {'on' if self.settings.show_raw_md else 'off'}.")

    def _slash_chatcolor(self, arg: str) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        colors = {"red": "#EF4444", "yellow": "#FBBF24", "green": "#22C55E",
                  "blue": "#3B82F6", "purple": "#A855F7", "clear": ""}
        if arg.lower() not in colors:
            self._show_system_message(f"Usage: /chatcolor <{'|'.join(colors.keys())}>")
            return
        db.set_chat_color(self._current_chat_id, colors[arg.lower()])
        self._refresh_chat_list()
        self._show_system_message(f"Chat color: {arg.lower()}")

    def _slash_macro(self, arg: str) -> None:
        parts = arg.split(None, 2)
        subcmd = parts[0].lower() if parts else ""
        if subcmd == "save" and len(parts) >= 3:
            name, text = parts[1], parts[2]
            macros = load_macros()
            macros[name] = text
            save_macros(macros)
            self._show_system_message(f"Saved macro: !!{name}")
        elif subcmd == "list":
            macros = load_macros()
            if not macros:
                self._show_system_message("No macros. Usage: /macro save <name> <text>")
                return
            lines = ["Macros:"]
            for name, text in macros.items():
                lines.append(f"  !!{name} — {text[:50]}")
            self._show_system_message("\n".join(lines))
        elif subcmd == "delete" and len(parts) >= 2:
            macros = load_macros()
            if parts[1] in macros:
                del macros[parts[1]]
                save_macros(macros)
                self._show_system_message(f"Deleted macro: !!{parts[1]}")
            else:
                self._show_system_message(f"No macro named '{parts[1]}'.")
        else:
            self._show_system_message("Usage: /macro save <name> <text> | /macro list | /macro delete <name>")

    def _slash_dashboard(self) -> None:
        s = db.dashboard_stats()
        self._show_system_message(
            f"Dashboard:\n"
            f"  Active chats: {s['total_chats']}\n"
            f"  Total messages: {s['total_messages']:,}\n"
            f"  Messages this week: {s['messages_this_week']}\n"
            f"  Favorite model: {model_display_name(s['favorite_model'])}\n"
            f"  Avg response length: ~{s['avg_response_chars'] // 4} tokens"
        )

    def _slash_timer(self) -> None:
        elapsed = time.monotonic() - self._session_start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        self._show_system_message(f"Session time: {mins}m {secs}s")

    def _slash_tree(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        chat = db.get_chat(self._current_chat_id)
        if not chat:
            return
        title = chat.title
        branches = [c for c in db.list_chats(include_archived=True)
                    if c.title.startswith(f"Branch of {title}")]
        if not branches:
            self._show_system_message(f"No branches from '{title}'.")
            return
        lines = [f"Branches from '{title}':"]
        for b in branches:
            lines.append(f"  +-- {b.title} ({b.created_at[:10]})")
        self._show_system_message("\n".join(lines))

    def _searxng_search(self, query: str, num_results: int = 5) -> List[dict]:
        """Query SearXNG and return results as list of {title, url, content}."""
        url = self.settings.searxng_url.rstrip("/")
        if not url:
            return []
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            self._show_system_message("Invalid SearXNG URL: must use http:// or https://")
            return []
        params = urllib.parse.urlencode({
            "q": query, "format": "json", "categories": "general",
            "language": "en", "pageno": "1",
        })
        try:
            req = urllib.request.Request(
                f"{url}/search?{params}",
                headers={"User-Agent": "Oracle-Chat/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            results = []
            for r in data.get("results", [])[:num_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                })
            return results
        except Exception as e:
            self._show_system_message(f"SearXNG error: {e}")
            return []

    def _format_search_results(self, query: str, results: List[dict]) -> str:
        """Format search results as context for the model."""
        if not results:
            return f"[Web search for '{query}' returned no results]"
        parts = [f"Web search results for '{query}':"]
        for i, r in enumerate(results, 1):
            parts.append(f"\n[{i}] {r['title']}\n    {r['url']}\n    {r['content']}")
        return "\n".join(parts)

    def _slash_web(self, arg: str) -> None:
        if not arg.strip():
            self._show_system_message("Usage: /web <query>\nSearches via SearXNG and adds results as context.")
            return
        if not self.settings.searxng_url:
            self._show_system_message(
                "SearXNG URL not configured.\n"
                "Set it in Settings → Auth → SearXNG URL (e.g. http://localhost:8888)")
            return
        self._show_system_message(f"Searching: {arg.strip()}...")
        results = self._searxng_search(arg.strip())
        if not results:
            return
        formatted = self._format_search_results(arg.strip(), results)
        # Show results as system message
        lines = [f"Found {len(results)} result(s):"]
        for r in results:
            lines.append(f"  {r['title']}")
            lines.append(f"    {r['url']}")
            if r['content']:
                lines.append(f"    {r['content'][:120]}")
        self._show_system_message("\n".join(lines))
        # Inject into input as context
        cursor = self.input_box.textCursor()
        cursor.insertText(f"[Web search context]\n{formatted}\n\n")
        self.input_box.setTextCursor(cursor)
        self.input_box.setFocus()

    def _on_web_search_btn(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        if not self.settings.searxng_url:
            self._show_system_message(
                "SearXNG URL not configured. Set it in Settings → Auth → SearXNG URL.")
            return
        query, ok = QInputDialog.getText(self, "Web Search", "Search query:")
        if ok and query.strip():
            self._slash_web(query.strip())

    def _slash_diff(self, arg: str) -> None:
        if not arg.strip():
            self._show_system_message("Usage: /diff <file path>\nShows what Apply would change.")
            return
        fpath = Path(arg.strip())
        blocks = getattr(self, "_all_code_blocks", [])
        if not blocks:
            self._show_system_message("No code blocks in this conversation.")
            return
        code = blocks[-1]
        if not fpath.exists():
            self._show_system_message(f"File not found: {fpath}\nApply would create it with {len(code.split(chr(10)))} lines.")
            return
        existing = fpath.read_text(encoding="utf-8", errors="replace").split("\n")
        new_lines = code.split("\n")
        added = len(set(new_lines) - set(existing))
        removed = len(set(existing) - set(new_lines))
        self._show_system_message(
            f"Diff preview for {fpath.name}:\n"
            f"  Existing: {len(existing)} lines\n"
            f"  New: {len(new_lines)} lines\n"
            f"  +{added} added, -{removed} removed"
        )

    def _on_history_prev(self) -> None:
        if self._current_chat_id is None:
            return
        if not self._input_history:
            self._input_history = db.get_user_messages(self._current_chat_id)
            self._input_history_idx = -1
        if self._input_history_idx < len(self._input_history) - 1:
            self._input_history_idx += 1
            self.input_box.setPlainText(self._input_history[self._input_history_idx])

    def _on_history_next(self) -> None:
        if self._input_history_idx > 0:
            self._input_history_idx -= 1
            self.input_box.setPlainText(self._input_history[self._input_history_idx])
        elif self._input_history_idx == 0:
            self._input_history_idx = -1
            self.input_box.clear()

    # ── Memory ────────────────────────────────────────────────────────────
    def _slash_memory(self, arg: str) -> None:
        parts = arg.split(None, 1)
        subcmd = parts[0].lower() if parts else ""
        subarg = parts[1].strip() if len(parts) > 1 else ""
        if subcmd == "add":
            if not subarg:
                self._show_system_message("Usage: /memory add <fact>")
                return
            title = self.chat_title_label.text() if self._current_chat_id else ""
            add_memory(subarg, title)
            self._show_system_message(f"Remembered: {subarg}")
        elif subcmd == "delete":
            try:
                idx = int(subarg) - 1
            except (ValueError, TypeError):
                self._show_system_message("Usage: /memory delete <number>")
                return
            facts = load_memory()
            if 0 <= idx < len(facts):
                removed = facts.pop(idx)
                save_memory(facts)
                self._show_system_message(f"Forgot: {removed['fact']}")
            else:
                self._show_system_message("Invalid index.")
        elif subcmd == "clear":
            save_memory([])
            self._show_system_message("All memories cleared.")
        else:
            facts = load_memory()
            if not facts:
                self._show_system_message("No memories. Use /memory add <fact>.")
                return
            lines = ["Memories:"]
            for i, f in enumerate(facts, 1):
                lines.append(f"  {i}. {f['fact']}")
            self._show_system_message("\n".join(lines))

    # ── Projects ─────────────────────────────────────────────────────────
    def _slash_project(self, arg: str) -> None:
        parts = arg.split(None, 1)
        subcmd = parts[0].lower() if parts else ""
        subarg = parts[1].strip() if len(parts) > 1 else ""
        if subcmd == "create":
            if not subarg:
                self._show_system_message("Usage: /project create <name>")
                return
            save_project(subarg, {"name": subarg, "files": {}})
            self._show_system_message(f"Project created: {subarg}")
        elif subcmd == "switch":
            if not subarg:
                self._show_system_message("Usage: /project switch <name>")
                return
            if not load_project(subarg):
                self._show_system_message(f"No project named '{subarg}'.")
                return
            self.settings.active_project = subarg
            save_settings(self.settings)
            if self._current_chat_id:
                db.set_project(self._current_chat_id, subarg)
            self._show_system_message(f"Switched to project: {subarg}")
        elif subcmd == "addfile":
            if not subarg:
                self._show_system_message("Usage: /project addfile <path>")
                return
            proj = self.settings.active_project
            if not proj:
                self._show_system_message("No active project. Use /project switch <name> first.")
                return
            p = Path(subarg)
            if not p.exists():
                self._show_system_message(f"File not found: {subarg}")
                return
            try:
                content = p.read_text(encoding="utf-8", errors="replace")[:50000]
            except OSError as e:
                self._show_system_message(f"Error reading: {e}")
                return
            data = load_project(proj)
            files = data.get("files", {})
            files[str(p)] = content
            data["files"] = files
            save_project(proj, data)
            self._show_system_message(f"Added {p.name} to project {proj} ({len(content)} chars)")
        elif subcmd == "files":
            proj = self.settings.active_project
            if not proj:
                self._show_system_message("No active project.")
                return
            data = load_project(proj)
            files = data.get("files", {})
            if not files:
                self._show_system_message(f"Project {proj} has no files.")
                return
            lines = [f"Project {proj} files:"]
            for path, content in files.items():
                lines.append(f"  {path} ({len(content)} chars)")
            self._show_system_message("\n".join(lines))
        elif subcmd == "list":
            projects = list_projects()
            if not projects:
                self._show_system_message("No projects. Use /project create <name>.")
                return
            active = self.settings.active_project
            lines = ["Projects:"]
            for p in projects:
                marker = " (active)" if p == active else ""
                lines.append(f"  {p}{marker}")
            self._show_system_message("\n".join(lines))
        elif subcmd == "delete":
            if not subarg:
                self._show_system_message("Usage: /project delete <name>")
                return
            if delete_project(subarg):
                if self.settings.active_project == subarg:
                    self.settings.active_project = ""
                    save_settings(self.settings)
                self._show_system_message(f"Deleted project: {subarg}")
            else:
                self._show_system_message(f"No project named '{subarg}'.")
        else:
            self._show_system_message(
                "Usage: /project <create|switch|addfile|files|list|delete> [arg]\n"
                f"Active project: {self.settings.active_project or '(none)'}"
            )

    # ── Thinking effort ──────────────────────────────────────────────────
    def _slash_thinking(self, arg: str) -> None:
        valid = {"off", "low", "high", "max", ""}
        if arg.lower() not in valid:
            self._show_system_message(
                f"Current: {self.settings.thinking_effort or 'default'}\n"
                "Usage: /thinking off|low|high|max"
            )
            return
        self.settings.thinking_effort = arg.lower() if arg.lower() != "off" else "off"
        save_settings(self.settings)
        self._show_system_message(f"Thinking effort: {arg.lower() or 'default'}")

    # ── Research ─────────────────────────────────────────────────────────
    def _slash_research(self, arg: str) -> None:
        if not arg.strip():
            self._show_system_message("Usage: /research <query>\nDoes multi-step web research with citations.")
            return
        if not self.settings.searxng_url:
            self._show_system_message("SearXNG URL not configured. Set in Settings → Auth.")
            return
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._show_system_message("Cannot research while streaming.")
            return
        self._show_system_message(f"Researching: {arg.strip()}...")
        results = self._searxng_search(arg.strip(), num_results=5)
        if not results:
            self._show_system_message("No search results.")
            return
        sources = []
        context_parts = []
        for i, r in enumerate(results, 1):
            sources.append(r["url"])
            page_text = r.get("content", "")[:1500]
            context_parts.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{page_text}")
        set_citation_sources(sources)
        self._citation_sources = sources
        context = "\n\n".join(context_parts)
        research_prompt = (
            f"Based on these web sources, provide a comprehensive answer to: {arg.strip()}\n"
            f"Cite sources using [1], [2], etc.\n\n{context}"
        )
        if self._current_chat_id is None:
            self._on_new_chat()
        db.add_message(self._current_chat_id, "user", research_prompt)
        db.add_message(self._current_chat_id, "assistant", "")
        self._stream_buffer = []
        self._render_messages(db.get_messages(self._current_chat_id))
        self._start_streaming_from_current_history()

    # ── Fact-check ───────────────────────────────────────────────────────
    def _slash_factcheck(self) -> None:
        if self._current_chat_id is None:
            self._show_system_message("No active chat.")
            return
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._show_system_message("Cannot fact-check while streaming.")
            return
        messages = db.get_messages(self._current_chat_id)
        last_asst = None
        for m in reversed(messages):
            if m.role == "assistant" and m.content:
                last_asst = m.content
                break
        if not last_asst:
            self._show_system_message("No assistant response to fact-check.")
            return
        prompt = (
            "Fact-check the following response. For each factual claim, state whether it's "
            "CORRECT, UNCERTAIN, or INCORRECT. Be specific and cite your reasoning.\n\n"
            f"{last_asst}"
        )
        db.add_message(self._current_chat_id, "user", prompt)
        db.add_message(self._current_chat_id, "assistant", "")
        self._stream_buffer = []
        self._render_messages(db.get_messages(self._current_chat_id))
        self._start_streaming_from_current_history()

    # ── Preview HTML artifact ────────────────────────────────────────────
    def _on_preview_html(self, index: int) -> None:
        blocks = getattr(self, "_all_code_blocks", [])
        if 0 <= index < len(blocks):
            safe_html = re.sub(r'<\s*script', '<!-- script', blocks[index], flags=re.IGNORECASE)
            safe_html = re.sub(r'<\s*/\s*script', '<!-- /script', safe_html, flags=re.IGNORECASE)
            safe_html = re.sub(r'\bon\w+\s*=', 'data-blocked=', safe_html, flags=re.IGNORECASE)
            safe_html = re.sub(r'<\s*iframe', '<!-- iframe', safe_html, flags=re.IGNORECASE)
            self.split_view.setHtml(safe_html, QUrl("about:blank"))
            self.split_view.setVisible(True)

    # ── Citation link ────────────────────────────────────────────────────
    def _on_citation(self, index: int) -> None:
        sources = getattr(self, "_citation_sources", [])
        if 1 <= index <= len(sources):
            url = QUrl(sources[index - 1])
            if url.scheme() in ("http", "https"):
                QDesktopServices.openUrl(url)

    def _slash_help(self) -> None:
        self._show_system_message(
            "Commands: (Tab to autocomplete)\n"
            "  /clear /delete <N> /replace old -> new\n"
            "  /model /compare /automodel /favorite /unfavorite\n"
            "  /system /chatprompt /persona /format /length\n"
            "  /prompt /template /snippet — save|load|list|delete\n"
            "  /export /import /merge <chat> /link <chat>\n"
            "  /compact /focus /theme dark|light /split [chat]\n"
            "  /stats /wc /cost /context /heatmap /timeline\n"
            "  /tag /untag /tags /bookmarks /notes /history\n"
            "  /archive /archived /unarchive /ephemeral\n"
            "  /search [role] <q> /grep <regex>\n"
            "  /checkpoint <name> /restore <name> /diff <file>\n"
            "  /workspace <dir> /budget <N> /schedule <Ns|m|h> <msg>\n"
            "  /web /research /factcheck /memory /project /thinking\n"
            "  /summary /autotitle /notify /help"
        )

    def _slash_bookmarks(self) -> None:
        bookmarks = db.get_bookmarked_messages()
        if not bookmarks:
            self._show_system_message("No bookmarked messages.")
            return
        lines = ["Bookmarked messages:"]
        for b in bookmarks[:20]:
            preview = (b["content"] or "")[:80].replace("\n", " ")
            if len(b["content"] or "") > 80:
                preview += "..."
            lines.append(f"  [{b['chat_title']}] {b['role']}: {preview}")
        if len(bookmarks) > 20:
            lines.append(f"  ... and {len(bookmarks) - 20} more")
        self._show_system_message("\n".join(lines))

    def _show_system_message(self, text: str) -> None:
        if self._current_chat_id is None:
            msg_html = self._render_message_html("system", text)
            self.chat_view.setHtml(msg_html)
            return
        messages = db.get_messages(self._current_chat_id)
        html_parts = ['<div style="max-width:780px;margin:0 auto;">']
        for m in messages:
            html_parts.append(self._render_message_html(m.role, m.content, m.attachments))
        html_parts.append(self._render_message_html("system", text))
        html_parts.append("</div>")
        self.chat_view.setHtml("".join(html_parts))
        self._scroll_to_bottom()

    # ── @file expansion helper ───────────────────────────────────────────
    @staticmethod
    def _expand_at_files(text: str) -> str:
        """Expand @/path references to <file> blocks for the API."""
        matches = _AT_FILE_RE.findall(text)
        if not matches:
            return text
        context_parts = []
        for fpath in matches:
            safe_path = fpath.replace('"', '\\"')
            p = Path(fpath)
            try:
                if p.stat().st_size > _MAX_FILE_INLINE_BYTES:
                    context_parts.append(
                        f'<file path="{safe_path}">\n[File too large — {p.stat().st_size:,} bytes, '
                        f'max {_MAX_FILE_INLINE_BYTES:,}]\n</file>'
                    )
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")
                context_parts.append(f'<file path="{safe_path}">\n{content}\n</file>')
            except OSError as e:
                context_parts.append(f'<file path="{safe_path}">\n[Error reading file: {e}]\n</file>')
        return "\n".join(context_parts) + "\n\n" + text

    # ── Send / stream ────────────────────────────────────────────────────
    def _on_send(self) -> None:
        text = self.input_box.toPlainText().strip()
        if not text and not self._pending_attachments:
            return

        if text.startswith("/"):
            self._handle_slash_command(text)
            return

        if not self.settings.configured:
            QMessageBox.warning(self, "Oracle",
                "No API key configured. Open Settings (Ctrl+,) to add one.")
            return
        if self._streaming_worker and self._streaming_worker.isRunning():
            return

        if self._current_chat_id is None:
            self._on_new_chat()
            if self._current_chat_id is None:
                return

        # Context window warning
        if self._current_chat_id:
            stats = db.chat_stats(self._current_chat_id)
            est_tokens = stats.get("total_chars", 0) // 4
            if est_tokens > 180_000:
                if QMessageBox.question(
                    self, "Context warning",
                    f"This conversation is ~{est_tokens:,} tokens, near the context limit.\n"
                    "Older messages may be truncated. Continue?",
                    QMessageBox.Yes | QMessageBox.No
                ) != QMessageBox.Yes:
                    return

        # Expand macros (!!name → macro text)
        macros = load_macros()
        for name, expansion in macros.items():
            text = text.replace(f"!!{name}", expansion)

        display_text = text

        # Token budget check
        chat_obj = db.get_chat(self._current_chat_id)
        if chat_obj and chat_obj.token_budget:
            stats = db.chat_stats(self._current_chat_id)
            est = stats.get("total_chars", 0) // 4
            if est >= chat_obj.token_budget:
                self._show_system_message(
                    f"Token budget exceeded ({est:,} / {chat_obj.token_budget:,}). "
                    f"Use /budget 0 to remove the limit."
                )
                return

        user_msg = db.add_message(self._current_chat_id, "user", display_text)
        for spec in self._pending_attachments:
            try:
                db.add_attachment(
                    message_id=user_msg.id,
                    chat_id=self._current_chat_id,
                    kind=spec.kind,
                    source_path=spec.path,
                    mime=spec.mime,
                )
            except OSError as e:
                QMessageBox.warning(self, "Attachment error",
                                    f"Could not save {spec.display_name}: {e}")
        self._pending_attachments.clear()
        self._refresh_attach_row()
        db.add_message(self._current_chat_id, "assistant", "")
        self._stream_buffer = []

        existing_title = self.chat_title_label.text().strip()
        if existing_title in {"", "New chat", "Start a new chat"}:
            new_title = (display_text[:48] + ("…" if len(display_text) > 48 else "")).replace("\n", " ")
            db.rename_chat(self._current_chat_id, new_title)
            self._refresh_chat_list()
            for i in range(self.chat_list.count()):
                it = self.chat_list.item(i)
                if it.data(Qt.UserRole) == self._current_chat_id:
                    self.chat_list.setCurrentItem(it)
                    break
            self.chat_title_label.setText(new_title)

        self.input_box.clear()
        # Auto-model switching
        if self.settings.auto_model:
            has_code = "```" in display_text or "@/" in display_text
            is_short = len(display_text) < 50 and not has_code
            if is_short:
                auto_mid = "claude-haiku-4-5-20251001"
            elif has_code or len(display_text) > 500:
                auto_mid = "claude-opus-4-6"
            else:
                auto_mid = None
            if auto_mid:
                idx = self.model_picker.findData(auto_mid)
                if idx >= 0:
                    self.model_picker.blockSignals(True)
                    self.model_picker.setCurrentIndex(idx)
                    self.model_picker.blockSignals(False)
        self._render_messages(db.get_messages(self._current_chat_id))
        self._start_streaming_from_current_history()

    def _start_streaming_from_current_history(self) -> None:
        """Build API history from DB and start streaming a response."""
        if self._current_chat_id is None:
            return
        # Network errors are handled by the streaming worker's failed() signal
        msgs = db.get_messages(self._current_chat_id)
        api_history: List[Dict[str, Any]] = []
        last_user_build_error: Optional[str] = None
        for m in msgs:
            if m.role == "assistant":
                if m.content:
                    api_history.append({"role": "assistant", "content": m.content})
                continue
            if m.role != "user":
                continue
            api_text = self._expand_at_files(m.content)
            if not m.attachments:
                api_history.append({"role": "user", "content": api_text})
                continue
            blocks: List[Dict[str, Any]] = []
            for a in m.attachments:
                try:
                    spec = att.AttachmentSpec(path=Path(a.stored_path), kind=a.kind, mime=a.mime)
                    blocks.append(att.build_content_block(spec))
                except (att.AttachmentBuildError, OSError) as e:
                    last_user_build_error = f"{a.original_name}: {e}"
            if m.content:
                blocks.append({"type": "text", "text": api_text})
            elif blocks:
                blocks.append({"type": "text", "text": "(see attachments)"})
            if blocks:
                api_history.append({"role": "user", "content": blocks})
        if (api_history and api_history[-1]["role"] == "assistant"
                and not api_history[-1]["content"]):
            api_history = api_history[:-1]

        if last_user_build_error:
            QMessageBox.warning(self, "Attachment error",
                                f"Could not include an attachment: {last_user_build_error}")

        model = self.model_picker.currentData() or self.settings.default_model

        chat = db.get_chat(self._current_chat_id)
        system_prompt = (chat.chat_system_prompt if chat and chat.chat_system_prompt
                         else self.settings.system_prompt) or None
        # Inject persistent memory
        mem_facts = load_memory()
        if mem_facts:
            mem_text = "User facts to remember:\n" + "\n".join(f"- {f['fact']}" for f in mem_facts)
            system_prompt = f"{mem_text}\n\n{system_prompt}" if system_prompt else mem_text
        # Inject project context
        if self.settings.active_project:
            proj_data = load_project(self.settings.active_project)
            proj_files = proj_data.get("files", {})
            if proj_files:
                proj_ctx = f"Project '{self.settings.active_project}' files:\n"
                for fpath, content in list(proj_files.items())[:5]:
                    safe_fpath = fpath.replace('"', '\\"')
                    proj_ctx += f"\n<file path=\"{safe_fpath}\">\n{content[:5000]}\n</file>\n"
                system_prompt = f"{system_prompt}\n\n{proj_ctx}" if system_prompt else proj_ctx
        # Apply persona
        if self.settings.persona and self.settings.persona in PERSONAS:
            persona_text = PERSONAS[self.settings.persona]
            system_prompt = f"{persona_text}\n\n{system_prompt}" if system_prompt else persona_text
        # Apply format hint
        format_hints = {
            "code": "Respond primarily with code. Minimal explanation.",
            "prose": "Respond in prose paragraphs. No bullet points or code unless asked.",
            "bullets": "Respond using bullet points. Be concise.",
            "table": "Use tables to organize information where possible.",
        }
        fmt = format_hints.get(self.settings.response_format, "")
        if fmt:
            system_prompt = f"{fmt}\n\n{system_prompt}" if system_prompt else fmt
        length_prefixes = {
            "brief": "Keep responses concise — a few sentences max. ",
            "detailed": "Provide thorough, detailed responses with examples and explanations. ",
        }
        prefix = length_prefixes.get(self.settings.response_length, "")
        if prefix and system_prompt:
            system_prompt = prefix + system_prompt
        elif prefix:
            system_prompt = prefix.strip()

        if self.settings.auth_mode == AUTH_CLAUDE_CODE:
            last_user_text = ""
            for m in reversed(msgs):
                if m.role == "user":
                    last_user_text = self._expand_at_files(m.content)
                    break
            chat = db.get_chat(self._current_chat_id)
            resume_id = chat.claude_session_id if chat else None
            self._streaming_worker = ClaudeCodeWorker(
                user_message=last_user_text,
                model=model,
                system_prompt=system_prompt,
                binary=self.settings.claude_binary or "claude",
                resume_session_id=resume_id,
                parent=self,
            )
            self._streaming_worker.session_ready.connect(self._on_session_ready)
        elif self.settings.auth_mode == AUTH_BRIDGE:
            self._streaming_worker = BridgeWorker(
                bridge_ip=self.settings.bridge_ip,
                model=model,
                history=api_history,
                system_prompt=system_prompt,
                max_tokens=self.settings.max_tokens,
                api_key=self.settings.bridge_api_key,
                parent=self,
            )
        elif self.settings.auth_mode == AUTH_CUSTOM:
            self._streaming_worker = CustomGatewayWorker(
                url=self.settings.custom_api_url,
                api_key=self.settings.custom_api_key,
                model=self.settings.custom_model or model,
                history=api_history,
                system_prompt=system_prompt,
                max_tokens=self.settings.max_tokens,
                parent=self,
            )
        else:
            self._streaming_worker = StreamWorker(
                api_key=self.settings.api_key,
                model=model,
                history=api_history,
                system_prompt=system_prompt,
                max_tokens=self.settings.max_tokens,
                thinking_effort=self.settings.thinking_effort,
                parent=self,
            )

        self._streaming_worker.chunk.connect(self._append_chunk_to_last)
        self._streaming_worker.finished_ok.connect(self._on_stream_ok)
        self._streaming_worker.failed.connect(self._on_stream_failed)
        self._streaming_worker.finished.connect(self._on_worker_done)

        self._streaming_chat_id = self._current_chat_id
        self._stream_start_time = time.monotonic()
        self.token_label.setText("Thinking...")
        self.send_btn.setVisible(False)
        self.stop_btn.setVisible(True)
        self._streaming_worker.start()

    def _on_session_ready(self, session_id: str) -> None:
        cid = self._streaming_chat_id or self._current_chat_id
        if cid is not None and session_id:
            db.set_claude_session_id(cid, session_id)

    def _on_stop(self) -> None:
        if self._streaming_worker:
            self._streaming_worker.cancel()
            # Keep partial response instead of discarding
            partial = "".join(self._stream_buffer)
            if partial and self._current_chat_id:
                db.update_last_message(self._current_chat_id, partial)

    def _on_stream_ok(self, full_text: str) -> None:
        cid = self._streaming_chat_id or self._current_chat_id
        reason = "complete"
        worker_fr = getattr(self._streaming_worker, "finish_reason", None)
        if cid is not None:
            db.update_last_message(cid, full_text)
            msgs = db.get_messages(cid)
            if msgs and msgs[-1].role == "assistant":
                if self._stream_start_time:
                    db.set_response_time(msgs[-1].id, time.monotonic() - self._stream_start_time)
                if worker_fr == "length":
                    reason = "max_tokens"
                elif worker_fr and worker_fr != "stop":
                    reason = worker_fr
                elif full_text and len(full_text) >= self.settings.max_tokens * 4 \
                        and not full_text.rstrip().endswith((".", "!", "?", "```", ")")):
                    reason = "max_tokens"
                db.set_stop_reason(msgs[-1].id, reason)
        old_text = self._last_regen_old_text
        self._last_regen_old_text = None
        self._stream_buffer = []

        # Auto-continue if response appears cut off — only if user is still on this chat
        if (self.settings.auto_continue and full_text and cid
                and cid == self._current_chat_id
                and reason == "max_tokens"
                and not full_text.rstrip().endswith((".", "!", "?", "```", "*", ")", "]"))):
            db.add_message(cid, "user", "continue")
            db.add_message(cid, "assistant", "")
            self._render_messages(db.get_messages(cid))
            self.token_label.setText("Auto-continuing...")
            self._start_streaming_from_current_history()
            return

        self._quick_replies = ["Continue", "Explain further", "Give me an example"]
        self._show_quick_replies = True
        if cid == self._current_chat_id:
            self._render_messages(db.get_messages(cid) if cid else [])
        # Auto-extract memory from user requests
        if self._current_chat_id and full_text:
            msgs = db.get_messages(self._current_chat_id)
            for m in reversed(msgs):
                if m.role == "user" and m.content:
                    lower = m.content.lower()
                    if any(phrase in lower for phrase in ("remember that", "remember i", "note that i", "keep in mind")):
                        add_memory(m.content, self.chat_title_label.text())
                    break

        # Auto-title after first exchange
        if (self.settings.auto_title and self._current_chat_id
                and full_text and not old_text):
            msgs = db.get_messages(self._current_chat_id)
            user_msgs = [m for m in msgs if m.role == "user"]
            asst_msgs = [m for m in msgs if m.role == "assistant" and m.content]
            if len(user_msgs) == 1 and len(asst_msgs) == 1:
                first_q = user_msgs[0].content[:80]
                first_a = full_text[:80]
                title_hint = first_q.split("\n")[0][:48]
                if title_hint and title_hint != self.chat_title_label.text():
                    db.rename_chat(self._current_chat_id, title_hint)
                    self.chat_title_label.setText(title_hint)
                    self.setWindowTitle(f"Oracle — {title_hint}")
                    self._refresh_chat_list()

        if old_text and old_text != full_text:
            old_lines = set(old_text.strip().split("\n"))
            new_lines = set(full_text.strip().split("\n"))
            added = len(new_lines - old_lines)
            removed = len(old_lines - new_lines)
            self._show_system_message(f"Regenerated: +{added} / -{removed} lines changed")

    def _on_stream_failed(self, message: str) -> None:
        cid = self._streaming_chat_id or self._current_chat_id
        # Auto-retry on rate limit
        if self.settings.auto_retry and "rate" in message.lower() and cid:
            partial = "".join(self._stream_buffer)
            if partial:
                db.update_last_message(cid, partial)
            self._stream_buffer = []
            self.token_label.setText("Rate limited — retrying in 5s...")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(5000, lambda _cid=cid: self._retry_streaming(_cid))
            return
        if cid is not None:
            partial = "".join(self._stream_buffer)
            db.update_last_message(
                cid,
                partial + (f"\n\n[error: {message}]" if not partial else f"\n\n[stopped: {message}]")
            )
        self._stream_buffer = []
        QMessageBox.critical(self, "Oracle — error", message)

    def _retry_streaming(self, cid: int = None) -> None:
        if cid is None or cid != self._current_chat_id:
            return
        self._stream_buffer = []
        self._start_streaming_from_current_history()

    def _on_worker_done(self) -> None:
        self.send_btn.setVisible(True)
        self.stop_btn.setVisible(False)
        self._streaming_worker = None
        self._stream_start_time = None
        self._update_token_count()
        if self.settings.notify_sound:
            QApplication.beep()

    def closeEvent(self, event) -> None:
        if self._current_chat_id is not None:
            db.set_draft(self._current_chat_id, self.input_box.toPlainText())
        db.delete_ephemeral_chats()
        if self._streaming_worker and self._streaming_worker.isRunning():
            self._streaming_worker.cancel()
            self._streaming_worker.wait(2000)
        if self._record_proc and self._record_proc.poll() is None:
            self._record_proc.terminate()
        if self._tts_proc and self._tts_proc.poll() is None:
            self._tts_proc.terminate()
        super().closeEvent(event)


def _load_app_icon() -> QIcon:
    """Resolve the Oracle icon — theme first (after install), bundled SVG as fallback."""
    icon = QIcon.fromTheme("oracle")
    if not icon.isNull():
        return icon
    # Fallback: directly load the bundled SVG (works before install.sh has been run)
    src_dir = Path(__file__).resolve().parent.parent
    for candidate in (
        src_dir / "assets" / "oracle.svg",
        src_dir / "assets" / "oracle.png",
    ):
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Oracle")
    app.setApplicationDisplayName("Oracle")
    app.setOrganizationName("Oracle")
    # Critical for Wayland: this tells the compositor our app_id, which it
    # uses to match the running window to the `~/.local/share/applications/
    # oracle.desktop` entry — that's how the taskbar finds our icon.
    app.setDesktopFileName("oracle")

    icon = _load_app_icon()
    app.setWindowIcon(icon)

    from .styles import STYLESHEET, STYLESHEET_LIGHT
    from .config import load as _load_cfg
    _cfg = _load_cfg()
    app.setStyleSheet(STYLESHEET_LIGHT if _cfg.theme == "light" else STYLESHEET)
    w = MainWindow()
    w.setWindowIcon(icon)   # belt and suspenders — also covers X11 fallback
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
