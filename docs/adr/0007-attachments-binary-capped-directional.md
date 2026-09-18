# Attachments are files, capped, direction on the Connection

Attachments sync as real files, not URL-only. Each Connection sets direction (both, Odoo→Desk, or Desk→Odoo), a size cap, and a MIME allow-list. Over the cap, store name + Desk URL on the Helpdesk Ticket. Uncapped both-ways binary was rejected (cron timeouts, filestore, Apps reviews). URL-only was rejected because Attachments are in the product contract.
