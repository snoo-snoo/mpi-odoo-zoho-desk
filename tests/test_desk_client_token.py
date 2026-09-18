# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: DeskClient token exchange and refresh."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_client import DeskClient, DeskClientError


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def _client(transport, refresh_token=""):
    return DeskClient(
        org_id="1",
        dc="eu",
        client_id="cid",
        client_secret="csecret",
        refresh_token=refresh_token,
        transport=transport,
    )


class TestDeskClientToken(unittest.TestCase):
    def test_self_client_code_returns_refresh_token(self):
        transport = FakeTransport(
            [
                {
                    "status_code": 200,
                    "json": {
                        "access_token": "acc",
                        "refresh_token": "1000.refresh",
                    },
                }
            ]
        )
        client = _client(transport)
        refresh = client.exchange_authorization_code("1000.grant")
        self.assertEqual(refresh, "1000.refresh")
        self.assertEqual(client.refresh_token, "1000.refresh")
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://accounts.zoho.eu/oauth/v2/token")
        self.assertEqual(call["data"]["grant_type"], "authorization_code")
        self.assertEqual(call["data"]["code"], "1000.grant")

    def test_self_client_code_error_is_surfaced(self):
        transport = FakeTransport(
            [{"status_code": 200, "json": {"error": "invalid_code"}}]
        )
        client = _client(transport)
        with self.assertRaises(DeskClientError) as ctx:
            client.exchange_authorization_code("expired")
        self.assertIn("invalid_code", str(ctx.exception))

    def test_refresh_error_body_is_surfaced(self):
        transport = FakeTransport(
            [{"status_code": 200, "json": {"error": "invalid_client"}}]
        )
        client = _client(transport, refresh_token="not-a-refresh")
        with self.assertRaises(DeskClientError) as ctx:
            client.refresh_access_token()
        self.assertIn("invalid_client", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
