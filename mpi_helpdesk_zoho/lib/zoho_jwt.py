# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Verify Zoho Desk webhook JWT against the DC JWKS."""

import logging

from .desk_hosts import desk_root

_logger = logging.getLogger(__name__)


def jwks_url(dc):
    return "%s/.well-known/jwks.json" % desk_root(dc)


def _decode_zoho_jwt(token, *, key, org_id=None, webhook_id=None):
    import jwt

    issuer = ("orgId:%s" % str(org_id).strip()) if org_id else None
    audience = ("webhookId:%s" % str(webhook_id).strip()) if webhook_id else None
    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_iss": bool(issuer),
        "verify_aud": bool(audience),
    }
    return jwt.decode(
        token,
        key=key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=audience,
        options=options,
    )


def verify_zoho_jwt(
    token,
    *,
    jwks=None,
    fetch_jwks=None,
    dc="com",
    org_id=None,
    webhook_id=None,
):
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as exc:
        raise RuntimeError("PyJWT is required to verify Desk webhook JWT") from exc

    if jwks is not None:
        keys = jwks.get("keys") or []
        last_error = None
        for key in keys:
            try:
                return _decode_zoho_jwt(
                    token,
                    key=jwt.algorithms.RSAAlgorithm.from_jwk(key),
                    org_id=org_id,
                    webhook_id=webhook_id,
                )
            except Exception as exc:  # noqa: BLE001 — try the next JWKS key
                last_error = exc
        if last_error:
            raise last_error
        raise ValueError("JWKS contained no usable keys")

    url = jwks_url(dc)

    def _fetch(url_to_fetch):
        if fetch_jwks:
            return fetch_jwks(url_to_fetch)
        import requests

        response = requests.get(url_to_fetch, timeout=30)
        response.raise_for_status()
        return response.json()

    try:
        client = PyJWKClient(url)
        signing_key = client.get_signing_key_from_jwt(token)
        return _decode_zoho_jwt(
            token,
            key=signing_key.key,
            org_id=org_id,
            webhook_id=webhook_id,
        )
    except Exception as first_error:
        _logger.info("Desk webhook JWT verify retry with fresh JWKS (%s)", first_error)
        data = _fetch(url)
        return verify_zoho_jwt(
            token,
            jwks=data,
            dc=dc,
            org_id=org_id,
            webhook_id=webhook_id,
        )
