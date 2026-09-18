# Part of mpi_helpdesk_zoho. See LICENSE file for full copyright and licensing details.

import logging
from datetime import timedelta

from odoo import api, fields, models

from ..lib.attachment_policy import decide_attachment
from ..lib.comment_visibility import desk_thread_to_odoo, odoo_message_to_desk
from ..lib.desk_client import DeskClientError
from ..lib.echo import payload_hash, should_apply
from ..lib.partner_match import resolve_partner
from ..lib.priority import desk_to_helpdesk, helpdesk_to_desk
from ..lib.source_removal import other_side_action
from ..lib.sync_scope import allows_inbound
from ..lib.ticket_fields import apply_desk_wins

_logger = logging.getLogger(__name__)


class MpiZohoSync(models.AbstractModel):
    _name = "mpi.zoho.desk.sync"
    _description = "Ticket Sync"

    def _cron_keep_going(self, done=1, remaining=None):
        if not self.env.context.get("cron_id"):
            return True
        cron = self.env["ir.cron"]
        if not hasattr(cron, "_commit_progress"):
            return True
        kwargs = {}
        if remaining is not None:
            kwargs["remaining"] = remaining
        return bool(cron._commit_progress(done, **kwargs))

    @api.private
    def _pull_connection(self, connection, *, backfill):
        client = connection._make_client()
        cutoff = None
        if backfill and connection.backfill_mode == "lookback":
            cutoff = fields.Datetime.now() - timedelta(days=connection.backfill_lookback_days or 90)
        start = 0
        page_size = 100
        while True:
            page = client.list_tickets(limit=page_size, **{"from": start, "sortBy": "modifiedTime"})
            tickets = page.get("data") or []
            if not tickets:
                break
            for row in tickets:
                if cutoff and row.get("closedTime") and self._parse_desk_dt(row.get("closedTime")) < cutoff:
                    continue
                try:
                    self._apply_desk_ticket(connection, client, row)
                except Exception:
                    _logger.exception("Ticket Sync failed for Desk ticket %s", row.get("id"))
                if not self._cron_keep_going(1):
                    return
            if len(tickets) < page_size:
                break
            start += len(tickets)
            if not backfill and start >= 300:
                break

    def _parse_desk_dt(self, value):
        if not value:
            return fields.Datetime.now()
        try:
            return fields.Datetime.to_datetime(value.replace("Z", ""))
        except Exception:
            return fields.Datetime.now()

    def _apply_desk_ticket(self, connection, client, row):
        department_id = str(row.get("departmentId") or row.get("department", {}).get("id") or "")
        if not allows_inbound(
            department_id=department_id,
            mapped_department_ids=connection._mapped_department_ids(),
        ):
            return
        desk_id = str(row.get("id"))
        incoming_hash = payload_hash(row)
        mapping = self.env["mpi.zoho.desk.ticket.map"].search(
            [("connection_id", "=", connection.id), ("desk_ticket_id", "=", desk_id)], limit=1
        )
        if mapping:
            origin = mapping.last_origin or "desk"
            if not should_apply(
                origin=origin,
                incoming_hash=incoming_hash,
                stored_hash=mapping.last_payload_hash,
            ):
                if origin == "connector":
                    mapping.last_origin = "desk"
                return
        detail = client.get_ticket(desk_id)
        ticket = mapping.helpdesk_ticket_id if mapping and mapping.helpdesk_ticket_id else False
        if not ticket:
            ticket = self._create_helpdesk_ticket(connection, detail)
        if mapping and not mapping.helpdesk_ticket_id:
            mapping.helpdesk_ticket_id = ticket
        if not mapping:
            mapping = self.env["mpi.zoho.desk.ticket.map"].create(
                {
                    "connection_id": connection.id,
                    "helpdesk_ticket_id": ticket.id,
                    "desk_ticket_id": desk_id,
                }
            )
        values = self._desk_to_helpdesk_values(connection, detail)
        ticket.with_context(mpi_zoho_skip_outbox=True).write(values)
        mapping.write({"last_payload_hash": incoming_hash, "last_origin": "desk", "source_removed": False})
        self._sync_threads_in(connection, client, mapping, desk_id)
        self._sync_attachments_in(connection, client, mapping, desk_id, detail)

    def _create_helpdesk_ticket(self, connection, detail):
        partner = self._partner_for_desk(connection, detail)
        stage = self._stage_for_desk_status(connection, detail.get("status"))
        team = connection.inbound_team_id
        return self.env["helpdesk.ticket"].with_context(mpi_zoho_skip_outbox=True).create(
            {
                "name": detail.get("subject") or "Desk ticket",
                "description": detail.get("description") or False,
                "company_id": connection.company_id.id,
                "partner_id": partner.id if partner else False,
                "stage_id": stage.id if stage else False,
                "team_id": team.id if team else False,
                "priority": desk_to_helpdesk(detail.get("priority")) or "1",
            }
        )

    def _desk_to_helpdesk_values(self, connection, detail):
        odoo_fields = {}
        desk_fields = {
            "name": detail.get("subject"),
            "description": detail.get("description"),
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

    def _partner_for_desk(self, connection, detail):
        contact = detail.get("contact") or {}
        account = detail.get("account") or {}
        email = contact.get("email") or account.get("email")
        name = contact.get("lastName") or account.get("accountName") or contact.get("firstName")
        vat = self._account_vat(account)
        domain = [("company_id", "in", [False, connection.company_id.id])]
        if email:
            domain = ["&"] + domain + [("email", "=ilike", email)]
        elif vat:
            domain = ["&"] + domain + [("vat", "=", vat)]
        elif name:
            domain = ["&"] + domain + [("name", "=ilike", name)]
        existing = self.env["res.partner"].search_read(domain, ["email", "vat", "name"], limit=20)
        kind = "contact" if contact.get("email") else "account"
        decision, partner_id = resolve_partner(
            kind=kind, email=email, vat=vat, name=name, existing=existing
        )
        if decision == "link" and partner_id:
            return self.env["res.partner"].browse(partner_id)
        return self.env["res.partner"].create(
            {
                "name": name or email or "Desk contact",
                "email": email,
                "vat": vat or False,
                "is_company": bool(account.get("id") and not contact.get("email")),
                "company_id": connection.company_id.id,
            }
        )

    def _account_vat(self, account):
        return (account.get("customFields") or {}).get("vat") or account.get("vat")

    def _sync_threads_in(self, connection, client, mapping, desk_id):
        payload = client.list_threads(desk_id)
        threads = payload.get("data") or payload.get("threads") or []
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
            if not thread_id or thread_id in known:
                continue
            visibility = desk_thread_to_odoo(is_public=bool(thread.get("isPublic", thread.get("ispublic"))))
            subtype = "mail.mt_comment" if visibility == "public" else "mail.mt_note"
            message = mapping.helpdesk_ticket_id.with_context(mpi_zoho_skip_outbox=True).message_post(
                body=thread.get("content") or thread.get("summary") or "",
                subtype_xmlid=subtype,
                message_type="comment",
            )
            self.env["mpi.zoho.desk.comment.map"].create(
                {
                    "ticket_map_id": mapping.id,
                    "desk_thread_id": thread_id,
                    "mail_message_id": message.id,
                }
            )

    def _sync_attachments_in(self, connection, client, mapping, desk_id, detail):
        payload = client.list_attachments(desk_id)
        attachments = payload.get("data") or []
        att_ids = [str(row.get("id") or "") for row in attachments if row.get("id")]
        known = set(
            self.env["mpi.zoho.desk.attachment.map"]
            .search(
                [
                    ("ticket_map_id", "=", mapping.id),
                    ("desk_attachment_id", "in", att_ids),
                ]
            )
            .mapped("desk_attachment_id")
        ) if att_ids else set()
        for row in attachments:
            desk_att_id = str(row.get("id") or "")
            if desk_att_id and desk_att_id in known:
                continue
            size = int(row.get("size") or 0)
            mimetype = row.get("type") or row.get("contentType") or "application/octet-stream"
            name = row.get("name") or "desk-file"
            url = row.get("href") or row.get("previewurl") or ""
            decision = decide_attachment(
                size_bytes=size,
                mimetype=mimetype,
                travel="desk_to_odoo",
                direction=connection.attachment_direction,
                max_bytes=connection.attachment_max_bytes or 0,
                mime_allow=connection._mime_allow_set(),
            )
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
                        "res_model": "helpdesk.ticket",
                        "res_id": mapping.helpdesk_ticket_id.id,
                        "mimetype": mimetype,
                    }
                )
            elif decision == "url_only":
                attachment = self.env["ir.attachment"].create(
                    {
                        "name": name,
                        "type": "url",
                        "url": url or False,
                        "res_model": "helpdesk.ticket",
                        "res_id": mapping.helpdesk_ticket_id.id,
                        "mimetype": mimetype,
                    }
                )
            self.env["mpi.zoho.desk.attachment.map"].create(
                {
                    "ticket_map_id": mapping.id,
                    "desk_attachment_id": desk_att_id,
                    "attachment_id": attachment.id if attachment else False,
                    "desk_url": url,
                    "stored_as": decision if decision != "skip" else "reject",
                }
            )

    @api.private
    def _flush_outbox(self, connection):
        client = connection._make_client()
        pending = self.env["mpi.zoho.desk.outbox"].search(
            [("connection_id", "=", connection.id), ("state", "=", "pending")],
            order="id",
        )
        for row in pending:
            try:
                self._flush_one(connection, client, row)
                row.write({"state": "done", "error": False})
            except DeskClientError as exc:
                row.write({"state": "error", "error": str(exc)})
                _logger.warning("Outbox %s failed: %s", row.id, exc)
            if not self._cron_keep_going(1):
                return

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
        if mapping and not should_apply(
            origin=mapping.last_origin or "desk",
            incoming_hash=incoming_hash,
            stored_hash=mapping.last_payload_hash,
        ):
            if mapping.last_origin == "connector":
                mapping.last_origin = "desk"
            return
        client = connection._make_client()
        detail = {"id": desk_id, "departmentId": ticket_payload.get("departmentId")}
        if not detail.get("departmentId"):
            detail = client.get_ticket(desk_id)
        self._apply_desk_ticket(connection, client, detail)
