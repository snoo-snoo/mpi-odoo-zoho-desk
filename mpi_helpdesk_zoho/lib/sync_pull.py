# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Pull pacing and side-content rules for Ticket Sync."""

COMMIT_EVERY = 20
CATCHUP_TICKET_CAP = 300
PAGE_SIZE = 50


def list_ticket_params(*, start, page_size=PAGE_SIZE, department_ids=None, sort_by="modifiedTime"):
    """Build Desk GET /tickets query params. department_ids limits inbound scope."""
    params = {
        "from": start,
        "limit": page_size,
        "sortBy": sort_by,
    }
    if department_ids:
        params["departmentIds"] = ",".join(str(dept_id) for dept_id in department_ids)
    return params


def should_sync_side_content(*, is_new, backfill, force_side_content=False):
    """Threads and attachments: new tickets, backfill, or webhook-forced events."""
    return bool(is_new or backfill or force_side_content)


def defer_attachment_binaries(*, backfill):
    """During Backfill store name+URL only; binaries come later via webhook/catch-up create."""
    return bool(backfill)


def partner_cache_key(*, email=None, vat=None, name=None):
    return (
        (email or "").strip().lower(),
        (vat or "").strip().upper(),
        (name or "").strip().lower(),
    )
