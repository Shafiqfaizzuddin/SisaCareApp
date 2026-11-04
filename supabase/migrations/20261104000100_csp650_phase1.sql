-- Phase 1 compatibility schema: columns and legacy IDs retained for existing APIs.
-- Applied through Supabase CLI migrations; do not edit after deployment.
create schema if not exists sisacare;

create table if not exists sisacare.analysis_drafts (
  id text primary key,
  user_id text,
  original_image_path text not null,
  annotated_image_path text not null,
  detection_json text not null,
  ai_report_json text not null,
  created_at text not null,
  consumed_at text,
  split_recycling_ids_json text
);

create table if not exists sisacare.reports (
  id text primary key,
  reference text not null,
  analysis_id text,
  reporter_role text not null,
  user_id text,
  guest_name text,
  guest_email text,
  notification_email text,
  original_image text,
  annotated_image text,
  title text not null,
  summary text not null,
  waste_identified text not null default '',
  recommended_action text not null default '',
  environmental_concern text not null default '',
  category text not null,
  final_categories_json text not null default '[]',
  ai_analysis_json text,
  location text not null,
  latitude double precision,
  longitude double precision,
  location_address text,
  location_address_source text,
  location_street text,
  location_city text,
  location_state text,
  location_postcode text,
  location_country text,
  location_source text,
  site_notes text not null default '',
  status text not null,
  validation_status text not null default 'pending',
  validated_at text,
  reviewer_id text,
  reviewed_at text,
  rejection_reason text,
  confirmed_ai_result_json text,
  activity_key text,
  data_origin text not null default 'legacy_unknown',
  activity_affiliation text not null default 'unknown',
  created_at text not null,
  updated_at text not null,
  assigned_team text,
  resolution_details text,
  after_photo text
);

create table if not exists sisacare.waste_detections (
  id text primary key,
  report_id text not null,
  class_name text not null,
  display_name text not null,
  waste_category text not null,
  material text not null,
  confidence double precision,
  x1 double precision,
  y1 double precision,
  x2 double precision,
  y2 double precision,
  source text not null default 'yolo',
  created_at text not null
);

create table if not exists sisacare.report_status_events (
  id text primary key,
  report_id text not null,
  actor_id text not null,
  previous_status text not null,
  new_status text not null,
  reason text,
  assigned_team text,
  resolution_details text,
  after_photo text,
  created_at text not null
);

create table if not exists sisacare.report_email_outbox (
  event_key text primary key,
  report_id text not null,
  event_type text not null,
  recipient_email text not null,
  created_at text not null,
  sent_at text,
  attempts bigint not null default 0,
  last_error text,
  claimed_at text,
  claim_token text,
  next_attempt_at text
);

create table if not exists sisacare.recycling_points (
  id text primary key,
  name text not null,
  latitude double precision not null,
  longitude double precision not null,
  accepted_materials_json text not null,
  active bigint not null default 1,
  description text not null default '',
  address text,
  address_source text,
  access_notes text not null default '',
  opening_hours text not null default '',
  data_origin text not null default 'production',
  public_verified bigint not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists sisacare.recycling_actions (
  id text primary key,
  user_id text not null,
  analysis_id text,
  original_photo text,
  confirmed_waste_json text not null,
  recycling_point_id text not null,
  proof_photo text not null,
  proof_latitude double precision,
  proof_longitude double precision,
  proof_location text,
  proof_location_source text,
  activity_key text not null,
  activity_affiliation text not null default 'unknown',
  verification_status text not null default 'pending',
  reviewer_id text,
  reviewed_at text,
  rejection_reason text,
  data_origin text not null default 'production',
  created_at text not null,
  updated_at text not null
);

create table if not exists sisacare.reward_events (
  id text primary key,
  report_id text,
  recycling_action_id text,
  user_id text not null,
  signed_amount bigint not null,
  points bigint not null,
  transaction_type text not null,
  source_activity_type text not null,
  source_activity_id text not null,
  activity_key text,
  reason text not null,
  activity_affiliation text not null default 'unknown',
  e_merit_classification text not null default 'ineligible_unknown',
  audit_reference text not null,
  reviewer_id text,
  data_origin text not null default 'production',
  created_at text not null
);

create table if not exists sisacare.public_participants (
  user_id text primary key,
  public_name text not null,
  role text not null,
  visible bigint not null default 1,
  disabled bigint not null default 0,
  deleted bigint not null default 0,
  data_origin text not null default 'production'
);

create table if not exists sisacare.member_identities (
  user_id text primary key,
  google_sub text,
  claimed_affiliation text,
  verified_affiliation text not null default 'pending_verification',
  matric_number text,
  matric_source text,
  matric_verified bigint not null default 0,
  matric_status text not null default 'not_submitted',
  matric_key text,
  matric_submitted_at text,
  matric_submitted_email text,
  matric_review_decision text,
  matric_reviewed_by text,
  matric_reviewed_at text,
  matric_rejection_reason text,
  matric_verification_method text
);

create table if not exists sisacare.google_auth_checks (
  token_hash text primary key,
  mode text not null,
  user_id text,
  completed_user_id text,
  expires_at bigint not null
);

create table if not exists sisacare.matric_reviews (
  id text primary key,
  user_id text not null,
  matric_number text not null,
  decision text not null,
  reviewer_id text not null,
  reviewed_at text not null,
  verification_method text not null,
  review_reference text not null,
  rejection_reason text
);

create table if not exists sisacare.e_merit_eligibility (
  id text primary key,
  user_id text not null,
  points_reserved bigint not null,
  status text not null default 'pending_approval',
  created_at text not null,
  matric_review_id text not null,
  required_points bigint not null default 50,
  conversion_rate bigint not null default 1,
  reviewer_id text,
  reviewed_at text,
  decision_reason text,
  reservation_reference text,
  data_origin text not null default 'production'
);

create table if not exists sisacare.education_articles (
  id text primary key,
  title text not null,
  summary text not null,
  body text not null,
  image_filename text,
  image_alt text not null default '',
  published bigint not null default 1,
  sort_order bigint not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists sisacare.browser_sessions (
  token_hash text primary key,
  user_id text not null,
  user_json text not null,
  created_at bigint not null,
  last_seen_at bigint not null
);

create unique index if not exists ux_reports_analysis_id on sisacare.reports (analysis_id);
create unique index if not exists ux_reports_reference on sisacare.reports (reference);
alter table sisacare.reports add constraint fk_reports_analysis_id foreign key (analysis_id) references sisacare.analysis_drafts(id) on delete no action;
alter table sisacare.waste_detections add constraint fk_waste_detections_report_id foreign key (report_id) references sisacare.reports(id) on delete cascade;
alter table sisacare.report_status_events add constraint fk_report_status_events_report_id foreign key (report_id) references sisacare.reports(id) on delete restrict;
alter table sisacare.report_email_outbox add constraint fk_report_email_outbox_report_id foreign key (report_id) references sisacare.reports(id) on delete restrict;
create unique index if not exists ux_recycling_actions_analysis_id on sisacare.recycling_actions (analysis_id);
alter table sisacare.recycling_actions add constraint fk_recycling_actions_recycling_point_id foreign key (recycling_point_id) references sisacare.recycling_points(id) on delete no action;
alter table sisacare.recycling_actions add constraint fk_recycling_actions_analysis_id foreign key (analysis_id) references sisacare.analysis_drafts(id) on delete no action;
create unique index if not exists ux_reward_events_recycling_action_id on sisacare.reward_events (recycling_action_id);
create unique index if not exists ux_reward_events_activity_key on sisacare.reward_events (activity_key)
  where transaction_type in ('report_award', 'recycling_award') and activity_key is not null;
create unique index if not exists ux_reward_events_report_id on sisacare.reward_events (report_id);
alter table sisacare.reward_events add constraint fk_reward_events_recycling_action_id foreign key (recycling_action_id) references sisacare.recycling_actions(id) on delete restrict;
alter table sisacare.reward_events add constraint fk_reward_events_report_id foreign key (report_id) references sisacare.reports(id) on delete restrict;
create unique index if not exists ux_public_participants_public_name on sisacare.public_participants (public_name);
create unique index if not exists ux_member_identities_matric_key on sisacare.member_identities (matric_key)
  where matric_status = 'verified';
create unique index if not exists ux_member_identities_google_sub on sisacare.member_identities (google_sub);
alter table sisacare.matric_reviews add constraint fk_matric_reviews_user_id foreign key (user_id) references sisacare.member_identities(user_id) on delete no action;
create unique index if not exists ux_e_merit_eligibility_reservation_reference on sisacare.e_merit_eligibility (reservation_reference);
alter table sisacare.e_merit_eligibility add constraint fk_e_merit_eligibility_matric_review_id foreign key (matric_review_id) references sisacare.matric_reviews(id) on delete no action;
alter table sisacare.e_merit_eligibility add constraint fk_e_merit_eligibility_user_id foreign key (user_id) references sisacare.member_identities(user_id) on delete no action;

create index if not exists ix_reports_owner on sisacare.reports(user_id, created_at);
create index if not exists ix_reports_status_time on sisacare.reports(status, created_at);
create index if not exists ix_reports_coordinates on sisacare.reports(latitude, longitude);
create index if not exists ix_report_status_time on sisacare.report_status_events(report_id, created_at);
create index if not exists ix_outbox_pending on sisacare.report_email_outbox(sent_at, next_attempt_at);
create index if not exists ix_reward_user on sisacare.reward_events(user_id);

-- New normalized records coexist with the compatibility tables above. Legacy
-- text IDs stay stable; authenticated owners use their existing Auth UUIDs.
create table sisacare.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
insert into sisacare.profiles (user_id) select id from auth.users on conflict do nothing;
create function sisacare.create_profile_for_auth_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into sisacare.profiles (user_id) values (new.id) on conflict do nothing;
  return new;
end;
$$;
create trigger sisacare_auth_profile_created after insert on auth.users
for each row execute function sisacare.create_profile_for_auth_user();
create table sisacare.role_grants (
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('admin', 'staff', 'driver')),
  granted_by uuid references auth.users(id),
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  primary key (user_id, role)
);
create table sisacare.report_images (
  id uuid primary key default gen_random_uuid(),
  report_id text not null references sisacare.reports(id) on delete restrict,
  image_kind text not null check (image_kind in ('original', 'annotated', 'after')),
  bucket_id text not null check (bucket_id = 'sisacare-private'),
  object_key text not null unique,
  content_type text not null check (content_type in ('image/jpeg', 'image/png', 'image/webp')),
  sha256 text not null check (length(sha256) = 64),
  byte_size bigint not null check (byte_size > 0),
  created_at timestamptz not null default now(),
  unique (report_id, image_kind)
);
create table sisacare.recycling_images (
  id uuid primary key default gen_random_uuid(),
  action_id text not null references sisacare.recycling_actions(id) on delete restrict,
  image_kind text not null check (image_kind in ('original', 'proof')),
  bucket_id text not null check (bucket_id = 'sisacare-private'),
  object_key text not null unique,
  content_type text not null,
  sha256 text not null check (length(sha256) = 64),
  byte_size bigint not null check (byte_size > 0),
  unique (action_id, image_kind)
);
create table sisacare.article_images (
  id uuid primary key default gen_random_uuid(),
  article_id text not null references sisacare.education_articles(id) on delete restrict,
  object_key text not null unique,
  content_type text not null,
  sha256 text not null check (length(sha256) = 64),
  byte_size bigint not null check (byte_size > 0),
  created_at timestamptz not null default now()
);
create table sisacare.ai_results (
  report_id text primary key references sisacare.reports(id) on delete restrict,
  analysis_id text references sisacare.analysis_drafts(id),
  provider text,
  model_id text,
  rule_version text,
  raw_result jsonb,
  reviewed_result jsonb,
  created_at timestamptz not null default now()
);
create table sisacare.report_assignments (
  id uuid primary key default gen_random_uuid(),
  report_id text not null references sisacare.reports(id) on delete restrict,
  team_name text not null,
  assignee_id uuid references auth.users(id),
  assigned_by uuid references auth.users(id),
  assigned_at timestamptz not null default now(),
  ended_at timestamptz
);
create index ix_report_assignments_active on sisacare.report_assignments(report_id) where ended_at is null;
create table sisacare.notifications (
  id uuid primary key default gen_random_uuid(),
  report_id text not null references sisacare.reports(id) on delete restrict,
  recipient_id uuid references auth.users(id),
  event_type text not null,
  channel text not null check (channel in ('email', 'in_app')),
  outbox_event_key text unique references sisacare.report_email_outbox(event_key),
  created_at timestamptz not null default now(),
  read_at timestamptz
);
create table sisacare.forecast_runs (
  id uuid primary key default gen_random_uuid(),
  model_name text not null,
  model_version text not null,
  horizon_start timestamptz not null,
  horizon_end timestamptz not null,
  generated_at timestamptz not null default now(),
  parameters jsonb not null default '{}'::jsonb,
  check (horizon_end > horizon_start)
);
create table sisacare.forecast_cells (
  run_id uuid not null references sisacare.forecast_runs(id) on delete cascade,
  cell_key text not null,
  center_latitude double precision not null check (center_latitude between -90 and 90),
  center_longitude double precision not null check (center_longitude between -180 and 180),
  predicted_count double precision not null check (predicted_count >= 0),
  lower_bound double precision,
  upper_bound double precision,
  primary key (run_id, cell_key)
);
create table sisacare.migration_runs (
  source_sha256 text primary key,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  row_counts jsonb,
  asset_counts jsonb
);

-- Private bucket. Only server credentials may transfer objects in Phase 1.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('sisacare-private', 'sisacare-private', false, 10485760,
        array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('sisacare-education', 'sisacare-education', false, 5242880,
        array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create function sisacare.is_admin() returns boolean language sql stable security definer
set search_path = '' as $$
  select auth.uid() is not null and (
    coalesce(auth.jwt() -> 'app_metadata' ->> 'role' = 'admin', false)
    or exists (select 1 from sisacare.role_grants g
               where g.user_id = auth.uid() and g.role = 'admin' and g.revoked_at is null)
  );
$$;
revoke all on function sisacare.is_admin() from public;
grant execute on function sisacare.is_admin() to authenticated;

-- The custom schema is not in the default Data API exposed-schema list. RLS
-- additionally protects it if an operator later exposes the schema.
grant usage on schema sisacare to authenticated;
do $$ declare t text; begin
  for t in select tablename from pg_tables where schemaname = 'sisacare' loop
    execute format('alter table sisacare.%I enable row level security', t);
    execute format('revoke all on sisacare.%I from anon, authenticated', t);
  end loop;
end $$;
grant select on sisacare.profiles, sisacare.reports, sisacare.report_images,
  sisacare.recycling_images,
  sisacare.article_images,
  sisacare.ai_results, sisacare.report_status_events, sisacare.report_assignments,
  sisacare.notifications, sisacare.education_articles, sisacare.recycling_points,
  sisacare.recycling_actions, sisacare.reward_events to authenticated;

create policy profiles_self_or_admin on sisacare.profiles for select to authenticated
  using (user_id = auth.uid() or sisacare.is_admin());
create policy reports_owner_or_admin on sisacare.reports for select to authenticated
  using (user_id = auth.uid()::text or sisacare.is_admin());
create policy report_images_owner_or_admin on sisacare.report_images for select to authenticated
  using (exists (select 1 from sisacare.reports r where r.id = report_id
                 and (r.user_id = auth.uid()::text or sisacare.is_admin())));
create policy ai_results_owner_or_admin on sisacare.ai_results for select to authenticated
  using (exists (select 1 from sisacare.reports r where r.id = report_id
                 and (r.user_id = auth.uid()::text or sisacare.is_admin())));
create policy status_events_owner_or_admin on sisacare.report_status_events for select to authenticated
  using (exists (select 1 from sisacare.reports r where r.id = report_id
                 and (r.user_id = auth.uid()::text or sisacare.is_admin())));
create policy assignments_owner_or_admin on sisacare.report_assignments for select to authenticated
  using (exists (select 1 from sisacare.reports r where r.id = report_id
                 and (r.user_id = auth.uid()::text or sisacare.is_admin())));
create policy notifications_recipient_or_admin on sisacare.notifications for select to authenticated
  using (recipient_id = auth.uid() or sisacare.is_admin());
create policy articles_published_or_admin on sisacare.education_articles for select to authenticated
  using (published = 1 or sisacare.is_admin());
create policy article_images_published_or_admin on sisacare.article_images for select to authenticated
  using (exists (select 1 from sisacare.education_articles a where a.id = article_id
                 and (a.published = 1 or sisacare.is_admin())));
create policy recycling_points_public_or_admin on sisacare.recycling_points for select to authenticated
  using ((active = 1 and public_verified = 1 and data_origin = 'production') or sisacare.is_admin());
create policy recycling_actions_owner_or_admin on sisacare.recycling_actions for select to authenticated
  using (user_id = auth.uid()::text or sisacare.is_admin());
create policy recycling_images_owner_or_admin on sisacare.recycling_images for select to authenticated
  using (exists (select 1 from sisacare.recycling_actions a where a.id = action_id
                 and (a.user_id = auth.uid()::text or sisacare.is_admin())));
create policy rewards_owner_or_admin on sisacare.reward_events for select to authenticated
  using (user_id = auth.uid()::text or sisacare.is_admin());

-- No authenticated Storage policy: clients cannot list, upload or download
-- private objects directly. The backend verifies ownership/admin role first.
