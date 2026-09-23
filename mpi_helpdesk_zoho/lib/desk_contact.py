# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Extract Partner identity from a Desk ticket payload."""


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if value:
        return {"id": value}
    return {}


def desk_contact_identity(detail):
    """Return email, name, vat, kind, contact_id, account_id from a Desk ticket."""
    detail = detail or {}
    contact = _as_dict(detail.get("contact"))
    account = _as_dict(detail.get("account") or contact.get("account"))
    email = (
        (contact.get("email") or detail.get("email") or account.get("email") or "")
        .strip()
    )
    first = (contact.get("firstName") or "").strip()
    last = (contact.get("lastName") or "").strip()
    full_name = " ".join(part for part in (first, last) if part).strip()
    name = (
        full_name
        or (account.get("accountName") or "").strip()
        or (detail.get("contactName") or "").strip()
        or (contact.get("lastName") or "").strip()
        or (contact.get("firstName") or "").strip()
    )
    vat = (
        (account.get("customFields") or {}).get("vat")
        or account.get("vat")
        or ""
    )
    contact_id = str(contact.get("id") or detail.get("contactId") or "").strip()
    account_id = str(account.get("id") or detail.get("accountId") or "").strip()
    kind = "contact" if email or contact_id or first or last else "account"
    return {
        "email": email or None,
        "name": name or None,
        "vat": vat or None,
        "kind": kind,
        "contact_id": contact_id or None,
        "account_id": account_id or None,
        "is_company": bool(account_id and not (email or contact_id)),
    }


def partner_display_name(*, name=None, email=None, contact_id=None):
    if name:
        return name
    if email:
        return email
    if contact_id:
        return "Desk contact %s" % contact_id
    return "Desk contact"
