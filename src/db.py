"""SQLite persistence for Oracle chats.

Schema:
    chats        (id, title, model, created_at, updated_at, claude_session_id)
    messages     (id, chat_id, role, content, created_at)
    attachments  (id, message_id, kind, original_name, stored_path, mime, created_at)
"""
from __future__ import annotations

import datetime as dt
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .config import DATA_DIR, DB_PATH


ATTACHMENTS_DIR = DATA_DIR / "attachments"


@dataclass
class Chat:
    id: int
    title: str
    model: str
    created_at: str
    updated_at: str
    claude_session_id: Optional[str] = None
    pinned: int = 0
    tags: str = ""
    chat_system_prompt: str = ""
    draft: str = ""
    archived: int = 0
    ephemeral: int = 0
    token_budget: int = 0
    checkpoint_data: str = ""
    color: str = ""
    project: str = ""


@dataclass
class Attachment:
    id: int
    message_id: int
    kind: str               # "image" | "pdf" | "docx"
    original_name: str
    stored_path: str        # absolute path on disk inside ATTACHMENTS_DIR
    mime: str
    created_at: str


@dataclass
class Message:
    id: int
    chat_id: int
    role: str          # "user" | "assistant" | "system"
    content: str
    created_at: str
    bookmarked: int = 0
    reaction: str = ""
    pinned_in_chat: int = 0
    collapsed: int = 0
    annotation: str = ""
    highlight: str = ""
    response_time: float = 0.0
    last_read: int = 0
    stop_reason: str = ""
    attachments: List[Attachment] = field(default_factory=list)


import contextlib

@contextlib.contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init() -> None:
    """Create tables if they don't exist; migrate older schemas in place."""
    with _connect() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                title             TEXT NOT NULL,
                model             TEXT NOT NULL,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL,
                claude_session_id TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
            CREATE TABLE IF NOT EXISTS attachments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id    INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                kind          TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path   TEXT NOT NULL,
                mime          TEXT NOT NULL,
                created_at    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_attachments_message_id ON attachments(message_id);
        """)
        # v0.1 → v0.3 schema migration: add claude_session_id if missing.
        cols = {r["name"] for r in c.execute("PRAGMA table_info(chats)").fetchall()}
        if "claude_session_id" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN claude_session_id TEXT")
        # v0.7 → v0.8 migrations
        if "pinned" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN pinned INTEGER DEFAULT 0")
        if "tags" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN tags TEXT DEFAULT ''")
        if "chat_system_prompt" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN chat_system_prompt TEXT DEFAULT ''")
        if "draft" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN draft TEXT DEFAULT ''")
        if "archived" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN archived INTEGER DEFAULT 0")
        msg_cols = {r["name"] for r in c.execute("PRAGMA table_info(messages)").fetchall()}
        if "bookmarked" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN bookmarked INTEGER DEFAULT 0")
        if "reaction" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN reaction TEXT DEFAULT ''")
        if "pinned_in_chat" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN pinned_in_chat INTEGER DEFAULT 0")
        if "collapsed" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN collapsed INTEGER DEFAULT 0")
        if "ephemeral" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN ephemeral INTEGER DEFAULT 0")
        if "token_budget" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN token_budget INTEGER DEFAULT 0")
        if "checkpoint_data" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN checkpoint_data TEXT DEFAULT ''")
        if "annotation" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN annotation TEXT DEFAULT ''")
        if "highlight" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN highlight TEXT DEFAULT ''")
        if "response_time" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN response_time REAL DEFAULT 0.0")
        if "last_read" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN last_read INTEGER DEFAULT 0")
        if "stop_reason" not in msg_cols:
            c.execute("ALTER TABLE messages ADD COLUMN stop_reason TEXT DEFAULT ''")
        if "color" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN color TEXT DEFAULT ''")
        if "project" not in cols:
            c.execute("ALTER TABLE chats ADD COLUMN project TEXT DEFAULT ''")
        c.execute("""CREATE TABLE IF NOT EXISTS message_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            original_content TEXT NOT NULL,
            role TEXT NOT NULL,
            replaced_at TEXT NOT NULL
        )""")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


_CHAT_COLS = ("id, title, model, created_at, updated_at, claude_session_id, "
              "pinned, tags, chat_system_prompt, draft, archived, ephemeral, "
              "token_budget, checkpoint_data, color, project")


def list_chats(include_archived: bool = False) -> List[Chat]:
    """Return chats, pinned first then most-recently-updated. Archived excluded by default."""
    with _connect() as c:
        where = "" if include_archived else "WHERE archived = 0"
        rows = c.execute(
            f"SELECT {_CHAT_COLS} FROM chats {where} ORDER BY pinned DESC, updated_at DESC"
        ).fetchall()
    return [Chat(**dict(r)) for r in rows]


def list_archived_chats() -> List[Chat]:
    with _connect() as c:
        rows = c.execute(
            f"SELECT {_CHAT_COLS} FROM chats WHERE archived = 1 ORDER BY updated_at DESC"
        ).fetchall()
    return [Chat(**dict(r)) for r in rows]


def get_chat(chat_id: int) -> Optional[Chat]:
    """Return a single chat by id."""
    with _connect() as c:
        row = c.execute(
            f"SELECT {_CHAT_COLS} FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
    return Chat(**dict(row)) if row else None


def set_claude_session_id(chat_id: int, session_id: str) -> None:
    """Persist the Claude Code session UUID for a chat (used by --resume)."""
    with _connect() as c:
        c.execute("UPDATE chats SET claude_session_id = ? WHERE id = ?", (session_id, chat_id))


def create_chat(title: str, model: str) -> Chat:
    now = _now()
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO chats(title, model, created_at, updated_at) VALUES (?,?,?,?)",
            (title, model, now, now),
        )
        cid = cur.lastrowid
    return Chat(id=cid, title=title, model=model, created_at=now, updated_at=now)


def rename_chat(chat_id: int, title: str) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?", (title, _now(), chat_id))


def delete_chat(chat_id: int) -> None:
    with _connect() as c:
        c.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def get_messages(chat_id: int) -> List[Message]:
    with _connect() as c:
        rows = c.execute(
            "SELECT id, chat_id, role, content, created_at, bookmarked, reaction, "
            "pinned_in_chat, collapsed, annotation, highlight, response_time, last_read, stop_reason "
            "FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
        msgs = [Message(**dict(r)) for r in rows]
        if not msgs:
            return msgs
        # Hydrate attachments in one query so message rendering is O(1) lookups.
        ids = [m.id for m in msgs]
        placeholders = ",".join("?" * len(ids))
        att_rows = c.execute(
            f"SELECT id, message_id, kind, original_name, stored_path, mime, created_at "
            f"FROM attachments WHERE message_id IN ({placeholders}) ORDER BY id ASC",
            ids,
        ).fetchall()
    by_msg: dict = {}
    for r in att_rows:
        by_msg.setdefault(r["message_id"], []).append(Attachment(**dict(r)))
    for m in msgs:
        m.attachments = by_msg.get(m.id, [])
    return msgs


def add_message(chat_id: int, role: str, content: str) -> Message:
    now = _now()
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO messages(chat_id, role, content, created_at) VALUES (?,?,?,?)",
            (chat_id, role, content, now),
        )
        mid = cur.lastrowid
        c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
    return Message(id=mid, chat_id=chat_id, role=role, content=content, created_at=now)


def update_last_message(chat_id: int, content: str) -> None:
    """Replace the most recent message's content (used during streaming completion)."""
    now = _now()
    with _connect() as c:
        row = c.execute(
            "SELECT id FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1", (chat_id,)
        ).fetchone()
        if row:
            c.execute("UPDATE messages SET content = ? WHERE id = ?", (content, row["id"]))
            c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))


def add_attachment(message_id: int, chat_id: int, kind: str,
                   source_path: Path, mime: str) -> Attachment:
    """Copy a file into Oracle's attachments dir and record it against a message.

    Files are stored under ATTACHMENTS_DIR/<chat_id>/<message_id>_<filename>
    so they survive chat re-opens and can be safely re-read at render time.
    """
    src = Path(source_path)
    dest_dir = ATTACHMENTS_DIR / str(chat_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{message_id}_{src.name}"
    # If the same physical path is already in the attachments dir (re-send of
    # an existing chat), don't copy onto itself.
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    now = _now()
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO attachments(message_id, kind, original_name, stored_path, mime, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (message_id, kind, src.name, str(dest), mime, now),
        )
        aid = cur.lastrowid
    return Attachment(
        id=aid, message_id=message_id, kind=kind, original_name=src.name,
        stored_path=str(dest), mime=mime, created_at=now,
    )


def delete_messages_from(chat_id: int, message_id: int) -> None:
    """Delete the given message and all subsequent messages in a chat."""
    with _connect() as c:
        c.execute("DELETE FROM messages WHERE chat_id = ? AND id >= ?", (chat_id, message_id))
        c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (_now(), chat_id))


def clear_messages(chat_id: int) -> None:
    """Delete all messages (and their attachments via CASCADE) for a chat."""
    with _connect() as c:
        c.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (_now(), chat_id))


def toggle_pin(chat_id: int) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET pinned = CASE WHEN pinned = 0 THEN 1 ELSE 0 END WHERE id = ?", (chat_id,))


def set_tags(chat_id: int, tags: str) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET tags = ? WHERE id = ?", (tags, chat_id))


def toggle_bookmark(message_id: int) -> None:
    with _connect() as c:
        c.execute(
            "UPDATE messages SET bookmarked = CASE WHEN bookmarked = 0 THEN 1 ELSE 0 END WHERE id = ?",
            (message_id,),
        )


def get_bookmarked_messages() -> List[dict]:
    """Return all bookmarked messages across chats."""
    with _connect() as c:
        rows = c.execute(
            "SELECT m.id, m.chat_id, m.role, m.content, m.created_at, c.title AS chat_title "
            "FROM messages m JOIN chats c ON m.chat_id = c.id "
            "WHERE m.bookmarked = 1 ORDER BY m.created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def copy_messages_up_to(src_chat_id: int, up_to_msg_id: int, dest_chat_id: int) -> None:
    """Copy messages from src chat up to and including up_to_msg_id into dest chat."""
    now = _now()
    with _connect() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? AND id <= ? ORDER BY id ASC",
            (src_chat_id, up_to_msg_id),
        ).fetchall()
        for r in rows:
            c.execute(
                "INSERT INTO messages(chat_id, role, content, created_at) VALUES (?,?,?,?)",
                (dest_chat_id, r["role"], r["content"], now),
            )


def chat_stats(chat_id: int) -> dict:
    """Return statistics for a chat."""
    with _connect() as c:
        rows = c.execute(
            "SELECT role, content, created_at FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
    if not rows:
        return {"msg_count": 0}
    user_count = sum(1 for r in rows if r["role"] == "user")
    asst_count = sum(1 for r in rows if r["role"] == "assistant")
    total_chars = sum(len(r["content"] or "") for r in rows)
    return {
        "msg_count": len(rows),
        "user_count": user_count,
        "assistant_count": asst_count,
        "total_chars": total_chars,
        "first_at": rows[0]["created_at"],
        "last_at": rows[-1]["created_at"],
    }


def set_reaction(message_id: int, reaction: str) -> None:
    with _connect() as c:
        c.execute("UPDATE messages SET reaction = ? WHERE id = ?", (reaction, message_id))


def set_chat_system_prompt(chat_id: int, prompt: str) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET chat_system_prompt = ? WHERE id = ?", (prompt, chat_id))


def set_draft(chat_id: int, draft: str) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET draft = ? WHERE id = ?", (draft, chat_id))


def duplicate_chat(chat_id: int) -> Optional[Chat]:
    """Clone a chat and all its messages."""
    src = get_chat(chat_id)
    if not src:
        return None
    new = create_chat(title=f"Copy of {src.title}", model=src.model)
    with _connect() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
        now = _now()
        for r in rows:
            c.execute(
                "INSERT INTO messages(chat_id, role, content, created_at) VALUES (?,?,?,?)",
                (new.id, r["role"], r["content"], now),
            )
    return new


def delete_last_n_messages(chat_id: int, n: int) -> int:
    """Delete the last N messages from a chat. Returns count deleted."""
    with _connect() as c:
        rows = c.execute(
            "SELECT id FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, n),
        ).fetchall()
        if not rows:
            return 0
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        c.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids)
        c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (_now(), chat_id))
        return len(ids)


def word_count(chat_id: int) -> dict:
    """Return word/char/reading-time stats."""
    with _connect() as c:
        rows = c.execute(
            "SELECT content FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
    text = " ".join(r["content"] or "" for r in rows)
    words = len(text.split())
    chars = len(text)
    reading_min = max(1, words // 250)
    return {"words": words, "chars": chars, "reading_min": reading_min}


def set_archived(chat_id: int, archived: int) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET archived = ? WHERE id = ?", (archived, chat_id))


def toggle_pin_message(message_id: int) -> None:
    with _connect() as c:
        c.execute(
            "UPDATE messages SET pinned_in_chat = CASE WHEN pinned_in_chat = 0 THEN 1 ELSE 0 END WHERE id = ?",
            (message_id,),
        )


def get_pinned_messages(chat_id: int) -> List[Message]:
    with _connect() as c:
        rows = c.execute(
            "SELECT id, chat_id, role, content, created_at, bookmarked, reaction, "
            "pinned_in_chat, collapsed, annotation, highlight, response_time, last_read, stop_reason "
            "FROM messages WHERE chat_id = ? AND pinned_in_chat = 1 ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
    return [Message(**dict(r)) for r in rows]


def save_edit_history(chat_id: int, role: str, content: str) -> None:
    with _connect() as c:
        c.execute(
            "INSERT INTO message_edits(chat_id, original_content, role, replaced_at) VALUES (?,?,?,?)",
            (chat_id, content, role, _now()),
        )


def get_edit_history(chat_id: int) -> list:
    with _connect() as c:
        rows = c.execute(
            "SELECT original_content, role, replaced_at FROM message_edits "
            "WHERE chat_id = ? ORDER BY replaced_at DESC LIMIT 20",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def toggle_collapsed(message_id: int) -> None:
    with _connect() as c:
        c.execute(
            "UPDATE messages SET collapsed = CASE WHEN collapsed = 0 THEN 1 ELSE 0 END WHERE id = ?",
            (message_id,),
        )


def set_token_budget(chat_id: int, budget: int) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET token_budget = ? WHERE id = ?", (budget, chat_id))


def set_ephemeral(chat_id: int, val: int) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET ephemeral = ? WHERE id = ?", (val, chat_id))


def delete_ephemeral_chats() -> None:
    with _connect() as c:
        c.execute("DELETE FROM chats WHERE ephemeral = 1")


def replace_in_messages(chat_id: int, old: str, new: str) -> int:
    """Replace text in all user messages of a chat. Returns count of affected messages."""
    escaped_old = _escape_like(old)
    with _connect() as c:
        rows = c.execute(
            "SELECT id, content FROM messages WHERE chat_id = ? AND role = 'user' AND content LIKE ? ESCAPE '\\'",
            (chat_id, f"%{escaped_old}%"),
        ).fetchall()
        for r in rows:
            updated = r["content"].replace(old, new)
            c.execute("UPDATE messages SET content = ? WHERE id = ?", (updated, r["id"]))
        return len(rows)


def merge_chat_into(src_chat_id: int, dest_chat_id: int) -> int:
    """Append all messages from src into dest. Returns count."""
    now = _now()
    with _connect() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (src_chat_id,),
        ).fetchall()
        for r in rows:
            c.execute(
                "INSERT INTO messages(chat_id, role, content, created_at) VALUES (?,?,?,?)",
                (dest_chat_id, r["role"], r["content"], now),
            )
        c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, dest_chat_id))
        return len(rows)


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_messages(chat_id: int, query: str, role: Optional[str] = None) -> List[dict]:
    """Search messages by content, optionally filtered by role."""
    escaped = _escape_like(query)
    with _connect() as c:
        if role:
            rows = c.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE chat_id = ? AND role = ? AND content LIKE ? ESCAPE '\\' ORDER BY id ASC",
                (chat_id, role, f"%{escaped}%"),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE chat_id = ? AND content LIKE ? ESCAPE '\\' ORDER BY id ASC",
                (chat_id, f"%{escaped}%"),
            ).fetchall()
    return [dict(r) for r in rows]


def get_user_messages(chat_id: int) -> List[str]:
    """Return all user message contents for input history."""
    with _connect() as c:
        rows = c.execute(
            "SELECT content FROM messages WHERE chat_id = ? AND role = 'user' ORDER BY id DESC",
            (chat_id,),
        ).fetchall()
    return [r["content"] for r in rows]


def get_all_chats_timeline() -> List[dict]:
    """Return all chats with first user message for timeline view."""
    with _connect() as c:
        rows = c.execute(
            "SELECT c.id, c.title, c.created_at, c.model, "
            "(SELECT content FROM messages WHERE chat_id = c.id AND role = 'user' ORDER BY id ASC LIMIT 1) AS first_msg "
            "FROM chats c WHERE c.archived = 0 ORDER BY c.created_at DESC",
        ).fetchall()
    return [dict(r) for r in rows]


def set_annotation(message_id: int, text: str) -> None:
    with _connect() as c:
        c.execute("UPDATE messages SET annotation = ? WHERE id = ?", (text, message_id))


def get_annotations(chat_id: int) -> List[dict]:
    """Return all annotated messages."""
    with _connect() as c:
        rows = c.execute(
            "SELECT id, role, content, annotation, created_at FROM messages "
            "WHERE chat_id = ? AND annotation != '' ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_checkpoint(chat_id: int, name: str) -> None:
    """Save current message IDs as a named checkpoint in JSON."""
    import json
    chat = get_chat(chat_id)
    if not chat:
        return
    checkpoints = json.loads(chat.checkpoint_data) if chat.checkpoint_data else {}
    with _connect() as c:
        rows = c.execute(
            "SELECT id FROM messages WHERE chat_id = ? ORDER BY id ASC", (chat_id,)
        ).fetchall()
    checkpoints[name] = [r["id"] for r in rows]
    with _connect() as c:
        c.execute("UPDATE chats SET checkpoint_data = ? WHERE id = ?",
                  (json.dumps(checkpoints), chat_id))


def restore_checkpoint(chat_id: int, name: str) -> bool:
    """Restore to a checkpoint by deleting messages added after it."""
    import json
    chat = get_chat(chat_id)
    if not chat or not chat.checkpoint_data:
        return False
    checkpoints = json.loads(chat.checkpoint_data)
    if name not in checkpoints:
        return False
    saved_ids = set(checkpoints[name])
    if not saved_ids:
        clear_messages(chat_id)
        return True
    with _connect() as c:
        c.execute(
            "DELETE FROM messages WHERE chat_id = ? AND id NOT IN ({})".format(
                ",".join("?" * len(saved_ids))
            ),
            [chat_id] + list(saved_ids),
        )
    return True


def list_checkpoints(chat_id: int) -> List[str]:
    import json
    chat = get_chat(chat_id)
    if not chat or not chat.checkpoint_data:
        return []
    return list(json.loads(chat.checkpoint_data).keys())


def set_highlight(message_id: int, color: str) -> None:
    with _connect() as c:
        c.execute("UPDATE messages SET highlight = ? WHERE id = ?", (color, message_id))


def set_response_time(message_id: int, seconds: float) -> None:
    with _connect() as c:
        c.execute("UPDATE messages SET response_time = ? WHERE id = ?", (seconds, message_id))


def set_chat_color(chat_id: int, color: str) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET color = ? WHERE id = ?", (color, chat_id))


def mark_messages_read(chat_id: int) -> None:
    with _connect() as c:
        c.execute("UPDATE messages SET last_read = 1 WHERE chat_id = ? AND last_read = 0",
                  (chat_id,))


def get_first_unread_id(chat_id: int) -> Optional[int]:
    with _connect() as c:
        row = c.execute(
            "SELECT id FROM messages WHERE chat_id = ? AND last_read = 0 ORDER BY id ASC LIMIT 1",
            (chat_id,),
        ).fetchone()
    return row["id"] if row else None


def search_all_chats(query: str) -> List[dict]:
    """Search across all chats."""
    escaped = _escape_like(query)
    with _connect() as c:
        rows = c.execute(
            "SELECT m.id, m.chat_id, m.role, m.content, m.created_at, c.title AS chat_title "
            "FROM messages m JOIN chats c ON m.chat_id = c.id "
            "WHERE m.content LIKE ? ESCAPE '\\' ORDER BY m.created_at DESC LIMIT 50",
            (f"%{escaped}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_attachments(chat_id: int) -> list:
    """Get all attachments for a chat."""
    with _connect() as c:
        rows = c.execute(
            "SELECT a.id, a.original_name, a.stored_path, a.kind, a.mime "
            "FROM attachments a JOIN messages m ON a.message_id = m.id "
            "WHERE m.chat_id = ? ORDER BY a.id ASC",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def auto_archive_stale(days: int) -> int:
    """Archive chats not updated in N days."""
    import datetime as _dt
    cutoff = (_dt.datetime.now() - _dt.timedelta(days=days)).isoformat(timespec="seconds")
    with _connect() as c:
        cur = c.execute(
            "UPDATE chats SET archived = 1 WHERE archived = 0 AND updated_at < ?",
            (cutoff,),
        )
        return cur.rowcount


def dashboard_stats() -> dict:
    """Aggregate stats across all chats."""
    import datetime as _dt
    week_ago = (_dt.datetime.now() - _dt.timedelta(days=7)).isoformat(timespec="seconds")
    with _connect() as c:
        total_chats = c.execute("SELECT COUNT(*) FROM chats WHERE archived = 0").fetchone()[0]
        total_msgs = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        week_msgs = c.execute("SELECT COUNT(*) FROM messages WHERE created_at > ?", (week_ago,)).fetchone()[0]
        fav_model = c.execute(
            "SELECT model, COUNT(*) AS cnt FROM chats GROUP BY model ORDER BY cnt DESC LIMIT 1"
        ).fetchone()
        avg_len = c.execute(
            "SELECT AVG(LENGTH(content)) FROM messages WHERE role = 'assistant' AND content != ''"
        ).fetchone()[0] or 0
    return {
        "total_chats": total_chats,
        "total_messages": total_msgs,
        "messages_this_week": week_msgs,
        "favorite_model": fav_model["model"] if fav_model else "none",
        "avg_response_chars": int(avg_len),
    }


def set_project(chat_id: int, project: str) -> None:
    with _connect() as c:
        c.execute("UPDATE chats SET project = ? WHERE id = ?", (project, chat_id))


def set_stop_reason(message_id: int, reason: str) -> None:
    with _connect() as c:
        c.execute("UPDATE messages SET stop_reason = ? WHERE id = ?", (reason, message_id))


def message_count(chat_id: int) -> int:
    with _connect() as c:
        row = c.execute("SELECT COUNT(*) FROM messages WHERE chat_id = ?", (chat_id,)).fetchone()
    return row[0] if row else 0


def message_counts_bulk() -> dict:
    """Return {chat_id: count} for all chats in one query."""
    with _connect() as c:
        rows = c.execute("SELECT chat_id, COUNT(*) AS cnt FROM messages GROUP BY chat_id").fetchall()
    return {r["chat_id"]: r["cnt"] for r in rows}


def total_chat_count() -> int:
    with _connect() as c:
        return c.execute("SELECT COUNT(*) FROM chats WHERE archived = 0").fetchone()[0]


def bulk_archive(chat_ids: List[int]) -> None:
    if not chat_ids:
        return
    with _connect() as c:
        placeholders = ",".join("?" * len(chat_ids))
        c.execute(f"UPDATE chats SET archived = 1 WHERE id IN ({placeholders})", chat_ids)


def bulk_delete(chat_ids: List[int]) -> None:
    if not chat_ids:
        return
    with _connect() as c:
        placeholders = ",".join("?" * len(chat_ids))
        c.execute(f"DELETE FROM chats WHERE id IN ({placeholders})", chat_ids)


def first_user_message(chat_id: int) -> Optional[str]:
    """Used to auto-title a chat from its first user message."""
    with _connect() as c:
        row = c.execute(
            "SELECT content FROM messages WHERE chat_id = ? AND role = 'user' ORDER BY id ASC LIMIT 1",
            (chat_id,),
        ).fetchone()
    return row["content"] if row else None
