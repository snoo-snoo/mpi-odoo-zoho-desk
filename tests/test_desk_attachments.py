# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_attachments import (
    desk_attachment_download_url,
    desk_attachment_id,
    desk_attachment_mimetype,
)


class _FakeClient:
    dc = "eu"


class TestDeskAttachments(unittest.TestCase):
    def test_mimetype_from_filename(self):
        row = {"name": "Servicebericht.pdf", "type": "attachment"}
        self.assertEqual(desk_attachment_mimetype(row), "application/pdf")

    def test_attachment_id_from_href(self):
        row = {
            "href": "https://desk.zoho.eu/api/v1/tickets/1/threads/2/attachments/99/content",
        }
        self.assertEqual(desk_attachment_id(row), "99")

    def test_download_url_for_thread_attachment(self):
        row = {"id": "99"}
        url = desk_attachment_download_url(
            _FakeClient(),
            row,
            desk_ticket_id="633",
            desk_thread_id="42",
        )
        self.assertEqual(
            url,
            "https://desk.zoho.eu/api/v1/tickets/633/threads/42/attachments/99/content",
        )


if __name__ == "__main__":
    unittest.main()
