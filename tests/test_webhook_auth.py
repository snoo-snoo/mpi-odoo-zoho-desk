# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: webhook_auth.authenticate — unsigned GET handshake, JWT on POST."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.webhook_auth import authenticate_webhook


class TestWebhookAuth(unittest.TestCase):
    def test_get_handshake_is_allowed_without_jwt(self):
        result = authenticate_webhook(method="GET", authorization=None, verify_jwt=lambda token: False)
        self.assertTrue(result.ok)
        self.assertTrue(result.handshake)

    def test_post_without_jwt_is_rejected(self):
        result = authenticate_webhook(method="POST", authorization=None, verify_jwt=lambda token: True)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "missing_jwt")

    def test_post_with_invalid_jwt_is_rejected(self):
        result = authenticate_webhook(
            method="POST",
            authorization="Bearer bad",
            verify_jwt=lambda token: False,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "invalid_jwt")

    def test_post_with_valid_jwt_is_allowed(self):
        result = authenticate_webhook(
            method="POST",
            authorization="Bearer good",
            verify_jwt=lambda token: token == "good",
        )
        self.assertTrue(result.ok)
        self.assertFalse(result.handshake)


if __name__ == "__main__":
    unittest.main()
