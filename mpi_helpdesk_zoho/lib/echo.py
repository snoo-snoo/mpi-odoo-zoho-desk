# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Origin stamp plus unchanged-hash echo suppression."""

import hashlib
import json


def payload_hash(payload):
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def should_apply(*, origin, incoming_hash, stored_hash):
    if origin == "connector":
        return False
    if incoming_hash and stored_hash and incoming_hash == stored_hash:
        return False
    return True
