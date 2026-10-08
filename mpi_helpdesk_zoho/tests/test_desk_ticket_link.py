# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDeskTicketLink(TransactionCase):
    def test_helpdesk_ticket_desk_url(self):
        connection = self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "desk_dc": "eu",
                "desk_agent_base_url": "https://helpdesk.oekofen.com",
                "desk_agent_portal": "oekofen",
                "company_id": self.env.company.id,
            }
        )
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Leak",
                "company_id": self.env.company.id,
            }
        )
        self.env["mpi.zoho.desk.ticket.map"].create(
            {
                "connection_id": connection.id,
                "helpdesk_ticket_id": ticket.id,
                "desk_ticket_id": "63383000025230899",
            }
        )
        self.assertEqual(
            ticket.mpi_zoho_desk_ticket_url,
            "https://helpdesk.oekofen.com/agent/oekofen/all/tickets/details/63383000025230899",
        )
        action = ticket.action_open_mpi_zoho_desk_ticket()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertEqual(action["target"], "new")
        self.assertIn("63383000025230899", action["url"])

    def test_resync_requires_desk_link(self):
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Local only", "company_id": self.env.company.id}
        )
        with self.assertRaises(UserError):
            ticket.action_mpi_zoho_resync_from_desk()

    def test_resync_calls_sync_with_force_flags(self):
        connection = self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "desk_dc": "eu",
                "company_id": self.env.company.id,
                "state": "verified",
            }
        )
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Linked", "company_id": self.env.company.id}
        )
        self.env["mpi.zoho.desk.ticket.map"].create(
            {
                "connection_id": connection.id,
                "helpdesk_ticket_id": ticket.id,
                "desk_ticket_id": "63383000025230899",
            }
        )
        sync = self.env["mpi.zoho.desk.sync"]
        with patch.object(type(sync), "resync_desk_ticket", autospec=True) as fake_resync:
            action = ticket.action_mpi_zoho_resync_from_desk()
        fake_resync.assert_called_once()
        self.assertEqual(fake_resync.call_args[0][1], connection)
        self.assertEqual(fake_resync.call_args[0][2], "63383000025230899")
        self.assertEqual(action.get("tag"), "display_notification")
