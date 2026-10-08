# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Desk thread list rows and ticket description text."""

import re
from datetime import datetime

_INLINE_IMAGE_TOKEN = re.compile(
    r"(?:/api/v1/threads/\d+/inlineImages/)?"
    r"[a-z0-9]{40,}(?:\?[a-z0-9=&_.]+)?(?:\.png|\.jpg|\.gif)?",
    re.I,
)
_FOOTNOTE_BLOCK = re.compile(
    r"\n\[\d+\]\s+[^\n]+(?:\n\[\d+\]\s+[^\n]+)*\s*$",
    re.I,
)
_SIGNATURE_START = re.compile(
    r"(?:"
    r"Meilleures salutations|Mit freundlichen Grüßen|Mit freundlichen Gruessen|"
    r"Best regards|Kind regards|Cordialement|Salutations distinguées|"
    r"Viele Grüße|Freundliche Grüße"
    r")\b",
    re.I,
)
_TRAILING_URL = re.compile(r"\s+(?:https?://\S+|www\.\S+)\s*$", re.I)
_WHITESPACE = re.compile(r"[ \t]+\n")
_MULTI_NL = re.compile(r"\n{3,}")


def desk_thread_datetime(thread):
    """Parse Desk thread time for ordering (sendDateTime preferred)."""
    if not thread:
        return datetime.min
    raw = thread.get("sendDateTime") or thread.get("createdTime")
    if not raw:
        return datetime.min
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(str(raw).replace("Z", ""))
        except ValueError:
            return datetime.min


def sort_threads_for_chatter(threads):
    """Oldest first — matches Odoo chatter (read top → bottom in time order).

    Desk list APIs default to newest-first; posting in that order without
    per-message dates scrambles the timeline.
    """
    return sorted(threads or [], key=desk_thread_datetime)


def is_truncated_desk_summary(text):
    text = (text or "").strip()
    return bool(text) and (text.endswith("...") or text.endswith("…"))


def thread_body(thread):
    """Full thread body; list API summaries ending in … are not used."""
    if not thread:
        return False
    content = str(thread.get("content") or "").strip()
    if content:
        return content
    summary = str(thread.get("summary") or "").strip()
    if summary and not is_truncated_desk_summary(summary):
        return summary
    return False


def trim_desk_html_before_signature(html):
    """Keep message body HTML (including content images); drop signature/footer block."""
    text = str(html or "").strip()
    if not text:
        return False
    sig = _SIGNATURE_START.search(text)
    if sig:
        text = text[: sig.start()]
    text = _FOOTNOTE_BLOCK.sub("", text)
    return text.strip() or False


def postprocess_desk_plaintext(plain):
    """Readable helpdesk description: no Desk inline-image tokens or email footers."""
    text = str(plain or "").strip()
    if not text:
        return False
    text = _INLINE_IMAGE_TOKEN.sub(" ", text)
    text = re.sub(r"\bNone\b", " ", text)
    text = re.sub(r"\[\d+\](?=\s|$)", " ", text)
    sig = _SIGNATURE_START.search(text)
    if sig:
        text = text[: sig.start()]
    text = _FOOTNOTE_BLOCK.sub("", text)
    while True:
        trimmed = _TRAILING_URL.sub("", text)
        if trimmed == text:
            break
        text = trimmed
    text = _WHITESPACE.sub("\n", text)
    text = _MULTI_NL.sub("\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip() or False


def desk_description_looks_corrupted(text):
    """True when description still has raw Desk inline URLs or plaintext token junk."""
    raw = str(text or "")
    if not raw:
        return False
    if "/inlineImages/" in raw:
        return True
    if _INLINE_IMAGE_TOKEN.search(raw):
        return True
    if re.search(r"\bNone\b.*\[\d+\]", raw):
        return True
    if re.search(r"/api/v1/threads/\d+/inlineImages/", raw):
        return True
    return False


def desk_plaintext_looks_corrupted(text):
    return desk_description_looks_corrupted(text)
