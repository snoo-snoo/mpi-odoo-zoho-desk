# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_threads import sort_threads_for_chatter, thread_body


class TestDeskThreads(unittest.TestCase):
    def test_thread_body_prefers_content(self):
        self.assertEqual(
            thread_body({"content": " full ", "summary": "short"}),
            "full",
        )

    def test_thread_body_rejects_truncated_summary(self):
        self.assertFalse(
            thread_body({"summary": "Hallo, Darf man wirklich ein KGT ..."})
        )
        self.assertEqual(
            thread_body({"content": "Full text from get_thread"}),
            "Full text from get_thread",
        )

    def test_sort_threads_oldest_first_for_chatter(self):
        threads = [
            {"id": "2", "sendDateTime": "2026-01-02T10:00:00.000Z", "content": "newer"},
            {"id": "1", "sendDateTime": "2026-01-01T10:00:00.000Z", "content": "older"},
        ]
        ordered = sort_threads_for_chatter(threads)
        self.assertEqual([row["id"] for row in ordered], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
