# Cron catch-up defaults to 15 minutes

Webhooks are the fast path. The Connection’s catch-up cron defaults to every 15 minutes. Five minutes was rejected on large Backfills; hourly was rejected when a webhook is missed. The interval is overridable on the Connection.
