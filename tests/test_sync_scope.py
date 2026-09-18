# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: sync_scope — Team Map outbound, Department Map inbound."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.sync_scope import allows_inbound, allows_outbound


class TestSyncScope(unittest.TestCase):
    def test_mapped_team_may_go_to_desk(self):
        self.assertTrue(allows_outbound(team_id=4, mapped_team_ids={4, 9}))

    def test_unmapped_team_stays_in_odoo(self):
        self.assertFalse(allows_outbound(team_id=1, mapped_team_ids={4, 9}))

    def test_missing_team_does_not_go_out(self):
        self.assertFalse(allows_outbound(team_id=None, mapped_team_ids={4}))

    def test_mapped_department_may_come_in(self):
        self.assertTrue(allows_inbound(department_id="D1", mapped_department_ids={"D1"}))

    def test_unmapped_department_stays_in_desk(self):
        self.assertFalse(allows_inbound(department_id="SPAM", mapped_department_ids={"D1"}))


if __name__ == "__main__":
    unittest.main()
