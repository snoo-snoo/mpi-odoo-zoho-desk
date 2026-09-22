# Zoho Desk Connector

Keeps Tickets aligned between Odoo and a Desk Organization. This is an Odoo Apps product, not a Fenci support shell.

## Language

**Zoho Desk Connector**:
The Odoo application that performs Ticket Sync through Connections.
_Avoid_: Fenci connector, CRM connector, support shell, integration app

**Connection**:
A configured pairing of one Odoo company to one Desk Organization. A multi-company database may have several Connections.
_Avoid_: Connector, integration, link, binding

**Desk Organization**:
The Zoho Desk tenant a Connection talks to.
_Avoid_: Zoho account, portal, org (unqualified), DC

**Ticket**:
A support conversation mapped one-to-one: one Helpdesk Ticket and one Zoho Desk ticket.
_Avoid_: Support Case, Case, Issue, incident, Desk ticket (when meaning the pair)

**Helpdesk Ticket**:
The Odoo side of a Ticket (Enterprise Helpdesk).
_Avoid_: MPI ticket, task, CRM ticket

**Ticket Sync**:
Both sides may create and update the same Ticket — Ticket fields, Comments, assignees, mapped custom fields, and Attachments. Attachment direction is set on the Connection.
_Avoid_: import, pull, mirror, one-way sync, cluster

**Ticket field**:
A property of the Ticket that has one current value (status, assignee, mapped custom field). On conflict, Desk wins.
_Avoid_: scalar, attribute, field (unqualified)

**Comment**:
A message appended to a Ticket on either side. Comments are not overwritten and are not a Ticket field.
_Avoid_: thread (when meaning the synced message), chatter, note

**Public Comment**:
A customer-visible Comment: Helpdesk customer message ↔ Desk public thread.
_Avoid_: email, reply (unqualified)

**Internal Note**:
A Comment the customer must not see: Helpdesk internal note ↔ Desk private thread. An Internal Note must never become a Public Comment.
_Avoid_: private comment (when meaning the Odoo record), log note

**Partner**:
The Odoo partner linked from a Zoho Contact or Account on a Ticket. Match on email (Contact) or VAT/name (Account); create a Partner if none matches.
_Avoid_: customer, client, account (unqualified), contact (when meaning the Odoo record)

**Attachment**:
A file on a Ticket that may be stored on both sides. The Connection sets direction (both, Odoo→Desk, Desk→Odoo), a size cap, and allowed types. Defaults: both ways, 10 MB, images/PDF/Office; no zip, exe, or html. Over the cap, keep the name and a Desk URL only.
_Avoid_: document, binary, link (when meaning the file)

**Agent Map**:
A pairing on the Connection of a Desk agent to an Odoo user. Email is the fallback; unmapped agents leave the assignee empty.
_Avoid_: user map, owner map

**Status Map**:
A pairing on the Connection of a Desk status to a Helpdesk stage. Unmapped statuses do not write the stage.
_Avoid_: stage map, pipeline map

**Team Map**:
A pairing on the Connection of a Helpdesk team that may take part in Ticket Sync. Unmapped teams stay in Odoo.
_Avoid_: team filter, outbound rule

**Department Map**:
A pairing on the Connection of a Desk department to a Helpdesk team whose tickets may take part in Ticket Sync. Inbound tickets land on that team. Unmapped departments stay in Desk.
_Avoid_: department filter, inbound rule

**Tag Map**:
A pairing on the Connection of a Desk tag to a Helpdesk tag. Tags sync only when mapped.
_Avoid_: label map

**Backfill**:
The first pull when a Connection is turned on: open tickets plus closed tickets inside a lookback (default 90 days), or the entire Desk history if that option is set.
_Avoid_: import, initial sync, full dump

**Source removal**:
When one side of a Ticket is deleted, the other side is closed or archived and marked removed at source. The other record is not deleted.
_Avoid_: cascade delete, disconnect, orphan
