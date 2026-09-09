"""Best-effort text extraction so Nudge can tutor from uploaded materials."""

from __future__ import annotations

import io

MAX_STORED_TEXT = 20_000

UPLOAD_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json", ".py", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".py"}


def ext_of(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def extract_text(filename: str, data: bytes) -> str:
    """Readable text for the tutor context; empty string when the file has none."""
    ext = ext_of(filename)
    try:
        if ext in TEXT_EXTENSIONS:
            return _cap(data.decode("utf-8", errors="replace"))
        if ext == ".pdf":
            return _cap(_pdf_text(data))
    except Exception:
        return ""
    return ""


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        chunk = page.extract_text() or ""
        parts.append(chunk)
        total += len(chunk)
        if total > MAX_STORED_TEXT:
            break
    return "\n".join(parts)


def _cap(text: str) -> str:
    return text.strip()[:MAX_STORED_TEXT]
