# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Desk attachment metadata and download URLs."""

import mimetypes
import re

from .desk_hosts import desk_root

_ATTACHMENT_ID_RE = re.compile(r"/attachments/([^/]+)")
_THREAD_IN_HREF_RE = re.compile(r"/threads/(\d+)/attachments/", re.I)


def desk_attachment_id(row):
    raw_id = row.get("id")
    if raw_id:
        return str(raw_id)
    href = (row.get("href") or row.get("downloadUrl") or "").strip()
    if not href:
        return ""
    match = _ATTACHMENT_ID_RE.search(href)
    return match.group(1) if match else ""


def desk_attachment_thread_id(row):
    for key in ("threadId", "thread_id"):
        raw = row.get(key)
        if raw:
            return str(raw)
    href = (row.get("href") or row.get("downloadUrl") or "").strip()
    match = _THREAD_IN_HREF_RE.search(href)
    return match.group(1) if match else False


def merge_desk_attachment_rows(*row_lists):
    """Dedupe Desk attachment metadata rows by attachment id."""
    merged = []
    seen = set()
    for rows in row_lists:
        for row in rows or []:
            att_id = desk_attachment_id(row)
            if not att_id or att_id in seen:
                continue
            seen.add(att_id)
            merged.append(row)
    return merged


def desk_attachment_mimetype(row):
    for key in ("contentType", "mimeType", "type"):
        raw = (row.get(key) or "").strip()
        if raw and "/" in raw:
            return raw
    name = row.get("name") or ""
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def desk_attachment_download_url(client, row, *, desk_ticket_id, desk_thread_id=None):
    href = (row.get("href") or row.get("downloadUrl") or row.get("previewurl") or "").strip()
    if href:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        base = desk_root(client.dc)
        return "%s%s" % (base, href if href.startswith("/") else "/" + href)
    att_id = desk_attachment_id(row)
    if not att_id or not desk_ticket_id:
        return ""
    base = desk_root(client.dc)
    if desk_thread_id:
        return "%s/api/v1/tickets/%s/threads/%s/attachments/%s/content" % (
            base,
            desk_ticket_id,
            desk_thread_id,
            att_id,
        )
    return "%s/api/v1/tickets/%s/attachments/%s/content" % (base, desk_ticket_id, att_id)
