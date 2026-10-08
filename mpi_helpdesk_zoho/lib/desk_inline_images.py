# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Embed Desk thread inlineImages as Odoo attachments in HTML descriptions."""

import logging
import mimetypes
import re

from .desk_hosts import desk_root

_logger = logging.getLogger(__name__)

_IMG_TAG = re.compile(r'(<img\b[^>]*\bsrc=)(["\'])([^"\']+)(\2[^>]*>)', re.I)
_INLINE_IMAGE_PATH = re.compile(r"/inlineImages/", re.I)


def desk_api_absolute_url(client, src):
    raw = (src or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    base = desk_root(client.dc).rstrip("/")
    if raw.startswith("/"):
        return "%s%s" % (base, raw)
    return "%s/%s" % (base, raw)


def is_desk_inline_image_src(src):
    return bool(_INLINE_IMAGE_PATH.search(src or ""))


def inline_image_filename(src):
    match = re.search(r"[?&]f=(\d+)\.(\w+)", src or "", re.I)
    if match:
        return "desk-inline-%s.%s" % (match.group(1), match.group(2).lower())
    match = re.search(r"/inlineImages/([^/?&]+)", src or "", re.I)
    if match:
        token = match.group(1)[:24]
        return "desk-inline-%s.png" % token
    return "desk-inline.png"


def embed_desk_inline_images(env, client, html, *, res_model, res_id):
    """Replace Desk inlineImages src with /web/image/<attachment id>."""
    text = str(html or "")
    if not text or not res_id:
        return text or False

    def _replace(match):
        prefix, quote, src, suffix = match.groups()
        if src.startswith("/web/"):
            return match.group(0)
        if not is_desk_inline_image_src(src):
            return match.group(0)
        url = desk_api_absolute_url(client, src)
        if not url:
            return match.group(0)
        try:
            content = client.download(url)
        except Exception as exc:
            _logger.warning("Desk inline image download failed (%s): %s", url, exc)
            return match.group(0)
        if not content:
            return match.group(0)
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
