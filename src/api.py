"""Anthropic API client + Qt worker for streaming chat responses.

The streaming generator runs inside a QThread so the main UI thread is never
blocked. Signals carry text chunks back to the window for incremental render.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Signal


class StreamWorker(QThread):
    """Background thread that streams a single assistant turn from Anthropic.

    Signals
    -------
    chunk(str)        — emitted for every text delta as it arrives
    finished_ok(str)  — emitted on clean completion with the full response text
    failed(str)       — emitted on any error with a human-readable message
    """
    chunk       = Signal(str)
    finished_ok = Signal(str)
    failed      = Signal(str)

    def __init__(self,
                 api_key: str,
                 model: str,
                 history: List[Dict[str, Any]],
                 system_prompt: Optional[str] = None,
                 max_tokens: int = 4096,
                 thinking_effort: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self._api_key       = api_key
        self._model         = model
        self._history       = history
        self._system_prompt = system_prompt or None
        self._max_tokens    = max_tokens
        self._thinking      = thinking_effort
        self._cancel        = False
        self._buffer: List[str] = []

    def cancel(self) -> None:
        """Request cancellation. The worker checks this between chunks."""
        self._cancel = True

    def run(self) -> None:  # QThread entry point
        try:
            import anthropic
        except ImportError as e:
            self.failed.emit(f"anthropic SDK not installed: {e}")
            return

        try:
            client = anthropic.Anthropic(api_key=self._api_key)
        except Exception as e:
            self.failed.emit(f"Failed to create Anthropic client: {e}")
            return

        # Build the request kwargs. The Messages API takes `messages` and an
        # optional top-level `system` parameter (NOT a system-role message).
        kwargs = {
            "model":      self._model,
            "max_tokens": self._max_tokens,
            "messages":   self._history,
        }
        if self._system_prompt:
            kwargs["system"] = self._system_prompt
        if self._thinking and self._thinking != "off":
            budget_map = {"low": 2000, "high": 10000, "max": 50000}
            budget = budget_map.get(self._thinking, 10000)
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            kwargs["max_tokens"] = max(self._max_tokens, budget + 1000)

        try:
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    if self._cancel:
                        break
                    self._buffer.append(text)
                    self.chunk.emit(text)
        except Exception as e:  # network, auth, rate-limit, malformed request, …
            self.failed.emit(_friendly_error(e))
            return

        if self._cancel:
            self.failed.emit("Cancelled by user.")
            return

        self.finished_ok.emit("".join(self._buffer))


def _friendly_error(e: BaseException) -> str:
    """Convert anthropic SDK errors into a human-readable single line."""
    try:
        import anthropic
    except ImportError:
        return f"{type(e).__name__}: {e}"

    if isinstance(e, anthropic.AuthenticationError):
        return ("Authentication failed (401). Check that your ANTHROPIC_API_KEY "
                "is valid and starts with 'sk-ant-'.")
    if isinstance(e, anthropic.PermissionDeniedError):
        return ("Permission denied (403). Your API key does not have access to "
                "this model or feature.")
    if isinstance(e, anthropic.NotFoundError):
        return f"Model not found: {e}. Check the model ID in Settings."
    if isinstance(e, anthropic.RateLimitError):
        return ("Rate-limited by Anthropic (429). Wait a moment and try again, "
                "or upgrade your plan at console.anthropic.com.")
    if isinstance(e, anthropic.APIConnectionError):
        return f"Network error reaching api.anthropic.com: {e}"
    if isinstance(e, anthropic.APIStatusError):
        return f"Anthropic API error ({getattr(e, 'status_code', '?')}): {e}"
    return f"{type(e).__name__}: {e}"
