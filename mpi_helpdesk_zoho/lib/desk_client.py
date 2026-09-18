# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Zoho Desk REST API v1 client. Transport is injected (requests or a fake)."""

from .desk_hosts import accounts_root, desk_root


class DeskClientError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class DeskClient:
    def __init__(
        self,
        *,
        org_id,
        dc,
        client_id,
        client_secret,
        refresh_token,
        transport,
        accounts_dc=None,
        ignore_source_id=None,
    ):
        self.org_id = org_id
        self.dc = dc or "com"
        self.accounts_dc = accounts_dc or self.dc
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.transport = transport
        self.ignore_source_id = ignore_source_id
        self._access_token = None

    def _headers(self, token):
        return {
            "Authorization": "Zoho-oauthtoken %s" % token,
            "orgId": str(self.org_id),
        }

    def _request(self, method, url, *, headers=None, json_body=None, params=None, data=None, files=None):
        return self.transport.request(
            method,
            url,
            headers=headers or {},
            json_body=json_body,
            params=params,
            data=data,
            files=files,
        )

    def refresh_access_token(self):
        url = "%s/oauth/v2/token" % accounts_root(self.accounts_dc)
        response = self._request(
            "POST",
            url,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
        )
        if response.get("status_code", 200) >= 400:
            raise DeskClientError("Token refresh failed", response.get("status_code"), response)
        token = response.get("json", {}).get("access_token")
        if not token:
            raise DeskClientError("Token refresh returned no access_token", payload=response)
        self._access_token = token
        return token

    def _authed(self, method, path, **kwargs):
        token = self._access_token or self.refresh_access_token()
        url = "%s/api/v1%s" % (desk_root(self.dc), path)
        headers = self._headers(token)
        extra = kwargs.pop("headers", None)
        if extra:
            headers.update(extra)
        response = self._request(method, url, headers=headers, **kwargs)
        if response.get("status_code") == 401:
            token = self.refresh_access_token()
            headers = self._headers(token)
            if extra:
                headers.update(extra)
            response = self._request(method, url, headers=headers, **kwargs)
        if response.get("status_code", 200) >= 400:
            raise DeskClientError(
                "Desk API %s %s failed" % (method, path),
                response.get("status_code"),
                response,
            )
        return response.get("json") or {}

    def list_tickets(self, **params):
        return self._authed("GET", "/tickets", params=params)

    def get_ticket(self, ticket_id):
        return self._authed("GET", "/tickets/%s" % ticket_id)

    def create_ticket(self, values):
        return self._authed("POST", "/tickets", json_body=values)

    def update_ticket(self, ticket_id, values):
        return self._authed("PATCH", "/tickets/%s" % ticket_id, json_body=values)

    def list_threads(self, ticket_id):
        return self._authed("GET", "/tickets/%s/threads" % ticket_id)

    def add_thread(self, ticket_id, content, *, is_public=True):
        return self._authed(
            "POST",
            "/tickets/%s/threads" % ticket_id,
            json_body={"content": content, "isPublic": is_public, "channel": "API"},
        )

    def list_attachments(self, ticket_id):
        return self._authed("GET", "/tickets/%s/attachments" % ticket_id)

    def add_attachment(self, ticket_id, filename, content, mimetype):
        return self._authed(
            "POST",
            "/tickets/%s/attachments" % ticket_id,
            files={"file": (filename, content, mimetype)},
        )

    def download(self, url):
        token = self._access_token or self.refresh_access_token()
        response = self._request("GET", url, headers=self._headers(token))
        if response.get("status_code") == 401:
            token = self.refresh_access_token()
            response = self._request("GET", url, headers=self._headers(token))
        if response.get("status_code", 200) >= 400:
            raise DeskClientError("Download failed", response.get("status_code"), response)
        return response.get("content") or b""

    def create_webhook(self, *, name, url, department_ids, ignore_source_id):
        subscriptions = {
            "Ticket_Add": {"departmentIds": list(department_ids)} if department_ids else None,
            "Ticket_Update": {"departmentIds": list(department_ids)} if department_ids else None,
            "Ticket_Thread_Add": {"departmentIds": list(department_ids)} if department_ids else None,
            "Ticket_Comment_Add": {"departmentIds": list(department_ids)} if department_ids else None,
        }
        payload = {
            "name": name,
            "url": url,
            "subscriptions": subscriptions,
            "ignoreSourceId": ignore_source_id,
        }
        return self._authed("POST", "/webhooks", json_body=payload)
