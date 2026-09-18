# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: ticket_fields.apply_desk_wins — Desk wins Ticket fields on collision."""

import unittest

from mpi_helpdesk_zoho.lib.ticket_fields import apply_desk_wins


class TestTicketFields(unittest.TestCase):
    def test_desk_status_wins_over_odoo_status(self):
        result = apply_desk_wins(
            odoo_fields={"status": "Open", "subject": "Leak"},
            desk_fields={"status": "Closed", "subject": "Leak"},
        )
        self.assertEqual(result["status"], "Closed")

    def test_desk_subject_wins(self):
        result = apply_desk_wins(
            odoo_fields={"subject": "Old"},
            desk_fields={"subject": "New from Desk"},
        )
        self.assertEqual(result["subject"], "New from Desk")

    def test_missing_desk_field_keeps_odoo(self):
        result = apply_desk_wins(
            odoo_fields={"priority": "2", "status": "Open"},
            desk_fields={"status": "Open"},
        )
        self.assertEqual(result["priority"], "2")


if __name__ == "__main__":
    unittest.main()
