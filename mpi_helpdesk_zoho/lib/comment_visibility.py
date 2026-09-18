# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

"""Public Comment ↔ customer message; Internal Note ↔ private thread."""


def desk_thread_to_odoo(*, is_public):
    return "public" if is_public else "internal"


def odoo_message_to_desk(*, visibility):
    return visibility == "public"
