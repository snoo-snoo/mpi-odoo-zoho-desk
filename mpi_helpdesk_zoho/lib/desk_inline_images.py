# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Embed Desk thread inlineImages as Odoo attachments in HTML descriptions."""

import html
import logging
import mimetypes
import re

from .desk_hosts import desk_root

_logger = logging.getLogger(__name__)

_IMG_TAG = re.compile(r'(<img\b[^>]*\bsrc=)(["\'])([^"\']+)(\2[^>]*>)', re.I)
_INLINE_IMAGE_PATH = re.compile(r"/inlineImages/", re.I)
# Desk thread HTML often omits /tickets/{ticketId}/ — see Zoho community reports.
_SHORT_INLINE_PATH = re.compile(
    r"/api/v1/threads/(\d+)/inlineImages/([^?\s\"']+)(\?[^\"'\s>]*)?",
    re.I,
)


def desk_api_absolute_url(client, src):
    raw = html.unescape((src or "").strip())
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    base = desk_root(client.dc).rstrip("/")
    if raw.startswith("/"):
        return "%s%s" % (base, raw)
    return "%s/%s" % (base, raw)


def desk_inline_image_download_url(client, src, *, desk_ticket_id=None):
    """Build a Desk API URL for an inlineImages src (fix shorthand paths)."""
    raw = html.unescape((src or "").strip())
    if not raw:
        return ""
    if re.search(r"/api/v1/tickets/\d+/threads/", raw, re.I):
        return desk_api_absolute_url(client, raw)
    match = _SHORT_INLINE_PATH.search(raw)
    if match and desk_ticket_id:
        thread_id, token, query = match.group(1), match.group(2), match.group(3) or ""
        path = "/api/v1/tickets/%s/threads/%s/inlineImages/%s%s" % (
            desk_ticket_id,
            thread_id,
            token,
            query,
        )
        return desk_api_absolute_url(client, path)
    return desk_api_absolute_url(client, raw)


def download_desk_inline_image(client, src, *, desk_ticket_id=None):
    """Try canonical and /content URLs; return (bytes, url_used)."""
    primary = desk_inline_image_download_url(client, src, desk_ticket_id=desk_ticket_id)
    candidates = []
    if primary:
        candidates.append(primary)
        if "/inlineImages/" in primary and not primary.rstrip("/").endswith("/content"):
            candidates.append(primary.rstrip("/") + "/content")
    seen = set()
    last_error = None
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            content = client.download(url) or b""
            if content:
                return content, url
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return b"", ""


def is_desk_inline_image_src(src):
    return bool(_INLINE_IMAGE_PATH.search(src or ""))


def inline_image_filename(src):
    src = html.unescape(src or "")
    match = re.search(r"[?&]f=(\d+)\.(\w+)", src, re.I)
    if match:
        return "desk-inline-%s.%s" % (match.group(1), match.group(2).lower())
    match = re.search(r"/inlineImages/([^/?&]+)", src, re.I)
    if match:
        token = match.group(1)[:24]
        return "desk-inline-%s.png" % token
    return "desk-inline.png"


def embed_desk_inline_images(env, client, html_body, *, res_model, res_id, desk_ticket_id=None):
    """Replace Desk inlineImages src with /web/image/<attachment id>."""
    text = str(html_body or "")
    if not text or not res_id:
        return text or False

    def _replace(match):
        prefix, quote, src, suffix = match.groups()
        src = html.unescape(src)
        if src.startswith("/web/"):
            return match.group(0)
        if not is_desk_inline_image_src(src):
            return match.group(0)
        try:
            content, _url = download_desk_inline_image(
                client, src, desk_ticket_id=desk_ticket_id
            )
        except Exception as exc:
            _logger.warning(
                "Desk inline image download failed (%s): %s",
                desk_inline_image_download_url(
                    client, src, desk_ticket_id=desk_ticket_id
                ),
                exc,
            )
            return ""
        if not content:
            return ""
        name = inline_image_filename(src)
        mimetype, _ = mimetypes.guess_type(name)
        attachment = env["ir.attachment"].sudo().create(
            {
                "name": name,
                "type": "binary",
                "raw": content,
                "res_model": res_model,
                "res_id": res_id,
                "mimetype": mimetype or "image/png",
            }
        )
        return "%s%s/web/image/%s%s" % (prefix, quote, attachment.id, suffix)

    embedded = _IMG_TAG.sub(_replace, text)
    return embedded.strip() or False
