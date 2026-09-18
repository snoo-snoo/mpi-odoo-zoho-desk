# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Source removal closes the other side and never deletes it."""


def other_side_action(*, deleted_side):
    if deleted_side in ("desk", "odoo"):
        return "close"
    return "none"
