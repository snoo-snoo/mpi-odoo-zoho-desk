# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_threads import (
    desk_description_looks_corrupted,
    postprocess_desk_plaintext,
    sort_threads_for_chatter,
    thread_body,
    trim_desk_html_before_signature,
)


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

    def test_trim_html_keeps_body_images_drops_signature(self):
        html = (
            '<p>Hallo, Darf man wirklich ein KGT installieren ?</p>'
            '<img src="/api/v1/threads/633/inlineImages/contentphoto'
            '?et=1a14e75f812&amp;f=1.png"/>'
            "<p>Meilleures salutations,</p>"
            '<img src="/api/v1/threads/633/inlineImages/signaturelogo?f=2.png"/>'
            "<p>Noé Laurent</p>"
        )
        trimmed = trim_desk_html_before_signature(html)
        self.assertIn("contentphoto", trimmed)
        self.assertNotIn("Meilleures salutations", trimmed)
        self.assertNotIn("signaturelogo", trimmed)

    def test_postprocess_strips_tokens_and_signature(self):
        raw = (
            "Hallo, Darf man wirklich ein KGT auf 4 x Einzelfundament installieren ? "
            "edbsnd7726d471e71407357237fb7dce282a2ddf83642d0e22d76bee75d2040ccb4"
            "?et=1a14e75f812&ha=00f00bcf2665a17e79a766164dc781fcd3c730a399119bfc0d804b2760a1ff89&f=1 "
            "[5] Meilleures salutations, Mit freundlichen Grüßen, * Noé Laurent "
            "None [1] www.okofen.fr\n[1] http://www.okofen.fr/"
        )
        plain = postprocess_desk_plaintext(raw)
        self.assertIn("KGT auf 4 x Einzelfundament", plain)
        self.assertNotIn("edbsnd7726", plain)
        self.assertNotIn("Meilleures salutations", plain)
        self.assertNotIn("okofen.fr", plain)
        self.assertTrue(desk_description_looks_corrupted(raw))
        self.assertFalse(desk_description_looks_corrupted(plain))

    def test_sort_threads_oldest_first_for_chatter(self):
        threads = [
            {"id": "2", "sendDateTime": "2026-01-02T10:00:00.000Z", "content": "newer"},
            {"id": "1", "sendDateTime": "2026-01-01T10:00:00.000Z", "content": "older"},
        ]
        ordered = sort_threads_for_chatter(threads)
        self.assertEqual([row["id"] for row in ordered], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
