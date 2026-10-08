# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Zoho data-center hosts for Desk and Accounts."""

DESK_ROOTS = {
    "com": "https://desk.zoho.com",
    "eu": "https://desk.zoho.eu",
    "in": "https://desk.zoho.in",
    "com.au": "https://desk.zoho.com.au",
    "jp": "https://desk.zoho.jp",
    "ca": "https://desk.zoho.ca",
    "sa": "https://desk.zoho.sa",
    "uk": "https://desk.zoho.uk",
}

ACCOUNTS_ROOTS = {
    "com": "https://accounts.zoho.com",
    "eu": "https://accounts.zoho.eu",
    "in": "https://accounts.zoho.in",
    "com.au": "https://accounts.zoho.com.au",
    "jp": "https://accounts.zoho.jp",
    "ca": "https://accounts.zoho.ca",
    "sa": "https://accounts.zoho.sa",
    "uk": "https://accounts.zoho.uk",
}


def desk_root(dc):
    return DESK_ROOTS.get(dc, DESK_ROOTS["com"])


def accounts_root(dc):
    return ACCOUNTS_ROOTS.get(dc, ACCOUNTS_ROOTS["com"])


def desk_agent_base_url_from_custom_domain(custom_domain):
    if not custom_domain:
        return False
    raw = str(custom_domain).strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/")
    return "https://%s" % raw.strip("/")


def desk_ticket_agent_url(dc, agent_portal, desk_ticket_id, *, agent_base_url=None):
    """Agent UI deep link (custom domain or Zoho DC, with /all/ tickets path)."""
    portal = (agent_portal or "").strip().strip("/")
    ticket_id = (desk_ticket_id or "").strip()
    if not portal or not ticket_id:
        return False
    base = (agent_base_url or "").strip().rstrip("/") or desk_root(dc)
    return "%s/agent/%s/all/tickets/details/%s" % (base, portal, ticket_id)
