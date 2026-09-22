# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib.desk_client import DeskClientError


class MpiZohoSetupWizard(models.TransientModel):
    _name = "mpi.zoho.desk.setup.wizard"
    _description = "Configure Ticket Sync"

    connection_id = fields.Many2one(
        "mpi.zoho.desk.connection", required=True, ondelete="cascade"
    )
    state = fields.Selection(
        [
            ("departments", "Departments"),
            ("statuses", "Statuses"),
            ("agents", "Agents"),
            ("tags", "Tags"),
            ("fields", "Custom fields"),
            ("backfill", "Backfill"),
        ],
        default="departments",
        required=True,
    )
    department_line_ids = fields.One2many(
        "mpi.zoho.desk.setup.department.line", "wizard_id"
    )
    status_line_ids = fields.One2many("mpi.zoho.desk.setup.status.line", "wizard_id")
    agent_line_ids = fields.One2many("mpi.zoho.desk.setup.agent.line", "wizard_id")
    tag_line_ids = fields.One2many("mpi.zoho.desk.setup.tag.line", "wizard_id")
    field_line_ids = fields.One2many("mpi.zoho.desk.setup.field.line", "wizard_id")

    backfill_mode = fields.Selection(
        [("lookback", "Open + lookback"), ("entire", "Entire history")],
        default="lookback",
        required=True,
    )
    backfill_lookback_days = fields.Integer(default=90)
    run_backfill = fields.Boolean(default=True, string="Run Backfill after apply")
    load_warning = fields.Text(readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        connection_id = values.get("connection_id") or self.env.context.get(
            "default_connection_id"
        )
        if not connection_id:
            return values
        connection = self.env["mpi.zoho.desk.connection"].browse(connection_id)
        values.setdefault("backfill_mode", connection.backfill_mode or "lookback")
        values.setdefault(
            "backfill_lookback_days", connection.backfill_lookback_days or 90
        )
        return values

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        records = super().create(vals_list)
        for wizard in records:
            if wizard.connection_id and not wizard.department_line_ids:
                wizard._load_from_desk()
        return records

    def _load_from_desk(self):
        self.ensure_one()
        connection = self.connection_id
        warnings = []
        try:
            client = connection._make_client()
            departments = client.list_departments()
            agents = client.list_agents()
            org_fields = client.list_organization_fields(module="tickets")
        except DeskClientError as exc:
            raise UserError(_("Could not load Desk metadata: %s") % exc) from exc

        try:
            tags = client.list_organization_tags()
        except DeskClientError as exc:
            tags = []
            warnings.append(_("Desk tags could not be loaded: %s") % exc)
        else:
            if not tags and not connection.tag_map_ids:
                warnings.append(
                    _(
                        "Desk returned no tags (or the self-client is not allowed to list "
                        "them). Re-generate the Self-Client Code with Desk.tickets.READ, "
                        "or map tags later on the Connection."
                    )
                )

        self._load_department_lines(departments)
        self._load_status_lines(org_fields)
        self._load_agent_lines(agents)
        self._load_tag_lines(tags)
        self._load_field_lines(org_fields)
        self.load_warning = "\n".join(warnings) if warnings else False

    def _load_department_lines(self, departments):
        self.ensure_one()
        connection = self.connection_id
        existing = {
            row.desk_department_id: row for row in connection.department_map_ids
        }
        team_by_dept = {
            row.desk_department_id: row.team_id
            for row in connection.team_map_ids
            if row.desk_department_id
        }
        lines = []
        for row in departments:
            desk_id = str(row.get("id") or "")
            if not desk_id:
                continue
            mapped = existing.get(desk_id)
            team = (mapped.team_id if mapped else False) or team_by_dept.get(desk_id)
            name = row.get("name") or (mapped.desk_department_name if mapped else "")
            if not team and name:
                team = self.env["helpdesk.team"].search(
                    [
                        ("name", "=", name),
                        ("company_id", "in", [False, connection.company_id.id]),
                    ],
                    limit=1,
                )
            sync = bool(mapped) if existing else False
            lines.append(
                (
                    0,
                    0,
                    {
                        "sync": sync,
                        "desk_department_id": desk_id,
                        "desk_department_name": name,
                        "team_id": team.id if team else False,
                        "create_team": sync and not team,
                    },
                )
            )
        self.department_line_ids = [(5, 0, 0)] + lines

    def _status_values_from_fields(self, org_fields):
        for field in org_fields:
            api_name = (field.get("apiName") or field.get("name") or "").lower()
            if api_name != "status":
                continue
            allowed = field.get("allowedValues") or field.get("pickListValues") or []
            values = []
            for entry in allowed:
                if isinstance(entry, dict):
                    value = entry.get("value") or entry.get("name") or entry.get("id")
                else:
                    value = entry
                if value:
                    values.append(str(value))
            return values
        return []

    def _load_status_lines(self, org_fields):
        self.ensure_one()
        connection = self.connection_id
        existing = {row.desk_status: row for row in connection.status_map_ids}
        statuses = self._status_values_from_fields(org_fields)
        if not statuses:
            statuses = list(existing.keys())
        lines = []
        for status in statuses:
            mapped = existing.get(status)
            stage = mapped.stage_id if mapped else False
            if not stage:
                stage = self.env["helpdesk.stage"].search(
                    [("name", "=", status)], limit=1
                )
            sync = bool(mapped) if existing else True
            lines.append(
                (
                    0,
                    0,
                    {
                        "sync": sync,
                        "desk_status": status,
                        "stage_id": stage.id if stage else False,
                        "create_stage": sync and not stage,
                    },
                )
            )
        self.status_line_ids = [(5, 0, 0)] + lines

    def _load_agent_lines(self, agents):
        self.ensure_one()
        connection = self.connection_id
        existing_by_id = {
            row.desk_agent_id: row for row in connection.agent_map_ids if row.desk_agent_id
        }
        existing_by_email = {
            (row.desk_agent_email or "").lower(): row
            for row in connection.agent_map_ids
            if row.desk_agent_email
        }
        lines = []
        for row in agents:
            agent_id = str(row.get("id") or "")
            email = (
                row.get("emailId")
                or row.get("email")
                or ((row.get("emailIds") or [None])[0])
                or ""
            )
            email = (email or "").strip()
            mapped = existing_by_id.get(agent_id) or existing_by_email.get(email.lower())
            user = mapped.user_id if mapped else False
            if not user and email:
                user = self.env["res.users"].search(
                    [
                        "|",
                        ("login", "=ilike", email),
                        ("partner_id.email", "=ilike", email),
                    ],
                    limit=1,
                )
            name = " ".join(
                part
                for part in [row.get("firstName") or "", row.get("lastName") or ""]
                if part
            ).strip() or email or agent_id
            lines.append(
                (
                    0,
                    0,
                    {
                        "sync": bool(mapped) or bool(user),
                        "desk_agent_id": agent_id,
                        "desk_agent_email": email,
                        "desk_agent_name": name,
                        "user_id": user.id if user else False,
                    },
                )
            )
        self.agent_line_ids = [(5, 0, 0)] + lines

    def _load_tag_lines(self, tags):
        self.ensure_one()
        connection = self.connection_id
        existing = {row.desk_tag: row for row in connection.tag_map_ids}
        lines = []
        seen = set()
        for row in tags:
            name = row.get("name") or row.get("tagName") or ""
            if not name:
                continue
            seen.add(name)
            mapped = existing.get(name)
            tag = mapped.tag_id if mapped else False
            if not tag:
                tag = self.env["helpdesk.tag"].search([("name", "=", name)], limit=1)
            lines.append(
                (
                    0,
                    0,
                    {
                        "sync": bool(mapped),
                        "desk_tag": name,
                        "tag_id": tag.id if tag else False,
                        "create_tag": bool(mapped) and not tag,
                    },
                )
            )
        for desk_tag, mapped in existing.items():
            if desk_tag in seen:
                continue
            lines.append(
                (
                    0,
                    0,
                    {
                        "sync": True,
                        "desk_tag": desk_tag,
                        "tag_id": mapped.tag_id.id if mapped.tag_id else False,
                        "create_tag": False,
                    },
                )
            )
        self.tag_line_ids = [(5, 0, 0)] + lines

    def _custom_fields_from_org(self, org_fields):
        builtins = {
            "subject",
            "description",
            "status",
            "priority",
            "assigneeId",
            "assignee",
            "departmentId",
            "department",
            "contactId",
            "contact",
            "accountId",
            "account",
            "email",
            "phone",
            "channel",
            "classification",
            "category",
            "subCategory",
            "dueDate",
            "createdTime",
            "modifiedTime",
            "closedTime",
            "ticketNumber",
            "id",
            "tags",
            "cf",
            "customFields",
        }
        result = []
        for field in org_fields:
            api_name = field.get("apiName") or field.get("name") or ""
            if not api_name:
                continue
            if api_name in builtins or api_name.lower() in builtins:
                continue
            is_custom = (
                field.get("isCustomField")
                or field.get("isCustom")
                or str(api_name).startswith("cf_")
                or field.get("type") not in (None, "System")
            )
            # Organization fields for tickets: prefer explicit custom flags; skip system status etc.
            if api_name.lower() == "status":
                continue
            if field.get("isCustomField") is False and not str(api_name).startswith("cf"):
                continue
            if is_custom or str(api_name).startswith("cf"):
                result.append(
                    {
                        "desk_field": api_name,
                        "label": field.get("displayLabel")
                        or field.get("i18NLabel")
                        or api_name,
                    }
                )
        return result

    def _load_field_lines(self, org_fields):
        self.ensure_one()
        connection = self.connection_id
        existing = {row.desk_field: row for row in connection.field_map_ids}
        customs = self._custom_fields_from_org(org_fields)
        if not customs and existing:
            customs = [{"desk_field": key, "label": key} for key in existing]
        lines = []
        for row in customs:
            desk_field = row["desk_field"]
            mapped = existing.get(desk_field)
            lines.append(
                (
                    0,
                    0,
                    {
                        "sync": bool(mapped),
                        "desk_field": desk_field,
                        "desk_field_label": row.get("label") or desk_field,
                        "helpdesk_field": mapped.helpdesk_field if mapped else False,
                    },
                )
            )
        self.field_line_ids = [(5, 0, 0)] + lines

    def action_next(self):
        self.ensure_one()
        order = ["departments", "statuses", "agents", "tags", "fields", "backfill"]
        idx = order.index(self.state)
        if idx >= len(order) - 1:
            return self.action_apply()
        self.state = order[idx + 1]
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        order = ["departments", "statuses", "agents", "tags", "fields", "backfill"]
        idx = order.index(self.state)
        if idx > 0:
            self.state = order[idx - 1]
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Configure Ticket Sync"),
            "res_model": "mpi.zoho.desk.setup.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        connection = self.connection_id
        teams = self._apply_department_maps(connection)
        self._apply_status_maps(connection, teams)
        self._apply_agent_maps(connection)
        self._apply_tag_maps(connection)
        self._apply_field_maps(connection)
        connection.write(
            {
                "backfill_mode": self.backfill_mode,
                "backfill_lookback_days": self.backfill_lookback_days,
            }
        )
        if self.run_backfill:
            connection._sync_from_desk(backfill=True)
        return {"type": "ir.actions.act_window_close"}

    def _apply_department_maps(self, connection):
        selected = self.department_line_ids.filtered("sync")
        teams = self.env["helpdesk.team"]
        dept_vals = []
        team_vals = []
        for line in selected:
            team = line.team_id
            if line.create_team and not team:
                team = self.env["helpdesk.team"].create(
                    {
                        "name": line.desk_department_name
                        or line.desk_department_id
                        or _("Desk team"),
                        "company_id": connection.company_id.id,
                    }
                )
            if not team:
                raise UserError(
                    _(
                        "Department %s needs a Helpdesk team or Create team checked."
                    )
                    % (line.desk_department_name or line.desk_department_id)
                )
            teams |= team
            dept_vals.append(
                {
                    "connection_id": connection.id,
                    "desk_department_id": line.desk_department_id,
                    "desk_department_name": line.desk_department_name,
                    "team_id": team.id,
                }
            )
            team_vals.append(
                {
                    "connection_id": connection.id,
                    "team_id": team.id,
                    "desk_department_id": line.desk_department_id,
                }
            )
        connection.department_map_ids.unlink()
        connection.team_map_ids.unlink()
        if dept_vals:
            self.env["mpi.zoho.desk.department.map"].create(dept_vals)
        if team_vals:
            self.env["mpi.zoho.desk.team.map"].create(team_vals)
        if teams and not connection.inbound_team_id:
            connection.inbound_team_id = teams[:1]
        return teams

    def _apply_status_maps(self, connection, teams):
        selected = self.status_line_ids.filtered("sync")
        vals = []
        for line in selected:
            stage = line.stage_id
            if line.create_stage and not stage:
                stage = self.env["helpdesk.stage"].create(
                    {
                        "name": line.desk_status,
                        "team_ids": [(6, 0, teams.ids)] if teams else False,
                    }
                )
            elif stage and teams:
                stage.write({"team_ids": [(4, team.id) for team in teams]})
            if not stage:
                raise UserError(
                    _("Status %s needs a Helpdesk stage or Create stage checked.")
                    % line.desk_status
                )
            vals.append(
                {
                    "connection_id": connection.id,
                    "desk_status": line.desk_status,
                    "stage_id": stage.id,
                }
            )
        connection.status_map_ids.unlink()
        if vals:
            self.env["mpi.zoho.desk.status.map"].create(vals)

    def _apply_agent_maps(self, connection):
        selected = self.agent_line_ids.filtered(
            lambda row: row.sync and row.desk_agent_id
        )
        vals = [
            {
                "connection_id": connection.id,
                "desk_agent_id": line.desk_agent_id,
                "desk_agent_email": line.desk_agent_email,
                "user_id": line.user_id.id if line.user_id else False,
            }
            for line in selected
        ]
        connection.agent_map_ids.unlink()
        if vals:
            self.env["mpi.zoho.desk.agent.map"].create(vals)

    def _apply_tag_maps(self, connection):
        selected = self.tag_line_ids.filtered("sync")
        vals = []
        for line in selected:
            tag = line.tag_id
            if line.create_tag and not tag:
                tag = self.env["helpdesk.tag"].create({"name": line.desk_tag})
            if not tag:
                raise UserError(
                    _("Tag %s needs a Helpdesk tag or Create tag checked.")
                    % line.desk_tag
                )
            vals.append(
                {
                    "connection_id": connection.id,
                    "desk_tag": line.desk_tag,
                    "tag_id": tag.id,
                }
            )
        connection.tag_map_ids.unlink()
        if vals:
            self.env["mpi.zoho.desk.tag.map"].create(vals)

    def _apply_field_maps(self, connection):
        selected = self.field_line_ids.filtered(
            lambda row: row.sync and row.desk_field and row.helpdesk_field
        )
        vals = [
            {
                "connection_id": connection.id,
                "desk_field": line.desk_field,
                "helpdesk_field": line.helpdesk_field,
            }
            for line in selected
        ]
        connection.field_map_ids.unlink()
        if vals:
            self.env["mpi.zoho.desk.field.map"].create(vals)


class MpiZohoSetupDepartmentLine(models.TransientModel):
    _name = "mpi.zoho.desk.setup.department.line"
    _description = "Setup department line"

    wizard_id = fields.Many2one(
        "mpi.zoho.desk.setup.wizard", required=True, ondelete="cascade"
    )
    sync = fields.Boolean(string="Sync")
    desk_department_id = fields.Char(required=True)
    desk_department_name = fields.Char(string="Department")
    team_id = fields.Many2one("helpdesk.team", string="Helpdesk team")
    create_team = fields.Boolean(string="Create team")


class MpiZohoSetupStatusLine(models.TransientModel):
    _name = "mpi.zoho.desk.setup.status.line"
    _description = "Setup status line"

    wizard_id = fields.Many2one(
        "mpi.zoho.desk.setup.wizard", required=True, ondelete="cascade"
    )
    sync = fields.Boolean(string="Sync")
    desk_status = fields.Char(required=True, string="Desk status")
    stage_id = fields.Many2one("helpdesk.stage", string="Helpdesk stage")
    create_stage = fields.Boolean(string="Create stage")


class MpiZohoSetupAgentLine(models.TransientModel):
    _name = "mpi.zoho.desk.setup.agent.line"
    _description = "Setup agent line"

    wizard_id = fields.Many2one(
        "mpi.zoho.desk.setup.wizard", required=True, ondelete="cascade"
    )
    sync = fields.Boolean(string="Sync")
    desk_agent_id = fields.Char(required=True)
    desk_agent_email = fields.Char(string="Email")
    desk_agent_name = fields.Char(string="Agent")
    user_id = fields.Many2one("res.users", string="Odoo user")


class MpiZohoSetupTagLine(models.TransientModel):
    _name = "mpi.zoho.desk.setup.tag.line"
    _description = "Setup tag line"

    wizard_id = fields.Many2one(
        "mpi.zoho.desk.setup.wizard", required=True, ondelete="cascade"
    )
    sync = fields.Boolean(string="Sync")
    desk_tag = fields.Char(required=True, string="Desk tag")
    tag_id = fields.Many2one("helpdesk.tag", string="Helpdesk tag")
    create_tag = fields.Boolean(string="Create tag")


class MpiZohoSetupFieldLine(models.TransientModel):
    _name = "mpi.zoho.desk.setup.field.line"
    _description = "Setup field line"

    wizard_id = fields.Many2one(
        "mpi.zoho.desk.setup.wizard", required=True, ondelete="cascade"
    )
    sync = fields.Boolean(string="Sync")
    desk_field = fields.Char(required=True, string="Desk field")
    desk_field_label = fields.Char(string="Label")
    helpdesk_field = fields.Char(string="Helpdesk field")
