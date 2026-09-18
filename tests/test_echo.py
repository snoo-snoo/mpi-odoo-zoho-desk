# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: echo.should_apply — origin stamp plus unchanged hash."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.echo import payload_hash, should_apply


class TestEcho(unittest.TestCase):
    def test_connector_origin_is_skipped(self):
        self.assertFalse(
            should_apply(origin="connector", incoming_hash="aaa", stored_hash="bbb")
        )

    def test_unchanged_payload_is_skipped(self):
        self.assertFalse(
            should_apply(origin="desk", incoming_hash="same", stored_hash="same")
        )

    def test_desk_change_is_applied(self):
        self.assertTrue(
            should_apply(origin="desk", incoming_hash="new", stored_hash="old")
        )

    def test_odoo_change_is_applied(self):
        self.assertTrue(
            should_apply(origin="odoo", incoming_hash="new", stored_hash="old")
        )

    def test_same_body_hashes_equal(self):
        self.assertEqual(payload_hash({"subject": "Heizung"}), payload_hash({"subject": "Heizung"}))

    def test_different_body_hashes_differ(self):
        self.assertNotEqual(
            payload_hash({"subject": "Heizung"}),
            payload_hash({"subject": "Pumpe"}),
        )


if __name__ == "__main__":
    unittest.main()
