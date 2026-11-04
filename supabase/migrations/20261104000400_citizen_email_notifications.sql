-- Phase 5: delivery state is private and server-owned. Existing outbox keys remain.
alter table sisacare.notifications
  add column if not exists delivery_status text not null default 'queued',
  add column if not exists attempts bigint not null default 0,
  add column if not exists last_error text,
  add column if not exists delivered_at timestamptz;
alter table sisacare.notifications
  add constraint notifications_delivery_status_check
  check (delivery_status in ('queued', 'retrying', 'sent', 'failed'));
create index if not exists ix_notifications_delivery_status
  on sisacare.notifications(delivery_status, created_at desc);
create index if not exists ix_report_email_outbox_claim
  on sisacare.report_email_outbox(sent_at, next_attempt_at, claimed_at);
insert into sisacare.notifications
  (report_id, recipient_id, event_type, channel, outbox_event_key, created_at)
select o.report_id, u.id, o.event_type, 'email', o.event_key, o.created_at::timestamptz
from sisacare.report_email_outbox o
join sisacare.reports r on r.id = o.report_id
left join auth.users u on u.id::text = r.user_id
on conflict (outbox_event_key) do nothing;
update sisacare.notifications n set
  delivery_status = case when o.sent_at is not null then 'sent'
                         when o.attempts >= 5 then 'failed'
                         when o.attempts > 0 then 'retrying' else 'queued' end,
  attempts = o.attempts,
  last_error = o.last_error,
  delivered_at = case when o.sent_at is null then null else o.sent_at::timestamptz end
from sisacare.report_email_outbox o where n.outbox_event_key = o.event_key;
