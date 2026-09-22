# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import logging
import secrets
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib.attachment_policy import DEFAULT_MAX_BYTES, DEFAULT_MIME_ALLOW
from ..lib.desk_client import DeskClient, DeskClientError
from ..lib.requests_transport import RequestsTransport

_logger = logging.getLogger(__name__)

DEFAULT_MIME_CSV = ",".join(sorted(DEFAULT_MIME_ALLOW))


class MpiZohoConnection(models.Model):
    _name = "mpi.zoho.desk.connection"
    _description = "Connection"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )

    desk_org_id = fields.Char(string="Desk Organization", required=True, tracking=True)
    desk_dc = fields.Selection(
        [
            ("com", "zoho.com"),
            ("eu", "zoho.eu"),
            ("in", "zoho.in"),
            ("com.au", "zoho.com.au"),
            ("jp", "zoho.jp"),
            ("ca", "zoho.ca"),
            ("sa", "zoho.sa"),
            ("uk", "zoho.uk"),
        ],
        default="eu",
        required=True,
        tracking=True,
    )
    accounts_dc = fields.Selection(
        selection="_selection_desk_dc",
        string="Accounts DC",
        help="Leave empty to use the same DC as Desk.",
    )
    client_id = fields.Char(groups="mpi_helpdesk_zoho.group_zoho_admin", copy=False)
    client_secret = fields.Char(groups="mpi_helpdesk_zoho.group_zoho_admin", copy=False)
    authorization_code = fields.Char(
        string="Self-Client Code",
        groups="mpi_helpdesk_zoho.group_zoho_admin",
        copy=False,
        help="Paste the code from Zoho API Console (Generate Code). "
        "It is valid for 10 minutes. Test Connection exchanges it.",
    )
    refresh_token = fields.Char(groups="mpi_helpdesk_zoho.group_zoho_admin", copy=False)

    attachment_direction = fields.Selection(
        [
            ("both", "Both ways"),
            ("odoo_to_desk", "Odoo → Desk"),
            ("desk_to_odoo", "Desk → Odoo"),
        ],
        default="both",
        required=True,
    )
    attachment_max_bytes = fields.Integer(default=DEFAULT_MAX_BYTES)
    attachment_mime_allow = fields.Text(default=DEFAULT_MIME_CSV)

    backfill_mode = fields.Selection(
        [("lookback", "Open + lookback"), ("entire", "Entire history")],
        default="lookback",
        required=True,
    )
    backfill_lookback_days = fields.Integer(default=90)
    inbound_team_id = fields.Many2one("helpdesk.team", string="Inbound Helpdesk team")
    catchup_interval_minutes = fields.Integer(default=15)

    webhook_token = fields.Char(
        copy=False, default=lambda self: secrets.token_urlsafe(24), index=True
    )
    webhook_id = fields.Char(copy=False, readonly=True)
    webhook_url = fields.Char(compute="_compute_webhook_url")
    ignore_source_id = fields.Char(copy=False, default=lambda self: str(uuid.uuid4()))

    state = fields.Selection(
        [("draft", "Draft"), ("verified", "Verified"), ("error", "Error")],
        default="draft",
        tracking=True,
    )
    last_error = fields.Text(readonly=True)
    last_catchup_at = fields.Datetime(readonly=True)

    agent_map_ids = fields.One2many("mpi.zoho.desk.agent.map", "connection_id")
    status_map_ids = fields.One2many("mpi.zoho.desk.status.map", "connection_id")
    team_map_ids = fields.One2many("mpi.zoho.desk.team.map", "connection_id")
    department_map_ids = fields.One2many("mpi.zoho.desk.department.map", "connection_id")
    tag_map_ids = fields.One2many("mpi.zoho.desk.tag.map", "connection_id")
    field_map_ids = fields.One2many("mpi.zoho.desk.field.map", "connection_id")
    ticket_map_ids = fields.One2many("mpi.zoho.desk.ticket.map", "connection_id")
    outbox_ids = fields.One2many("mpi.zoho.desk.outbox", "connection_id")

    _company_uniq = models.Constraint(
        "UNIQUE(company_id)",
        "Only one Connection is allowed per company.",
    )
    _webhook_token_uniq = models.Constraint(
        "UNIQUE(webhook_token)",
        "Webhook token must be unique.",
    )

    @api.model
    def _selection_desk_dc(self):
        return self._fields["desk_dc"].selection

    @api.depends("webhook_token")
    def _compute_webhook_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for connection in self:
            token = connection.webhook_token or ""
            connection.webhook_url = "%s/mpi_helpdesk_zoho/desk/webhook/%s" % (base.rstrip("/"), token)

    def _mime_allow_set(self):
        self.ensure_one()
        raw = self.attachment_mime_allow or ""
        return frozenset(part.strip() for part in raw.split(",") if part.strip())

    def _mapped_team_ids(self):
        self.ensure_one()
        return set(self.team_map_ids.mapped("team_id").ids)

    def _mapped_department_ids(self):
        self.ensure_one()
        return set(self.department_map_ids.mapped("desk_department_id"))

    def _token_client(self, transport=None):
        self.ensure_one()
        return DeskClient(
            org_id=(self.desk_org_id or "").strip(),
            dc=self.desk_dc,
            accounts_dc=self.accounts_dc or self.desk_dc,
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=self.refresh_token or "",
            transport=transport or RequestsTransport(),
            ignore_source_id=self.ignore_source_id,
        )

    def _ensure_refresh_token(self, transport=None):
        self.ensure_one()
        code = (self.authorization_code or "").strip()
        if not code:
            return
        if not (self.client_id and self.client_secret):
            raise UserError(
                _("Enter the Zoho self-client ID and secret before the Self-Client Code.")
            )
        client = self._token_client(transport=transport)
        try:
            refresh = client.exchange_authorization_code(code)
        except DeskClientError as exc:
            self.write({"state": "error", "last_error": str(exc)})
            raise UserError(_("Desk refused the Self-Client Code: %s") % exc) from exc
        self.write({"refresh_token": refresh, "authorization_code": False})

    def _make_client(self, transport=None):
        self.ensure_one()
        self._ensure_refresh_token(transport=transport)
        if not (self.client_id and self.client_secret and self.refresh_token and self.desk_org_id):
            raise UserError(
                _(
                    "The Connection is missing Zoho self-client credentials. "
                    "Enter Client ID, Client Secret, Desk Organization, "
                    "and a fresh Self-Client Code."
                )
            )
        return self._token_client(transport=transport)

    def _probe_tickets(self, client):
        try:
            return client.list_tickets(**{"from": 1, "limit": 1})
        except DeskClientError as exc:
            if "OAUTH_ORG_MISMATCH" not in str(exc) or not client.org_id:
                raise
            client.org_id = ""
            return client.list_tickets(**{"from": 1, "limit": 1})

    def action_test_connection(self):
        self.ensure_one()
        first_verify = self.state != "verified"
        try:
            client = self._make_client()
            self._probe_tickets(client)
        except DeskClientError as exc:
            self.write({"state": "error", "last_error": str(exc)})
            raise UserError(_("Desk refused the Connection: %s") % exc) from exc
        self.write({"state": "verified", "last_error": False})
        if first_verify:
            return self.action_configure_sync()
        return True

    def action_configure_sync(self):
        self.ensure_one()
        if self.state != "verified":
            raise UserError(_("Verify the Connection before configuring Ticket Sync."))
        wizard = self.env["mpi.zoho.desk.setup.wizard"].create(
            {"connection_id": self.id}
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Configure Ticket Sync"),
            "res_model": "mpi.zoho.desk.setup.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_register_webhook(self):
        self.ensure_one()
        client = self._make_client()
        department_ids = list(self._mapped_department_ids())
        try:
            created = client.create_webhook(
                name="mpi_helpdesk_zoho %s" % self.name,
                url=self.webhook_url,
                department_ids=department_ids,
                ignore_source_id=self.ignore_source_id,
            )
        except DeskClientError as exc:
            self.write({"state": "error", "last_error": str(exc)})
            raise UserError(
                _(
                    "Desk could not create the webhook. Paste this URL in Desk instead:\n%s\n\n%s"
                )
                % (self.webhook_url, exc)
            ) from exc
        webhook_id = created.get("id") or created.get("webhookId")
        self.write({"webhook_id": webhook_id, "state": "verified", "last_error": False})
        return True

    def action_backfill(self):
        self.ensure_one()
        self._sync_from_desk(backfill=True)
        return True

    def action_catch_up(self):
        now = fields.Datetime.now()
        for connection in self:
            connection._process_outbox()
            interval = (connection.catchup_interval_minutes or 15) * 60
            last = connection.last_catchup_at
            if last and (now - last).total_seconds() < interval:
                continue
            connection._sync_from_desk(backfill=False)
            connection.last_catchup_at = now
        return True

    @api.model
    def _cron_catch_up(self):
        self.search([("active", "=", True), ("state", "=", "verified")]).action_catch_up()

    def _schedule_catchup_once(self):
        data = self.env.cr.precommit.data
        if data.get("mpi.zoho.desk.catchup_scheduled"):
            return
        data["mpi.zoho.desk.catchup_scheduled"] = True
        cron = self.env.ref(
            "mpi_helpdesk_zoho.cron_mpi_helpdesk_zoho_catchup", raise_if_not_found=False
        )
        if cron:
            cron._trigger()

    def _sync_from_desk(self, *, backfill):
        self.ensure_one()
        self.env["mpi.zoho.desk.sync"]._pull_connection(self, backfill=backfill)

    def _process_outbox(self):
        self.ensure_one()
        self.env["mpi.zoho.desk.sync"]._flush_outbox(self)
