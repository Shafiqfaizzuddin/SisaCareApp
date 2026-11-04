# Phase 5: citizen status email notifications

## How delivery works

The existing Supabase Auth identity and stored verified `notification_email` snapshot are reused. A citizen whose report has no verified recipient snapshot (for example, some historical reports) cannot be emailed automatically; the transition still succeeds. An administrator's successful **Pending Verification -> Resolved** transition always queues a citizen resolution email when that snapshot exists. Optional `Assigned`, `In Progress`, and `Pending Verification` emails are controlled by `NOTIFY_CITIZEN_ON_ASSIGNMENT` and `NOTIFY_CITIZEN_ON_PROGRESS`, both off by default. Reassignment creates another `Assigned` event when enabled.

The workflow inserts its status-history event, outbox row and notification row in one database transaction. Failed authorization, missing proof, or conflicting transitions produce no email event. SMTP runs later in the existing background worker, independently of Florence-2 and Ollama. A delivery failure updates the notification state and never reverses a committed status transition.

Each queue key includes the immutable status-event ID. A unique key prevents the same transition from creating duplicate outbox or notification rows. Concurrent workers lease events; PostgreSQL uses `FOR UPDATE SKIP LOCKED`, and SQLite uses `BEGIN IMMEDIATE`. Leases expire after five minutes. Attempts use a bounded backoff and stop after five failures; an administrator can explicitly requeue an exhausted event after fixing the provider. The email has a stable `Message-ID`. SMTP itself has no transaction with the database, so a process crash after SMTP accepts a message but before the delivery result is saved can cause a repeat send after the lease expires. The queue provides durable, at-least-once delivery rather than an impossible exactly-once SMTP guarantee.

Delivery states are `queued`, `retrying`, `sent`, and `failed`. The database stores attempt count, sanitized error type, next-attempt time, and delivery time. It does not store SMTP passwords or message bodies. The admin dashboard shows a masked recipient hint, waiting and failed counts, and a retry button for exhausted events.

## API

Both routes require the existing authenticated administrator dependency.

| Route | Description |
| --- | --- |
| `GET /api/admin/notifications/email?status=failed&limit=100` | Recent delivery events and whether admin/citizen SMTP channels are configured. Status is optional; limit is 1-200. |
| `POST /api/admin/notifications/email/{event_key}/retry` | Resets an unsent event after five failures to queued. Returns 409 for an event that is not exhausted. It does not send synchronously. |

Citizen emails have HTML and plain-text parts with the reference, status, a link to the citizen's authenticated report page, and minimal report context. The URL comes only from validated server-side `EMAIL_PUBLIC_BASE_URL`; report IDs are URL-encoded. Dynamic text is HTML-escaped. The sender address and SMTP credentials never enter the React bundle.
Queued optional updates describe the status at the recorded transition; if delivery is delayed, the authenticated report link shows the latest status.

## Configuration and migration

Apply `supabase/migrations/20261104000400_citizen_email_notifications.sql` before deploying the updated backend against Supabase PostgreSQL. It adds delivery state to existing notification records and backfills them from the existing outbox. The SQLite-to-Supabase import script also copies delivery state when an import is performed after this migration. Local SQLite upgrades the old outbox constraint and backfills notification rows without deleting historical outbox records. Keep a database backup before any production migration.

Set the following in **backend-only** environment configuration or a server secret store:

```text
EMAIL_PUBLIC_BASE_URL=https://your-sisacare-domain.example
USER_SMTP_HOST=<delivery-capable-provider-host>
USER_SMTP_PORT=587
USER_SMTP_SECURITY=starttls
USER_SMTP_USERNAME=<provider-username>
USER_SMTP_PASSWORD=<provider-secret>
USER_SMTP_FROM=updates@your-verified-domain.example
NOTIFY_CITIZEN_ON_ASSIGNMENT=false
NOTIFY_CITIZEN_ON_PROGRESS=false
```

`USER_SMTP_HOST` may point to Mailtrap Sandbox in local development; sandbox messages appear in Mailtrap and do not reach citizen inboxes. For a real-delivery rehearsal, use a provider account authorized to send to external mailboxes. The existing separate `ADMIN_SMTP_*` channel can remain on Mailtrap while `USER_SMTP_*` uses the real provider. A blank user host pauses delivery but retains queued citizen events. Production configuration requires encrypted SMTP and an HTTPS public URL. Never commit actual credentials, place them in `VITE_*` variables, or send them to browser code.

## Automated verification

```powershell
cd backend
python -m pytest tests/test_phase5_notifications.py tests/test_report_email.py tests/test_csp650_phase2.py
cd ../frontend
npm test -- --run src/components/admin/EmailDeliveryPanel.test.tsx src/pages/AdminDashboardPage.test.tsx
npm run build
```

Tests use mocked SMTP and temporary SQLite files. They verify required resolution messages without configured SMTP, optional assignment/progress updates, different keys for repeated assignments, no event from unauthorized/conflicting transitions, a single concurrent SQLite lease, five failed attempts, admin visibility and retry, template status/link/escaping, and preservation of legacy outbox rows. No test claims delivery through a real SMTP provider.

## Real-provider verification checklist

1. Back up production data, apply the Supabase migration, restart the backend worker, and verify `GET /api/admin/notifications/email` as an administrator. Confirm citizen SMTP reports configured. Check that a citizen and staff user receive 403.
2. Use a dedicated test citizen account with a confirmed email address and a new report. Confirm its private report page opens from the configured HTTPS origin after sign-in. Avoid using a real citizen's address for rehearsal.
3. Have an authorized administrator verify the report, assign it to an authorized staff account, and have that staff account start collection and upload a valid cleanup proof. Have the administrator verify cleanup as Resolved. Confirm exactly one new resolved notification row for that status-history event.
4. Inspect the test mailbox, including spam or quarantine. Check sender, recipient, subject, plain-text and HTML parts, reference, `Resolved` status, and report link. Follow the link after signing in. Check the admin delivery panel shows `sent`, one attempt, and a delivery timestamp.
5. With assignment/progress switches enabled in a staging environment, repeat and check each status email and its unique event key. Switch them off again if only resolution notices are desired.
6. Simulate a provider outage using a staging SMTP host or revoked test credential. Verify the report status still resolves, the outbox moves through `retrying` to `failed`, only an error type appears in the admin view, and no credential appears in logs. Restore the provider and use the admin retry action; verify it becomes `sent`.
7. Confirm the provider's accepted-message record and final mailbox receipt. A `sent` database state means the SMTP server accepted the message; it does not prove final inbox placement. Review the provider's delivery/bounce dashboard for that final result.

For a one-off staging delivery check while the backend is configured, run `python -c "from app.services.report_email import dispatch_pending_report_emails; print(dispatch_pending_report_emails())"` from `backend`. This invokes the same bounded worker pass and does not depend on local AI services.
