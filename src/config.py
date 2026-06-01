"""Config — loads / saves Oracle settings to ~/.config/oracle/config.ini.

Settings:
    api_key         — Anthropic API key (sk-ant-...)
    default_model   — claude-opus-4-8 | claude-opus-4-7 | claude-opus-4-6 | claude-opus-4-5 | claude-sonnet-4-6 | claude-sonnet-4-5 | claude-haiku-4-5-20251001
    system_prompt   — optional system prompt prepended to every conversation
    max_tokens      — per-response cap (default 4096)
"""
from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Anthropic model catalog — keys are display names, values are API model IDs.
MODELS = {
    "Claude Opus 4.8":   "claude-opus-4-8",
    "Claude Opus 4.7":   "claude-opus-4-7",
    "Claude Opus 4.6":   "claude-opus-4-6",
    "Claude Opus 4.5":   "claude-opus-4-5",
    "Claude Sonnet 4.6": "claude-sonnet-4-6",
    "Claude Sonnet 4.5": "claude-sonnet-4-5",
    "Claude Haiku 4.5":  "claude-haiku-4-5-20251001",
}
DEFAULT_MODEL = "claude-sonnet-4-6"

# Approximate pricing per 1M tokens (input/output) for cost estimation
MODEL_PRICING = {
    "claude-opus-4-8":   (15.0, 75.0),
    "claude-opus-4-7":   (15.0, 75.0),
    "claude-opus-4-6":   (15.0, 75.0),
    "claude-opus-4-5":   (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}

CONFIG_DIR  = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "oracle"
CONFIG_PATH = CONFIG_DIR / "config.ini"
DATA_DIR    = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "oracle"
DB_PATH     = DATA_DIR / "chats.db"


# Auth modes
AUTH_API         = "api"          # Anthropic API key — uses the `anthropic` SDK
AUTH_CLAUDE_CODE = "claude_code"  # Relay through the local `claude` CLI binary
AUTH_BRIDGE      = "bridge"       # Relay through the bridge_to_claude OpenAI gateway
AUTH_CUSTOM      = "custom"       # Any OpenAI-compatible gateway (Ollama, Grok, Gemini, etc.)
DEFAULT_AUTH     = AUTH_API

# Bridge defaults — only the IP is user-configurable; port + path are fixed
# to the bridge's defaults (see bridge_to_claude/README.md §Configuration).
BRIDGE_PORT      = 7331
BRIDGE_PATH      = "/v1/chat/completions"
BRIDGE_DEFAULT_IP = "127.0.0.1"

PROMPTS_PATH = CONFIG_DIR / "prompts.json"

PERSONAS = {
    "reviewer": "You are a senior code reviewer. Focus on bugs, edge cases, security issues, and style. Be direct and specific.",
    "tutor": "You are a patient programming tutor. Explain concepts step by step with examples. Check understanding before moving on.",
    "architect": "You are a software architect. Focus on system design, patterns, trade-offs, and scalability. Think about the big picture.",
    "debugger": "You are a debugging expert. Systematically isolate issues. Ask clarifying questions about symptoms, check assumptions, suggest targeted tests.",
    "writer": "You are a technical writer. Produce clear, well-structured documentation and explanations. Use examples and diagrams.",
}
TEMPLATES_PATH = CONFIG_DIR / "templates.json"
RECENT_FILES_PATH = CONFIG_DIR / "recent_files.json"
SNIPPETS_PATH = CONFIG_DIR / "snippets.json"
MACROS_PATH = CONFIG_DIR / "macros.json"
FILTERS_PATH = CONFIG_DIR / "filters.json"
MEMORY_PATH = CONFIG_DIR / "memory.json"
PROJECTS_DIR = CONFIG_DIR / "projects"


@dataclass
class Settings:
    api_key:         Optional[str] = None
    default_model:   str           = DEFAULT_MODEL
    system_prompt:   str           = ""
    max_tokens:      int           = 4096
    auth_mode:       str           = DEFAULT_AUTH
    claude_binary:   str           = "claude"
    bridge_ip:       str           = BRIDGE_DEFAULT_IP
    compact_mode:    bool          = False
    response_length: str           = "normal"
    notify_sound:    bool          = False
    theme:           str           = "dark"
    focus_mode:      bool          = False
    auto_model:      bool          = False
    favorite_models: str           = ""
    searxng_url:     str           = ""
    custom_api_url:  str           = ""         # e.g. "http://localhost:11434/v1/chat/completions"
    custom_api_key:  str           = ""
    custom_model:    str           = ""         # e.g. "llama3", "gpt-4o", "gemini-pro"
    thinking_effort: str           = ""         # "" | "off" | "low" | "high" | "max"
    active_project:  str           = ""
    auto_continue:   bool          = True
    auto_retry:      bool          = True
    response_format: str           = ""
    persona:         str           = ""
    typewriter_mode: bool          = False
    show_raw_md:     bool          = False
    font_size:       int           = 14
    sidebar_sort:    str           = "recent"   # "recent" | "alpha" | "model"
    show_thinking:   bool          = True
    auto_title:      bool          = True

    @property
    def configured(self) -> bool:
        if self.auth_mode == AUTH_CLAUDE_CODE:
            # Relay mode — only needs the binary present; auth is Claude Code's
            # responsibility (it'll either be logged in via /login or have its
            # own ANTHROPIC_API_KEY set in the user's environment).
            return bool(self.claude_binary and self.claude_binary.strip())
        if self.auth_mode == AUTH_BRIDGE:
            return bool(self.bridge_ip and self.bridge_ip.strip())
        if self.auth_mode == AUTH_CUSTOM:
            return bool(self.custom_api_url and self.custom_model)
        return bool(self.api_key and self.api_key.strip())


def _ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load() -> Settings:
    """Load settings from disk, layering env vars on top of config.ini."""
    _ensure_dirs()
    s = Settings()
    if CONFIG_PATH.exists():
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_PATH)
        if "oracle" in cfg:
            section = cfg["oracle"]
            s.api_key       = section.get("api_key") or None
            s.default_model = section.get("default_model", DEFAULT_MODEL)
            s.system_prompt = section.get("system_prompt", "")
            s.max_tokens    = section.getint("max_tokens", 4096)
            s.auth_mode        = section.get("auth_mode", DEFAULT_AUTH)
            s.claude_binary    = section.get("claude_binary", "claude")
            s.bridge_ip        = section.get("bridge_ip", BRIDGE_DEFAULT_IP)
            s.compact_mode     = section.getboolean("compact_mode", False)
            s.response_length  = section.get("response_length", "normal")
            s.notify_sound     = section.getboolean("notify_sound", False)
            s.theme            = section.get("theme", "dark")
            s.focus_mode       = section.getboolean("focus_mode", False)
            s.auto_model       = section.getboolean("auto_model", False)
            s.favorite_models  = section.get("favorite_models", "")
            s.searxng_url      = section.get("searxng_url", "")
            s.custom_api_url   = section.get("custom_api_url", "")
            s.custom_api_key   = section.get("custom_api_key", "")
            s.custom_model     = section.get("custom_model", "")
            s.thinking_effort  = section.get("thinking_effort", "")
            s.active_project   = section.get("active_project", "")
            s.auto_continue    = section.getboolean("auto_continue", True)
            s.auto_retry       = section.getboolean("auto_retry", True)
            s.response_format  = section.get("response_format", "")
            s.persona          = section.get("persona", "")
            s.typewriter_mode  = section.getboolean("typewriter_mode", False)
            s.show_raw_md      = section.getboolean("show_raw_md", False)
            s.font_size        = section.getint("font_size", 14)
            s.sidebar_sort     = section.get("sidebar_sort", "recent")
            s.show_thinking    = section.getboolean("show_thinking", True)
            s.auto_title       = section.getboolean("auto_title", True)
    # Environment variable always wins (well-known precedence).
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        s.api_key = env_key
    return s


def save(settings: Settings) -> None:
    """Persist settings to ~/.config/oracle/config.ini (mode 0600)."""
    _ensure_dirs()
    cfg = configparser.ConfigParser()
    cfg["oracle"] = {
        "api_key":       settings.api_key or "",
        "default_model": settings.default_model or DEFAULT_MODEL,
        "system_prompt": settings.system_prompt or "",
        "max_tokens":    str(settings.max_tokens or 4096),
        "auth_mode":        settings.auth_mode or DEFAULT_AUTH,
        "claude_binary":    settings.claude_binary or "claude",
        "bridge_ip":        settings.bridge_ip or BRIDGE_DEFAULT_IP,
        "compact_mode":     str(settings.compact_mode),
        "response_length":  settings.response_length or "normal",
        "notify_sound":     str(settings.notify_sound),
        "theme":            settings.theme or "dark",
        "focus_mode":       str(settings.focus_mode),
        "auto_model":       str(settings.auto_model),
        "favorite_models":  settings.favorite_models or "",
        "searxng_url":      settings.searxng_url or "",
        "custom_api_url":   settings.custom_api_url or "",
        "custom_api_key":   settings.custom_api_key or "",
        "custom_model":     settings.custom_model or "",
        "thinking_effort":  settings.thinking_effort or "",
        "active_project":   settings.active_project or "",
        "auto_continue":    str(settings.auto_continue),
        "auto_retry":       str(settings.auto_retry),
        "response_format":  settings.response_format or "",
        "persona":          settings.persona or "",
        "typewriter_mode":  str(settings.typewriter_mode),
        "show_raw_md":      str(settings.show_raw_md),
        "font_size":        str(settings.font_size),
        "sidebar_sort":     settings.sidebar_sort or "recent",
        "show_thinking":    str(settings.show_thinking),
        "auto_title":       str(settings.auto_title),
    }
    fd = os.open(str(CONFIG_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        cfg.write(f)


def load_prompts() -> list:
    """Load prompt presets from ~/.config/oracle/prompts.json."""
    _ensure_dirs()
    if not PROMPTS_PATH.exists():
        return []
    import json
    try:
        data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_prompts(prompts: list) -> None:
    """Persist prompt presets to disk."""
    _ensure_dirs()
    import json
    PROMPTS_PATH.write_text(json.dumps(prompts, indent=2, ensure_ascii=False), encoding="utf-8")


def find_prompt(name: str) -> Optional[dict]:
    """Find a prompt preset by name (case-insensitive)."""
    for p in load_prompts():
        if p.get("name", "").lower() == name.lower():
            return p
    return None


def load_templates() -> list:
    _ensure_dirs()
    if not TEMPLATES_PATH.exists():
        return []
    import json
    try:
        data = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_templates(templates: list) -> None:
    _ensure_dirs()
    import json
    TEMPLATES_PATH.write_text(json.dumps(templates, indent=2, ensure_ascii=False), encoding="utf-8")


def load_recent_files() -> list:
    _ensure_dirs()
    if not RECENT_FILES_PATH.exists():
        return []
    import json
    try:
        data = json.loads(RECENT_FILES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[:10]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_recent_files(files: list) -> None:
    _ensure_dirs()
    import json
    RECENT_FILES_PATH.write_text(json.dumps(files[:10], ensure_ascii=False), encoding="utf-8")


def add_recent_file(path: str) -> None:
    files = load_recent_files()
    if path in files:
        files.remove(path)
    files.insert(0, path)
    save_recent_files(files[:10])


def load_snippets() -> list:
    _ensure_dirs()
    if not SNIPPETS_PATH.exists():
        return []
    import json
    try:
        data = json.loads(SNIPPETS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_snippets(snippets: list) -> None:
    _ensure_dirs()
    import json
    SNIPPETS_PATH.write_text(json.dumps(snippets, indent=2, ensure_ascii=False), encoding="utf-8")


def load_macros() -> dict:
    _ensure_dirs()
    if not MACROS_PATH.exists():
        return {}
    import json
    try:
        data = json.loads(MACROS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_macros(macros: dict) -> None:
    _ensure_dirs()
    import json
    MACROS_PATH.write_text(json.dumps(macros, indent=2, ensure_ascii=False), encoding="utf-8")


def load_filters() -> dict:
    _ensure_dirs()
    if not FILTERS_PATH.exists():
        return {}
    import json
    try:
        data = json.loads(FILTERS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_filters(filters: dict) -> None:
    _ensure_dirs()
    import json
    FILTERS_PATH.write_text(json.dumps(filters, indent=2, ensure_ascii=False), encoding="utf-8")


def load_memory() -> list:
    _ensure_dirs()
    if not MEMORY_PATH.exists():
        return []
    import json
    try:
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_memory(facts: list) -> None:
    _ensure_dirs()
    import json
    MEMORY_PATH.write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")


def add_memory(fact: str, source: str = "") -> None:
    import datetime as _dt
    facts = load_memory()
    facts.append({"fact": fact, "source_chat": source, "created": _dt.datetime.now().isoformat(timespec="seconds")})
    save_memory(facts)


def _safe_project_name(name: str) -> str:
    """Sanitize project name to prevent path traversal."""
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()
    if not safe:
        safe = "unnamed"
    return safe


def load_project(name: str) -> dict:
    _ensure_dirs()
    import json
    name = _safe_project_name(name)
    p = PROJECTS_DIR / f"{name}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_project(name: str, data: dict) -> None:
    _ensure_dirs()
    import json
    name = _safe_project_name(name)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECTS_DIR / f"{name}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_projects() -> list:
    _ensure_dirs()
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return [p.stem for p in sorted(PROJECTS_DIR.glob("*.json"))]


def delete_project(name: str) -> bool:
    name = _safe_project_name(name)
    p = PROJECTS_DIR / f"{name}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def model_display_name(model_id: str) -> str:
    """Reverse-lookup: API id → friendly display label."""
    for display, mid in MODELS.items():
        if mid == model_id:
            return display
    return model_id
