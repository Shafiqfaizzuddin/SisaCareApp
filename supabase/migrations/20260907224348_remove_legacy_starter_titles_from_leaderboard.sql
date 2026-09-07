update public.profiles
set title = 'No title yet',
    current_title_id = null,
    updated_at = timezone('utc', now())
where points = 0;

delete from public.achievements
where is_active = false
  and achievement_name in ('First Step', 'Clean Streets', 'Waste Watcher', 'Community Guardian');

delete from public.titles
where is_active = false
  and title_name in ('Community Starter', 'Neighbourhood Scout', 'Waste Watcher', 'Community Guardian');

create or replace view public.leaderboard_view
with (security_invoker = true, security_barrier = true)
as
select profiles.id as user_id,
       profiles.name as full_name,
       profiles.points as total_points,
       profiles.valid_reports as valid_report_count,
       count(reports.report_id)::integer as total_report_count,
       case
         when profiles.points < 10 then 'No title yet'
         else coalesce(titles.title_name, profiles.title, 'No title yet')
       end as current_title,
       dense_rank() over (order by profiles.points desc, profiles.created_at) as points_rank,
       dense_rank() over (order by profiles.valid_reports desc, profiles.created_at) as reports_rank
from public.profiles
left join public.reports on reports.user_id = profiles.id
left join public.titles on titles.title_id = profiles.current_title_id and titles.is_active = true
where profiles.role = 'user'
  and profiles.is_active = true
group by profiles.id, titles.title_name;

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

grant select on public.leaderboard_view to anon, authenticated;
grant select on public.my_impact to authenticated;