# Webhooks plus cron catch-up

Desk → Odoo uses Zoho webhooks with a cron catch-up. Poll-only is too slow for bidirectional Ticket Sync; webhooks-only miss events. Databases Zoho cannot reach fall back to cron; that limit belongs in the Apps description.
