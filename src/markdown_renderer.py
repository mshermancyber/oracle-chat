"""Markdown → HTML renderer for chat messages.

QTextBrowser supports a subset of HTML 4 + CSS 2.1. Important constraints
that shape this module:

  • External stylesheets and class selectors don't apply, so every visual
    detail must be in inline `style="…"` attributes.
  • That's why pygments is invoked with `noclasses=True` — it emits inline
    `style="color:#…"` spans instead of CSS class names.
  • The Markdown parser is reset between calls so streaming-time partial
    content doesn't leak state into the next render.

Streaming-render trade-off: parsing the full message on every chunk is
O(n) over message length, but markdown is fast (typically <5ms for a 4-KB
response) and QTextBrowser's diff renderer absorbs the work. We accept
transient "in-progress" rendering of unclosed code fences mid-stream.
"""
from __future__ import annotations

import html as _html
import re
import threading
from typing import List, Tuple

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension


# Single shared parser — reset() called before each conversion. Cheaper than
# constructing a Markdown instance per message.
_MD = markdown.Markdown(
    extensions=[
        "fenced_code",   # ```lang … ``` blocks
        "tables",        # GitHub-style pipe tables
        "nl2br",         # treat single newlines as <br/>
        "sane_lists",    # smarter ordered/unordered list handling
        CodeHiliteExtension(
            noclasses=True,             # emit inline styles, not CSS classes
            pygments_style="monokai",   # dark-theme palette to match Oracle
            linenums=False,
            guess_lang=False,            # only highlight when language is specified
        ),
    ],
    output_format="html5",
)


_code_blocks: List[str] = []
_render_lock = threading.Lock()

_FENCED_RE = re.compile(
    r'^```(\w*)\s*\n(.*?)^```\s*$',
    re.MULTILINE | re.DOTALL,
)

_CODEHILITE_RE = re.compile(r'<div class="codehilite"[^>]*>')

_CODE_DIV_STYLE = (
    '<div style="background:#1E1E1E;border:1px solid #2A3A5A;'
    'border-radius:6px;padding:10px 12px;margin:8px 0;'
    "font-family:Consolas,'JetBrains Mono',Menlo,monospace;font-size:13px;\">"
)

_CODE_DIV_ADJUSTED = (
    '<div style="background:#1E1E1E;border:1px solid #2A3A5A;border-top:none;'
    'border-radius:0 0 6px 6px;padding:10px 12px;margin:0 0 8px 0;'
    "font-family:Consolas,'JetBrains Mono',Menlo,monospace;font-size:13px;\">"
)


def _extract_code_blocks(md_text: str) -> List[Tuple[str, str]]:
    """Extract (language, code) tuples from fenced code blocks."""
    blocks = []
    for m in _FENCED_RE.finditer(md_text):
        lang = m.group(1) or ""
        code = m.group(2)
        if code.endswith("\n"):
            code = code[:-1]
        blocks.append((lang, code))
    return blocks


def _make_code_header(index: int, lang: str) -> str:
    lang_display = _html.escape(lang) if lang else "code"
    preview_link = ""
    if lang_display == "html":
        preview_link = (
            '&nbsp;&nbsp;'
            f'<a href="oracle://preview/{index}" style="color:#A855F7;text-decoration:none;">Preview</a>'
        )
    return (
        f'<table style="width:100%;background:#1A1A2E;border:1px solid #2A3A5A;'
        f'border-radius:6px 6px 0 0;margin:8px 0 0 0;" cellpadding="4" cellspacing="0">'
        f'<tr>'
        f'<td style="color:#94A3B8;font-size:11px;border:none;">{lang_display}</td>'
        f'<td style="text-align:right;font-size:11px;border:none;">'
        f'<a href="oracle://copy/{index}" style="color:#60A5FA;text-decoration:none;">Copy</a>'
        f'&nbsp;&nbsp;'
        f'<a href="oracle://apply/{index}" style="color:#60A5FA;text-decoration:none;">Apply</a>'
        f'&nbsp;&nbsp;'
        f'<a href="oracle://run/{index}" style="color:#22C55E;text-decoration:none;">Run</a>'
        f'{preview_link}'
        f'</td>'
        f'</tr></table>'
    )


def _inject_code_headers(html: str, extracted: List[Tuple[str, str]],
                         offset: int = 0) -> str:
    if not extracted:
        return html
    parts = html.split(_CODE_DIV_STYLE)
    if len(parts) <= 1:
        return html

    rebuilt = [parts[0]]
    for i, part in enumerate(parts[1:]):
        if i < len(extracted):
            header = _make_code_header(offset + i, extracted[i][0])
            rebuilt.append(header)
            rebuilt.append(_CODE_DIV_ADJUSTED)
        else:
            rebuilt.append(_CODE_DIV_STYLE)
        rebuilt.append(part)
    return "".join(rebuilt)


def get_code_blocks() -> List[str]:
    """Return code blocks extracted from the most recent render() call."""
    return list(_code_blocks)


def render(text: str, block_offset: int = 0) -> str:
    """Convert a markdown string to HTML suitable for QTextBrowser."""
    global _code_blocks
    with _render_lock:
        if not text:
            _code_blocks = []
            return ""

        extracted = _extract_code_blocks(text)
        _code_blocks = [code for (_lang, code) in extracted]

        _MD.reset()
        result = _MD.convert(text)
        result = _style_latex(result)
        result = _style_thinking(result)
        result = _style_citations(result)
        result = _wrap_for_qtextbrowser(result)
        result = _inject_code_headers(result, extracted, block_offset)
        return result


_LATEX_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
_LATEX_INLINE_RE = re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)')


def _style_latex(html_text: str) -> str:
    """Style LaTeX expressions with a distinct math appearance."""
    html_text = _LATEX_BLOCK_RE.sub(
        r'<div style="background:#0F1A35;border:1px solid #2A3A5A;border-radius:6px;'
        r'padding:10px 14px;margin:8px 0;font-family:serif;font-size:15px;'
        r'color:#FBBF24;text-align:center;">\1</div>',
        html_text,
    )
    html_text = _LATEX_INLINE_RE.sub(
        r'<span style="font-family:serif;color:#FBBF24;font-style:italic;">\1</span>',
        html_text,
    )
    return html_text


def _style_thinking(html_text: str) -> str:
    """Style <thinking>...</thinking> blocks as collapsible sections."""
    for open_tag in ('<thinking>', '&lt;thinking&gt;'):
        html_text = html_text.replace(
            open_tag,
            '<div style="background:#1A1A2E;border:1px solid #2A3A5A;border-radius:6px;'
            'padding:8px 12px;margin:8px 0;font-size:12px;color:#94A3B8;">'
            '<div style="font-size:10px;color:#60A5FA;font-weight:600;margin-bottom:4px;">THINKING</div>'
        )
    for close_tag in ('</thinking>', '&lt;/thinking&gt;'):
        html_text = html_text.replace(close_tag, '</div>')
    return html_text


_citation_sources: List[str] = []

_CITATION_RE = re.compile(r'\[(\d+)\]')


def set_citation_sources(sources: List[str]) -> None:
    global _citation_sources
    _citation_sources = list(sources)


def _style_citations(html_text: str) -> str:
    """Style [N] citation references as clickable links."""
    if not _citation_sources:
        return html_text
    def _replace_citation(m):
        idx = int(m.group(1))
        if 1 <= idx <= len(_citation_sources):
            return (f'<a href="oracle://citation/{idx}" '
                    f'style="color:#60A5FA;font-weight:600;text-decoration:none;">[{idx}]</a>')
        return m.group(0)
    return _CITATION_RE.sub(_replace_citation, html_text)


def _wrap_for_qtextbrowser(html: str) -> str:
    """Tweak the pygments / markdown output so it renders well in QTextBrowser.

    QTextBrowser handles `<pre>` and `<code>` but doesn't honour padding on
    pygments' default `<div class="codehilite">` container — we add inline
    styling here so the dark code background shows correctly.
    """
    # codehilite wraps code in <div class="codehilite" style="..."><pre>…</pre></div>.
    # Replace the div with an inline-styled equivalent (regex because codehilite
    # may include an inline background style from pygments).
    html = _CODEHILITE_RE.sub(_CODE_DIV_STYLE, html)
    # Inline-style standalone <pre> (when no codehilite — i.e. unfenced indented blocks)
    html = html.replace(
        '<pre><code>',
        '<pre style="background:#1E1E1E;border:1px solid #2A3A5A;border-radius:6px;'
        'padding:10px 12px;margin:8px 0;font-family:Consolas,\'JetBrains Mono\',Menlo,monospace;'
        'font-size:13px;color:#E5ECF7;"><code>'
    )
    # Inline `code` in regular paragraphs
    html = html.replace(
        '<code>',
        '<code style="background:#17223B;color:#FBBF24;padding:1px 5px;'
        'border-radius:3px;font-family:Consolas,\'JetBrains Mono\',Menlo,monospace;'
        'font-size:13px;">'
    )
    # Tables — give them a visible border
    html = html.replace(
        '<table>',
        '<table style="border-collapse:collapse;margin:10px 0;border:1px solid #2A3A5A;">'
    )
    html = html.replace(
        '<th>',
        '<th style="background:#17223B;border:1px solid #2A3A5A;padding:6px 10px;text-align:left;font-weight:600;">'
    )
    html = html.replace(
        '<td>',
        '<td style="border:1px solid #2A3A5A;padding:6px 10px;">'
    )
    # Blockquotes — left border accent
    html = html.replace(
        '<blockquote>',
        '<blockquote style="border-left:3px solid #60A5FA;margin:8px 0;padding:4px 12px;color:#CBD5E1;background:#0F1A35;">'
    )
    # Headings — keep them visually distinct but compact
    for h_tag, size in (("h1", "20px"), ("h2", "17px"), ("h3", "15px"), ("h4", "14px")):
        html = html.replace(
            f"<{h_tag}>",
            f'<{h_tag} style="font-size:{size};margin:10px 0 6px;color:#E5ECF7;font-weight:600;">'
        )
    # Lists — tighten spacing
    html = html.replace('<ul>', '<ul style="margin:6px 0;padding-left:22px;">')
    html = html.replace('<ol>', '<ol style="margin:6px 0;padding-left:22px;">')
    html = html.replace('<li>', '<li style="margin:2px 0;">')
    # Horizontal rule
    html = html.replace('<hr />', '<hr style="border:none;border-top:1px solid #2A3A5A;margin:12px 0;"/>')
    return html
