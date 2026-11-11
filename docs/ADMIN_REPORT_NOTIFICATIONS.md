# Administrator report notifications

New reports send the existing administrator submission email and queue a Telegram alert. Each successful status-history event after submission queues one administrator email and one Telegram alert when their destinations are configured. This covers verification or rejection, assignment or reassignment, collection started, cleanup proof submitted, rework, and verified resolution. Failed or unauthorized transitions queue nothing. Citizen emails keep their existing separate behavior.

The queue writes inside the report transaction. A background worker sends independently every 60 seconds; an email or Telegram outage does not undo the report update. Jobs have a five-minute lease, up to five attempts with bounded backoff, and an administrator-only manual retry after exhaustion. The `event_key` is derived from the immutable status-event ID and channel. A provider can accept a message just before the worker crashes, so delivery is at least once rather than exactly once. Telegram's returned message ID is stored for investigation. The administrator dashboard shows masked destinations, failures, and retry controls.

Messages include the report reference, category, event time, and status transition. The email has HTML and plain-text parts. Telegram has an **Open report** inline button when `EMAIL_PUBLIC_BASE_URL` is a public HTTPS origin; Telegram rejects `localhost` URLs in buttons, so local-only setups send the alert without a button. The link points to the existing authenticated `/admin/reports/{id}` page. No message contains a private storage URL, reporter email, or login token. The event describes the transition when it happened; the report page shows the latest state if delivery was delayed.

## Setup

1. Apply `supabase/migrations/20261110000100_admin_report_notifications.sql` before starting the updated backend against Supabase PostgreSQL. SQLite creates its equivalent table on startup. Back up the database before deployment; neither path deletes historical notifications.
2. Create a bot through Telegram BotFather. Create a **private** channel whose membership is restricted to administrators, add the bot as a channel administrator with posting permission, and obtain its numeric channel ID (typically beginning with `-100`). Review channel membership when an administrator leaves. Do not make a public invite link. The bot only posts; no Telegram webhook or status-changing bot command is required.
3. Put the following values in `backend/.env` or backend deployment secrets. Never put the bot token or SMTP credentials in `VITE_*` variables, frontend code, or version control:

   ```text
   ADMIN_NOTIFICATION_EMAIL=admin@example.com
   ADMIN_SMTP_HOST=<admin-smtp-host>
   ADMIN_SMTP_PORT=587
   ADMIN_SMTP_SECURITY=starttls
   ADMIN_SMTP_USERNAME=<username>
   ADMIN_SMTP_PASSWORD=<secret>
   ADMIN_SMTP_FROM=alerts@your-verified-domain.example
   TELEGRAM_BOT_TOKEN=<bot-token>
   TELEGRAM_ADMIN_CHAT_ID=-1001234567890
   NOTIFY_ADMIN_ON_STATUS=true
   EMAIL_PUBLIC_BASE_URL=https://your-sisacare-domain.example
   ```

   The administrator email address may be configured before SMTP is ready; its queued jobs wait for a sender. The Telegram channel ID may likewise be configured before the token; its jobs wait. Leave a destination blank to disable that channel's *new* jobs. Set `NOTIFY_ADMIN_ON_STATUS=false` to pause new status-event jobs while retaining new-report Telegram alerts. Existing queued jobs are not deleted by a configuration change.
4. `ADMIN_SMTP_*` can remain on Mailtrap Sandbox for development, where messages **do not** reach a real Gmail inbox. Use a delivery-capable provider and verified sender if administrator email must reach a real inbox. `USER_SMTP_*` and Supabase Auth SMTP remain independent.
5. Restart FastAPI and open the Administrator alerts section on the admin dashboard. Only authenticated administrators can call `GET /api/admin/notifications/admin?status=failed&limit=100` and `POST /api/admin/notifications/admin/{event_key}/retry`. The existing Email Delivery section remains for citizen and historical submission email jobs.

## Verification

Run backend tests with the project virtual environment and a writable pytest temp directory:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_admin_report_notifications.py tests/test_report_email.py tests/test_phase5_notifications.py --basetemp=.pytest_admin_notification_check
cd ..\frontend
npm test -- --run src/components/admin/AdminNotificationPanel.test.tsx src/pages/AdminDashboardPage.test.tsx
npm run build
```

For a real-provider rehearsal, create a report with a test citizen account; verify one submission email job and one Telegram job, then verify or reject the report and complete a staff workflow. Confirm each status-history event has one job per configured channel, the private Telegram message has a working **Open report** button, and the email HTML/plain-text link requires administrator sign-in. Check the actual provider inbox or Mailtrap capture as appropriate. Test a temporary provider outage, confirm report transitions still commit, and inspect retry/failure states in the dashboard. An SMTP `sent` state means the server accepted the message; inspect the provider's delivery log to confirm inbox receipt.
