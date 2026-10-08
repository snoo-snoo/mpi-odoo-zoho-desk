# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Zoho OAuth helpers shared by Connection and DeskClient."""


def desk_oauth_is_rate_limited(message):
    text = str(message or "").lower()
    return "too many requests" in text
