"""Bridge backend — relay through the local `bridge_to_claude` HTTP gateway.

The bridge exposes an OpenAI-compatible `/v1/chat/completions` endpoint on
the user-configured IP at port 7331 (the bridge's default). We only ask the
user for the IP; everything else (port, path, no API key) uses bridge defaults.

Wire format: standard OpenAI Server-Sent Events stream.
  Each non-empty line begins with `data: ` followed by either `[DONE]` or a
  JSON chunk shaped like {choices:[{delta:{content:"..."}}]}.

Limitations carried from the bridge:
  • No image / document support — the bridge silently drops non-text blocks.
    We flatten multi-part user content to text + `[Attachment: ...]` markers
    so Claude at least knows there was a file the user couldn't send.
  • Stateless — full conversation history is replayed every turn.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from PySide6.QtCore import QThread, Signal

from .config import BRIDGE_PATH, BRIDGE_PORT, AUTH_CUSTOM


def _flatten_content(content: Any) -> str:
    """Turn an Anthropic multi-part content list into plain text for the bridge.

    Text blocks pass through unchanged; image/document blocks become a short
    `[Attachment: <kind>]` marker so the assistant knows a file was elided.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "image":
            parts.append("[Attachment: image — not supported via bridge mode]")
        elif btype == "document":
            title = block.get("title", "document")
            parts.append(f"[Attachment: {title} — not supported via bridge mode]")
    result = "\n".join(p for p in parts if p)
    return result if result else "(empty message)"


def _build_openai_messages(history: List[Dict[str, Any]],
                            system_prompt: Optional[str]) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    for h in history:
        role = h.get("role")
        if role not in ("user", "assistant"):
            continue
        msgs.append({"role": role, "content": _flatten_content(h.get("content"))})
    return msgs


class BridgeWorker(QThread):
    """Background thread that streams a chat turn through the local bridge.

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
                 bridge_ip:    str,
                 model:        str,
                 history:      List[Dict[str, Any]],
                 system_prompt: Optional[str] = None,
                 max_tokens:   int = 4096,
                 api_key:      str = "",
                 parent=None) -> None:
        super().__init__(parent)
        import re as _re
        _ip = bridge_ip.strip()
        self._invalid = False
        if not _re.fullmatch(r'[A-Za-z0-9._:-]+', _ip):
            self._invalid = True
            self._invalid_msg = f"Invalid bridge IP: {_ip!r}"
            self._url = ""
        else:
            self._url = f"http://{_ip}:{BRIDGE_PORT}{BRIDGE_PATH}"
        self._api_key = api_key
        self._payload = {
            "model":      model,
            "messages":   _build_openai_messages(history, system_prompt),
            "stream":     True,
            "max_tokens": max_tokens,
        }
        self._cancel = False
        self._buffer: List[str] = []
        self._client: Optional[httpx.Client] = None
        self.finish_reason: Optional[str] = None

    def cancel(self) -> None:
        self._cancel = True
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    def run(self) -> None:
        if getattr(self, '_invalid', False):
            self.failed.emit(self._invalid_msg)
            return
        try:
            self._client = httpx.Client(timeout=httpx.Timeout(connect=10.0, read=600.0,
                                                              write=30.0, pool=10.0))
            headers = {"Accept": "text/event-stream",
                       "Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            with self._client.stream(
                "POST", self._url,
                json=self._payload,
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")[:500]
                    self.failed.emit(self._friendly_status(resp.status_code, body))
                    return
                for raw in resp.iter_lines():
                    if self._cancel:
                        break
                    if not raw:
                        continue
                    line = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        evt = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if "error" in evt:
                        err_msg = evt["error"].get("message", "Unknown bridge error")
                        self.failed.emit(f"Bridge error: {err_msg}")
                        return
                    choices = evt.get("choices") or []
                    if not choices:
                        continue
                    fr = choices[0].get("finish_reason")
                    if fr:
                        self.finish_reason = fr
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        self._buffer.append(text)
                        self.chunk.emit(text)
        except httpx.ConnectError as e:
            self.failed.emit(
                f"Cannot reach the bridge at {self._url}. Is it running? "
                f"(see bridge_to_claude/README — `./run.sh` to start it). Details: {e}"
            )
            return
        except httpx.ReadTimeout:
            self.failed.emit("Bridge request timed out waiting for a response.")
            return
        except Exception as e:
            self.failed.emit(f"Bridge error: {type(e).__name__}: {e}")
            return
        finally:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass

        if self._cancel:
            self.failed.emit("Cancelled by user.")
            return
        self.finished_ok.emit("".join(self._buffer))

    @staticmethod
    def _friendly_status(code: int, body: str) -> str:
        if code == 401:
            return ("Bridge returned 401 — it was started with --api-key but Oracle "
                    "doesn't pass one. Restart the bridge without --api-key, or "
                    "extend Oracle to send a Bearer token.")
        if code == 404:
            return f"Bridge returned 404 for {BRIDGE_PATH}. Is this really the bridge?"
        if code >= 500:
            return f"Bridge returned {code}: {body[:200]}"
        return f"Bridge returned HTTP {code}: {body[:200]}"


class CustomGatewayWorker(QThread):
    """OpenAI-compatible gateway for any provider (Ollama, Grok, Gemini, ChatGPT, etc.)."""
    chunk       = Signal(str)
    finished_ok = Signal(str)
    failed      = Signal(str)

    def __init__(self,
                 url:           str,
                 api_key:       str,
                 model:         str,
                 history:       List[Dict[str, Any]],
                 system_prompt: Optional[str] = None,
                 max_tokens:    int = 4096,
                 parent=None) -> None:
        super().__init__(parent)
        self._url = url.rstrip("/")
        from urllib.parse import urlparse
        self._invalid_url = False
        if "://" in self._url and not self._url.startswith(("http://", "https://")):
            self._invalid_url = True
        elif not self._url.startswith(("http://", "https://")):
            self._url = "http://" + self._url
        parsed = urlparse(self._url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            self._url = ""
            self._invalid_url = True
        elif not self._url.endswith("/chat/completions"):
            self._url = self._url.rstrip("/") + "/v1/chat/completions"
        self._api_key = api_key
        self._payload = {
            "model":      model,
            "messages":   _build_openai_messages(history, system_prompt),
            "stream":     True,
            "max_tokens": max_tokens,
        }
        self._cancel = False
        self._buffer: List[str] = []
        self._client: Optional[httpx.Client] = None
        self.finish_reason: Optional[str] = None

    def cancel(self) -> None:
        self._cancel = True
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    def run(self) -> None:
        if self._invalid_url:
            self.failed.emit(f"Invalid gateway URL: must use http:// or https://")
            return
        headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            self._client = httpx.Client(timeout=httpx.Timeout(connect=10.0, read=600.0,
                                                              write=30.0, pool=10.0))
            with self._client.stream("POST", self._url, json=self._payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")[:500]
                    self.failed.emit(f"Gateway returned HTTP {resp.status_code}: {body[:200]}")
                    return
                for raw in resp.iter_lines():
                    if self._cancel:
                        break
                    if not raw:
                        continue
                    line = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        evt = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if "error" in evt:
                        err_msg = evt["error"].get("message", "Unknown gateway error")
                        self.failed.emit(f"Gateway error: {err_msg}")
                        return
                    choices = evt.get("choices") or []
                    if not choices:
                        continue
                    fr = choices[0].get("finish_reason")
                    if fr:
                        self.finish_reason = fr
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        self._buffer.append(text)
                        self.chunk.emit(text)
        except httpx.ConnectError as e:
            self.failed.emit(f"Cannot reach gateway at {self._url}: {e}")
            return
        except httpx.ReadTimeout:
            self.failed.emit("Gateway request timed out.")
            return
        except Exception as e:
            self.failed.emit(f"Gateway error: {type(e).__name__}: {e}")
            return
        finally:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
        if self._cancel:
            self.failed.emit("Cancelled by user.")
            return
        self.finished_ok.emit("".join(self._buffer))
