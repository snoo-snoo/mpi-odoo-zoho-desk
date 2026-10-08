# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_oauth import desk_oauth_is_rate_limited


class TestDeskOAuth(unittest.TestCase):
    def test_rate_limit_message(self):
        self.assertTrue(
            desk_oauth_is_rate_limited(
                "You have made too many requests continuously. Please try again after some time."
            )
        )
        self.assertFalse(desk_oauth_is_rate_limited("invalid_client"))


if __name__ == "__main__":
    unittest.main()
