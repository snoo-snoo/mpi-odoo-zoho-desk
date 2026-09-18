# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: source_removal — close the other side, never delete it."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.source_removal import other_side_action


class TestSourceRemoval(unittest.TestCase):
    def test_desk_delete_closes_helpdesk_ticket(self):
        self.assertEqual(other_side_action(deleted_side="desk"), "close")

    def test_helpdesk_archive_closes_desk_ticket(self):
        self.assertEqual(other_side_action(deleted_side="odoo"), "close")

    def test_never_cascade_deletes(self):
        self.assertNotEqual(other_side_action(deleted_side="desk"), "delete")
        self.assertNotEqual(other_side_action(deleted_side="odoo"), "delete")


if __name__ == "__main__":
    unittest.main()
