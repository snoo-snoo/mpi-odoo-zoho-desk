# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


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
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            Connection.create(
                {
                    "name": "Desk EU 2",
                    "desk_org_id": "2",
                    "company_id": self.env.company.id,
                }
            )

    def test_mapped_team_queues_create(self):
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
