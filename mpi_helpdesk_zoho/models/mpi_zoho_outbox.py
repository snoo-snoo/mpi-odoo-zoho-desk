# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MpiZohoOutbox(models.Model):
    _name = "mpi.zoho.desk.outbox"
    _description = "Desk outbox"
    _order = "id"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade", index=True
    )
    helpdesk_ticket_id = fields.Many2one("helpdesk.ticket", ondelete="set null", index=True)
    event_type = fields.Selection(
        [
            ("create_ticket", "Create ticket"),
            ("update_ticket", "Update ticket"),
            ("add_comment", "Add comment"),
            ("add_attachment", "Add attachment"),
            ("close_ticket", "Close ticket"),
        ],
        required=True,
    )
    payload = fields.Json()
    state = fields.Selection(
        [("pending", "Pending"), ("done", "Done"), ("error", "Error")],
        default="pending",
        required=True,
    )
    error = fields.Text()
