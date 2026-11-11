"""Durable, event-keyed administrator email and Telegram delivery jobs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from uuid import uuid4

from app.core.config import get_settings
from app.repositories import reports


def queue_admin_event(db, report_id: str, status_event_id: str, now: str,
                      *, include_email: bool = True) -> None:
    """Call inside the report transaction, after inserting its history event."""
    settings = get_settings()
    if not include_email and not settings.telegram_admin_chat_id:
        return
    if include_email and not settings.notify_admin_on_status:
        return
    recipients = []
    address = settings.admin_notification_email.strip()
    parsed = parseaddr(address)[1]
    if include_email and parsed and parsed == address and address.count('@') == 1 and not any(c.isspace() for c in address):
        recipients.append(('email', address))
    if settings.telegram_admin_chat_id:
        recipients.append(('telegram', settings.telegram_admin_chat_id))
    for channel, recipient in recipients:
        db.execute("""INSERT OR IGNORE INTO admin_notification_outbox
            (event_key,status_event_id,report_id,channel,recipient,created_at)
            VALUES (?,?,?,?,?,?)""",
            (f"{status_event_id}:{channel}", status_event_id, report_id, channel, recipient, now))


def claim_pending(limit: int = 10, *, email_ready: bool, telegram_ready: bool) -> list[dict]:
    now = reports._utc_now()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    lock = " FOR UPDATE OF o SKIP LOCKED" if get_settings().persistence_backend == 'postgres' else ""
    with reports._connect() as db:
        reports.initialize_database(db)
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute("""SELECT o.event_key,o.channel,o.recipient,o.status_event_id,
            r.id AS report_id,r.reference,r.title,r.category,
            e.previous_status,e.new_status,e.reason,e.created_at AS event_at
            FROM admin_notification_outbox o
            JOIN reports r ON r.id = o.report_id
            JOIN report_status_events e ON e.id = o.status_event_id
            WHERE o.sent_at IS NULL AND o.attempts < 5
              AND ((o.channel = 'email' AND ?) OR (o.channel = 'telegram' AND ?))
              AND (o.claimed_at IS NULL OR o.claimed_at < ?)
              AND (o.next_attempt_at IS NULL OR o.next_attempt_at <= ?)
            ORDER BY o.created_at LIMIT ?""" + lock,
            (email_ready, telegram_ready, stale, now, max(1, min(limit, 50)))).fetchall()
        token = uuid4().hex
        for row in rows:
            db.execute("UPDATE admin_notification_outbox SET claimed_at = ?,claim_token = ? WHERE event_key = ?",
                       (now, token, row['event_key']))
        db.commit()
        return [dict(row) | {'claim_token': token} for row in rows]


def finish(event_key: str, token: str, *, error_type: str | None = None,
           provider_message_id: str | None = None, retry_after: int | None = None) -> None:
    with reports._connect() as db:
        if error_type is None:
            db.execute("""UPDATE admin_notification_outbox SET sent_at = ?,attempts = attempts + 1,
                last_error = NULL,claimed_at = NULL,claim_token = NULL,next_attempt_at = NULL,
                provider_message_id = ? WHERE event_key = ? AND claim_token = ? AND sent_at IS NULL""",
                (reports._utc_now(), provider_message_id, event_key, token))
        else:
            row = db.execute("SELECT attempts FROM admin_notification_outbox WHERE event_key = ? AND claim_token = ?",
                             (event_key, token)).fetchone()
            if row is not None:
                attempts = row['attempts'] + 1
                delay = (max(1, min(retry_after, 86400)) if retry_after is not None
                         else min(60 * (2 ** row['attempts']), 3600))
                next_attempt = None if attempts >= 5 else (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
                db.execute("""UPDATE admin_notification_outbox SET attempts = ?,last_error = ?,
                    next_attempt_at = ?,claimed_at = NULL,claim_token = NULL
                    WHERE event_key = ? AND claim_token = ?""",
                    (attempts, error_type[:100], next_attempt, event_key, token))
        db.commit()


def list_deliveries(*, status: str | None = None, limit: int = 100) -> list[dict]:
    if status not in {None, 'queued', 'retrying', 'sent', 'failed'}:
        raise ValueError('Invalid delivery status.')
    with reports._connect() as db:
        reports.initialize_database(db)
        state = "CASE WHEN o.sent_at IS NOT NULL THEN 'sent' WHEN o.attempts >= 5 THEN 'failed' WHEN o.attempts > 0 THEN 'retrying' ELSE 'queued' END"
        where = f'WHERE {state} = ?' if status else ''
        parameters = (status, max(1, min(limit, 200))) if status else (max(1, min(limit, 200)),)
        rows = db.execute("""SELECT o.event_key,o.channel,o.recipient,o.attempts,o.last_error,
            o.created_at,o.sent_at,o.next_attempt_at,r.reference,e.new_status
            FROM admin_notification_outbox o JOIN reports r ON r.id = o.report_id
            JOIN report_status_events e ON e.id = o.status_event_id
            """ + where + " ORDER BY o.created_at DESC LIMIT ?", parameters).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        recipient = item.pop('recipient')
        item['recipient_hint'] = ('Private admin channel' if item['channel'] == 'telegram'
                                  else recipient[:1] + '***@' + recipient.partition('@')[2])
        item['delivery_status'] = ('sent' if item['sent_at'] else 'failed' if item['attempts'] >= 5
                                   else 'retrying' if item['attempts'] else 'queued')
        result.append(item)
    return result


def retry_failed(event_key: str) -> bool:
    with reports._connect() as db:
        reports.initialize_database(db)
        db.execute('BEGIN IMMEDIATE')
        lock = ' FOR UPDATE' if get_settings().persistence_backend == 'postgres' else ''
        row = db.execute('SELECT attempts,sent_at FROM admin_notification_outbox WHERE event_key = ?' + lock,
                         (event_key,)).fetchone()
        if row is None or row['sent_at'] is not None or row['attempts'] < 5:
            return False
        db.execute("""UPDATE admin_notification_outbox SET attempts = 0,last_error = NULL,
            next_attempt_at = NULL,claimed_at = NULL,claim_token = NULL WHERE event_key = ?""", (event_key,))
        db.commit()
        return True
