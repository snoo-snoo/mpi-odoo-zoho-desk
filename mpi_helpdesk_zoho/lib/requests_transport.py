# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""requests-based transport for DeskClient."""

from .desk_client import DeskClientError


class RequestsTransport:
    def __init__(self, timeout=30):
        self.timeout = timeout

    def request(self, method, url, *, headers=None, json_body=None, params=None, data=None, files=None):
        import requests

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
                data=data,
                files=files,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise DeskClientError(
                "Desk API %s %s timed out after %ss" % (method, url, self.timeout),
                None,
                None,
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise DeskClientError("Desk API %s %s failed: %s" % (method, url, exc), None, None) from exc
        payload = None
        if response.content:
            try:
                payload = response.json()
            except ValueError:
                payload = {"text": response.text}
        return {
            "status_code": response.status_code,
            "json": payload,
            "content": response.content,
        }
