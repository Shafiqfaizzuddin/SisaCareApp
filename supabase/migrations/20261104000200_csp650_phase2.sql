-- Phase 2 preserves legacy report and status rows; only new transitions use these fields.
alter table sisacare.reports add column if not exists resolution_seconds bigint;
alter table sisacare.report_assignments add column if not exists cleanup_note text;
with ranked as (
  select id, row_number() over (partition by report_id order by assigned_at desc, id desc) as position
  from sisacare.report_assignments where ended_at is null
)
update sisacare.report_assignments a set ended_at = a.assigned_at
from ranked r where r.id = a.id and r.position > 1;
create unique index ux_active_report_assignment on sisacare.report_assignments(report_id) where ended_at is null;
create unique index ux_assignment_proof_parent on sisacare.report_assignments(report_id, id, assignee_id);
create table sisacare.cleanup_proofs (
  id text primary key, report_id text not null references sisacare.reports(id) on delete restrict,
  assignee_id uuid not null references auth.users(id), assignment_id uuid not null references sisacare.report_assignments(id),
  object_key text not null unique, content_type text not null,
  sha256 text not null check (length(sha256) = 64), byte_size bigint not null check (byte_size > 0),
  note text not null, created_at text not null,
  foreign key (report_id, assignment_id, assignee_id)
    references sisacare.report_assignments(report_id, id, assignee_id) on delete restrict
);
alter table sisacare.cleanup_proofs enable row level security;
revoke all on sisacare.cleanup_proofs from anon, authenticated;
grant select on sisacare.cleanup_proofs to authenticated;
create function sisacare.is_assigned_staff(target_report text) returns boolean
language sql stable security definer set search_path = '' as $$
  select auth.uid() is not null and exists (
    select 1 from sisacare.report_assignments a
    join sisacare.role_grants g on g.user_id = a.assignee_id
    where a.report_id = target_report and a.assignee_id = auth.uid()
      and a.ended_at is null and g.role in ('staff','driver') and g.revoked_at is null);
$$;
revoke all on function sisacare.is_assigned_staff(text) from public;
grant execute on function sisacare.is_assigned_staff(text) to authenticated;
create policy staff_read_reports on sisacare.reports for select to authenticated
  using (sisacare.is_assigned_staff(id));
create policy staff_read_assignments on sisacare.report_assignments for select to authenticated
  using (assignee_id = auth.uid() and sisacare.is_assigned_staff(report_id));
create policy staff_read_history on sisacare.report_status_events for select to authenticated
  using (sisacare.is_assigned_staff(report_id));
create policy staff_read_images on sisacare.report_images for select to authenticated
  using (sisacare.is_assigned_staff(report_id));
create policy staff_read_proofs on sisacare.cleanup_proofs for select to authenticated
  using (sisacare.is_assigned_staff(report_id) or sisacare.is_admin());
