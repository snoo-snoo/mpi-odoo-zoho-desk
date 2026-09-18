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
