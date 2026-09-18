# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Decide whether an Attachment is stored, linked, skipped, or rejected."""

DEFAULT_MAX_BYTES = 10 * 1024 * 1024

DEFAULT_MIME_ALLOW = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
    }
)

_DIRECTION_ALLOWS = {
    "both": frozenset({"desk_to_odoo", "odoo_to_desk"}),
    "odoo_to_desk": frozenset({"odoo_to_desk"}),
    "desk_to_odoo": frozenset({"desk_to_odoo"}),
}


def decide_attachment(
    *,
    size_bytes,
    mimetype,
    travel,
    direction,
    max_bytes=DEFAULT_MAX_BYTES,
    mime_allow=DEFAULT_MIME_ALLOW,
):
    """Return store | url_only | reject | skip."""
    allowed_travel = _DIRECTION_ALLOWS.get(direction, frozenset())
    if travel not in allowed_travel:
        return "skip"
    if mimetype not in mime_allow:
        return "reject"
    if size_bytes > max_bytes:
        return "url_only"
    return "store"
