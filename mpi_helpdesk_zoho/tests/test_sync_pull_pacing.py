# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSyncPullPacing(TransactionCase):
    def _connection(self):
        return self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "company_id": self.env.company.id,
                "client_id": "c",
                "client_secret": "s",
                "refresh_token": "r",
                "state": "verified",
            }
        )

    def test_pull_skips_without_department_map(self):
        connection = self._connection()
        client = MagicMock()
        with patch.object(type(connection), "_make_client", return_value=client):
            self.env["mpi.zoho.desk.sync"]._pull_connection(connection, backfill=False)
        client.list_tickets.assert_not_called()

    def test_pull_passes_department_ids(self):
        connection = self._connection()
        self.env["mpi.zoho.desk.department.map"].create(
            {
                "connection_id": connection.id,
                "desk_department_id": "D1",
                "desk_department_name": "Support",
            }
        )
        client = MagicMock()
        client.list_tickets.return_value = {"data": []}
        with patch.object(type(connection), "_make_client", return_value=client):
            self.env["mpi.zoho.desk.sync"]._pull_connection(connection, backfill=False)
        kwargs = client.list_tickets.call_args.kwargs
        self.assertEqual(kwargs.get("departmentIds"), "D1")

    def test_partner_cache_reuses_record(self):
        connection = self._connection()
        sync = self.env["mpi.zoho.desk.sync"]
        cache = {}
        detail = {
            "contact": {"email": "same@example.com", "lastName": "Same"},
            "account": {},
        }
        first = sync._partner_for_desk(connection, detail, partner_cache=cache)
        second = sync._partner_for_desk(connection, detail, partner_cache=cache)
        self.assertEqual(first, second)
        self.assertEqual(len(cache), 1)
