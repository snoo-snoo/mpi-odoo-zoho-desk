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
        headers = {
            "Authorization": "Zoho-oauthtoken %s" % token,
        }
        if self.org_id:
            headers["orgId"] = str(self.org_id).strip()
        return headers

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

    def _token_payload(self, response):
        payload = response.get("json") or {}
        if not isinstance(payload, dict):
            payload = {}
        return payload

    def _raise_token_error(self, fallback, response):
        payload = self._token_payload(response)
        zoho_error = payload.get("error_description") or payload.get("error")
        message = "%s: %s" % (fallback, zoho_error) if zoho_error else fallback
        raise DeskClientError(message, response.get("status_code"), response)

    def exchange_authorization_code(self, code):
        url = "%s/oauth/v2/token" % accounts_root(self.accounts_dc)
        response = self._request(
            "POST",
            url,
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
            },
        )
        payload = self._token_payload(response)
        if response.get("status_code", 200) >= 400 or payload.get("error"):
            self._raise_token_error("Self-Client Code exchange failed", response)
        refresh = payload.get("refresh_token")
        if not refresh:
            self._raise_token_error(
                "Self-Client Code exchange returned no refresh_token", response
            )
        self.refresh_token = refresh
        self._access_token = payload.get("access_token")
        return refresh

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
        payload = self._token_payload(response)
        if response.get("status_code", 200) >= 400 or payload.get("error"):
            self._raise_token_error("Token refresh failed", response)
        token = payload.get("access_token")
        if not token:
            self._raise_token_error("Token refresh returned no access_token", response)
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
            self._raise_api_error(method, path, response)
        return response.get("json") or {}

    def _raise_api_error(self, method, path, response):
        payload = self._token_payload(response)
        code = payload.get("errorCode") or payload.get("error") or ""
        detail = payload.get("message") or payload.get("error_description") or ""
        extra = " ".join(part for part in (code, detail) if part)
        message = "Desk API %s %s failed" % (method, path)
        if extra:
            message = "%s: %s" % (message, extra)
        raise DeskClientError(message, response.get("status_code"), response)

    def list_tickets(self, **params):
        return self._authed("GET", "/tickets", params=params)

    def _list_paginated(self, path, **params):
        """Collect all pages from a Desk list endpoint. Yields each row."""
        start = 0
        page_size = int(params.pop("limit", 100) or 100)
        while True:
            page_params = dict(params)
            page_params["limit"] = page_size
            page_params["from"] = start
            page = self._authed("GET", path, params=page_params)
            rows = page.get("data") or []
            for row in rows:
                yield row
            if len(rows) < page_size:
                break
            start += len(rows)

    def list_departments(self, **params):
        return list(self._list_paginated("/departments", **params))

    def list_agents(self, **params):
        return list(self._list_paginated("/agents", **params))

    def list_ticket_tags(self, *, department_id, **params):
        """List tags for one Desk department. Official path is /ticketTags (not /organizationTags)."""
        params = dict(params)
        params["departmentId"] = department_id
        return list(self._list_paginated("/ticketTags", **params))

    def search_ticket_tags(self, *, department_id, search_val="", **params):
        params = dict(params)
        params["departmentId"] = department_id
        if search_val:
            params["searchVal"] = search_val
        return list(self._list_paginated("/tags/search", **params))

    def list_organization_tags(self, **params):
        """Aggregate tags across departments. Skips departments that return FORBIDDEN."""
        department_id = params.pop("department_id", None) or params.pop("departmentId", None)
        if department_id:
            return self._list_tags_for_department(department_id, **params)
        tags = []
        seen = set()
        last_error = None
        for department in self.list_departments():
            desk_id = department.get("id")
            if not desk_id:
                continue
            try:
                rows = self._list_tags_for_department(desk_id, **params)
            except DeskClientError as exc:
                last_error = exc
                if self._is_forbidden(exc):
                    continue
                raise
            for row in rows:
                name = row.get("name") or row.get("tagName") or ""
                key = name or str(row.get("id") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                tags.append(row)
        if not tags and last_error and self._is_forbidden(last_error):
            # Token or agent profile cannot list tags; caller may continue without them.
            return []
        return tags

    def _list_tags_for_department(self, department_id, **params):
        try:
            return self.list_ticket_tags(department_id=department_id, **params)
        except DeskClientError as exc:
            if not self._is_forbidden(exc):
                raise
        try:
            return self.search_ticket_tags(department_id=department_id, **params)
        except DeskClientError as exc:
            if self._is_forbidden(exc):
                return []
            raise

    @staticmethod
    def _is_forbidden(exc):
        if getattr(exc, "status_code", None) == 403:
            return True
        text = str(exc).upper()
        return "FORBIDDEN" in text or "NOT AUTHORIZED" in text

    def list_organization_fields(self, *, module="tickets", **params):
        params = dict(params)
        params.setdefault("module", module)
        return list(self._list_paginated("/organizationFields", **params))

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
