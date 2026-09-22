# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""OAuth scopes the buyer pastes into Zoho API Console → Generate Code."""

# Least privilege for Ticket Sync, maps, and webhook registration.
# Desk.tickets.ALL is not used: it includes DELETE; we close, we do not delete.
SELF_CLIENT_SCOPES = (
    "Desk.tickets.READ",
    "Desk.tickets.CREATE",
    "Desk.tickets.UPDATE",
    "Desk.basic.READ",
    "Desk.fields.READ",
    "Desk.settings.READ",
    "Desk.webhooks.CREATE",
)

SELF_CLIENT_SCOPE_CSV = ",".join(SELF_CLIENT_SCOPES)
