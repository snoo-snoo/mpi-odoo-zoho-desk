# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

from unittest.mock import MagicMock, patch

from odoo.addons.mpi_helpdesk_zoho.lib.echo import payload_hash
from odoo.addons.mpi_helpdesk_zoho.lib import sync_pull
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSyncPullPacing(TransactionCase):
    def _connection(self):
        return self.env["mpi.zoho.desk.connection"].create(
            {
                "name": "Desk EU",
                "desk_org_id": "1",
                "company_id": self.env.company.id,
                "client_id": "c",
                "client_secret": "s",
                "refresh_token": "r",
                "state": "verified",
            }
        )

    def test_pull_skips_without_department_map(self):
        connection = self._connection()
        client = MagicMock()
        with patch.object(type(connection), "_make_client", return_value=client), patch.object(
            type(connection), "_notify_pull_skipped_no_department_map"
        ) as notify:
            self.env["mpi.zoho.desk.sync"]._pull_connection(connection, backfill=False)
        client.list_tickets.assert_not_called()
        notify.assert_called_once()

    def test_pull_passes_department_ids(self):
        connection = self._connection()
        self.env["mpi.zoho.desk.department.map"].create(
            {
                "connection_id": connection.id,
                "desk_department_id": "D1",
                "desk_department_name": "Support",
            }
        )
        client = MagicMock()
        client.list_tickets.return_value = {"data": []}
        with patch.object(type(connection), "_make_client", return_value=client):
            self.env["mpi.zoho.desk.sync"]._pull_connection(connection, backfill=False)
        kwargs = client.list_tickets.call_args.kwargs
        self.assertEqual(kwargs.get("departmentIds"), "D1")

    def test_partner_cache_reuses_record(self):
        connection = self._connection()
        sync = self.env["mpi.zoho.desk.sync"]
        cache = {}
        detail = {
            "contact": {"email": "same@example.com", "lastName": "Same"},
            "account": {},
        }
        first = sync._partner_for_desk(connection, detail, partner_cache=cache)
        second = sync._partner_for_desk(connection, detail, partner_cache=cache)
        self.assertEqual(first, second)
        self.assertEqual(len(cache), 1)

    def test_mapping_needs_side_content_when_threads_missing(self):
        connection = self._connection()
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Desk thread gap", "company_id": self.env.company.id}
        )
        ticket_map = self.env["mpi.zoho.desk.ticket.map"].create(
            {
                "connection_id": connection.id,
                "helpdesk_ticket_id": ticket.id,
                "desk_ticket_id": "63383000025185805",
            }
        )
        self.env["mpi.zoho.desk.comment.map"].create(
            {
                "ticket_map_id": ticket_map.id,
                "desk_thread_id": "1",
                "mail_message_id": self.env["mail.message"].create(
                    {"body": "only one", "model": "helpdesk.ticket", "res_id": ticket.id}
                ).id,
            }
        )
        sync = self.env["mpi.zoho.desk.sync"]
        self.assertFalse(
            sync._mapping_needs_side_content(ticket_map, threads=[{"id": "1"}])
        )
        self.assertTrue(
            sync._mapping_needs_side_content(
                ticket_map, threads=[{"id": "1"}, {"id": "2"}]
            )
        )

    def _department(self, connection):
        self.env["mpi.zoho.desk.department.map"].create(
            {
                "connection_id": connection.id,
                "desk_department_id": "D1",
                "desk_department_name": "Support",
            }
        )

    def test_unchanged_ticket_skips_desk_reads(self):
        connection = self._connection()
        self._department(connection)
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Already imported", "company_id": self.env.company.id}
        )
        row = {"id": "T-1", "departmentId": "D1", "subject": "Already imported"}
        ticket_map = self.env["mpi.zoho.desk.ticket.map"].create(
            {
                "connection_id": connection.id,
                "helpdesk_ticket_id": ticket.id,
                "desk_ticket_id": "T-1",
                "last_origin": "desk",
                "last_payload_hash": payload_hash(row),
            }
        )
        self.env["mpi.zoho.desk.comment.map"].create(
            {
                "ticket_map_id": ticket_map.id,
                "desk_thread_id": "thread-1",
                "mail_message_id": self.env["mail.message"].create(
                    {"body": "imported", "model": "helpdesk.ticket", "res_id": ticket.id}
                ).id,
            }
        )
        client = MagicMock()
        self.env["mpi.zoho.desk.sync"]._apply_desk_ticket(
            connection, client, row, backfill=False
        )
        client.get_ticket.assert_not_called()
        client.list_threads.assert_not_called()

    def test_backfill_posts_at_most_five_threads_per_run(self):
        connection = self._connection()
        self._department(connection)
        client = MagicMock()
        client.list_tickets.return_value = {
            "data": [{"id": "T-9", "departmentId": "D1", "subject": "Long thread"}]
        }
        client.get_ticket.return_value = {
            "id": "T-9",
            "departmentId": "D1",
            "subject": "Long thread",
            "description": "Full description",
        }
        client.list_threads.return_value = [
            {"id": str(index), "content": "<p>Body %s</p>" % index, "isPublic": True}
            for index in range(6)
        ]
        client.list_ticket_attachments.return_value = []
        with patch.object(type(connection), "_make_client", return_value=client):
            complete = self.env["mpi.zoho.desk.sync"]._pull_connection(connection, backfill=True)
        self.assertFalse(complete)
        ticket_map = self.env["mpi.zoho.desk.ticket.map"].search(
            [("desk_ticket_id", "=", "T-9")]
        )
        comments = self.env["mpi.zoho.desk.comment.map"].search(
            [("ticket_map_id", "=", ticket_map.id)]
        )
        self.assertEqual(len(comments), sync_pull.BACKFILL_THREAD_POST_CAP)
        self.assertFalse(ticket_map.desk_threads_synced)
        client.get_thread.assert_not_called()

    def test_thread_webhook_posts_one_thread(self):
        connection = self._connection()
        self._department(connection)
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "Live", "company_id": self.env.company.id}
        )
        self.env["mpi.zoho.desk.ticket.map"].create(
            {
                "connection_id": connection.id,
                "helpdesk_ticket_id": ticket.id,
                "desk_ticket_id": "T-2",
                "last_origin": "desk",
                "desk_threads_synced": True,
            }
        )
        client = MagicMock()
        with patch.object(type(connection), "_make_client", return_value=client):
            self.env["mpi.zoho.desk.sync"]._apply_webhook_event(
                connection,
                {
                    "eventType": "Ticket_Thread_Add",
                    "payload": {
                        "id": "thread-new",
                        "ticketId": "T-2",
                        "content": "<p>Neue Antwort</p>",
                        "isPublic": True,
                    },
                },
            )
        client.list_threads.assert_not_called()
        client.get_ticket.assert_not_called()
        client.get_thread.assert_not_called()
        comment = self.env["mpi.zoho.desk.comment.map"].search(
            [("desk_thread_id", "=", "thread-new")]
        )
        self.assertEqual(len(comment), 1)
        self.assertIn("Neue Antwort", comment.mail_message_id.body)

    def test_commit_batch_size_cron_backfill(self):
        self.assertEqual(
            sync_pull.commit_batch_size(backfill=True, cron_id=78),
            sync_pull.COMMIT_EVERY_CRON_BACKFILL,
        )
        self.assertEqual(
            sync_pull.commit_batch_size(backfill=False, cron_id=78),
            sync_pull.COMMIT_EVERY,
        )
