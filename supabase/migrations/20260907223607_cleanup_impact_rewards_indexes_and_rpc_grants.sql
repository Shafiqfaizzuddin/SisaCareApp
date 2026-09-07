revoke execute on function public.admin_validate_report(uuid, text, text) from anon;
revoke execute on function public.admin_validate_report(uuid, text, text) from public;
grant execute on function public.admin_validate_report(uuid, text, text) to authenticated;

revoke execute on function public.admin_update_report_status(uuid, text, text) from anon;
revoke execute on function public.admin_update_report_status(uuid, text, text) from public;
grant execute on function public.admin_update_report_status(uuid, text, text) to authenticated;

revoke execute on function public.admin_confirm_duplicate_report(uuid, uuid, text) from anon;
revoke execute on function public.admin_confirm_duplicate_report(uuid, uuid, text) from public;
grant execute on function public.admin_confirm_duplicate_report(uuid, uuid, text) to authenticated;

revoke execute on function public.refresh_user_rewards(uuid) from anon;
revoke execute on function public.refresh_user_rewards(uuid) from public;
revoke execute on function public.refresh_user_rewards(uuid) from authenticated;