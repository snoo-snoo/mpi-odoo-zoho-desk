# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MpiZohoTicketMap(models.Model):
    _name = "mpi.zoho.desk.ticket.map"
    _description = "Ticket map"
    _rec_name = "desk_ticket_id"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade", index=True
    )
    helpdesk_ticket_id = fields.Many2one(
        "helpdesk.ticket", ondelete="set null", index=True
    )
    desk_ticket_id = fields.Char(required=True, index=True)
    last_payload_hash = fields.Char()
    last_origin = fields.Selection(
        [("desk", "Desk"), ("odoo", "Odoo"), ("connector", "Connector")]
    )
    source_removed = fields.Boolean()

    _ticket_uniq = models.Constraint(
        "UNIQUE(helpdesk_ticket_id)",
        "A Helpdesk Ticket maps to only one Desk ticket.",
    )
    _desk_uniq = models.Constraint(
        "UNIQUE(connection_id, desk_ticket_id)",
        "A Desk ticket maps to only one Helpdesk Ticket on a Connection.",
    )


class MpiZohoCommentMap(models.Model):
    _name = "mpi.zoho.desk.comment.map"
    _description = "Comment map"

    ticket_map_id = fields.Many2one(
        "mpi.zoho.desk.ticket.map", required=True, ondelete="cascade", index=True
    )
    desk_thread_id = fields.Char(required=True)
    mail_message_id = fields.Many2one("mail.message", ondelete="set null")

    _thread_uniq = models.Constraint(
        "UNIQUE(ticket_map_id, desk_thread_id)",
        "Each Desk thread is mapped once.",
    )


class MpiZohoAttachmentMap(models.Model):
    _name = "mpi.zoho.desk.attachment.map"
    _description = "Attachment map"

    ticket_map_id = fields.Many2one(
        "mpi.zoho.desk.ticket.map", required=True, ondelete="cascade", index=True
    )
    desk_attachment_id = fields.Char()
    attachment_id = fields.Many2one("ir.attachment", ondelete="set null")
    desk_url = fields.Char()
    stored_as = fields.Selection(
        [("store", "File"), ("url_only", "Name and URL"), ("reject", "Rejected")]
    )
