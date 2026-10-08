# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from ..lib.attachment_policy import decide_attachment
from ..lib.desk_attachments import (
    desk_attachment_download_url,
    desk_attachment_id,
    desk_attachment_mimetype,
)
from ..lib.comment_visibility import desk_thread_to_odoo, odoo_message_to_desk
from ..lib.desk_client import DeskClientError
from ..lib.desk_contact import desk_contact_identity, partner_display_name
from ..lib.desk_inline_images import embed_desk_inline_images
from ..lib.desk_threads import (
    desk_description_looks_corrupted,
    is_truncated_desk_summary,
    sort_threads_for_chatter,
    thread_body,
    trim_desk_html_before_signature,
)
from ..lib.echo import payload_hash, should_apply
from ..lib.partner_match import resolve_partner
from ..lib.priority import desk_to_helpdesk, helpdesk_to_desk
from ..lib.source_removal import other_side_action
from ..lib.sync_pull import (
    CATCHUP_TICKET_CAP,
    PAGE_SIZE,
    commit_batch_size,
    defer_attachment_binaries,
    list_ticket_params,
    partner_cache_key,
    should_sync_side_content,
)

from psycopg2 import IntegrityError, InterfaceError, OperationalError
from ..lib.sync_scope import allows_inbound
from ..lib.ticket_fields import apply_desk_wins

_logger = logging.getLogger(__name__)


class MpiZohoSync(models.AbstractModel):
    _name = "mpi.zoho.desk.sync"
    _description = "Ticket Sync"

    def _cron_keep_going(self, done=1, remaining=None):
        if not self.env.context.get("cron_id"):
            return True
        if getattr(self.env.cr, "closed", False):
            return False
        cron = self.env["ir.cron"]
        if not hasattr(cron, "_commit_progress"):
            return True
        kwargs = {}
        if remaining is not None:
            kwargs["remaining"] = remaining
        try:
            return bool(cron._commit_progress(done, **kwargs))
        except InterfaceError:
            return False

    def _is_fatal_db_error(self, exc):
        if isinstance(exc, (InterfaceError, OperationalError)):
            return True
        if getattr(self.env.cr, "closed", False):
            return True
        return getattr(exc, "pgcode", None) == "57014"

    def _desk_ticket_mapping(self, connection, desk_id, desk_map_cache=None):
        if desk_map_cache is not None:
            cached = desk_map_cache.get(desk_id)
            if cached is not None and cached:
                return cached
        mapping = self.env["mpi.zoho.desk.ticket.map"].search(
            [("connection_id", "=", connection.id), ("desk_ticket_id", "=", desk_id)],
            limit=1,
        )
        if desk_map_cache is not None and mapping:
            desk_map_cache[desk_id] = mapping
        return mapping

    def _claim_desk_ticket_mapping(self, connection, desk_id, desk_map_cache=None):
        mapping = self._desk_ticket_mapping(connection, desk_id, desk_map_cache)
        if mapping:
            return mapping
        TicketMap = self.env["mpi.zoho.desk.ticket.map"]
        vals = {
            "connection_id": connection.id,
            "desk_ticket_id": desk_id,
        }
        try:
            with self.env.cr.savepoint():
                mapping = TicketMap.create(vals)
        except IntegrityError:
            mapping = self._desk_ticket_mapping(connection, desk_id, desk_map_cache)
            if not mapping:
                raise
        if desk_map_cache is not None:
            desk_map_cache[desk_id] = mapping
        return mapping

    def _link_helpdesk_ticket_to_mapping(self, mapping, ticket):
        if mapping.helpdesk_ticket_id:
            return mapping.helpdesk_ticket_id
        try:
            with self.env.cr.savepoint():
                mapping.helpdesk_ticket_id = ticket
        except IntegrityError:
            existing = self.env["mpi.zoho.desk.ticket.map"].search(
                [("helpdesk_ticket_id", "=", ticket.id)],
                limit=1,
            )
            if existing and existing != mapping:
                _logger.warning(
                    "Helpdesk ticket %s is already mapped to Desk ticket %s; "
                    "keeping Desk ticket %s on this row.",
                    ticket.id,
                    existing.desk_ticket_id,
                    mapping.desk_ticket_id,
                )
                return existing.helpdesk_ticket_id
            mapping = self._desk_ticket_mapping(
                mapping.connection_id, mapping.desk_ticket_id
            )
        return mapping.helpdesk_ticket_id or ticket

    @api.private
    def _pull_connection(self, connection, *, backfill):
        client = connection._make_client()
        cutoff = None
        if backfill and connection.backfill_mode == "lookback":
            cutoff = fields.Datetime.now() - timedelta(days=connection.backfill_lookback_days or 90)
        department_ids = sorted(connection._mapped_department_ids())
        if not department_ids:
            connection._notify_pull_skipped_no_department_map()
            return True
        partner_cache = {}
        desk_map_cache = {}
        start = 1
        page_size = PAGE_SIZE
        batch = 0
        commit_every = commit_batch_size(
            backfill=backfill, cron_id=self.env.context.get("cron_id")
        )
        stopped_early = False
        while True:
            params = list_ticket_params(
                start=start,
                page_size=page_size,
                department_ids=department_ids,
            )
            page = client.list_tickets(**params)
            tickets = page.get("data") or []
            if not tickets:
                break
            for row in tickets:
                if cutoff and row.get("closedTime") and self._parse_desk_dt(row.get("closedTime")) < cutoff:
                    continue
                try:
                    self._apply_desk_ticket(
                        connection,
                        client,
                        row,
                        backfill=backfill,
                        partner_cache=partner_cache,
                        desk_map_cache=desk_map_cache,
                    )
                except Exception as exc:
                    if self._is_fatal_db_error(exc) or self._sync_abort_pull(exc):
                        _logger.exception(
                            "Ticket Sync aborted for Desk ticket %s", row.get("id")
                        )
                        raise
                    _logger.exception("Ticket Sync failed for Desk ticket %s", row.get("id"))
                batch += 1
                if batch >= commit_every:
                    if not self._cron_keep_going(batch):
                        stopped_early = True
                        break
                    batch = 0
            if stopped_early:
                break
            if len(tickets) < page_size:
                break
            start += len(tickets)
            if not backfill and start > CATCHUP_TICKET_CAP:
                break
        if batch and not stopped_early:
            if not self._cron_keep_going(batch):
                stopped_early = True
        return not stopped_early

    @staticmethod
    def _sync_abort_pull(exc):
        """Stop the pull when PostgreSQL canceled the statement or closed the cursor."""
        if getattr(exc, "pgcode", None) == "57014":
            return True
        message = str(exc).lower()
        return "cursor already closed" in message or "connection already closed" in message

    def _parse_desk_dt(self, value):
        if not value:
            return fields.Datetime.now()
        try:
            return fields.Datetime.to_datetime(value.replace("Z", ""))
        except Exception:
            return fields.Datetime.now()

    def _apply_desk_ticket(
        self,
        connection,
        client,
        row,
        *,
        backfill=False,
        force_side_content=False,
        force_apply=False,
        partner_cache=None,
        desk_map_cache=None,
    ):
        department_id = str(row.get("departmentId") or row.get("department", {}).get("id") or "")
        if not allows_inbound(
            department_id=department_id,
            mapped_department_ids=connection._mapped_department_ids(),
        ):
            return
        desk_id = str(row.get("id"))
        incoming_hash = payload_hash(row)
        mapping = self._desk_ticket_mapping(connection, desk_id, desk_map_cache)
        apply_ticket_fields = True
        if mapping and not force_apply:
            origin = mapping.last_origin or "desk"
            if not should_apply(
                origin=origin,
                incoming_hash=incoming_hash,
                stored_hash=mapping.last_payload_hash,
            ):
                apply_ticket_fields = False
                if origin == "connector":
                    mapping.last_origin = "desk"
        else:
            mapping = self._claim_desk_ticket_mapping(connection, desk_id, desk_map_cache)
        detail = client.get_ticket(desk_id)
        threads = sort_threads_for_chatter(client.list_threads(desk_id))
        description_html = self._desk_ticket_description_html(client, desk_id, detail, threads)
        ticket = mapping.helpdesk_ticket_id or False
        is_new = not ticket
        if not ticket:
            ticket = self._create_helpdesk_ticket(
                connection,
                detail,
                partner_cache=partner_cache,
            )
            ticket = self._link_helpdesk_ticket_to_mapping(mapping, ticket)
            is_new = True
        description = self._finalize_ticket_description(client, ticket, description_html)
        if apply_ticket_fields:
            values = self._desk_to_helpdesk_values(
                connection, detail, description_text=description
            )
            ticket.with_context(mpi_zoho_skip_outbox=True).write(values)
            mapping.write(
                {"last_payload_hash": incoming_hash, "last_origin": "desk", "source_removed": False}
            )
        elif description and self._description_needs_refresh(ticket.description, description):
            ticket.with_context(mpi_zoho_skip_outbox=True).write({"description": description})
        sync_side_content = (
            should_sync_side_content(
                is_new=is_new,
                backfill=backfill,
                force_side_content=force_side_content,
            )
            or self._mapping_needs_side_content(mapping)
        )
        if sync_side_content:
            defer = defer_attachment_binaries(backfill=backfill)
            self._sync_threads_in(
                connection,
                client,
                mapping,
                desk_id,
                threads=threads,
                defer_binaries=False,
            )
            self._sync_attachments_in(
                connection,
                client,
                mapping,
                desk_id,
                detail,
                defer_binaries=defer,
            )

    def resync_desk_ticket(self, connection, desk_ticket_id):
        """Pull one Desk ticket now (fields, description, threads, attachments)."""
        connection = connection.sudo()
        desk_id = str(desk_ticket_id or "").strip()
        if not desk_id:
            return False
        client = connection._make_client()
        try:
            detail = client.get_ticket(desk_id)
        except DeskClientError as exc:
            raise UserError(_("Could not load Desk ticket %s: %s") % (desk_id, exc)) from exc
        department_id = str(
            detail.get("departmentId") or detail.get("department", {}).get("id") or ""
        )
        if not allows_inbound(
            department_id=department_id,
            mapped_department_ids=connection._mapped_department_ids(),
        ):
            raise UserError(
                _(
                    "This ticket's Desk department is not mapped for inbound sync. "
                    "Add it on the Connection Department Map."
                )
            )
        self._apply_desk_ticket(
            connection,
            client,
            detail,
            backfill=False,
            force_side_content=True,
            force_apply=True,
        )
        return True

    def _desk_ticket_description_html(self, client, desk_id, detail, threads):
        raw = (detail.get("description") or "").strip()
        if raw and not is_truncated_desk_summary(raw):
            return trim_desk_html_before_signature(raw)
        for thread in sort_threads_for_chatter(threads):
            full = self._resolve_thread(client, desk_id, thread)
            body = thread_body(full)
            if body:
                return trim_desk_html_before_signature(body)
        return False

    def _finalize_ticket_description(self, client, ticket, html):
        trimmed = trim_desk_html_before_signature(html) if html else False
        if not trimmed or not ticket:
            return trimmed or False
        return (
            embed_desk_inline_images(
                self.env,
                client,
                trimmed,
                res_model="helpdesk.ticket",
                res_id=ticket.id,
            )
            or trimmed
        )

    @staticmethod
    def _description_needs_refresh(current, new):
        current = (current or "").strip()
        new = (new or "").strip()
        if not new:
            return False
        if not current:
            return True
        if current.rstrip().endswith("...") or current.rstrip().endswith("…"):
            return True
        if desk_description_looks_corrupted(current):
            return True
        return len(new) > len(current) + 40

    def _mapping_needs_side_content(self, mapping):
        if not mapping or not mapping.helpdesk_ticket_id:
            return False
        return (
            self.env["mpi.zoho.desk.comment.map"].search_count(
                [("ticket_map_id", "=", mapping.id)], limit=1
            )
            == 0
        )

    def _resolve_thread(self, client, desk_id, thread):
        thread_id = thread.get("id")
        if not thread_id:
            return thread
        try:
            return client.get_thread(desk_id, thread_id)
        except DeskClientError:
            _logger.warning("Could not load Desk thread %s on ticket %s", thread_id, desk_id)
            return thread

    def _create_helpdesk_ticket(
        self, connection, detail, partner_cache=None, *, description_text=False
    ):
        partner = self._partner_for_desk(connection, detail, partner_cache=partner_cache)
        stage = self._stage_for_desk_status(connection, detail.get("status"))
        department_id = str(detail.get("departmentId") or detail.get("department", {}).get("id") or "")
        team = self._inbound_team_for_department(connection, department_id)
        return self.env["helpdesk.ticket"].with_context(mpi_zoho_skip_outbox=True).create(
            {
                "name": detail.get("subject") or "Desk ticket",
                "description": description_text or False,
                "company_id": connection.company_id.id,
                "partner_id": partner.id if partner else False,
                "stage_id": stage.id if stage else False,
                "team_id": team.id if team else False,
                "priority": desk_to_helpdesk(detail.get("priority")) or "1",
            }
        )

    def _inbound_team_for_department(self, connection, department_id):
        if department_id:
            mapped = connection.department_map_ids.filtered(
                lambda row: row.desk_department_id == department_id and row.team_id
            )[:1]
            if mapped.team_id:
                return mapped.team_id
        return connection.inbound_team_id

    def _desk_to_helpdesk_values(self, connection, detail, *, description_text=False):
        odoo_fields = {}
        desk_fields = {
            "name": detail.get("subject"),
            "description": description_text,
        }
        priority = desk_to_helpdesk(detail.get("priority"))
        if priority:
            desk_fields["priority"] = priority
        stage = self._stage_for_desk_status(connection, detail.get("status"))
        if stage:
            desk_fields["stage_id"] = stage.id
        user = self._user_for_desk_agent(connection, detail)
        if user:
            desk_fields["user_id"] = user.id
        tags = self._tags_for_desk(connection, detail)
        if tags is not None:
            desk_fields["tag_ids"] = [(6, 0, tags.ids)]
        for field_map in connection.field_map_ids:
            custom = (detail.get("cf") or {}) | (detail.get("customFields") or {})
            if field_map.desk_field in custom and field_map.helpdesk_field:
                desk_fields[field_map.helpdesk_field] = custom[field_map.desk_field]
        return apply_desk_wins(odoo_fields=odoo_fields, desk_fields=desk_fields)

    def _stage_for_desk_status(self, connection, status):
        if not status:
            return self.env["helpdesk.stage"]
        return connection.status_map_ids.filtered(lambda row: row.desk_status == status)[:1].stage_id

    def _user_for_desk_agent(self, connection, detail):
        assignee = detail.get("assignee") or {}
        email = (assignee.get("email") or "").strip()
        agent_id = str(assignee.get("id") or "")
        mapped = connection.agent_map_ids.filtered(
            lambda row: (agent_id and row.desk_agent_id == agent_id)
            or (email and (row.desk_agent_email or "").lower() == email.lower())
        )[:1]
        if mapped.user_id:
            return mapped.user_id
        if email:
            user = self.env["res.users"].search(
                ["|", ("login", "=ilike", email), ("partner_id.email", "=ilike", email)],
                limit=1,
            )
            return user
        return self.env["res.users"]

    def _tags_for_desk(self, connection, detail):
        names = detail.get("tags") or []
        if not names or not connection.tag_map_ids:
            return None
        ids = []
        for name in names:
            mapped = connection.tag_map_ids.filtered(lambda row: row.desk_tag == name)[:1]
            if mapped.tag_id:
                ids.append(mapped.tag_id.id)
        return self.env["helpdesk.tag"].browse(ids)

    def _partner_for_desk(self, connection, detail, partner_cache=None):
        identity = desk_contact_identity(detail)
        email = identity.get("email")
        name = identity.get("name")
        vat = identity.get("vat")
        cache_key = partner_cache_key(
            email=email,
            vat=vat,
            name=name,
            contact_id=identity.get("contact_id"),
            account_id=identity.get("account_id"),
        )
        if partner_cache is not None and cache_key is not None and cache_key in partner_cache:
            return partner_cache[cache_key]

        partner = None
        if email or vat or name:
            domain = [("company_id", "in", [False, connection.company_id.id])]
            if email:
                domain = ["&"] + domain + [("email", "=ilike", email)]
            elif vat:
                domain = ["&"] + domain + [("vat", "=", vat)]
            else:
                domain = ["&"] + domain + [("name", "=ilike", name)]
            existing = self.env["res.partner"].search_read(
                domain, ["email", "vat", "name"], limit=20
            )
            kind = identity.get("kind") or ("contact" if email else "account")
            decision, partner_id = resolve_partner(
                kind=kind, email=email, vat=vat, name=name, existing=existing
            )
            if decision == "link" and partner_id:
                partner = self.env["res.partner"].browse(partner_id)

        if not partner:
            partner = self.env["res.partner"].create(
                {
                    "name": partner_display_name(
                        name=name, email=email, contact_id=identity.get("contact_id")
                    ),
                    "email": email or False,
                    "vat": vat or False,
                    "is_company": bool(identity.get("is_company")),
                    "company_id": connection.company_id.id,
                }
            )
        if partner_cache is not None and cache_key is not None:
            partner_cache[cache_key] = partner
        return partner

    def _sync_threads_in(
        self, connection, client, mapping, desk_id, *, threads=None, defer_binaries=False
    ):
        threads = threads if threads is not None else client.list_threads(desk_id)
        threads = sort_threads_for_chatter(threads)
        thread_ids = [str(thread.get("id") or "") for thread in threads if thread.get("id")]
        known = set(
            self.env["mpi.zoho.desk.comment.map"]
            .search(
                [
                    ("ticket_map_id", "=", mapping.id),
                    ("desk_thread_id", "in", thread_ids),
                ]
            )
            .mapped("desk_thread_id")
        ) if thread_ids else set()
        for thread in threads:
            thread_id = str(thread.get("id") or "")
            if not thread_id:
                continue
            thread = self._resolve_thread(client, desk_id, thread)
            att_rows = thread.get("attachments") or []
            if thread_id in known:
                self._sync_attachments_on_known_thread(
                    connection,
                    client,
                    mapping,
                    desk_id,
                    thread_id,
                    att_rows,
                    defer_binaries=defer_binaries,
                )
                continue
            visibility = desk_thread_to_odoo(is_public=bool(thread.get("isPublic", thread.get("ispublic"))))
            subtype = "mail.mt_comment" if visibility == "public" else "mail.mt_note"
            attachment_ids = self._desk_attachment_ids_for_message(
                connection,
                client,
                mapping,
                att_rows,
                defer_binaries=defer_binaries,
                desk_ticket_id=desk_id,
                desk_thread_id=thread_id,
            )
            raw_time = thread.get("sendDateTime") or thread.get("createdTime")
            message = mapping.helpdesk_ticket_id.with_context(mpi_zoho_skip_outbox=True).message_post(
                body=thread_body(thread) or "",
                subtype_xmlid=subtype,
                message_type="comment",
                attachment_ids=attachment_ids or False,
                date=fields.Datetime.to_string(self._parse_desk_dt(raw_time)),
            )
            self.env["mpi.zoho.desk.comment.map"].create(
                {
                    "ticket_map_id": mapping.id,
                    "desk_thread_id": thread_id,
                    "mail_message_id": message.id,
                }
            )

    def _sync_attachments_on_known_thread(
        self,
        connection,
        client,
        mapping,
        desk_id,
        thread_id,
        att_rows,
        *,
        defer_binaries=False,
    ):
        if not att_rows:
            return
        comment_map = self.env["mpi.zoho.desk.comment.map"].search(
            [("ticket_map_id", "=", mapping.id), ("desk_thread_id", "=", thread_id)],
            limit=1,
        )
        if not comment_map.mail_message_id:
            return
        attachment_ids = self._desk_attachment_ids_for_message(
            connection,
            client,
            mapping,
            att_rows,
            defer_binaries=defer_binaries,
            desk_ticket_id=desk_id,
            desk_thread_id=thread_id,
            mail_message=comment_map.mail_message_id,
        )
        if attachment_ids:
            message = comment_map.mail_message_id
            existing = set(message.attachment_ids.ids)
            link = [(4, att_id) for att_id in attachment_ids if att_id not in existing]
            if link:
                message.write({"attachment_ids": link})

    def _desk_attachment_ids_for_message(
        self,
        connection,
        client,
        mapping,
        rows,
        *,
        defer_binaries=False,
        desk_ticket_id=None,
        desk_thread_id=None,
        mail_message=None,
    ):
        attachment_ids = []
        for row in rows:
            attachment = self._ingest_desk_attachment_row(
                connection,
                client,
                mapping,
                row,
                defer_binaries=defer_binaries,
                desk_ticket_id=desk_ticket_id,
                desk_thread_id=desk_thread_id,
                mail_message=mail_message,
            )
            if attachment:
                attachment_ids.append(attachment.id)
        return attachment_ids

    def _ingest_desk_attachment_row(
        self,
        connection,
        client,
        mapping,
        row,
        *,
        defer_binaries=False,
        desk_ticket_id=None,
        desk_thread_id=None,
        mail_message=None,
    ):
        desk_att_id = desk_attachment_id(row)
        if not desk_att_id:
            return self.env["ir.attachment"]
        existing = self.env["mpi.zoho.desk.attachment.map"].search(
            [
                ("ticket_map_id", "=", mapping.id),
                ("desk_attachment_id", "=", desk_att_id),
            ],
            limit=1,
        )
        if existing.attachment_id:
            return existing.attachment_id
        size = int(row.get("size") or 0)
        mimetype = desk_attachment_mimetype(row)
        name = row.get("name") or "desk-file"
        url = desk_attachment_download_url(
            client,
            row,
            desk_ticket_id=desk_ticket_id or mapping.desk_ticket_id,
            desk_thread_id=desk_thread_id,
        )
        decision = decide_attachment(
            size_bytes=size,
            mimetype=mimetype,
            travel="desk_to_odoo",
            direction=connection.attachment_direction,
            max_bytes=connection.attachment_max_bytes or 0,
            mime_allow=connection._mime_allow_set(),
        )
        if defer_binaries and decision == "store":
            decision = "url_only"
        if decision == "reject" and url:
            decision = "url_only"
        if decision in ("skip", "reject"):
            self.env["mpi.zoho.desk.attachment.map"].create(
                {
                    "ticket_map_id": mapping.id,
                    "desk_attachment_id": desk_att_id,
                    "desk_url": url,
                    "stored_as": "reject",
                }
            )
            return self.env["ir.attachment"]
        res_model = "helpdesk.ticket"
        res_id = mapping.helpdesk_ticket_id.id
        if mail_message:
            res_model = "mail.message"
            res_id = mail_message.id
        attachment = self.env["ir.attachment"]
        if decision == "store":
            content = b""
            if url:
                try:
                    content = client.download(url) or b""
                except DeskClientError:
                    _logger.warning("Could not download Desk attachment %s", desk_att_id)
            attachment = self.env["ir.attachment"].create(
                {
                    "name": name,
                    "type": "binary",
                    "raw": content,
                    "res_model": res_model,
                    "res_id": res_id,
                    "mimetype": mimetype,
                }
            )
        elif decision == "url_only":
            attachment = self.env["ir.attachment"].create(
                {
                    "name": name,
                    "type": "url",
                    "url": url or False,
                    "res_model": res_model,
                    "res_id": res_id,
                    "mimetype": mimetype,
                }
            )
        self.env["mpi.zoho.desk.attachment.map"].create(
            {
                "ticket_map_id": mapping.id,
                "desk_attachment_id": desk_att_id,
                "attachment_id": attachment.id if attachment else False,
                "desk_url": url,
                "stored_as": decision,
            }
        )
        return attachment

    def _sync_attachments_in(
        self, connection, client, mapping, desk_id, detail, *, defer_binaries=False
    ):
        attachments = client.list_ticket_attachments(desk_id)
        for row in attachments:
            self._ingest_desk_attachment_row(
                connection,
                client,
                mapping,
                row,
                defer_binaries=defer_binaries,
                desk_ticket_id=desk_id,
            )

    @api.private
    def _flush_outbox(self, connection):
        client = connection._make_client()
        pending = self.env["mpi.zoho.desk.outbox"].search(
            [("connection_id", "=", connection.id), ("state", "=", "pending")],
            order="id",
            limit=200,
        )
        batch = 0
        for row in pending:
            try:
                self._flush_one(connection, client, row)
                row.write({"state": "done", "error": False})
            except DeskClientError as exc:
                row.write({"state": "error", "error": str(exc)})
                _logger.warning("Outbox %s failed: %s", row.id, exc)
            batch += 1
            if batch >= COMMIT_EVERY:
                if not self._cron_keep_going(batch):
                    return
                batch = 0
        if batch:
            self._cron_keep_going(batch)

    def _flush_one(self, connection, client, row):
        ticket = row.helpdesk_ticket_id
        payload = row.payload or {}
        if row.event_type == "create_ticket" and ticket:
            if ticket.mpi_zoho_desk_ticket_id:
                return
            created = client.create_ticket(self._helpdesk_to_desk_values(connection, ticket))
            desk_id = str(created.get("id"))
            self.env["mpi.zoho.desk.ticket.map"].create(
                {
                    "connection_id": connection.id,
                    "helpdesk_ticket_id": ticket.id,
                    "desk_ticket_id": desk_id,
                    "last_origin": "connector",
                    "last_payload_hash": payload_hash(created),
                }
            )
            return
        mapping = self.env["mpi.zoho.desk.ticket.map"].search(
            [("helpdesk_ticket_id", "=", ticket.id if ticket else 0)], limit=1
        )
        desk_id = (mapping.desk_ticket_id if mapping else None) or payload.get("desk_ticket_id")
        if not desk_id:
            return
        if row.event_type == "update_ticket" and ticket:
            client.update_ticket(desk_id, self._helpdesk_to_desk_values(connection, ticket))
            mapping.write({"last_origin": "connector", "last_payload_hash": payload_hash(payload)})
        elif row.event_type == "add_comment":
            is_public = odoo_message_to_desk(visibility=payload.get("visibility") or "internal")
            created = client.add_thread(desk_id, payload.get("body") or "", is_public=is_public)
            if mapping and created.get("id"):
                self.env["mpi.zoho.desk.comment.map"].create(
                    {
                        "ticket_map_id": mapping.id,
                        "desk_thread_id": str(created.get("id")),
                        "mail_message_id": payload.get("message_id") or False,
                    }
                )
            if mapping:
                mapping.last_origin = "connector"
        elif row.event_type == "close_ticket" and other_side_action(deleted_side="odoo") == "close":
            client.update_ticket(desk_id, {"status": "Closed"})
            if mapping:
                mapping.source_removed = True
        elif row.event_type == "add_attachment" and ticket:
            self._push_attachment(connection, client, mapping, ticket, payload)

    def _helpdesk_to_desk_values(self, connection, ticket):
        values = {
            "subject": ticket.name,
            "description": ticket.description or "",
            "priority": helpdesk_to_desk(ticket.priority),
        }
        status = connection.status_map_ids.filtered(lambda row: row.stage_id == ticket.stage_id)[:1]
        if status:
            values["status"] = status.desk_status
        department_id = self._outbound_department_id(connection, ticket)
        if department_id:
            values["departmentId"] = department_id
        assignee_id = self._desk_agent_for_user(connection, ticket.user_id)
        if assignee_id:
            values["assigneeId"] = assignee_id
        tags = self._desk_tags_for_ticket(connection, ticket)
        if tags:
            values["tags"] = tags
        if ticket.partner_id.email:
            values["email"] = ticket.partner_id.email
            values["contact"] = {"email": ticket.partner_id.email, "lastName": ticket.partner_id.name}
        for field_map in connection.field_map_ids:
            if field_map.helpdesk_field in ticket._fields:
                values.setdefault("cf", {})[field_map.desk_field] = ticket[field_map.helpdesk_field]
        return values

    def _outbound_department_id(self, connection, ticket):
        team_row = connection.team_map_ids.filtered(lambda row: row.team_id == ticket.team_id)[:1]
        if team_row.desk_department_id:
            return team_row.desk_department_id
        if len(connection.department_map_ids) == 1:
            return connection.department_map_ids.desk_department_id
        return False

    def _desk_agent_for_user(self, connection, user):
        if not user:
            return False
        mapped = connection.agent_map_ids.filtered(lambda row: row.user_id == user)[:1]
        if mapped.desk_agent_id:
            return mapped.desk_agent_id
        return False

    def _desk_tags_for_ticket(self, connection, ticket):
        if not connection.tag_map_ids or not ticket.tag_ids:
            return []
        names = []
        for tag in ticket.tag_ids:
            mapped = connection.tag_map_ids.filtered(lambda row: row.tag_id == tag)[:1]
            if mapped.desk_tag:
                names.append(mapped.desk_tag)
        return names

    def _push_attachment(self, connection, client, mapping, ticket, payload):
        attachment = self.env["ir.attachment"].browse(payload.get("attachment_id") or 0)
        if not attachment:
            return
        decision = decide_attachment(
            size_bytes=attachment.file_size or 0,
            mimetype=attachment.mimetype or "application/octet-stream",
            travel="odoo_to_desk",
            direction=connection.attachment_direction,
            max_bytes=connection.attachment_max_bytes or 0,
            mime_allow=connection._mime_allow_set(),
        )
        if decision != "store" or not mapping:
            return
        raw = attachment.raw or b""
        created = client.add_attachment(mapping.desk_ticket_id, attachment.name, raw, attachment.mimetype)
        self.env["mpi.zoho.desk.attachment.map"].create(
            {
                "ticket_map_id": mapping.id,
                "desk_attachment_id": str(created.get("id") or ""),
                "attachment_id": attachment.id,
                "stored_as": "store",
            }
        )

    @api.private
    def _apply_webhook_event(self, connection, event):
        payload = event if isinstance(event, dict) else {}
        ticket_payload = payload.get("payload") or payload.get("ticket") or payload
        desk_id = ticket_payload.get("id") or payload.get("ticketId")
        event_type = payload.get("eventType") or payload.get("event") or ""
        if event_type in ("Ticket_Delete",) and desk_id:
            mapping = self.env["mpi.zoho.desk.ticket.map"].search(
                [("connection_id", "=", connection.id), ("desk_ticket_id", "=", str(desk_id))],
                limit=1,
            )
            if mapping and other_side_action(deleted_side="desk") == "close":
                closed = connection.status_map_ids.filtered(
                    lambda row: row.desk_status.lower() in ("closed", "close")
                )[:1].stage_id
                if closed:
                    mapping.helpdesk_ticket_id.with_context(mpi_zoho_skip_outbox=True).write(
                        {"stage_id": closed.id}
                    )
                mapping.source_removed = True
            return
        if not desk_id:
            return
        mapping = self.env["mpi.zoho.desk.ticket.map"].search(
            [("connection_id", "=", connection.id), ("desk_ticket_id", "=", str(desk_id))],
            limit=1,
        )
        incoming_hash = payload_hash(payload)
        force_side = event_type in {
            "Ticket_Add",
            "Ticket_Thread_Add",
            "Ticket_Comment_Add",
        } or "attachment" in (event_type or "").lower()
        if mapping and not should_apply(
            origin=mapping.last_origin or "desk",
            incoming_hash=incoming_hash,
            stored_hash=mapping.last_payload_hash,
        ):
            if mapping.last_origin == "connector":
                mapping.last_origin = "desk"
            if not force_side:
                return
        client = connection._make_client()
        detail = {"id": desk_id, "departmentId": ticket_payload.get("departmentId")}
        if not detail.get("departmentId"):
            detail = client.get_ticket(desk_id)
        self._apply_desk_ticket(
            connection,
            client,
            detail,
            backfill=False,
            force_side_content=force_side or not mapping,
            partner_cache={},
        )
