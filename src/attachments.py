"""Attachment handling — turn a file on disk into an Anthropic content block.

Supported kinds:
  • image   — png/jpeg/gif/webp → native `image` content block (base64 source)
  • pdf     — application/pdf  → native `document` content block (base64 source)
  • docx    — converted to PDF via `libreoffice --headless`, then sent as a
              `document` block. The converted PDF is cached next to the
              original so repeat sends don't re-convert.

Anything else raises UnsupportedAttachment.
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .config import DATA_DIR


PDF_CACHE_DIR = DATA_DIR / "pdf-cache"


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
DOC_EXTS   = {".pdf", ".docx"}
ALL_EXTS   = IMAGE_EXTS | DOC_EXTS

IMAGE_MIME = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}


class UnsupportedAttachment(Exception):
    pass


class AttachmentBuildError(Exception):
    pass


@dataclass
class AttachmentSpec:
    """A user-facing attachment: a file the user picked, with a classified kind."""
    path: Path
    kind: str         # "image" | "pdf" | "docx"
    mime: str

    @property
    def display_name(self) -> str:
        return self.path.name


def classify(path: Path) -> AttachmentSpec:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return AttachmentSpec(path=path, kind="image", mime=IMAGE_MIME[ext])
    if ext == ".pdf":
        return AttachmentSpec(path=path, kind="pdf", mime="application/pdf")
    if ext == ".docx":
        return AttachmentSpec(
            path=path,
            kind="docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    raise UnsupportedAttachment(
        f"Unsupported file type: {path.name} (only images and .docx/.pdf are supported)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# .docx → PDF conversion (cached)
# ─────────────────────────────────────────────────────────────────────────────
def _libreoffice_binary() -> Optional[str]:
    return shutil.which("libreoffice") or shutil.which("soffice")


def _docx_pdf_cache_path(docx_path: Path) -> Path:
    """Cache converted PDFs in Oracle's data dir, keyed by abs-path + mtime hash.

    Keeps the cache out of the user's working directories (we don't want a
    .oracle-pdf-cache/ appearing next to a file they attached from ~/Downloads).
    """
    st = docx_path.stat()
    key = f"{docx_path.resolve()}|{int(st.st_mtime)}|{st.st_size}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return PDF_CACHE_DIR / f"{digest}_{docx_path.stem}.pdf"


def docx_to_pdf(docx_path: Path) -> Path:
    """Convert a .docx to PDF via libreoffice, returning the PDF path.

    Cached: if the cached PDF for this (path, mtime, size) exists, reuse it.
    """
    cached = _docx_pdf_cache_path(docx_path)
    if cached.exists():
        return cached

    binary = _libreoffice_binary()
    if not binary:
        raise AttachmentBuildError(
            "libreoffice is not installed — install libreoffice to upload .docx files, "
            "or convert to PDF first."
        )

    cached.parent.mkdir(parents=True, exist_ok=True)
    # libreoffice writes to --outdir as <stem>.pdf — we then rename to the
    # hashed cache name so multiple docx files with the same stem don't collide.
    raw_output = cached.parent / (docx_path.stem + ".pdf")
    if raw_output.exists():
        raw_output.unlink()
    try:
        proc = subprocess.run(
            [binary, "--headless", "--convert-to", "pdf",
             "--outdir", str(cached.parent), str(docx_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise AttachmentBuildError(f"libreoffice timed out converting {docx_path.name}")
    except OSError as e:
        raise AttachmentBuildError(f"Failed to run libreoffice: {e}")

    if proc.returncode != 0 or not raw_output.exists():
        err = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["unknown error"]
        raise AttachmentBuildError(
            f"libreoffice failed to convert {docx_path.name}: {err[0]}"
        )
    raw_output.replace(cached)
    return cached


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic API content-block builders
# ─────────────────────────────────────────────────────────────────────────────
def build_content_block(spec: AttachmentSpec) -> Dict:
    """Return an Anthropic Messages API content block for this attachment."""
    if spec.kind == "image":
        data = base64.standard_b64encode(spec.path.read_bytes()).decode("ascii")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": spec.mime, "data": data},
        }
    if spec.kind == "pdf":
        data = base64.standard_b64encode(spec.path.read_bytes()).decode("ascii")
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    if spec.kind == "docx":
        pdf_path = docx_to_pdf(spec.path)
        data = base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")
        # The block still carries the original docx filename in `title` so
        # Claude knows what to call it in its response.
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
            "title": spec.path.name,
        }
    raise UnsupportedAttachment(f"Cannot build content block for kind={spec.kind}")


def guess_mime(path: Path) -> str:
    """Best-effort MIME for storage metadata."""
    ext = path.suffix.lower()
    if ext in IMAGE_MIME:
        return IMAGE_MIME[ext]
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"
