# Oracle Chat v1.0.0

A native Linux desktop chat client for AI models. Works with Anthropic Claude, OpenAI ChatGPT, Google Gemini, xAI Grok, Ollama, DeepSeek, and any OpenAI-compatible API.

**GitHub:** [github.com/mshermancyber/oracle-chat](https://github.com/mshermancyber/oracle-chat)

```
┌─────────────────────────┬──────────────────────────────────────────────────────┐
│  ＋  New chat           │  How do I reverse a list?  [gemini-2.5-flash ▾] [Cmd]│
│  12 chats               ├──────────────────────────────────────────────────────┤
│  Search chats...        │                                                      │
│ ─────────────────────── │  YOU  14:32                                          │
│  📌 Python tricks       │  How do I reverse a list in Python?                  │
│  🔵 API design          │                                      Edit  Branch    │
│  Debug segfault         │                                                      │
│  Explain SVD            │  CLAUDE  14:32  (1.8s, confident)                    │
│                         │  Three idiomatic options:                            │
│                         │    1. list.reverse()  — in place                     │
│                         │    2. reversed(list)  — iterator                     │
│                         │    3. list[::-1]      — slice copy                   │
│                         │              +1 -1 Copy Regenerate Branch Speak      │
│                         │                                                      │
│                         │    Continue     Explain further     Give an example   │
│                         ├──────────────────────────────────────────────────────┤
│  ⚙  Settings            │  ~12 tokens     [Attach] [Mic] [Web]  [Stop] [Send] │
└─────────────────────────┴──────────────────────────────────────────────────────┘
```

## Highlights

- **Multi-provider** — connect to Claude, ChatGPT, Gemini, Grok, Ollama, DeepSeek, Groq, Together, OpenRouter, LM Studio, or any OpenAI-compatible gateway
- **130+ features** — streaming, file uploads, code execution, voice I/O, web search, research agent, conversation memory, project knowledge bases, artifacts preview, and much more
- **Native Qt6** — PySide6 GUI that feels right on KDE, GNOME, XFCE, sway, Hyprland
- **Fully local** — all data stays on your machine in SQLite + JSON files
- **Dark & light themes** — with customizable font size

## Quick Start

```bash
git clone https://github.com/mshermancyber/oracle-chat.git
cd oracle-chat
./install.sh
oracle
```

See [INSTALL.md](INSTALL.md) for distro-specific instructions.

## Documentation

| Document | Contents |
|----------|----------|
| [INSTALL.md](INSTALL.md) | Installation for Debian/Ubuntu, Arch, Fedora, and manual setup |
| [USER.md](USER.md) | Complete usage guide — all features, shortcuts, and 60+ slash commands |
| [MODELS.md](MODELS.md) | How to configure models and connect to different AI providers |

## Authentication Modes

Oracle supports 4 connection backends. Switch in Settings (Ctrl+,) > Auth tab.

| Mode | Provider | What You Need |
|------|----------|---------------|
| **Anthropic API** (default) | Claude | `sk-ant-...` API key from console.anthropic.com |
| **Claude Code relay** | Claude | Local `claude` CLI binary + `claude /login` session |
| **Bridge gateway** | Claude | Running `bridge_to_claude` instance on your LAN |
| **Custom Gateway** | Any provider | API URL + optional key + model name |

The Custom Gateway mode works with any OpenAI-compatible endpoint. Built-in presets for 11 providers auto-fill URL and default model.

## Feature Overview

**Chat:** streaming responses, stop/regenerate/edit, conversation branching, quick-reply suggestions, auto-continue, auto-retry on rate limit, auto-title

**Input:** Enter to send, @file mentions, drag-and-drop, clipboard image paste, voice dictation, smart paste detection, input history, macros, tab-complete slash commands

**Code:** syntax-highlighted blocks with Copy/Apply/Run buttons, HTML artifact preview, paste-as-code

**Organization:** pin, archive, tag, color-code, duplicate, merge chats, project folders, saved filters, sidebar search + sort, bulk operations

**Search:** Ctrl+F in-conversation, cross-chat search, regex grep, role-filtered search, bookmarks, annotations

**AI Features:** web search (SearXNG), deep research with citations, fact-checking, conversation summary, auto-title, persistent memory, personas, thinking effort control

**Export:** Markdown, styled HTML, conversation import

**Settings:** tabbed dialog (Auth, Model, Behavior, Display, About), 20+ toggles, Commands menu button, keyboard shortcut overlay (Ctrl+/)

## Project Layout

```
oracle-chat/
├── oracle.py             # entry point
├── run.sh                # launcher (auto-creates venv)
├── install.sh            # one-shot installer
├── requirements.txt      # PySide6, anthropic, markdown, Pygments, httpx
├── assets/oracle.svg     # app icon
├── README.md             # this file
├── INSTALL.md            # installation guide
├── USER.md               # usage guide
├── MODELS.md             # model configuration guide
└── src/
    ├── api.py            # Anthropic SDK streaming client
    ├── bridge_api.py     # OpenAI-compatible gateway clients (Bridge + Custom)
    ├── claude_code_api.py # Claude Code CLI relay
    ├── config.py         # settings, memory, projects, prompts
    ├── db.py             # SQLite persistence
    ├── markdown_renderer.py # markdown + LaTeX + thinking + citations
    ├── styles.py         # dark + light Qt stylesheets
    └── window.py         # main UI (4000+ lines)
```

## License

GPL-3.0. See [LICENSE](LICENSE) for details. The AI models and APIs are governed by their respective providers' terms of service.

## Credits

[github.com/mshermancyber/oracle-chat](https://github.com/mshermancyber/oracle-chat)
