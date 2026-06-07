"""Claude Code relay backend — subprocesses the local `claude` CLI binary.

**EXPERIMENTAL.** This backend pipes through Claude Code so Oracle can use
the user's `claude /login` (OAuth) session instead of a separate API key.

Important: we deliberately do NOT use `--bare`, because `--bare` mode
disables OAuth and keychain reads. The trade-off is that Claude Code's
normal startup behavior runs on every send (auto-memory, CLAUDE.md
discovery in cwd, hooks, plugins). We mitigate the CLAUDE.md leak by
running the subprocess from a dedicated neutral cwd (`~/.local/share/
oracle/relay-cwd`) so it won't accidentally inhale unrelated project
context.

Each Oracle chat stores a Claude Code session UUID so we can `--resume`
it on subsequent turns and keep multi-turn context intact.

Stream protocol:
    The CLI emits one JSON object per line. Event types we care about:
      • `system` / subtype=`init`             — first event, contains `session_id`
      • `stream_event` / event.type=`content_block_delta`
        with `delta.type=text_delta`           — incremental text chunk
      • `assistant` / `message.content[*].text` — final assembled message
      • `result`                              — terminal event (cost, tokens)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from .config import DATA_DIR


# Neutral cwd for the subprocess. Created on demand. Keeps Claude Code's
# CLAUDE.md auto-discovery from inhaling unrelated project context.
RELAY_CWD = DATA_DIR / "relay-cwd"


def cleanup_relay_attachments() -> None:
    """Remove stale staged attachment directories from previous sessions."""
    att_dir = RELAY_CWD / "attachments"
    if att_dir.is_dir():
        for child in att_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)


def claude_binary_available(binary: str = "claude") -> bool:
    """Return True if the given binary looks like a valid claude CLI."""
    if not binary or not binary.strip():
        return False
    resolved = shutil.which(binary)
    if not resolved and os.path.isabs(binary) and os.access(binary, os.X_OK):
        resolved = binary
    if not resolved:
        return False
    base = os.path.basename(resolved).lower()
    if "claude" not in base:
        return False
    return True


class ClaudeCodeWorker(QThread):
    """Background thread that relays a chat turn through `claude -p`.

    Signals
    -------
    chunk(str)            — emitted for every text delta as it arrives
    session_ready(str)    — emitted once with the session UUID (caller persists it for --resume)
    finished_ok(str)      — emitted on clean completion with the full response text
    failed(str)           — emitted on any error with a human-readable message
    """
    chunk         = Signal(str)
    session_ready = Signal(str)
    finished_ok   = Signal(str)
    failed        = Signal(str)

    def __init__(self,
                 user_message:  str,
                 model:         str,
                 system_prompt: Optional[str] = None,
                 binary:        str = "claude",
                 resume_session_id: Optional[str] = None,
                 attachment_paths: Optional[List[Path]] = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._user_message       = user_message
        self._model              = model
        self._system_prompt      = (system_prompt or "").strip() or None
        self._binary             = binary or "claude"
        self._resume_session_id  = resume_session_id
        self._attachment_paths   = list(attachment_paths or [])
        self._cancel             = False
        self._buffer: List[str]  = []
        self._proc: Optional[subprocess.Popen] = None

    def cancel(self) -> None:
        """Request cancellation. Terminates the subprocess if still running."""
        self._cancel = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except (OSError, ProcessLookupError):
                pass

    # ── attachment staging ────────────────────────────────────────────────
    def _stage_attachments(self) -> str:
        """Copy attachment files into RELAY_CWD and return @-references to append.

        Files are namespaced per turn under RELAY_CWD/attachments/<uuid>/ so
        repeated sends don't collide and a follow-up `--resume` turn can still
        reach prior attachments by their stable per-chat path.
        """
        if not self._attachment_paths:
            return ""
        bucket = RELAY_CWD / "attachments" / uuid.uuid4().hex[:8]
        bucket.mkdir(parents=True, exist_ok=True)
        refs: List[str] = []
        for src in self._attachment_paths:
            src = Path(src)
            if not src.exists():
                continue
            # Sanitize for the relay shell: drop spaces/quotes from the filename.
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", src.name)
            dest = bucket / safe_name
            try:
                shutil.copy2(src, dest)
            except OSError:
                continue
            # Use a path relative to RELAY_CWD so the @-reference resolves inside
            # the subprocess's cwd.
            rel = dest.relative_to(RELAY_CWD)
            refs.append(f"@{rel}")
        return ("\n\nAttached files:\n" + "\n".join(refs)) if refs else ""

    # ── argv builder ──────────────────────────────────────────────────────
    def _build_argv(self) -> List[str]:
        # NOTE: we deliberately do NOT pass --bare. --bare disables OAuth /
        # keychain reads, which would defeat the entire purpose of this
        # backend (using the user's `claude /login` session). CLAUDE.md
        # auto-discovery is suppressed instead by running the subprocess
        # from a dedicated neutral cwd (see run() below).
        argv = [
            self._binary,
            "-p", self._user_message + self._attachment_refs,
            "--output-format", "stream-json",
            "--verbose",                       # required when --output-format=stream-json + --print
            "--include-partial-messages",      # token-level deltas
            "--model", self._model,
            "--disable-slash-commands",        # we don't want slash-commands firing in the relay
        ]
        if self._system_prompt:
            argv += ["--append-system-prompt", self._system_prompt]
        if self._resume_session_id:
            argv += ["--resume", self._resume_session_id]
        return argv

    # ── thread entry ──────────────────────────────────────────────────────
    def run(self) -> None:
        if not claude_binary_available(self._binary):
            self.failed.emit(
                f"`{self._binary}` is not on PATH. Install Claude Code from "
                "https://docs.claude.com/en/docs/claude-code/installation, "
                "or point Oracle at the binary in Settings."
            )
            return

        try:
            RELAY_CWD.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        try:
            self._attachment_refs = self._stage_attachments()
        except Exception as e:
            self.failed.emit(f"Failed to stage attachments: {e}")
            return
        argv = self._build_argv()
        try:
            self._proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,                 # line-buffered
                env=os.environ.copy(),
                cwd=str(RELAY_CWD),        # keeps CLAUDE.md auto-discovery from leaking project context
            )
        except FileNotFoundError:
            self.failed.emit(f"`{self._binary}` not found.")
            return
        except OSError as e:
            self.failed.emit(f"Failed to launch `{self._binary}`: {e}")
            return

        had_error = False
        final_text_from_assistant: Optional[str] = None

        try:
            assert self._proc.stdout is not None
            for raw in self._proc.stdout:
                if self._cancel:
                    break
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    # Defensive: log-style lines from claude --debug etc. Ignore.
                    continue

                etype = event.get("type")
                subtype = event.get("subtype")

                # First-event: pick up the session UUID and tell the UI
                if etype == "system" and subtype == "init":
                    sid = event.get("session_id")
                    if sid:
                        self.session_ready.emit(str(sid))
                    continue

                # Status pings — ignore
                if etype == "system" and subtype == "status":
                    continue

                # Incremental text deltas (preferred path when partial-messages on)
                if etype == "stream_event":
                    inner = event.get("event") or {}
                    if inner.get("type") == "content_block_delta":
                        delta = inner.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                self._buffer.append(text)
                                self.chunk.emit(text)
                    continue

                # Full assistant message (fallback if no partial events arrived)
                if etype == "assistant":
                    msg = event.get("message") or {}
                    if event.get("error"):
                        had_error = True
                        # Extract message text — usually "Not logged in · Please run /login" or similar
                        text_blocks = [b.get("text", "") for b in (msg.get("content") or [])
                                        if b.get("type") == "text"]
                        err_text = " ".join(text_blocks).strip() or "unknown error"
                        self.failed.emit(_friendly_claude_error(err_text))
                        return
                    if not self._buffer:  # no partial events arrived; capture full text here
                        text_blocks = [b.get("text", "") for b in (msg.get("content") or [])
                                        if b.get("type") == "text"]
                        final_text_from_assistant = "".join(text_blocks)
                    continue

                # Terminal event
                if etype == "result":
                    if event.get("is_error"):
                        had_error = True
                        msg = event.get("result") or "Claude Code reported an error."
                        self.failed.emit(_friendly_claude_error(str(msg)))
                        return
                    # otherwise: clean completion, fall through to the post-loop emit
                    continue

            # Drain stderr for diagnostics if the process is dead but we still have output
            rc = self._proc.poll()
            if rc is None:
                rc = self._proc.wait(timeout=2)
            if rc != 0 and not had_error and not self._cancel:
                err = (self._proc.stderr.read() if self._proc.stderr else "") or f"exit code {rc}"
                self.failed.emit(_friendly_claude_error(err.strip()))
                return

        except Exception as e:
            self.failed.emit(f"Claude Code relay error: {type(e).__name__}: {e}")
            return
        finally:
            try:
                if self._proc and self._proc.stdout: self._proc.stdout.close()
                if self._proc and self._proc.stderr: self._proc.stderr.close()
            except Exception:
                pass

        if self._cancel:
            self.failed.emit("Cancelled by user.")
            return

        full = "".join(self._buffer) if self._buffer else (final_text_from_assistant or "")
        self.finished_ok.emit(full)


def _friendly_claude_error(text: str) -> str:
    """Map known Claude Code error strings to user-friendly messages."""
    t = (text or "").lower()
    if "not logged in" in t or "please run /login" in t:
        return ("Claude Code is not logged in. Open a terminal and run `claude /login`, "
                "or set ANTHROPIC_API_KEY in your environment.")
    if "authentication_failed" in t or "401" in t:
        return ("Claude Code authentication failed. Re-run `claude /login` in your terminal.")
    if "rate" in t and "limit" in t:
        return "Rate-limited by Anthropic. Wait a moment and try again."
    return f"Claude Code error: {text.strip()}"
