# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: desk_contact identity from Desk ticket payloads."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_contact import desk_contact_identity, partner_display_name
from mpi_helpdesk_zoho.lib.sync_pull import partner_cache_key


class TestDeskContact(unittest.TestCase):
    def test_nested_contact_email_and_full_name(self):
        identity = desk_contact_identity(
            {
                "contact": {
                    "id": "C1",
                    "firstName": "Lucas",
                    "lastName": "Carol",
                    "email": "carol@zylker.com",
                }
            }
        )
        self.assertEqual(identity["email"], "carol@zylker.com")
        self.assertEqual(identity["name"], "Lucas Carol")
        self.assertEqual(identity["contact_id"], "C1")
        self.assertEqual(identity["kind"], "contact")

    def test_top_level_email_fallback(self):
        identity = desk_contact_identity({"email": "top@ex.com", "contactId": "C9"})
        self.assertEqual(identity["email"], "top@ex.com")
        self.assertEqual(identity["contact_id"], "C9")

    def test_account_name_when_no_person(self):
        identity = desk_contact_identity(
            {"account": {"id": "A1", "accountName": "Kunde GmbH", "vat": "ATU1"}}
        )
        self.assertEqual(identity["name"], "Kunde GmbH")
        self.assertEqual(identity["vat"], "ATU1")
        self.assertTrue(identity["is_company"])

    def test_empty_cache_key_is_none(self):
        self.assertIsNone(partner_cache_key())

    def test_contact_id_keeps_cache_distinct(self):
        a = partner_cache_key(contact_id="1")
        b = partner_cache_key(contact_id="2")
        self.assertNotEqual(a, b)

    def test_display_name_fallbacks(self):
        self.assertEqual(partner_display_name(name="Ann"), "Ann")
        self.assertEqual(partner_display_name(email="a@b.c"), "a@b.c")
        self.assertEqual(partner_display_name(contact_id="99"), "Desk contact 99")
        self.assertEqual(partner_display_name(), "Desk contact")


if __name__ == "__main__":
    unittest.main()
