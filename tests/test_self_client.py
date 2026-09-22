# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: self-client OAuth scopes for Generate Code."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.self_client import SELF_CLIENT_SCOPE_CSV, SELF_CLIENT_SCOPES


class TestSelfClientScopes(unittest.TestCase):
    def test_generate_code_string_is_comma_separated(self):
        self.assertEqual(SELF_CLIENT_SCOPE_CSV, ",".join(SELF_CLIENT_SCOPES))
        self.assertFalse(" " in SELF_CLIENT_SCOPE_CSV)

    def test_ticket_sync_can_read_create_and_update(self):
        for scope in (
            "Desk.tickets.READ",
            "Desk.tickets.CREATE",
            "Desk.tickets.UPDATE",
        ):
            self.assertIn(scope, SELF_CLIENT_SCOPES)

    def test_maps_and_webhook_registration_are_covered(self):
        for scope in (
            "Desk.basic.READ",
            "Desk.fields.READ",
            "Desk.settings.READ",
            "Desk.webhooks.CREATE",
        ):
            self.assertIn(scope, SELF_CLIENT_SCOPES)

    def test_does_not_ask_to_delete_tickets(self):
        self.assertNotIn("Desk.tickets.DELETE", SELF_CLIENT_SCOPES)
        self.assertNotIn("Desk.tickets.ALL", SELF_CLIENT_SCOPES)
