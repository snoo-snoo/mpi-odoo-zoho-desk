# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

try:
    from psycopg2 import IntegrityError
except ImportError:
    from psycopg.errors import UniqueViolation as IntegrityError


@tagged("post_install", "-at_install")
class TestConnection(TransactionCase):
    def test_one_connection_per_company(self):
        Connection = self.env["mpi.zoho.desk.connection"]
        Connection.create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "company_id": self.env.company.id,
            }
        )
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                Connection.create(
                    {
                        "name": "Desk EU 2",
                        "desk_org_id": "2",
                        "company_id": self.env.company.id,
                    }
                )

    def test_mapped_team_queues_create_once_per_request(self):
        connection = self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "company_id": self.env.company.id,
            }
        )
        team = self.env["helpdesk.team"].search([], limit=1)
        if not team:
            team = self.env["helpdesk.team"].create({"name": "Support"})
        self.env["mpi.zoho.desk.team.map"].create(
            {"connection_id": connection.id, "team_id": team.id}
        )
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Boiler leak",
                "team_id": team.id,
                "company_id": self.env.company.id,
            }
        )
        outbox = self.env["mpi.zoho.desk.outbox"].search(
            [("helpdesk_ticket_id", "=", ticket.id), ("event_type", "=", "create_ticket")]
        )
        self.assertEqual(len(outbox), 1)
        self.assertTrue(self.env.cr.precommit.data.get("mpi.zoho.desk.catchup_scheduled"))

    def test_unmapped_team_does_not_queue(self):
        self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "company_id": self.env.company.id,
            }
        )
        team = self.env["helpdesk.team"].create({"name": "Internal IT"})
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "VPN",
                "team_id": team.id,
                "company_id": self.env.company.id,
            }
        )
        outbox = self.env["mpi.zoho.desk.outbox"].search(
            [("helpdesk_ticket_id", "=", ticket.id)]
        )
        self.assertFalse(outbox)

    def test_self_client_code_is_exchanged_for_refresh_token(self):
        connection = self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "company_id": self.env.company.id,
                "client_id": "cid",
                "client_secret": "csecret",
                "authorization_code": "1000.grant",
            }
        )

        class FakeTransport:
            def request(self, method, url, **kwargs):
                return {
                    "status_code": 200,
                    "json": {
                        "access_token": "acc",
                        "refresh_token": "1000.refresh",
                    },
                }

        connection._ensure_refresh_token(transport=FakeTransport())
        self.assertEqual(connection.refresh_token, "1000.refresh")
        self.assertFalse(connection.authorization_code)

    def test_probe_retries_without_org_on_mismatch(self):
        connection = self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "wrong-org",
                "company_id": self.env.company.id,
            }
        )

        class FakeTransport:
            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append(kwargs.get("headers") or {})
                if len(self.calls) == 1:
                    return {
                        "status_code": 403,
                        "json": {
                            "errorCode": "OAUTH_ORG_MISMATCH",
                            "message": "The orgId does not match the token.",
                        },
                    }
                return {"status_code": 200, "json": {"data": []}}

        client = connection._token_client(transport=FakeTransport())
        client._access_token = "acc"
        page = connection._probe_tickets(client)
        self.assertEqual(page.get("data"), [])
        self.assertFalse(client.org_id)


@tagged("post_install", "-at_install")
class TestWebhookHttp(HttpCase):
    def _connection(self):
        return self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "company_id": self.env.company.id,
            }
        )

    def test_unknown_token_is_404(self):
        response = self.url_open("/mpi_helpdesk_zoho/desk/webhook/not-a-real-token")
        self.assertEqual(response.status_code, 404)

    def test_get_handshake_is_200(self):
        connection = self._connection()
        response = self.url_open("/mpi_helpdesk_zoho/desk/webhook/%s" % connection.webhook_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "ok")

    def test_post_without_jwt_is_401(self):
        connection = self._connection()
        url = "/mpi_helpdesk_zoho/desk/webhook/%s" % connection.webhook_token
        response = self.url_open(
            url,
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 401)
