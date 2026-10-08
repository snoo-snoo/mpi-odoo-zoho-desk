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


def _split_url_query(url):
    if "?" in url:
        return url.split("?", 1)
    return url, ""


def _inline_image_url_variants(url):
    """Desk inlineImages may use /content before the query string, or no query with OAuth."""
    if not url:
        return []
    variants = [url]
    path, query = _split_url_query(url)
    if not path.rstrip("/").endswith("/content"):
        if query:
            variants.append(path.rstrip("/") + "/content?" + query)
        else:
            variants.append(path.rstrip("/") + "/content")
    path_only = path.rstrip("/")
    if path_only.endswith("/content"):
        path_only = path_only[: -len("/content")]
    if query:
        variants.append(path_only + "/content")
        variants.append(path_only)
    else:
        variants.append(path_only + "/content")
    seen = set()
    ordered = []
    for item in variants:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


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


def desk_inline_image_candidate_urls(client, src, *, desk_ticket_id=None):
    """Ordered Desk URLs to try (ticket-scoped, shorthand, /content variants)."""
    src = html.unescape((src or "").strip())
    seeds = []
    ticket_url = desk_inline_image_download_url(client, src, desk_ticket_id=desk_ticket_id)
    if ticket_url:
        seeds.append(ticket_url)
    shorthand = desk_api_absolute_url(client, src)
    if shorthand and shorthand not in seeds:
        seeds.append(shorthand)
    candidates = []
    seen = set()
    for seed in seeds:
        for url in _inline_image_url_variants(seed):
            if url not in seen:
                seen.add(url)
                candidates.append(url)
    return candidates


def download_desk_inline_image(client, src, *, desk_ticket_id=None):
    """Try Desk inlineImages URL variants; return (bytes, url_used)."""
    last_error = None
    for url in desk_inline_image_candidate_urls(
        client, src, desk_ticket_id=desk_ticket_id
    ):
        try:
            content = client.download(url) or b""
            if content and not _looks_like_error_payload(content):
                return content, url
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return b"", ""


def _looks_like_error_payload(content):
    """Skip JSON error bodies mistaken for empty images."""
    if not content or content[:1] not in (b"{", b"["):
        return False
    try:
        text = content[:200].decode("utf-8", errors="ignore").lower()
    except Exception:
        return False
    return "error" in text or "invalid" in text


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
            status = getattr(exc, "status_code", None)
            detail = " HTTP %s" % status if status else ""
            _logger.info(
                "Desk inline image not embedded%s (%s): %s",
                detail,
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
