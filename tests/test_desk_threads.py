# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_threads import (
    desk_ticket_description,
    sort_threads_for_chatter,
    thread_body,
)


class TestDeskThreads(unittest.TestCase):
    def test_description_falls_back_to_first_thread(self):
        detail = {"description": "", "subject": "Servicebericht"}
        threads = [
            {"id": "1", "summary": "Short"},
            {"id": "2", "content": "Hallo Raphael, anbei der Servicebericht."},
        ]
        self.assertEqual(
            desk_ticket_description(detail, threads),
            "Hallo Raphael, anbei der Servicebericht.",
        )

    def test_description_prefers_ticket_field(self):
        detail = {"description": "<p>Desk HTML body</p>"}
        threads = [{"content": "Thread only"}]
        self.assertEqual(desk_ticket_description(detail, threads), "<p>Desk HTML body</p>")

    def test_thread_body_prefers_content(self):
        self.assertEqual(
            thread_body({"content": " full ", "summary": "short"}),
            "full",
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
