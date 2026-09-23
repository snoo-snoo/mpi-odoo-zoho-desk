# Pull pacing for large Ticket Sync

Listing tickets without departmentIds and syncing threads/attachments on every catch-up row caused Odoo.sh slow queries after large Backfills. Pulls now filter by mapped Department Maps, commit cron progress in batches of 20, cache Partner matches per run, sync threads/attachments only for new tickets / Backfill / forced webhook events, and defer attachment binaries during Backfill to URL-only.
