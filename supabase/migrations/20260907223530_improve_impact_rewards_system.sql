alter table public.reports
  add column if not exists duplicate_of_report_id uuid references public.reports(report_id) on delete set null,
  add column if not exists duplicate_status text not null default 'unique',
  add column if not exists suspicious_status text not null default 'clear',
  add column if not exists suspicious_reason text,
  add column if not exists is_clear_photo boolean,
  add column if not exists has_accurate_location boolean,
  add column if not exists has_useful_description boolean,
  add column if not exists quality_score integer not null default 0,
  add column if not exists points_awarded integer not null default 0;

alter table public.reports
  drop constraint if exists reports_duplicate_status_check,
  add constraint reports_duplicate_status_check
    check (duplicate_status in ('unique', 'possible_duplicate', 'confirmed_duplicate'));

alter table public.reports
  drop constraint if exists reports_suspicious_status_check,
  add constraint reports_suspicious_status_check
    check (suspicious_status in ('clear', 'suspicious', 'confirmed_fake'));

alter table public.reports
  drop constraint if exists reports_quality_score_check,
  add constraint reports_quality_score_check check (quality_score >= 0 and quality_score <= 15);

alter table public.reports
  drop constraint if exists reports_points_awarded_check,
  add constraint reports_points_awarded_check check (points_awarded >= 0);

alter table public.reward_rules drop constraint if exists reward_rules_reward_type_check;
alter table public.reward_rules
  add constraint reward_rules_reward_type_check
    check (reward_type in (
      'report_submitted',
      'valid_report',
      'admin_validation_bonus',
      'clear_photo',
      'accurate_location',
      'useful_description',
      'case_completed',
      'duplicate_confirmation',
      'achievement_bonus',
      'manual_adjustment'
    ));

insert into public.reward_rules (rule_name, reward_type, points, is_active)
values
  ('Registered report received', 'report_submitted', 0, true),
  ('Valid report', 'valid_report', 20, true),
  ('Admin validation bonus', 'admin_validation_bonus', 10, true),
  ('Clear photo', 'clear_photo', 5, true),
  ('Accurate location', 'accurate_location', 5, true),
  ('Useful description', 'useful_description', 5, true),
  ('Report eventually completed', 'case_completed', 10, true),
  ('Duplicate incident confirmation', 'duplicate_confirmation', 3, true),
  ('Achievement milestone bonus', 'achievement_bonus', 0, true),
  ('Manual adjustment', 'manual_adjustment', 0, true)
on conflict (reward_type) do update
set rule_name = excluded.rule_name,
    points = excluded.points,
    is_active = excluded.is_active,
    updated_at = timezone('utc', now());

insert into public.titles (title_name, description, minimum_points, is_active)
values
  ('New Reporter', 'Submitted a first validated environmental report.', 10, true),
  ('Eco Reporter', 'Building a verified record of community reports.', 100, true),
  ('Community Helper', 'Consistently helping improve local public spaces.', 300, true),
  ('Waste Guardian', 'A trusted reporter with strong verified impact.', 750, true),
  ('Community Champion', 'A leading contributor to municipal cleanup outcomes.', 1500, true),
  ('Environmental Guardian', 'An elite contributor protecting the environment at scale.', 3000, true)
on conflict (title_name) do update
set description = excluded.description,
    minimum_points = excluded.minimum_points,
    is_active = true;

update public.titles
set is_active = false
where title_name not in (
  'New Reporter',
  'Eco Reporter',
  'Community Helper',
  'Waste Guardian',
  'Community Champion',
  'Environmental Guardian'
);

insert into public.achievements (achievement_name, description, criteria_type, criteria_value, bonus_points, title_id, is_active)
select seed.achievement_name,
       seed.description,
       'points',
       seed.criteria_value,
       0,
       titles.title_id,
       true
from (values
  ('New Reporter', 'Earn 10 points from validated waste reports.', 10),
  ('Eco Reporter', 'Earn 100 points from validated waste reports.', 100),
  ('Community Helper', 'Earn 300 points from validated waste reports.', 300),
  ('Waste Guardian', 'Earn 750 points from validated waste reports.', 750),
  ('Community Champion', 'Earn 1,500 points from validated waste reports.', 1500),
  ('Environmental Guardian', 'Earn 3,000 points from validated waste reports.', 3000)
) as seed(achievement_name, description, criteria_value)
join public.titles on titles.title_name = seed.achievement_name
on conflict (achievement_name) do update
set description = excluded.description,
    criteria_type = excluded.criteria_type,
    criteria_value = excluded.criteria_value,
    bonus_points = excluded.bonus_points,
    title_id = excluded.title_id,
    is_active = true;

update public.achievements
set is_active = false
where achievement_name not in (
  'New Reporter',
  'Eco Reporter',
  'Community Helper',
  'Waste Guardian',
  'Community Champion',
  'Environmental Guardian'
);

create table if not exists public.user_notifications (
  notification_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  report_id uuid references public.reports(report_id) on delete set null,
  notification_type text not null,
  title text not null,
  body text not null,
  is_read boolean not null default false,
  created_at timestamp with time zone not null default timezone('utc', now()),
  constraint user_notifications_notification_type_check check (notification_type in ('impact'))
);

alter table public.user_notifications enable row level security;

drop policy if exists "Users can view their notifications" on public.user_notifications;
create policy "Users can view their notifications"
  on public.user_notifications
  for select
  to authenticated
  using (user_id = (select auth.uid()) or public.is_admin());

drop policy if exists "Users can mark their notifications read" on public.user_notifications;
create policy "Users can mark their notifications read"
  on public.user_notifications
  for update
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

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
  select coalesce(sum(points), 0)::integer into total
  from public.reward_transactions
  where user_id = target_user_id;

  select count(*)::integer into valid_count
  from public.reports
  where user_id = target_user_id
    and validation_status = 'valid'
    and duplicate_status <> 'confirmed_duplicate';

  update public.profiles
  set points = total,
      valid_reports = valid_count,
      updated_at = timezone('utc', now())
  where id = target_user_id;

  select reward_rule_id into bonus_rule_id
  from public.reward_rules
  where reward_type = 'achievement_bonus' and is_active = true
  limit 1;

  for achievement_record in
    insert into public.user_achievements (user_id, achievement_id)
    select target_user_id, achievement_id
    from public.achievements
    where is_active = true
      and (
        (criteria_type = 'points' and total >= criteria_value)
        or (criteria_type = 'valid_reports' and valid_count >= criteria_value)
      )
    on conflict (user_id, achievement_id) do nothing
    returning achievement_id
  loop
    insert into public.user_titles (user_id, title_id)
    select target_user_id, title_id
    from public.achievements
    where achievement_id = achievement_record.achievement_id
      and title_id is not null
    on conflict (user_id, title_id) do nothing;

    if bonus_rule_id is not null then
      insert into public.reward_transactions (user_id, reward_rule_id, achievement_id, points, description)
      select target_user_id,
             bonus_rule_id,
             achievement_id,
             bonus_points,
             'Achievement unlocked: ' || achievement_name
      from public.achievements
      where achievement_id = achievement_record.achievement_id
        and bonus_points > 0
      on conflict do nothing;
    end if;
  end loop;

  select coalesce(sum(points), 0)::integer into total
  from public.reward_transactions
  where user_id = target_user_id;

  insert into public.user_titles (user_id, title_id)
  select target_user_id, title_id
  from public.titles
  where is_active = true and minimum_points <= total
  on conflict (user_id, title_id) do nothing;

  select title_id, title_name into selected_title
  from public.titles
  where is_active = true and minimum_points <= total
  order by minimum_points desc
  limit 1;

  update public.profiles
  set points = total,
      valid_reports = valid_count,
      current_title_id = selected_title.title_id,
      title = coalesce(selected_title.title_name, 'No title yet'),
      updated_at = timezone('utc', now())
  where id = target_user_id;
end;
$$;

create or replace function public.admin_confirm_duplicate_report(target_report_id uuid, original_report_id uuid, note text default null)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  admin_user_id uuid := (select auth.uid());
  target_report public.reports%rowtype;
  original_report public.reports%rowtype;
begin
  if not public.is_admin() then
    raise exception 'Administrator access is required.';
  end if;

  if target_report_id = original_report_id then
    raise exception 'A report cannot be marked as a duplicate of itself.';
  end if;

  select * into target_report from public.reports where report_id = target_report_id for update;
  if target_report.report_id is null then
    raise exception 'Duplicate report not found.';
  end if;
  if target_report.validation_status <> 'pending' then
    raise exception 'This report already has a final validation decision.';
  end if;

  select * into original_report from public.reports where report_id = original_report_id;
  if original_report.report_id is null then
    raise exception 'Original report not found.';
  end if;

  insert into public.report_validations (report_id, admin_id, validation_status, validation_note)
  values (target_report_id, admin_user_id, 'valid', coalesce(nullif(trim(note), ''), 'Confirmed as a duplicate incident report.'));

  update public.reports
  set validation_status = 'valid',
      duplicate_status = 'confirmed_duplicate',
      duplicate_of_report_id = original_report_id,
      case_status = original_report.case_status,
      quality_score = 0
  where report_id = target_report_id;

  if target_report.user_id is not null then
    insert into public.reward_transactions (user_id, report_id, reward_rule_id, points, description)
    select target_report.user_id, target_report_id, reward_rule_id, points, rule_name
    from public.reward_rules
    where reward_type = 'duplicate_confirmation' and is_active = true and points <> 0
    on conflict do nothing;

    update public.reports
    set points_awarded = coalesce((select sum(points)::integer from public.reward_transactions where report_id = target_report_id), 0)
    where report_id = target_report_id;

    perform public.refresh_user_rewards(target_report.user_id);
  end if;
end;
$$;

create or replace view public.my_impact
with (security_invoker = true)
as
select
  profiles.id as user_id,
  profiles.points as total_points,
  profiles.valid_reports as verified_reports,
  coalesce(resolved_stats.cases_resolved, 0)::integer as cases_resolved,
  coalesce(active_stats.locations_currently_handled, 0)::integer as locations_currently_handled,
  coalesce(achievement_stats.achievements_unlocked, 0)::integer as achievements_unlocked,
  case
    when profiles.points < 10 then 'No title yet'
    else coalesce(titles.title_name, profiles.title, 'No title yet')
  end as current_title,
  coalesce(notification_stats.unread_impact_notifications, 0)::integer as unread_impact_notifications
from public.profiles
left join public.titles on titles.title_id = profiles.current_title_id and titles.is_active = true
left join lateral (
  select count(*)::integer as cases_resolved
  from public.reports
  where reports.user_id = profiles.id
    and reports.validation_status = 'valid'
    and reports.case_status = 'completed'
    and reports.duplicate_status <> 'confirmed_duplicate'
) resolved_stats on true
left join lateral (
  select count(distinct coalesce(
    case
      when reports.latitude is not null and reports.longitude is not null
        then round(reports.latitude, 4)::text || ',' || round(reports.longitude, 4)::text
      else null
    end,
    lower(trim(reports.location_address)),
    reports.report_id::text
  ))::integer as locations_currently_handled
  from public.reports
  where reports.user_id = profiles.id
    and reports.validation_status = 'valid'
    and reports.case_status in ('processing', 'in_progress')
    and reports.duplicate_status <> 'confirmed_duplicate'
) active_stats on true
left join lateral (
  select count(*)::integer as achievements_unlocked
  from public.user_achievements
  where user_achievements.user_id = profiles.id
) achievement_stats on true
left join lateral (
  select count(*)::integer as unread_impact_notifications
  from public.user_notifications
  where user_notifications.user_id = profiles.id
    and user_notifications.notification_type = 'impact'
    and user_notifications.is_read = false
) notification_stats on true
where profiles.id = (select auth.uid());

grant select on public.my_impact to authenticated;