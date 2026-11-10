# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: sync_pull — list params, side-content, partner cache key."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from datetime import datetime

from mpi_helpdesk_zoho.lib.sync_pull import (
    defer_attachment_binaries,
    list_ticket_params,
    lookback_page_exhausted,
    partner_cache_key,
    should_sync_side_content,
)


class TestSyncPull(unittest.TestCase):
    def test_list_params_include_department_ids(self):
        params = list_ticket_params(start=1, department_ids=["D1", "D2"])
        self.assertEqual(params["departmentIds"], "D1,D2")
        self.assertEqual(params["from"], 1)
        self.assertEqual(params["limit"], 50)
        self.assertEqual(params["sortBy"], "-modifiedTime")

    def test_list_params_omit_departments_when_empty(self):
        params = list_ticket_params(start=51, department_ids=[])
        self.assertNotIn("departmentIds", params)

    def test_side_content_on_new_or_backfill(self):
        self.assertTrue(should_sync_side_content(is_new=True, backfill=False))
        self.assertTrue(should_sync_side_content(is_new=False, backfill=True))
        self.assertFalse(should_sync_side_content(is_new=False, backfill=False))
        self.assertTrue(
            should_sync_side_content(is_new=False, backfill=False, force_side_content=True)
        )

    def test_defer_binaries_only_on_backfill(self):
        self.assertTrue(defer_attachment_binaries(backfill=True))
        self.assertFalse(defer_attachment_binaries(backfill=False))

    def test_partner_cache_key_normalizes(self):
        self.assertEqual(
            partner_cache_key(email=" A@Ex.COM ", vat="at123", name=" Ann ", contact_id="C1"),
            ("C1", "", "a@ex.com", "AT123", "ann"),
        )

    def test_partner_cache_key_empty_is_none(self):
        self.assertIsNone(partner_cache_key())

    def test_lookback_stops_when_page_is_all_older_closed(self):
        cutoff = datetime(2026, 8, 1)
        older = datetime(2026, 1, 1)
        newer = datetime(2026, 9, 1)
        self.assertTrue(lookback_page_exhausted([older, older], cutoff))
        self.assertFalse(lookback_page_exhausted([older, None], cutoff))
        self.assertFalse(lookback_page_exhausted([older, newer], cutoff))
        self.assertFalse(lookback_page_exhausted([], cutoff))


if __name__ == "__main__":
    unittest.main()
