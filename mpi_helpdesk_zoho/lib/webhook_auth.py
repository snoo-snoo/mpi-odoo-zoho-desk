# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Unsigned GET handshake; JWT on event POST."""

from collections import namedtuple

WebhookAuth = namedtuple("WebhookAuth", "ok handshake reason")


def parse_bearer(authorization):
    if not authorization:
        return None
    prefix = "Bearer "
    if authorization.startswith(prefix):
        token = authorization[len(prefix) :].strip()
        return token or None
    return authorization.strip() or None


def authenticate_webhook(*, method, authorization, verify_jwt):
    if method == "GET":
        return WebhookAuth(ok=True, handshake=True, reason=None)
    token = parse_bearer(authorization)
    if not token:
        return WebhookAuth(ok=False, handshake=False, reason="missing_jwt")
    if not verify_jwt(token):
        return WebhookAuth(ok=False, handshake=False, reason="invalid_jwt")
    return WebhookAuth(ok=True, handshake=False, reason=None)
