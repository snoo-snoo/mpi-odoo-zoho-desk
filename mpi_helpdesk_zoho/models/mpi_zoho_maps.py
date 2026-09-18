# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MpiZohoAgentMap(models.Model):
    _name = "mpi.zoho.desk.agent.map"
    _description = "Agent Map"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade", index=True
    )
    desk_agent_id = fields.Char(required=True)
    desk_agent_email = fields.Char()
    user_id = fields.Many2one("res.users", ondelete="cascade")


class MpiZohoStatusMap(models.Model):
    _name = "mpi.zoho.desk.status.map"
    _description = "Status Map"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade", index=True
    )
    desk_status = fields.Char(required=True)
    stage_id = fields.Many2one("helpdesk.stage", required=True, ondelete="cascade")


class MpiZohoTeamMap(models.Model):
    _name = "mpi.zoho.desk.team.map"
    _description = "Team Map"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade", index=True
    )
    team_id = fields.Many2one("helpdesk.team", required=True, ondelete="cascade")
    desk_department_id = fields.Char(
        help="Desk department used when this team creates a ticket."
    )


class MpiZohoDepartmentMap(models.Model):
    _name = "mpi.zoho.desk.department.map"
    _description = "Department Map"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade", index=True
    )
    desk_department_id = fields.Char(required=True)
    desk_department_name = fields.Char()


class MpiZohoTagMap(models.Model):
    _name = "mpi.zoho.desk.tag.map"
    _description = "Tag Map"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade", index=True
    )
    desk_tag = fields.Char(required=True)
    tag_id = fields.Many2one(
        "helpdesk.tag",
        required=True,
        ondelete="cascade",
        help="Enterprise Helpdesk tag (helpdesk.tag).",
    )


class MpiZohoFieldMap(models.Model):
    _name = "mpi.zoho.desk.field.map"
    _description = "Custom field map"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade", index=True
    )
    desk_field = fields.Char(required=True)
    helpdesk_field = fields.Char(required=True)
