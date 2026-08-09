create extension if not exists pgcrypto;

create table public.titles (
  title_id uuid primary key default gen_random_uuid(),
  title_name text not null unique,
  description text not null default '',
  minimum_points integer not null check (minimum_points >= 0),
  badge_icon text,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now())
);

insert into public.titles (title_name, description, minimum_points)
values
  ('Community Starter', 'Beginning a cleaner-community contribution journey.', 0),
  ('Neighbourhood Scout', 'A dependable observer helping identify local waste issues.', 250),
  ('Waste Watcher', 'A consistent contributor with verified community impact.', 500),
  ('Community Guardian', 'A leading contributor protecting shared public spaces.', 1000)
on conflict (title_name) do update
set description = excluded.description,
    minimum_points = excluded.minimum_points,
    is_active = true;

alter table public.profiles
  add column if not exists phone_number text,
  add column if not exists avatar_url text,
  add column if not exists current_title_id uuid references public.titles (title_id),
  add column if not exists is_active boolean not null default true;

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.profiles
    where id = (select auth.uid())
      and role = 'admin'
      and is_active = true
  );
$$;

revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to anon, authenticated;

create table public.waste_categories (
  waste_category_id text primary key,
  category_name text not null unique,
  description text not null default '',
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now())
);

insert into public.waste_categories (
  waste_category_id,
  category_name,
  description
)
values
  ('household', 'Household waste', 'Furniture, food waste, appliances, or mixed domestic rubbish.'),
  ('recyclable', 'Recyclable materials', 'Plastic, paper, glass, metal, or reusable materials.'),
  ('construction_debris', 'Construction debris', 'Concrete, timber, tiles, soil, or renovation materials.'),
  ('other', 'Other material', 'Waste that does not match the listed categories.')
on conflict (waste_category_id) do update
set category_name = excluded.category_name,
    description = excluded.description,
    is_active = true;

create sequence if not exists public.report_reference_seq start with 1001;

create or replace function public.generate_report_reference()
returns text
language sql
volatile
set search_path = ''
as $$
  select 'SCA-' || to_char(timezone('utc', now()), 'YYYYMMDD') || '-' ||
    lpad(nextval('public.report_reference_seq')::text, 4, '0');
$$;

revoke all on function public.generate_report_reference() from public;

create table public.reports (
  report_id uuid primary key default gen_random_uuid(),
  reference text not null unique default public.generate_report_reference(),
  user_id uuid references public.profiles (id) on delete set null,
  reporter_type text not null check (reporter_type in ('guest', 'user')),
  guest_name text,
  guest_email text,
  description text,
  image_path text not null,
  selected_waste_category_id text references public.waste_categories (waste_category_id),
  latitude numeric(9, 6) check (latitude between -90 and 90),
  longitude numeric(9, 6) check (longitude between -180 and 180),
  location_address text not null,
  validation_status text not null default 'pending'
    check (validation_status in ('pending', 'valid', 'invalid')),
  case_status text not null default 'processing'
    check (case_status in ('processing', 'in_progress', 'completed')),
  submitted_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint reports_reporter_details_check check (
    (reporter_type = 'guest' and user_id is null and
      nullif(trim(guest_name), '') is not null and
      nullif(trim(guest_email), '') is not null)
    or
    (reporter_type = 'user' and user_id is not null and
      guest_name is null and guest_email is null)
  )
);

create table public.ai_analyses (
  analysis_id uuid primary key default gen_random_uuid(),
  report_id uuid not null unique references public.reports (report_id) on delete cascade,
  waste_category_id text not null references public.waste_categories (waste_category_id),
  confidence_score numeric(5, 2) check (confidence_score between 0 and 100),
  risk_level text check (risk_level in ('low', 'medium', 'high', 'critical')),
  generated_report text,
  model_name text,
  analyzed_at timestamptz not null default timezone('utc', now())
);

create table public.report_validations (
  validation_id uuid primary key default gen_random_uuid(),
  report_id uuid not null references public.reports (report_id) on delete cascade,
  admin_id uuid not null references public.profiles (id),
  validation_status text not null check (validation_status in ('valid', 'invalid')),
  validation_note text,
  validated_at timestamptz not null default timezone('utc', now())
);

create table public.report_status_history (
  history_id uuid primary key default gen_random_uuid(),
  report_id uuid not null references public.reports (report_id) on delete cascade,
  changed_by uuid not null references public.profiles (id),
  previous_status text not null
    check (previous_status in ('processing', 'in_progress', 'completed')),
  new_status text not null
    check (new_status in ('processing', 'in_progress', 'completed')),
  note text,
  changed_at timestamptz not null default timezone('utc', now())
);

create table public.reward_rules (
  reward_rule_id uuid primary key default gen_random_uuid(),
  rule_name text not null unique,
  reward_type text not null unique
    check (reward_type in (
      'report_submitted',
      'valid_report',
      'achievement_bonus',
      'manual_adjustment'
    )),
  points integer not null,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

insert into public.reward_rules (rule_name, reward_type, points)
values
  ('Registered report received', 'report_submitted', 10),
  ('Administrator validated report', 'valid_report', 40),
  ('Achievement milestone bonus', 'achievement_bonus', 0),
  ('Manual adjustment', 'manual_adjustment', 0)
on conflict (reward_type) do update
set rule_name = excluded.rule_name,
    points = excluded.points,
    is_active = true,
    updated_at = timezone('utc', now());

create table public.achievements (
  achievement_id uuid primary key default gen_random_uuid(),
  achievement_name text not null unique,
  description text not null,
  icon_url text,
  criteria_type text not null check (criteria_type in ('points', 'valid_reports')),
  criteria_value integer not null check (criteria_value >= 0),
  bonus_points integer not null default 0 check (bonus_points >= 0),
  title_id uuid references public.titles (title_id),
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now())
);

insert into public.achievements (
  achievement_name,
  description,
  criteria_type,
  criteria_value,
  title_id
)
select values_table.achievement_name,
       values_table.description,
       values_table.criteria_type,
       values_table.criteria_value,
       titles.title_id
from (
  values
    ('First Step', 'Submit your first valid community report.', 'valid_reports', 1, 'Community Starter'),
    ('Clean Streets', 'Help verify five illegal dumping locations.', 'valid_reports', 5, 'Neighbourhood Scout'),
    ('Waste Watcher', 'Reach 500 points through valid reports.', 'points', 500, 'Waste Watcher'),
    ('Community Guardian', 'Make a sustained contribution worth 1,000 points.', 'points', 1000, 'Community Guardian')
) as values_table(achievement_name, description, criteria_type, criteria_value, title_name)
join public.titles on titles.title_name = values_table.title_name
on conflict (achievement_name) do update
set description = excluded.description,
    criteria_type = excluded.criteria_type,
    criteria_value = excluded.criteria_value,
    title_id = excluded.title_id,
    is_active = true;

create table public.user_achievements (
  user_achievement_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  achievement_id uuid not null references public.achievements (achievement_id) on delete cascade,
  achieved_at timestamptz not null default timezone('utc', now()),
  unique (user_id, achievement_id)
);

create table public.user_titles (
  user_title_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  title_id uuid not null references public.titles (title_id) on delete cascade,
  unlocked_at timestamptz not null default timezone('utc', now()),
  unique (user_id, title_id)
);

create table public.reward_transactions (
  transaction_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  report_id uuid references public.reports (report_id) on delete set null,
  reward_rule_id uuid not null references public.reward_rules (reward_rule_id),
  achievement_id uuid references public.achievements (achievement_id) on delete set null,
  points integer not null,
  description text not null,
  awarded_at timestamptz not null default timezone('utc', now())
);

create unique index reward_transactions_report_rule_unique
on public.reward_transactions (user_id, report_id, reward_rule_id)
where report_id is not null;

create unique index reward_transactions_achievement_rule_unique
on public.reward_transactions (user_id, achievement_id, reward_rule_id)
where achievement_id is not null;

create table public.educational_content (
  content_id uuid primary key default gen_random_uuid(),
  created_by uuid references public.profiles (id) on delete set null,
  title text not null,
  content text not null,
  category text not null,
  image_url text,
  status text not null default 'draft' check (status in ('draft', 'published')),
  published_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint educational_content_publish_date_check check (
    status = 'draft' or published_at is not null
  )
);

insert into public.educational_content (title, content, category, status, published_at)
values
  ('Household waste', 'Bulky furniture, appliances, food waste, and mixed domestic items should use scheduled bulky-waste collection or an approved community facility.', 'household', 'published', timezone('utc', now())),
  ('Recyclable materials', 'Separate clean paper, cardboard, glass, metal, and accepted plastics, then use a recognised recycling collection point.', 'recyclable', 'published', timezone('utc', now())),
  ('Construction debris', 'Concrete, timber, tiles, soil, plasterboard, and renovation offcuts require collection through a licensed construction-waste contractor.', 'construction_debris', 'published', timezone('utc', now())),
  ('Hazardous or unknown waste', 'Do not touch chemicals, batteries, paint, oils, leaking containers, or unidentified materials. Report the location for trained personnel to assess.', 'other', 'published', timezone('utc', now()))
on conflict do nothing;

create index reports_user_id_idx on public.reports (user_id);
create index reports_submitted_at_idx on public.reports (submitted_at desc);
create index reports_case_status_idx on public.reports (case_status);
create index reports_validation_status_idx on public.reports (validation_status);
create index report_validations_report_id_idx on public.report_validations (report_id);
create index report_status_history_report_id_idx on public.report_status_history (report_id);
create index reward_transactions_user_id_idx on public.reward_transactions (user_id, awarded_at desc);
create index educational_content_status_idx on public.educational_content (status, published_at desc);

create trigger on_reports_updated
  before update on public.reports
  for each row execute procedure public.set_updated_at();

create trigger on_reward_rules_updated
  before update on public.reward_rules
  for each row execute procedure public.set_updated_at();

create trigger on_educational_content_updated
  before update on public.educational_content
  for each row execute procedure public.set_updated_at();

create or replace function public.refresh_user_rewards(target_user_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  total integer;
  valid_count integer;
  achievement_record record;
  bonus_rule_id uuid;
  selected_title record;
begin
  select coalesce(sum(points), 0)::integer
  into total
  from public.reward_transactions
  where user_id = target_user_id;

  select count(*)::integer
  into valid_count
  from public.reports
  where user_id = target_user_id
    and validation_status = 'valid';

  update public.profiles
  set points = total,
      valid_reports = valid_count,
      updated_at = timezone('utc', now())
  where id = target_user_id;

  select reward_rule_id
  into bonus_rule_id
  from public.reward_rules
  where reward_type = 'achievement_bonus'
    and is_active = true
  limit 1;

  for achievement_record in
    insert into public.user_achievements (user_id, achievement_id)
    select target_user_id, achievements.achievement_id
    from public.achievements
    where achievements.is_active = true
      and (
        (achievements.criteria_type = 'points' and total >= achievements.criteria_value)
        or
        (achievements.criteria_type = 'valid_reports' and valid_count >= achievements.criteria_value)
      )
    on conflict (user_id, achievement_id) do nothing
    returning achievement_id
  loop
    insert into public.user_titles (user_id, title_id)
    select target_user_id, achievements.title_id
    from public.achievements
    where achievements.achievement_id = achievement_record.achievement_id
      and achievements.title_id is not null
    on conflict (user_id, title_id) do nothing;

    if bonus_rule_id is not null then
      insert into public.reward_transactions (
        user_id,
        reward_rule_id,
        achievement_id,
        points,
        description
      )
      select target_user_id,
             bonus_rule_id,
             achievements.achievement_id,
             achievements.bonus_points,
             'Achievement unlocked: ' || achievements.achievement_name
      from public.achievements
      where achievements.achievement_id = achievement_record.achievement_id
        and achievements.bonus_points > 0
      on conflict do nothing;
    end if;
  end loop;

  select coalesce(sum(points), 0)::integer
  into total
  from public.reward_transactions
  where user_id = target_user_id;

  insert into public.user_titles (user_id, title_id)
  select target_user_id, titles.title_id
  from public.titles
  where titles.is_active = true
    and titles.minimum_points <= total
  on conflict (user_id, title_id) do nothing;

  select titles.title_id, titles.title_name
  into selected_title
  from public.titles
  where titles.is_active = true
    and titles.minimum_points <= total
  order by titles.minimum_points desc
  limit 1;

  update public.profiles
  set points = total,
      valid_reports = valid_count,
      current_title_id = selected_title.title_id,
      title = coalesce(selected_title.title_name, 'Community Starter'),
      updated_at = timezone('utc', now())
  where id = target_user_id;
end;
$$;

revoke all on function public.refresh_user_rewards(uuid) from public;

create or replace function public.submit_report(
  guest_name text,
  guest_email text,
  description text,
  image_path text,
  location_address text,
  latitude numeric default null,
  longitude numeric default null,
  selected_waste_category_id text default null
)
returns table (
  report_id uuid,
  reference text,
  submitted_at timestamptz,
  awarded_points integer
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  caller_id uuid := (select auth.uid());
  caller_role text;
  created_report public.reports%rowtype;
  submission_rule public.reward_rules%rowtype;
begin
  if nullif(trim(location_address), '') is null then
    raise exception 'A location is required.';
  end if;

  if nullif(trim(image_path), '') is null then
    raise exception 'A report image is required.';
  end if;

  if selected_waste_category_id is not null and not exists (
    select 1 from public.waste_categories
    where waste_categories.waste_category_id = submit_report.selected_waste_category_id
      and is_active = true
  ) then
    raise exception 'The selected waste category is not available.';
  end if;

  if caller_id is null then
    if nullif(trim(guest_name), '') is null or nullif(trim(guest_email), '') is null then
      raise exception 'Guest name and email are required.';
    end if;

    insert into public.reports (
      reporter_type,
      guest_name,
      guest_email,
      description,
      image_path,
      location_address,
      latitude,
      longitude,
      selected_waste_category_id
    )
    values (
      'guest',
      trim(guest_name),
      lower(trim(guest_email)),
      nullif(trim(description), ''),
      trim(image_path),
      trim(location_address),
      latitude,
      longitude,
      selected_waste_category_id
    )
    returning * into created_report;
  else
    select role into caller_role
    from public.profiles
    where id = caller_id and is_active = true;

    if caller_role <> 'user' then
      raise exception 'Only registered users can submit an account-linked report.';
    end if;

    insert into public.reports (
      user_id,
      reporter_type,
      description,
      image_path,
      location_address,
      latitude,
      longitude,
      selected_waste_category_id
    )
    values (
      caller_id,
      'user',
      nullif(trim(description), ''),
      trim(image_path),
      trim(location_address),
      latitude,
      longitude,
      selected_waste_category_id
    )
    returning * into created_report;

    select * into submission_rule
    from public.reward_rules
    where reward_type = 'report_submitted' and is_active = true
    limit 1;

    if submission_rule.reward_rule_id is not null and submission_rule.points <> 0 then
      insert into public.reward_transactions (
        user_id,
        report_id,
        reward_rule_id,
        points,
        description
      )
      values (
        caller_id,
        created_report.report_id,
        submission_rule.reward_rule_id,
        submission_rule.points,
        submission_rule.rule_name
      )
      on conflict do nothing;

      perform public.refresh_user_rewards(caller_id);
    end if;
  end if;

  return query
  select created_report.report_id,
         created_report.reference,
         created_report.submitted_at,
         case when caller_id is null then 0 else coalesce(submission_rule.points, 0) end;
end;
$$;

revoke all on function public.submit_report(text, text, text, text, text, numeric, numeric, text) from public;
grant execute on function public.submit_report(text, text, text, text, text, numeric, numeric, text) to anon, authenticated;

create or replace function public.admin_validate_report(
  target_report_id uuid,
  decision text,
  note text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  admin_user_id uuid := (select auth.uid());
  target_report public.reports%rowtype;
  valid_rule public.reward_rules%rowtype;
begin
  if not public.is_admin() then
    raise exception 'Administrator access is required.';
  end if;

  if decision not in ('valid', 'invalid') then
    raise exception 'Validation must be valid or invalid.';
  end if;

  select * into target_report
  from public.reports
  where report_id = target_report_id
  for update;

  if target_report.report_id is null then
    raise exception 'Report not found.';
  end if;

  if target_report.validation_status <> 'pending' then
    raise exception 'This report already has a final validation decision.';
  end if;

  insert into public.report_validations (
    report_id,
    admin_id,
    validation_status,
    validation_note
  )
  values (target_report_id, admin_user_id, decision, nullif(trim(note), ''));

  update public.reports
  set validation_status = decision,
      case_status = case when decision = 'invalid' then 'completed' else case_status end
  where report_id = target_report_id;

  if decision = 'invalid' and target_report.case_status <> 'completed' then
    insert into public.report_status_history (
      report_id,
      changed_by,
      previous_status,
      new_status,
      note
    )
    values (
      target_report_id,
      admin_user_id,
      target_report.case_status,
      'completed',
      'Case closed after report was marked invalid.'
    );
  end if;

  if decision = 'valid' and target_report.user_id is not null then
    select * into valid_rule
    from public.reward_rules
    where reward_type = 'valid_report' and is_active = true
    limit 1;

    if valid_rule.reward_rule_id is not null and valid_rule.points <> 0 then
      insert into public.reward_transactions (
        user_id,
        report_id,
        reward_rule_id,
        points,
        description
      )
      values (
        target_report.user_id,
        target_report_id,
        valid_rule.reward_rule_id,
        valid_rule.points,
        valid_rule.rule_name
      )
      on conflict do nothing;
    end if;

    perform public.refresh_user_rewards(target_report.user_id);
  end if;
end;
$$;

revoke all on function public.admin_validate_report(uuid, text, text) from public;
grant execute on function public.admin_validate_report(uuid, text, text) to authenticated;

create or replace function public.admin_update_report_status(
  target_report_id uuid,
  new_status text,
  note text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  admin_user_id uuid := (select auth.uid());
  previous_status text;
begin
  if not public.is_admin() then
    raise exception 'Administrator access is required.';
  end if;

  if new_status not in ('processing', 'in_progress', 'completed') then
    raise exception 'Invalid report status.';
  end if;

  select case_status into previous_status
  from public.reports
  where report_id = target_report_id
  for update;

  if previous_status is null then
    raise exception 'Report not found.';
  end if;

  if previous_status = new_status then
    return;
  end if;

  update public.reports
  set case_status = new_status
  where report_id = target_report_id;

  insert into public.report_status_history (
    report_id,
    changed_by,
    previous_status,
    new_status,
    note
  )
  values (
    target_report_id,
    admin_user_id,
    previous_status,
    new_status,
    nullif(trim(note), '')
  );
end;
$$;

revoke all on function public.admin_update_report_status(uuid, text, text) from public;
grant execute on function public.admin_update_report_status(uuid, text, text) to authenticated;

create or replace function public.sync_education_published_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status = 'published' and new.published_at is null then
    new.published_at = timezone('utc', now());
  elsif new.status = 'draft' then
    new.published_at = null;
  end if;
  return new;
end;
$$;

revoke all on function public.sync_education_published_at() from public;

create trigger on_educational_content_publish
  before insert or update of status on public.educational_content
  for each row execute procedure public.sync_education_published_at();

insert into public.user_titles (user_id, title_id)
select profiles.id, titles.title_id
from public.profiles
cross join public.titles
where titles.title_name = 'Community Starter'
on conflict (user_id, title_id) do nothing;

update public.profiles
set current_title_id = titles.title_id,
    title = titles.title_name
from public.titles
where titles.title_name = 'Community Starter'
  and profiles.current_title_id is null;

create or replace view public.leaderboard_view
with (security_barrier = true)
as
select profiles.id as user_id,
       profiles.name as full_name,
       profiles.points as total_points,
       profiles.valid_reports as valid_report_count,
       count(reports.report_id)::integer as total_report_count,
       coalesce(titles.title_name, profiles.title) as current_title,
       dense_rank() over (order by profiles.points desc, profiles.created_at asc) as points_rank,
       dense_rank() over (order by profiles.valid_reports desc, profiles.created_at asc) as reports_rank
from public.profiles
left join public.reports on reports.user_id = profiles.id
left join public.titles on titles.title_id = profiles.current_title_id
where profiles.role = 'user'
  and profiles.is_active = true
group by profiles.id, titles.title_name;

revoke all on public.leaderboard_view from public;
grant select on public.leaderboard_view to anon, authenticated;

alter table public.titles enable row level security;
alter table public.waste_categories enable row level security;
alter table public.reports enable row level security;
alter table public.ai_analyses enable row level security;
alter table public.report_validations enable row level security;
alter table public.report_status_history enable row level security;
alter table public.reward_rules enable row level security;
alter table public.reward_transactions enable row level security;
alter table public.achievements enable row level security;
alter table public.user_achievements enable row level security;
alter table public.user_titles enable row level security;
alter table public.educational_content enable row level security;

revoke all on public.titles from anon, authenticated;
revoke all on public.waste_categories from anon, authenticated;
revoke all on public.reports from anon, authenticated;
revoke all on public.ai_analyses from anon, authenticated;
revoke all on public.report_validations from anon, authenticated;
revoke all on public.report_status_history from anon, authenticated;
revoke all on public.reward_rules from anon, authenticated;
revoke all on public.reward_transactions from anon, authenticated;
revoke all on public.achievements from anon, authenticated;
revoke all on public.user_achievements from anon, authenticated;
revoke all on public.user_titles from anon, authenticated;
revoke all on public.educational_content from anon, authenticated;

grant select on public.titles, public.waste_categories, public.reward_rules,
  public.achievements, public.educational_content to anon, authenticated;
grant select on public.reports, public.ai_analyses, public.report_validations,
  public.report_status_history, public.reward_transactions,
  public.user_achievements, public.user_titles to authenticated;
grant insert, update, delete on public.educational_content to authenticated;

drop policy if exists "Users can update their own name" on public.profiles;
drop policy if exists "Users can update their own profile" on public.profiles;
create policy "Users can update their own profile"
on public.profiles
for update
to authenticated
using ((select auth.uid()) = id)
with check (
  (select auth.uid()) = id
  and (
    current_title_id is null
    or exists (
      select 1 from public.user_titles
      where user_titles.user_id = (select auth.uid())
        and user_titles.title_id = profiles.current_title_id
    )
  )
);

grant update (name, phone_number, avatar_url, current_title_id)
on public.profiles to authenticated;

create policy "Admins can view all profiles"
on public.profiles for select to authenticated
using (public.is_admin());

create policy "Active titles are public"
on public.titles for select to anon, authenticated
using (is_active = true or public.is_admin());

create policy "Active waste categories are public"
on public.waste_categories for select to anon, authenticated
using (is_active = true or public.is_admin());

create policy "Users can view their own reports"
on public.reports for select to authenticated
using (user_id = (select auth.uid()) or public.is_admin());

create policy "Users can view their own report analyses"
on public.ai_analyses for select to authenticated
using (
  public.is_admin()
  or exists (
    select 1 from public.reports
    where reports.report_id = ai_analyses.report_id
      and reports.user_id = (select auth.uid())
  )
);

create policy "Users can view their report validations"
on public.report_validations for select to authenticated
using (
  public.is_admin()
  or exists (
    select 1 from public.reports
    where reports.report_id = report_validations.report_id
      and reports.user_id = (select auth.uid())
  )
);

create policy "Users can view their report status history"
on public.report_status_history for select to authenticated
using (
  public.is_admin()
  or exists (
    select 1 from public.reports
    where reports.report_id = report_status_history.report_id
      and reports.user_id = (select auth.uid())
  )
);

create policy "Active reward rules are public"
on public.reward_rules for select to anon, authenticated
using (is_active = true or public.is_admin());

create policy "Users can view their reward transactions"
on public.reward_transactions for select to authenticated
using (user_id = (select auth.uid()) or public.is_admin());

create policy "Active achievements are public"
on public.achievements for select to anon, authenticated
using (is_active = true or public.is_admin());

create policy "Users can view their achievements"
on public.user_achievements for select to authenticated
using (user_id = (select auth.uid()) or public.is_admin());

create policy "Users can view their titles"
on public.user_titles for select to authenticated
using (user_id = (select auth.uid()) or public.is_admin());

create policy "Published education is public"
on public.educational_content for select to anon, authenticated
using (status = 'published' or public.is_admin());

create policy "Admins can create education"
on public.educational_content for insert to authenticated
with check (public.is_admin() and created_by = (select auth.uid()));

create policy "Admins can update education"
on public.educational_content for update to authenticated
using (public.is_admin())
with check (public.is_admin());

create policy "Admins can delete education"
on public.educational_content for delete to authenticated
using (public.is_admin());

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'report-images',
  'report-images',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Guests can upload report images" on storage.objects;
create policy "Guests can upload report images"
on storage.objects for insert to anon
with check (
  bucket_id = 'report-images'
  and (storage.foldername(name))[1] = 'guest'
);

drop policy if exists "Users can upload report images" on storage.objects;
create policy "Users can upload report images"
on storage.objects for insert to authenticated
with check (
  bucket_id = 'report-images'
  and (storage.foldername(name))[1] = (select auth.uid())::text
);

drop policy if exists "Users and admins can view report images" on storage.objects;
create policy "Users and admins can view report images"
on storage.objects for select to authenticated
using (
  bucket_id = 'report-images'
  and (
    owner_id = (select auth.uid())::text
    or public.is_admin()
  )
);

drop policy if exists "Users can remove their unsubmitted report images" on storage.objects;
create policy "Users can remove their unsubmitted report images"
on storage.objects for delete to authenticated
using (
  bucket_id = 'report-images'
  and owner_id = (select auth.uid())::text
);

do $$
declare
  profile_record record;
begin
  for profile_record in select id from public.profiles where role = 'user'
  loop
    perform public.refresh_user_rewards(profile_record.id);
  end loop;
end;
$$;
