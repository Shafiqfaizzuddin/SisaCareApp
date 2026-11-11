-- Administrator delivery jobs are server-owned and reference immutable report events.
create table if not exists sisacare.admin_notification_outbox (
  event_key text primary key,
  status_event_id text not null references sisacare.report_status_events(id) on delete restrict,
  report_id text not null references sisacare.reports(id) on delete restrict,
  channel text not null check (channel in ('email', 'telegram')),
  recipient text not null,
  created_at timestamptz not null,
  sent_at timestamptz,
  attempts integer not null default 0,
  last_error text,
  claimed_at timestamptz,
  claim_token text,
  next_attempt_at timestamptz,
  provider_message_id text,
  unique (status_event_id, channel, recipient)
);
create index if not exists idx_admin_notification_pending
  on sisacare.admin_notification_outbox(sent_at, next_attempt_at, claimed_at);
alter table sisacare.admin_notification_outbox enable row level security;
-- No browser grants: only the FastAPI PostgreSQL connection can enqueue and deliver.
