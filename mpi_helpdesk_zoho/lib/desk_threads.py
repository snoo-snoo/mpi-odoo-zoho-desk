# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Desk thread list rows and ticket description text."""

from datetime import datetime


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
