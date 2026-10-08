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


def desk_ticket_description(detail, threads=None):
    """Prefer ticket description; fall back to the first thread with body text."""
    description = (detail or {}).get("description") if detail else None
    if description and str(description).strip():
        return description
    for thread in sort_threads_for_chatter(threads):
        body = thread_body(thread)
        if body:
            return body
    return False


def thread_body(thread):
    if not thread:
        return False
    content = thread.get("content") or thread.get("summary") or ""
    content = str(content).strip()
    return content or False
