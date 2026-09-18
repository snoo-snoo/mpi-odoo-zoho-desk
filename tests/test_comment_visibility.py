# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: comment_visibility — Public Comment vs Internal Note."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.comment_visibility import (
    desk_thread_to_odoo,
    odoo_message_to_desk,
)


class TestCommentVisibility(unittest.TestCase):
    def test_public_desk_thread_is_customer_message(self):
        self.assertEqual(desk_thread_to_odoo(is_public=True), "public")

    def test_private_desk_thread_is_internal_note(self):
        self.assertEqual(desk_thread_to_odoo(is_public=False), "internal")

    def test_customer_message_stays_public_on_desk(self):
        self.assertTrue(odoo_message_to_desk(visibility="public"))

    def test_internal_note_stays_private_on_desk(self):
        self.assertFalse(odoo_message_to_desk(visibility="internal"))

    def test_internal_never_maps_to_public(self):
        self.assertNotEqual(desk_thread_to_odoo(is_public=False), "public")
        self.assertFalse(odoo_message_to_desk(visibility="internal"))


if __name__ == "__main__":
    unittest.main()
