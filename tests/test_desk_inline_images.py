# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_inline_images import (
    _inline_image_url_variants,
    desk_inline_image_download_url,
    inline_image_filename,
    is_desk_inline_image_src,
)


class _FakeClient:
    dc = "eu"


class TestDeskInlineImages(unittest.TestCase):
    def test_content_variant_before_query_string(self):
        url = (
            "https://desk.zoho.eu/api/v1/tickets/1/threads/2/inlineImages/token"
            "?et=abc&ha=def&f=1.png"
        )
        variants = _inline_image_url_variants(url)
        self.assertIn(
            "https://desk.zoho.eu/api/v1/tickets/1/threads/2/inlineImages/token/content?et=abc&ha=def&f=1.png",
            variants,
        )
        self.assertNotIn(url + "/content", variants)

    def test_fixes_shorthand_inline_path_with_ticket_id(self):
        src = (
            "/api/v1/threads/63383000025185809/inlineImages/edbsnb5e3c895b2d88"
            "?et=1a14ea8894c&amp;ha=abc&amp;f=1.png"
        )
        url = desk_inline_image_download_url(
            _FakeClient(),
            src,
            desk_ticket_id="63383000025230899",
        )
        self.assertIn("/tickets/63383000025230899/threads/63383000025185809/inlineImages/", url)
        self.assertIn("ha=abc", url)
        self.assertNotIn("&amp;", url)

    def test_inline_image_detection_and_filename(self):
        src = "/api/v1/threads/1/inlineImages/token?f=3.png"
        self.assertTrue(is_desk_inline_image_src(src))
        self.assertEqual(inline_image_filename(src), "desk-inline-3.png")
        self.assertFalse(is_desk_inline_image_src("https://example.com/logo.png"))


if __name__ == "__main__":
    unittest.main()
