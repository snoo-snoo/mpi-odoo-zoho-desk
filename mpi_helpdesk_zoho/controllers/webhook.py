# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import json
import logging

from odoo import http
from odoo.http import request

from ..lib.webhook_auth import authenticate_webhook
from ..lib.zoho_jwt import verify_zoho_jwt

_logger = logging.getLogger(__name__)


class MpiZohoDeskWebhook(http.Controller):
    @http.route(
        "/mpi_helpdesk_zoho/desk/webhook/<string:token>",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def desk_webhook(self, token, **kwargs):
        connection = (
            request.env["mpi.zoho.desk.connection"]
            .sudo()
            .search([("webhook_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not connection:
            return request.make_response("unknown connection", status=404)

        def _verify(jwt_token):
            try:
                verify_zoho_jwt(jwt_token, dc=connection.desk_dc)
                return True
            except Exception:
                _logger.warning("Desk webhook JWT rejected for Connection %s", connection.id)
                return False

        authorization = request.httprequest.headers.get("Authorization")
        auth = authenticate_webhook(
            method=request.httprequest.method,
            authorization=authorization,
            verify_jwt=_verify,
        )
        if not auth.ok:
            return request.make_response(auth.reason or "forbidden", status=401)
        if auth.handshake:
            return request.make_response("ok", status=200)

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except json.JSONDecodeError:
            return request.make_response("invalid json", status=400)
        request.env["mpi.zoho.desk.sync"].sudo()._apply_webhook_event(connection, payload)
        return request.make_response("ok", status=200)
