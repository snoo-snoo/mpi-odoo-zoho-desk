# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get("mpi_zoho_skip_outbox"):
            return records
        for attachment in records:
            if attachment.res_model == "helpdesk.ticket" and attachment.res_id:
                ticket = self.env["helpdesk.ticket"].browse(attachment.res_id)
                if ticket.exists():
                    ticket._mpi_zoho_queue("add_attachment", {"attachment_id": attachment.id})
        return records
