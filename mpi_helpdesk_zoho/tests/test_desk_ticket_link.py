# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDeskTicketLink(TransactionCase):
    def test_helpdesk_ticket_desk_url(self):
        connection = self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "desk_dc": "eu",
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
            "https://desk.zoho.eu/agent/oekofen/tickets/details/63383000025230899",
        )
        action = ticket.action_open_mpi_zoho_desk_ticket()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertEqual(action["target"], "new")
        self.assertIn("63383000025230899", action["url"])
