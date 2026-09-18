# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mpi_zoho_connection_id = fields.Many2one(
        "mpi.zoho.desk.connection",
        string="Connection",
        compute="_compute_mpi_zoho_connection",
    )

    def _compute_mpi_zoho_connection(self):
        for settings in self:
            settings.mpi_zoho_connection_id = self.env["mpi.zoho.desk.connection"].search(
                [("company_id", "=", self.env.company.id)], limit=1
            )

    def action_open_mpi_zoho_connection(self):
        connection = self.env["mpi.zoho.desk.connection"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        action = {
            "type": "ir.actions.act_window",
            "name": "Connection",
            "res_model": "mpi.zoho.desk.connection",
            "view_mode": "form",
            "target": "current",
        }
        if connection:
            action["res_id"] = connection.id
        return action
