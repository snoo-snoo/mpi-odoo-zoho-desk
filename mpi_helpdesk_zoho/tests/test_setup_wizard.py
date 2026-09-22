# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged


class FakeDeskClient:
    def list_departments(self, **params):
        return [
            {"id": "D1", "name": "Support"},
            {"id": "D2", "name": "Spam"},
        ]

    def list_agents(self, **params):
        return [
            {
                "id": "A1",
                "emailId": "agent@example.com",
                "firstName": "Ann",
                "lastName": "Agent",
            }
        ]

    def list_organization_tags(self, **params):
        return [{"name": "vip"}]

    def list_organization_fields(self, *, module="tickets", **params):
        return [
            {
                "apiName": "status",
                "type": "Picklist",
                "allowedValues": ["Open", "Closed"],
            },
            {
                "apiName": "cf_serial",
                "displayLabel": "Serial",
                "isCustomField": True,
            },
        ]


@tagged("post_install", "-at_install")
class TestSetupWizard(TransactionCase):
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

    def test_apply_creates_team_and_both_maps(self):
        connection = self._connection()
        with patch.object(
            type(connection), "_make_client", return_value=FakeDeskClient()
        ):
            wizard = self.env["mpi.zoho.desk.setup.wizard"].create(
                {"connection_id": connection.id}
            )
        support = wizard.department_line_ids.filtered(
            lambda row: row.desk_department_id == "D1"
        )
        spam = wizard.department_line_ids.filtered(
            lambda row: row.desk_department_id == "D2"
        )
        support.write({"sync": True, "create_team": True, "team_id": False})
        spam.write({"sync": False})
        for line in wizard.status_line_ids:
            line.write({"sync": True, "create_stage": True, "stage_id": False})
        wizard.run_backfill = False
        wizard.action_apply()

        self.assertEqual(len(connection.department_map_ids), 1)
        self.assertEqual(connection.department_map_ids.desk_department_id, "D1")
        self.assertTrue(connection.department_map_ids.team_id)
        self.assertEqual(connection.department_map_ids.team_id.name, "Support")
        self.assertEqual(len(connection.team_map_ids), 1)
        self.assertEqual(
            connection.team_map_ids.desk_department_id,
            connection.department_map_ids.desk_department_id,
        )
        self.assertEqual(
            connection.team_map_ids.team_id, connection.department_map_ids.team_id
        )
        self.assertFalse(
            connection.department_map_ids.filtered(
                lambda row: row.desk_department_id == "D2"
            )
        )

    def test_inbound_uses_paired_team(self):
        connection = self._connection()
        team = self.env["helpdesk.team"].create(
            {"name": "Paired", "company_id": self.env.company.id}
        )
        self.env["mpi.zoho.desk.department.map"].create(
            {
                "connection_id": connection.id,
                "desk_department_id": "D1",
                "desk_department_name": "Support",
                "team_id": team.id,
            }
        )
        sync = self.env["mpi.zoho.desk.sync"]
        result = sync._inbound_team_for_department(connection, "D1")
        self.assertEqual(result, team)
        fallback = sync._inbound_team_for_department(connection, "OTHER")
        self.assertFalse(fallback)

    def test_configure_sync_opens_wizard_without_backfill(self):
        connection = self._connection()
        sync_calls = []

        def fake_sync(self_conn, *, backfill):
            sync_calls.append(backfill)

        with patch.object(
            type(connection), "_make_client", return_value=FakeDeskClient()
        ), patch.object(
            type(connection), "_sync_from_desk", autospec=True, side_effect=fake_sync
        ):
            action = connection.action_configure_sync()
        self.assertEqual(action["res_model"], "mpi.zoho.desk.setup.wizard")
        self.assertTrue(action["res_id"])
        self.assertEqual(sync_calls, [])

    def test_first_verify_opens_wizard_not_backfill(self):
        connection = self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "company_id": self.env.company.id,
                "client_id": "c",
                "client_secret": "s",
                "refresh_token": "r",
                "state": "draft",
            }
        )
        sync_calls = []

        def fake_sync(self_conn, *, backfill):
            sync_calls.append(backfill)

        fake_client = FakeDeskClient()
        fake_client.list_tickets = MagicMock(return_value={"data": []})

        with patch.object(
            type(connection), "_make_client", return_value=fake_client
        ), patch.object(
            type(connection), "_probe_tickets", return_value={"data": []}
        ), patch.object(
            type(connection), "_sync_from_desk", autospec=True, side_effect=fake_sync
        ):
            action = connection.action_test_connection()
        self.assertEqual(connection.state, "verified")
        self.assertEqual(action["res_model"], "mpi.zoho.desk.setup.wizard")
        self.assertEqual(sync_calls, [])
