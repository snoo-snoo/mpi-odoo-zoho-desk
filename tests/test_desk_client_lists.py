# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Seam: DeskClient list helpers for departments, agents, tags, fields."""

import unittest

from lib_import import ensure_lib_package

ensure_lib_package()

from mpi_helpdesk_zoho.lib.desk_client import DeskClient


class FakeTransport:
    def __init__(self, pages_by_path):
        self.pages_by_path = pages_by_path
        self.calls = []

    def request(self, method, url, *, headers=None, json_body=None, params=None, data=None, files=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params or {},
                "data": data,
            }
        )
        if "/oauth/v2/token" in url:
            return {"status_code": 200, "json": {"access_token": "tok"}, "content": b""}
        path = url.split("/api/v1", 1)[-1].split("?", 1)[0]
        pages = self.pages_by_path.get(path, [])
        start = int((params or {}).get("from") or 0)
        limit = int((params or {}).get("limit") or 100)
        chunk = pages[start : start + limit]
        return {"status_code": 200, "json": {"data": chunk}, "content": b""}


class TestDeskClientLists(unittest.TestCase):
    def _client(self, pages_by_path):
        return DeskClient(
            org_id="1",
            dc="eu",
            client_id="c",
            client_secret="s",
            refresh_token="r",
            transport=FakeTransport(pages_by_path),
        )

    def test_list_departments_paginates(self):
        rows = [{"id": str(i), "name": "D%s" % i} for i in range(3)]
        client = self._client({"/departments": rows})
        client.transport.pages_by_path["/departments"] = rows
        # force page size 2 via limit
        result = client.list_departments(limit=2)
        self.assertEqual([r["id"] for r in result], ["0", "1", "2"])
        desk_calls = [c for c in client.transport.calls if "/departments" in c["url"]]
        self.assertEqual(len(desk_calls), 2)
        self.assertEqual(desk_calls[0]["params"]["from"], 0)
        self.assertEqual(desk_calls[1]["params"]["from"], 2)

    def test_list_agents(self):
        client = self._client(
            {"/agents": [{"id": "A1", "emailId": "a@ex.com", "firstName": "Ann"}]}
        )
        result = client.list_agents()
        self.assertEqual(result[0]["id"], "A1")

    def test_list_organization_tags(self):
        client = self._client({"/organizationTags": [{"name": "vip"}]})
        result = client.list_organization_tags()
        self.assertEqual(result[0]["name"], "vip")

    def test_list_organization_fields_passes_module(self):
        client = self._client(
            {
                "/organizationFields": [
                    {"apiName": "status", "type": "Picklist", "allowedValues": ["Open"]}
                ]
            }
        )
        result = client.list_organization_fields(module="tickets")
        self.assertEqual(result[0]["apiName"], "status")
        field_calls = [c for c in client.transport.calls if "/organizationFields" in c["url"]]
        self.assertEqual(field_calls[0]["params"]["module"], "tickets")


if __name__ == "__main__":
    unittest.main()
