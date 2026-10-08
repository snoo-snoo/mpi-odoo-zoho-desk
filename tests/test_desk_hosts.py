# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: desk_hosts — DC to Desk and Accounts roots."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_hosts import accounts_root, desk_root, desk_ticket_agent_url
from mpi_helpdesk_zoho.lib.zoho_jwt import jwks_url


class TestDeskHosts(unittest.TestCase):
    def test_eu_desk_and_accounts(self):
        self.assertEqual(desk_root("eu"), "https://desk.zoho.eu")
        self.assertEqual(accounts_root("eu"), "https://accounts.zoho.eu")

    def test_unknown_dc_falls_back_to_com(self):
        self.assertEqual(desk_root("xx"), "https://desk.zoho.com")

    def test_jwks_follows_desk_root(self):
        self.assertEqual(jwks_url("eu"), "https://desk.zoho.eu/.well-known/jwks.json")

    def test_desk_ticket_agent_url(self):
        url = desk_ticket_agent_url("eu", "oekofen", "63383000025230899")
        self.assertEqual(
            url,
            "https://desk.zoho.eu/agent/oekofen/tickets/details/63383000025230899",
        )
        self.assertFalse(desk_ticket_agent_url("eu", "", "63383000025230899"))


if __name__ == "__main__":
    unittest.main()
