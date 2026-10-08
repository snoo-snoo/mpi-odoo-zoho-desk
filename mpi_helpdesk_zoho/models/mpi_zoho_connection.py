# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import json
import logging
import secrets
import uuid
from datetime import timedelta

from psycopg2 import InterfaceError

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib.attachment_policy import DEFAULT_MAX_BYTES, DEFAULT_MIME_ALLOW
from ..lib.desk_client import DeskClient, DeskClientError
from ..lib.desk_oauth import desk_oauth_is_rate_limited
from ..lib.desk_hosts import desk_agent_base_url_from_custom_domain, desk_ticket_agent_url
from ..lib.requests_transport import RequestsTransport
from ..lib.self_client import SELF_CLIENT_SCOPE_CSV

_logger = logging.getLogger(__name__)

DEFAULT_MIME_CSV = ",".join(sorted(DEFAULT_MIME_ALLOW))
_PENDING_BACKFILL_PARAM = "mpi_helpdesk_zoho.pending_backfill_connection_ids"


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
    desk_agent_base_url = fields.Char(
        string="Desk agent URL",
        tracking=True,
        help="Agent UI origin, e.g. https://helpdesk.example.com. "
        "Filled from Desk custom domain when you test the Connection. "
        "Leave empty to use the Zoho DC host (desk.zoho.eu).",
    )
    desk_agent_portal = fields.Char(
        string="Desk agent portal",
        tracking=True,
        help="Portal segment from your agent URL: …/agent/<this>/all/tickets/… "
        "Filled automatically when you test the Connection.",
    )
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
        help="Paste the code from the Zoho API console here. "
        "It is valid for 10 minutes. The required permissions are listed below. "
        "Then click Test Connection.",
    )
    refresh_token = fields.Char(groups="mpi_helpdesk_zoho.group_zoho_admin", copy=False)
    desk_access_token = fields.Char(
        groups="mpi_helpdesk_zoho.group_zoho_admin", copy=False
    )
    desk_access_token_expires_at = fields.Datetime(copy=False)
    desk_api_backoff_until = fields.Datetime(
        copy=False,
        readonly=True,
        help="Pause Desk API calls until this time after Zoho OAuth rate limiting.",
    )
    self_client_scopes = fields.Char(
        compute="_compute_self_client_scopes",
        string="Required permissions",
        help="Enter this list when you create the code in the Zoho API console.",
    )

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
    backfill_list_from = fields.Integer(
        default=1,
        copy=False,
        help="Desk list API offset for the next backfill cron chunk (1-based).",
    )
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

    @api.depends()
    def _compute_self_client_scopes(self):
        for connection in self:
            connection.self_client_scopes = SELF_CLIENT_SCOPE_CSV

    @api.depends("webhook_token")
    def _compute_webhook_url(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for connection in self:
            token = connection.webhook_token or ""
            connection.webhook_url = "%s/mpi_helpdesk_zoho/desk/webhook/%s" % (base.rstrip("/"), token)

    def _mime_allow_set(self):
        self.ensure_one()
        raw = self.attachment_mime_allow or ""
        parsed = frozenset(part.strip() for part in raw.split(",") if part.strip())
        return parsed | DEFAULT_MIME_ALLOW

    def _mapped_team_ids(self):
        self.ensure_one()
        return set(self.team_map_ids.mapped("team_id").ids)

    def _mapped_department_ids(self):
        self.ensure_one()
        return set(self.department_map_ids.mapped("desk_department_id"))

    def _desk_access_token_still_valid(self):
        self.ensure_one()
        token = (self.desk_access_token or "").strip()
        expires = self.desk_access_token_expires_at
        if not token or not expires:
            return False
        skew = fields.Datetime.now() + timedelta(minutes=2)
        return expires > skew

    def _desk_api_backoff_active(self):
        self.ensure_one()
        until = self.desk_api_backoff_until
        return bool(until and until > fields.Datetime.now())

    def _desk_store_access_token(self, token, expires_in=3600):
        self.ensure_one()
        seconds = max(int(expires_in or 3600) - 120, 60)
        self.sudo().write(
            {
                "desk_access_token": token,
                "desk_access_token_expires_at": fields.Datetime.now()
                + timedelta(seconds=seconds),
                "desk_api_backoff_until": False,
            }
        )

    def _desk_register_oauth_backoff(self, message, *, minutes=30):
        self.ensure_one()
        self.sudo().write(
            {
                "desk_api_backoff_until": fields.Datetime.now()
                + timedelta(minutes=minutes),
                "last_error": message,
            }
        )

    def _bind_desk_client_oauth(self, client):
        self.ensure_one()
        connection = self

        def on_refreshed(token, expires_in):
            connection._desk_store_access_token(token, expires_in)

        def on_refresh_failed(payload, _response):
            message = (
                payload.get("error_description")
                or payload.get("error")
                or "Token refresh failed"
            )
            if desk_oauth_is_rate_limited(message):
                connection._desk_register_oauth_backoff(message)

        client._on_access_token_refreshed = on_refreshed
        client._on_access_token_refresh_failed = on_refresh_failed

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
        self._bind_desk_client_oauth(client)
        try:
            refresh = client.exchange_authorization_code(code)
        except DeskClientError as exc:
            self.write({"state": "error", "last_error": str(exc)})
            raise UserError(_("Desk refused the Self-Client Code: %s") % exc) from exc
        self.write({"refresh_token": refresh, "authorization_code": False})

    def _make_client(self, transport=None):
        self.ensure_one()
        if self._desk_api_backoff_active():
            raise UserError(
                _(
                    "Zoho temporarily limited API access (too many token requests). "
                    "Try again after %(until)s.",
                    until=fields.Datetime.to_string(self.desk_api_backoff_until),
                )
            )
        self._ensure_refresh_token(transport=transport)
        if not (self.client_id and self.client_secret and self.refresh_token and self.desk_org_id):
            raise UserError(
                _(
                    "The Connection is missing Zoho self-client credentials. "
                    "Enter Client ID, Client Secret, Desk Organization, "
                    "and a fresh Self-Client Code."
                )
            )
        client = self._token_client(transport=transport)
        self._bind_desk_client_oauth(client)
        if self._desk_access_token_still_valid():
            client._access_token = self.desk_access_token
        return client

    def _probe_tickets(self, client):
        try:
            return client.list_tickets(**{"from": 1, "limit": 1})
        except DeskClientError as exc:
            if "OAUTH_ORG_MISMATCH" not in str(exc) or not client.org_id:
                raise
            client.org_id = ""
            return client.list_tickets(**{"from": 1, "limit": 1})

    def _desk_agent_ui_from_api(self, client):
        self.ensure_one()
        target = (self.desk_org_id or "").strip()
        organization = False
        if target:
            try:
                organization = client.get_organization(target)
            except DeskClientError:
                organization = False
        if not organization:
            page = client.list_organizations()
            organizations = page.get("data") or []
            for row in organizations:
                if str(row.get("id") or "") == target:
                    organization = row
                    break
            if not organization and len(organizations) == 1:
                organization = organizations[0]
        if not organization:
            return False, False
        portal = organization.get("portalName") or organization.get("companyName")
        base_url = desk_agent_base_url_from_custom_domain(organization.get("customDomain"))
        return portal, base_url

    def desk_ticket_url(self, desk_ticket_id):
        self.ensure_one()
        return desk_ticket_agent_url(
            self.desk_dc,
            self.desk_agent_portal,
            desk_ticket_id,
            agent_base_url=self.desk_agent_base_url,
        )

    def action_test_connection(self):
        self.ensure_one()
        first_verify = self.state != "verified"
        try:
            client = self._make_client()
            self._probe_tickets(client)
            portal, base_url = self._desk_agent_ui_from_api(client)
        except DeskClientError as exc:
            self.write({"state": "error", "last_error": str(exc)})
            raise UserError(_("Desk refused the Connection: %s") % exc) from exc
        values = {"state": "verified", "last_error": False}
        if portal and portal != self.desk_agent_portal:
            values["desk_agent_portal"] = portal
        if base_url and base_url != self.desk_agent_base_url:
            values["desk_agent_base_url"] = base_url
        self.write(values)
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
        for connection in self:
            if connection.state != "verified":
                raise UserError(_("Verify the Connection before running Backfill."))
            if not connection._mapped_department_ids():
                raise UserError(
                    _(
                        "Add at least one Department Map before Backfill. "
                        "Inbound Ticket Sync needs a mapped Desk department."
                    )
                )
            connection._schedule_backfill_once()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Backfill scheduled"),
                "message": _(
                    "Ticket Sync backfill runs on the catch-up cron so the request "
                    "does not hit the 15-minute web time limit. Large histories "
                    "may take several cron runs."
                ),
                "type": "success",
                "sticky": False,
            },
        }

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
        if self._cron_process_pending_backfill():
            return
        self.search([("active", "=", True), ("state", "=", "verified")]).action_catch_up()

    @api.model
    def _pending_backfill_connection_ids(self):
        param = self.env["ir.config_parameter"].sudo()
        raw = param.get_param(_PENDING_BACKFILL_PARAM, "[]")
        try:
            ids = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(ids, list):
            return []
        return [connection_id for connection_id in ids if isinstance(connection_id, int)]

    @api.model
    def _enqueue_pending_backfill(self, connection_ids):
        connection_ids = [connection_id for connection_id in connection_ids if connection_id]
        if not connection_ids:
            return
        param = self.env["ir.config_parameter"].sudo()
        pending = set(self._pending_backfill_connection_ids())
        pending.update(connection_ids)
        param.set_param(_PENDING_BACKFILL_PARAM, json.dumps(sorted(pending)))

    @api.model
    def _set_pending_backfill_connection_ids(self, connection_ids):
        self.env["ir.config_parameter"].sudo().set_param(
            _PENDING_BACKFILL_PARAM,
            json.dumps(sorted(set(connection_ids))),
        )

    @api.model
    def _cron_process_pending_backfill(self):
        """Run queued Backfills. Returns True when work remains or was attempted."""
        pending_ids = self._pending_backfill_connection_ids()
        if not pending_ids:
            return False
        still_pending = []
        sync = self.env["mpi.zoho.desk.sync"]
        for connection in self.browse(pending_ids).exists():
            if not connection.active or connection.state != "verified":
                continue
            try:
                complete = sync._pull_connection(connection, backfill=True)
            except DeskClientError as exc:
                if desk_oauth_is_rate_limited(exc):
                    connection._desk_register_oauth_backoff(str(exc))
                    _logger.warning(
                        "Backfill paused for Connection %s: Zoho OAuth rate limit (%s).",
                        connection.id,
                        exc,
                    )
                else:
                    _logger.exception(
                        "Backfill failed for Connection %s; will retry on next cron.",
                        connection.id,
                    )
                still_pending.append(connection.id)
                continue
            except Exception:
                _logger.exception(
                    "Backfill failed for Connection %s; will retry on next cron.",
                    connection.id,
                )
                still_pending.append(connection.id)
                continue
            if not complete:
                still_pending.append(connection.id)
        try:
            self._set_pending_backfill_connection_ids(still_pending)
        except InterfaceError:
            _logger.warning(
                "Could not persist Zoho backfill queue; cron worker is shutting down."
            )
        return bool(still_pending)

    def _notify_pull_skipped_no_department_map(self):
        self.ensure_one()
        title = _("Zoho Desk Ticket Sync")
        message = _(
            "Ticket Sync pull skipped for Connection %(name)s: add at least one Department Map.",
            name=self.display_name,
        )
        _logger.info(message)
        group = self.env.ref(
            "mpi_helpdesk_zoho.group_zoho_admin", raise_if_not_found=False
        )
        if not group:
            return
        payload = {"type": "warning", "title": title, "message": message}
        bus = self.env["bus.bus"].sudo()
        for user in group.users:
            if user.partner_id:
                bus._sendone(user.partner_id, "simple_notification", payload)

    def _schedule_backfill_once(self):
        self.write({"backfill_list_from": 1})
        self._enqueue_pending_backfill(self.ids)
        self._schedule_catchup_once()

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
        return self.env["mpi.zoho.desk.sync"]._pull_connection(self, backfill=backfill)

    def _process_outbox(self):
        self.ensure_one()
        self.env["mpi.zoho.desk.sync"]._flush_outbox(self)
