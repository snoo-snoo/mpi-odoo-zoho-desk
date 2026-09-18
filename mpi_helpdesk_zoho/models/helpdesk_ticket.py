# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

from ..lib.source_removal import other_side_action
from ..lib.sync_scope import allows_outbound


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    mpi_zoho_map_ids = fields.One2many("mpi.zoho.desk.ticket.map", "helpdesk_ticket_id")
    mpi_zoho_desk_ticket_id = fields.Char(compute="_compute_mpi_zoho", string="Desk ticket")
    mpi_zoho_source_removed = fields.Boolean(compute="_compute_mpi_zoho", string="Removed at source")

    @api.depends("mpi_zoho_map_ids.desk_ticket_id", "mpi_zoho_map_ids.source_removed")
    def _compute_mpi_zoho(self):
        for ticket in self:
            mapping = ticket.mpi_zoho_map_ids[:1]
            ticket.mpi_zoho_desk_ticket_id = mapping.desk_ticket_id if mapping else False
            ticket.mpi_zoho_source_removed = mapping.source_removed if mapping else False

    def _mpi_zoho_connection(self):
        self.ensure_one()
        return self.env["mpi.zoho.desk.connection"].search(
            [("company_id", "=", self.company_id.id), ("active", "=", True)], limit=1
        )

    def _mpi_zoho_queue(self, event_type, payload=None):
        if self.env.context.get("mpi_zoho_skip_outbox"):
            return
        for ticket in self:
            connection = ticket._mpi_zoho_connection()
            if not connection:
                continue
            if not allows_outbound(
                team_id=ticket.team_id.id if ticket.team_id else None,
                mapped_team_ids=connection._mapped_team_ids(),
            ):
                continue
            self.env["mpi.zoho.desk.outbox"].sudo().create(
                {
                    "connection_id": connection.id,
                    "helpdesk_ticket_id": ticket.id,
                    "event_type": event_type,
                    "payload": payload or {},
                }
            )
            cron = self.env.ref("mpi_helpdesk_zoho.cron_mpi_helpdesk_zoho_catchup", raise_if_not_found=False)
            if cron:
                cron._trigger()

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        tickets._mpi_zoho_queue("create_ticket")
        return tickets

    def write(self, vals):
        result = super().write(vals)
        tracked = {"name", "description", "priority", "user_id", "stage_id", "tag_ids", "partner_id"}
        if tracked.intersection(vals):
            self.filtered(lambda t: t.mpi_zoho_desk_ticket_id)._mpi_zoho_queue("update_ticket", vals)
        if vals.get("active") is False:
            for ticket in self:
                if ticket.mpi_zoho_desk_ticket_id and other_side_action(deleted_side="odoo") == "close":
                    ticket._mpi_zoho_queue(
                        "close_ticket", {"desk_ticket_id": ticket.mpi_zoho_desk_ticket_id}
                    )
        return result

    def unlink(self):
        for ticket in self:
            if ticket.mpi_zoho_desk_ticket_id and other_side_action(deleted_side="odoo") == "close":
                ticket._mpi_zoho_queue(
                    "close_ticket", {"desk_ticket_id": ticket.mpi_zoho_desk_ticket_id}
                )
        return super().unlink()

    def _message_post_after_hook(self, message, msg_values):
        result = super()._message_post_after_hook(message, msg_values)
        if self.env.context.get("mpi_zoho_skip_outbox"):
            return result
        subtype = message.subtype_id
        internal = bool(subtype and subtype.internal)
        visibility = "internal" if internal else "public"
        message_type = msg_values.get("message_type") or message.message_type
        if message_type in ("comment", "email"):
            self._mpi_zoho_queue(
                "add_comment",
                {"message_id": message.id, "visibility": visibility, "body": message.body},
            )
        return result
