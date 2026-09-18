# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: partner_match.resolve — match then create."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.partner_match import resolve_partner


class TestPartnerMatch(unittest.TestCase):
    def test_contact_matches_existing_email(self):
        decision = resolve_partner(
            kind="contact",
            email="eva@kunde.at",
            vat=None,
            name="Eva Kunde",
            existing=[{"id": 7, "email": "eva@kunde.at", "vat": False, "name": "Eva"}],
        )
        self.assertEqual(decision, ("link", 7))

    def test_account_matches_vat(self):
        decision = resolve_partner(
            kind="account",
            email=None,
            vat="ATU12345678",
            name="Kunde GmbH",
            existing=[{"id": 3, "email": "office@kunde.at", "vat": "ATU12345678", "name": "Kunde GmbH"}],
        )
        self.assertEqual(decision, ("link", 3))

    def test_account_matches_name_when_no_vat(self):
        decision = resolve_partner(
            kind="account",
            email="office@kunde.at",
            vat=None,
            name="Kunde GmbH",
            existing=[{"id": 3, "email": "other@x.at", "vat": False, "name": "Kunde GmbH"}],
        )
        self.assertEqual(decision, ("link", 3))

    def test_no_match_creates(self):
        decision = resolve_partner(
            kind="contact",
            email="neu@kunde.at",
            vat=None,
            name="Neu",
            existing=[{"id": 7, "email": "eva@kunde.at", "vat": False, "name": "Eva"}],
        )
        self.assertEqual(decision, ("create", None))

    def test_email_match_is_case_insensitive(self):
        decision = resolve_partner(
            kind="contact",
            email="Eva@Kunde.at",
            vat=None,
            name="Eva",
            existing=[{"id": 7, "email": "eva@kunde.at", "vat": False, "name": "Eva"}],
        )
        self.assertEqual(decision, ("link", 7))


if __name__ == "__main__":
    unittest.main()
