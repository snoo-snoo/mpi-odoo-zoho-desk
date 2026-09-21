# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.
{
    "name": "MPI Helpdesk Zoho Desk Connector",
    "version": "19.0.1.1.2",
    "author": "Michael Plöckinger, MPI GmbH",
    "website": "https://mpi-erp.at",
    "license": "OPL-1",
    "price": 19.90,
    "currency": "EUR",
    "category": "Services/Helpdesk",
    "summary": "Bidirectional Ticket Sync between Odoo Enterprise Helpdesk and Zoho Desk",
    "description": """
MPI Helpdesk Zoho Desk Connector
================================
Keeps Helpdesk Tickets aligned with Zoho Desk. One Connection per company.

    - Bidirectional Ticket Sync (fields, Comments, assignees, mapped custom fields, Attachments)
    - Desk wins Ticket fields; Comments append; visibility is preserved
    - Team Map and Department Map control what crosses
    - Buyer brings a Zoho self-client; webhooks plus a 15-minute catch-up
    - Enterprise Helpdesk required
    """,
    "depends": ["helpdesk", "mail"],
    "external_dependencies": {
        "python": ["requests", "PyJWT"],
    },
    "data": [
        "security/mpi_helpdesk_zoho_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/mpi_zoho_connection_views.xml",
        "views/helpdesk_ticket_views.xml",
        "views/res_config_settings_views.xml",
        "views/mpi_helpdesk_zoho_menus.xml",
    ],
    "images": [
        "static/description/icon.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
