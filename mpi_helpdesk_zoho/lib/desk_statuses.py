# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Unique Desk ticket statuses from organizationFields (drop translation aliases)."""

# Desk API values ↔ common UI translations. Tickets use the API value.
_STATUS_ALIASES = {
    "open": "Open",
    "offen": "Open",
    "on hold": "On Hold",
    "onhold": "On Hold",
    "zurückgestellt": "On Hold",
    "zurueckgestellt": "On Hold",
    "wartend": "On Hold",
    "in der warteschleife": "On Hold",
    "escalated": "Escalated",
    "eskaliert": "Escalated",
    "closed": "Closed",
    "close": "Closed",
    "geschlossen": "Closed",
}


def _entry_value(entry):
    if isinstance(entry, dict):
        value = entry.get("value") or entry.get("name")
        return str(value).strip() if value else ""
    return str(entry).strip() if entry not in (None, "") else ""


def _canonical(value):
    return _STATUS_ALIASES.get(value.casefold(), value)


def unique_desk_statuses(entries):
    """Return API status values, one row per status (translations collapsed)."""
    chosen = {}
    order = []
    for entry in entries or []:
        value = _entry_value(entry)
        if not value:
            continue
        key = _canonical(value).casefold()
        if key not in chosen:
            chosen[key] = _canonical(value)
            order.append(key)
            continue
        current = chosen[key]
        # Prefer the Desk API spelling over a translated sibling.
        if current.casefold() != key and value.casefold() == key:
            chosen[key] = value
    return [chosen[key] for key in order]


def status_values_from_fields(org_fields):
    for field in org_fields or []:
        api_name = (field.get("apiName") or field.get("name") or "").lower()
        if api_name != "status":
            continue
        raw = field.get("pickListValues") or field.get("allowedValues") or []
        return unique_desk_statuses(raw)
    return []
