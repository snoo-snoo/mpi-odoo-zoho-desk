# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Verify Zoho Desk webhook JWT against the DC JWKS."""

from .desk_hosts import desk_root


def jwks_url(dc):
    return "%s/.well-known/jwks.json" % desk_root(dc)


def verify_zoho_jwt(token, *, jwks=None, fetch_jwks=None, dc="com"):
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
                return jwt.decode(token, key=jwt.algorithms.RSAAlgorithm.from_jwk(key), algorithms=["RS256"])
            except Exception as exc:  # noqa: BLE001 — try the next JWKS key
                last_error = exc
        if last_error:
            raise last_error
        raise ValueError("JWKS contained no usable keys")

    url = jwks_url(dc)
    if fetch_jwks:
        data = fetch_jwks(url)
        return verify_zoho_jwt(token, jwks=data, dc=dc)
    client = PyJWKClient(url)
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(token, signing_key.key, algorithms=["RS256"])
