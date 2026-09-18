# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: attachment_policy.decide — Connection direction, cap, and MIME list."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.attachment_policy import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MIME_ALLOW,
    decide_attachment,
)


class TestAttachmentPolicy(unittest.TestCase):
    def test_png_under_cap_both_ways_is_stored(self):
        decision = decide_attachment(
            size_bytes=3 * 1024 * 1024,
            mimetype="image/png",
            travel="desk_to_odoo",
            direction="both",
            max_bytes=DEFAULT_MAX_BYTES,
            mime_allow=DEFAULT_MIME_ALLOW,
        )
        self.assertEqual(decision, "store")

    def test_over_cap_keeps_name_and_url_only(self):
        decision = decide_attachment(
            size_bytes=11 * 1024 * 1024,
            mimetype="image/png",
            travel="desk_to_odoo",
            direction="both",
            max_bytes=DEFAULT_MAX_BYTES,
            mime_allow=DEFAULT_MIME_ALLOW,
        )
        self.assertEqual(decision, "url_only")

    def test_zip_is_rejected(self):
        decision = decide_attachment(
            size_bytes=1024,
            mimetype="application/zip",
            travel="desk_to_odoo",
            direction="both",
            max_bytes=DEFAULT_MAX_BYTES,
            mime_allow=DEFAULT_MIME_ALLOW,
        )
        self.assertEqual(decision, "reject")

    def test_inbound_skipped_when_direction_is_odoo_to_desk(self):
        decision = decide_attachment(
            size_bytes=1024,
            mimetype="image/png",
            travel="desk_to_odoo",
            direction="odoo_to_desk",
            max_bytes=DEFAULT_MAX_BYTES,
            mime_allow=DEFAULT_MIME_ALLOW,
        )
        self.assertEqual(decision, "skip")

    def test_outbound_skipped_when_direction_is_desk_to_odoo(self):
        decision = decide_attachment(
            size_bytes=1024,
            mimetype="application/pdf",
            travel="odoo_to_desk",
            direction="desk_to_odoo",
            max_bytes=DEFAULT_MAX_BYTES,
            mime_allow=DEFAULT_MIME_ALLOW,
        )
        self.assertEqual(decision, "skip")


if __name__ == "__main__":
    unittest.main()
