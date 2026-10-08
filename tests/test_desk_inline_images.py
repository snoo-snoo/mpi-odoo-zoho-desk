# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_inline_images import (
    desk_api_absolute_url,
    inline_image_filename,
    is_desk_inline_image_src,
)


class _FakeClient:
    dc = "eu"


class TestDeskInlineImages(unittest.TestCase):
    def test_absolute_api_url(self):
        url = desk_api_absolute_url(
            _FakeClient(),
            "/api/v1/threads/1/inlineImages/abc?f=1.png",
        )
        self.assertEqual(
            url,
            "https://desk.zoho.eu/api/v1/threads/1/inlineImages/abc?f=1.png",
        )

    def test_inline_image_detection_and_filename(self):
        src = "/api/v1/threads/1/inlineImages/token?f=3.png"
        self.assertTrue(is_desk_inline_image_src(src))
        self.assertEqual(inline_image_filename(src), "desk-inline-3.png")
        self.assertFalse(is_desk_inline_image_src("https://example.com/logo.png"))


if __name__ == "__main__":
    unittest.main()
