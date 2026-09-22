# Each buyer brings a Zoho self-client

The Connection stores client id, secret, refresh token, org id, and data center. MPI does not publish a shared Zoho client or broker tokens. Every Odoo URL is different; a shared client would make MPI a party to every Desk Organization.

Generate Code on that self-client must request these scopes (comma-separated, no spaces):

`Desk.tickets.READ,Desk.tickets.CREATE,Desk.tickets.UPDATE,Desk.basic.READ,Desk.fields.READ,Desk.settings.READ,Desk.webhooks.CREATE`

- `Desk.tickets.READ` / `CREATE` / `UPDATE` — Ticket Sync (tickets, threads, attachments) and listing ticket tags for the Tag Map. Close via update; do not request `DELETE` or `ALL`.
- `Desk.basic.READ` — departments, agents, organization for maps and setup.
- `Desk.fields.READ` — ticket organization fields (Status Map, custom field map).
- `Desk.settings.READ` — optional Desk settings reads during setup; not required for ticket tags (`GET /ticketTags` uses `Desk.tickets.READ`).
- `Desk.webhooks.CREATE` — Register webhook. Pasting the webhook URL in Desk still works without it.

`Desk.contacts.*` is not requested: the Ticket payload carries contact and account; Partners are matched in Odoo.
