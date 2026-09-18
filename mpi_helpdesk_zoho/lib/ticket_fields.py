# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Desk wins Ticket fields when both sides wrote."""


def apply_desk_wins(*, odoo_fields, desk_fields):
    merged = dict(odoo_fields)
    for key, value in desk_fields.items():
        if value is not None:
            merged[key] = value
    return merged
