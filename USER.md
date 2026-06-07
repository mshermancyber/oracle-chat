# Oracle Chat — User Guide

## Basics

- **Enter** sends your message
- **Shift+Enter** inserts a new line
- **@** opens a file picker to reference a file inline
- **Tab** auto-completes slash commands
- **Up/Down** in an empty input box recalls previous messages

---

## Message Actions

Every message bubble has action links at the bottom:

**On your messages:** Copy | Pin | Reply | Bookmark | Edit | Branch | Note | Color

**On Claude's messages:** +1 | -1 | Copy | Pin | Reply | Bookmark | Collapse | Regenerate | Branch | Note | Color | Speak

| Action | What it does |
|--------|-------------|
| **Copy** | Copies the message text to clipboard |
| **Pin** | Pins the message to the top of the conversation |
| **Reply** | Quotes the message in your input with `>` prefix |
| **Bookmark** | Stars the message (list with `/bookmarks`) |
| **Edit** | Loads the message into input, deletes it and everything after |
| **Regenerate** | Deletes the response and re-sends to get a new one |
| **Branch** | Forks the conversation into a new chat from this point |
| **Collapse** | Hides long responses, shows first 150 chars |
| **Note** | Adds a private annotation (yellow sticky, not sent to model) |
| **Color** | Highlights the message with a colored border |
| **Speak** | Reads the response aloud (requires espeak-ng or festival) |
| **+1 / -1** | Thumbs up/down reaction |

---

## Code Blocks

Fenced code blocks in responses get a header bar with:

- **Copy** — copy code to clipboard
- **Apply** — write code to a file (opens save dialog)
- **Run** — execute Python code locally (30s timeout)
- **Preview** — (HTML blocks only) render live in the split view pane

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Enter | Send message |
| Shift+Enter | New line |
| @ | Open file picker |
| Tab | Autocomplete slash command |
| Up/Down | Input history (when empty) |
| Ctrl+N | New chat |
| Ctrl+F | Search in conversation |
| Ctrl+M | Quick model switch (popup menu) |
| Ctrl+Z | Undo last delete action |
| Ctrl+V | Paste (images auto-detected) |
| Ctrl+Shift+V | Paste as fenced code block |
| Ctrl+= / Ctrl+- | Zoom in/out |
| Ctrl+, | Open Settings |
| Ctrl+/ | Show shortcut overlay |
| Ctrl+1-9 | Jump to chat by position |
| Alt+Up/Down | Navigate between chats |
| Alt+J/K | Navigate between messages |

---

## Slash Commands

Type a command and press Enter. Press **Tab** to autocomplete.

### Chat Management
| Command | Description |
|---------|-------------|
| `/clear` | Clear all messages in current chat |
| `/delete <N>` | Delete last N messages |
| `/replace old -> new` | Find and replace in your messages |
| `/merge <chat>` | Append another chat's messages into this one |
| `/link <chat>` | Pull recent messages from another chat as context |
| `/summary` | AI-generated conversation summary |
| `/autotitle` | AI-generated chat title |

### Model & Provider
| Command | Description |
|---------|-------------|
| `/model <name>` | Switch model (fuzzy match) |
| `/compare <model>` | Send last message to a different model too |
| `/automodel` | Toggle auto model switching by complexity |
| `/favorite <model>` | Pin model to top of picker (star) |
| `/unfavorite <model>` | Remove from favorites |

### System Prompt & Personas
| Command | Description |
|---------|-------------|
| `/system <text>` | Set global system prompt |
| `/chatprompt <text>` | Set per-chat system prompt (overrides global) |
| `/persona <name>` | Load persona: `reviewer`, `tutor`, `architect`, `debugger`, `writer` |
| `/format <type>` | Response format: `code`, `prose`, `bullets`, `table` |
| `/length <level>` | Response length: `brief`, `normal`, `detailed` |
| `/thinking <level>` | Thinking effort: `off`, `low`, `high`, `max` |
| `/systempromptpreview` | Show the effective combined prompt |

### Presets & Libraries
| Command | Description |
|---------|-------------|
| `/prompt save\|load\|list\|delete` | System prompt presets |
| `/template save\|load\|list\|delete` | Conversation templates (prompt + first message) |
| `/snippet save\|paste\|list\|delete` | Text snippet library (saves clipboard) |
| `/macro save\|list\|delete <name> <text>` | Input macros (type `!!name` to expand) |

### Organization
| Command | Description |
|---------|-------------|
| `/tag <name>` | Tag current chat |
| `/untag <name>` | Remove tag |
| `/tags` | List current chat's tags |
| `/chatcolor <color>` | Color dot: `red`, `yellow`, `green`, `blue`, `purple`, `clear` |
| `/archive` | Archive current chat (hidden from sidebar) |
| `/archived` | List archived chats |
| `/unarchive <name>` | Restore from archive |
| `/autoclean <N>d` | Archive chats untouched for N days |
| `/filter save\|load\|list\|delete` | Saved sidebar search filters |

### Search
| Command | Description |
|---------|-------------|
| `/search [user\|assistant] <query>` | Search messages in current chat |
| `/searchall <query>` | Search across all chats |
| `/grep <regex>` | Regex search with line numbers |
| `/bookmarks` | List all bookmarked messages |
| `/notes` | List all annotations in this chat |

### Research & Web
| Command | Description |
|---------|-------------|
| `/web <query>` | Search via SearXNG, inject results as context |
| `/research <query>` | Multi-step research: search, fetch, synthesize with citations |
| `/factcheck` | Fact-check the last assistant response |

### Export & Statistics
| Command | Description |
|---------|-------------|
| `/export` | Export as Markdown |
| `/exporthtml` | Export as styled HTML |
| `/import` | Import a Markdown conversation |
| `/stats` | Message count, tokens, dates, model |
| `/wc` | Word count, characters, reading time |
| `/cost` | Estimated API cost for this chat |
| `/context` | Context window usage bar |
| `/heatmap` | Activity by hour (ASCII chart) |
| `/timeline` | Chronological list of all chats |
| `/dashboard` | Aggregate stats across all chats |
| `/timer` | Session duration |

### View & Display
| Command | Description |
|---------|-------------|
| `/compact` | Toggle compact message layout |
| `/focus` | Toggle sidebar (expand chat to full width) |
| `/theme dark\|light` | Switch theme |
| `/rawmd` | Toggle raw markdown view |
| `/typewriter` | Toggle typewriter scroll during streaming |
| `/split [chat]` | Toggle split view, optionally show another chat |

### Projects & Memory
| Command | Description |
|---------|-------------|
| `/memory` | List remembered facts |
| `/memory add <fact>` | Remember a fact across all conversations |
| `/memory delete <N>` | Forget a fact by number |
| `/memory clear` | Clear all memories |
| `/project create <name>` | Create a project |
| `/project switch <name>` | Set active project |
| `/project addfile <path>` | Add file to project knowledge base |
| `/project files` | List files in active project |
| `/project list` | List all projects |
| `/project delete <name>` | Delete a project |

### Tools
| Command | Description |
|---------|-------------|
| `/workspace <dir>` | Add directory file listing as context |
| `/schedule <Ns\|m\|h> <msg>` | Send a message after a delay |
| `/budget <N>` | Set token budget for this chat |
| `/checkpoint <name>` | Save conversation state |
| `/restore <name>` | Restore to a checkpoint |
| `/history` | View edit history |
| `/tree` | Show conversation branches |
| `/diff <file>` | Preview what Apply would change |
| `/ephemeral` | Start a temporary chat (deleted on close) |
| `/notify` | Toggle notification sound |
| `/gallery` | List images in this chat |
| `/help` | Show command summary |

---

## Web Search

Oracle integrates with [SearXNG](https://docs.searxng.org/) for web search:

1. Set your SearXNG URL in Settings > Auth (e.g. `http://localhost:8888`)
2. Use `/web <query>` to search and inject results as context
3. Use `/research <query>` for multi-step research with numbered citations
4. Click `[1]`, `[2]` citation links in responses to open source URLs

---

## Voice

**Input:** Click the microphone button or use it during a conversation. Requires `arecord` (ALSA) + `whisper` CLI.

**Output:** Click "Speak" on any assistant message. Requires `espeak-ng`, `espeak`, or `festival`.

---

## Data Storage

All data stays on your machine:

| Path | Contents |
|------|----------|
| `~/.config/oracle/config.ini` | Settings (API keys stored with 0600 permissions) |
| `~/.config/oracle/prompts.json` | Saved prompt presets |
| `~/.config/oracle/templates.json` | Conversation templates |
| `~/.config/oracle/snippets.json` | Snippet library |
| `~/.config/oracle/macros.json` | Input macros |
| `~/.config/oracle/memory.json` | Cross-conversation memory |
| `~/.config/oracle/projects/` | Project knowledge bases |
| `~/.local/share/oracle/chats.db` | Chat history (SQLite) |
| `~/.local/share/oracle/attachments/` | Uploaded files |
| `~/.local/share/oracle/clipboard-paste/` | Pasted images |
