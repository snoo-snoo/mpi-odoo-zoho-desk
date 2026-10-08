# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Unsigned GET handshake; JWT on event POST (X-ZDesk-JWT)."""

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


def desk_webhook_jwt_token(*, authorization=None, x_zdesk_jwt=None):
    """Desk sends JWT in X-ZDesk-JWT; Bearer is a fallback for tests."""
    return parse_bearer(x_zdesk_jwt) or parse_bearer(authorization)


def authenticate_webhook(
    *,
    method,
    authorization=None,
    x_zdesk_jwt=None,
    validation_post=False,
    verify_jwt,
):
    if method == "GET":
        return WebhookAuth(ok=True, handshake=True, reason=None)
    token = desk_webhook_jwt_token(authorization=authorization, x_zdesk_jwt=x_zdesk_jwt)
    if not token:
        if validation_post:
            return WebhookAuth(ok=True, handshake=True, reason="validation_post")
        return WebhookAuth(ok=False, handshake=False, reason="missing_jwt")
    if not verify_jwt(token):
        return WebhookAuth(ok=False, handshake=False, reason="invalid_jwt")
    return WebhookAuth(ok=True, handshake=False, reason=None)
