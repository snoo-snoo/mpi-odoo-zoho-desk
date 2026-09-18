# Desk webhooks via API, JWT on events, paste-URL fallback

After OAuth the module creates the Desk webhook (Department Map filters, `ignoreSourceId`). Event POSTs must verify Zoho JWT; the subscription GET may be unsigned and must return 200. If API create fails (missing `Desk.webhooks.CREATE`), the admin pastes the Connection URL in the Desk UI. Paste-only was rejected: maps and ignore-source would live outside Odoo.
