-- Forecast runs are server-written. One run stores one weekly horizon; batches
-- link successive weeks from the same reproducible training invocation.
alter table sisacare.forecast_runs add column if not exists batch_id uuid;
alter table sisacare.forecast_runs add column if not exists data_provenance text not null default 'legacy_unknown';
alter table sisacare.forecast_runs add column if not exists training_metadata jsonb not null default '{}'::jsonb;
alter table sisacare.forecast_runs add column if not exists evaluation_results jsonb not null default '{}'::jsonb;
alter table sisacare.forecast_runs add column if not exists status text not null default 'available';
create index if not exists ix_forecast_latest on sisacare.forecast_runs(data_provenance, generated_at desc);
alter table sisacare.forecast_runs enable row level security;
alter table sisacare.forecast_cells enable row level security;
revoke all on sisacare.forecast_runs, sisacare.forecast_cells from anon, authenticated;
grant select on sisacare.forecast_runs, sisacare.forecast_cells to authenticated;
create policy admin_read_forecast_runs on sisacare.forecast_runs for select to authenticated
  using (sisacare.is_admin());
create policy admin_read_forecast_cells on sisacare.forecast_cells for select to authenticated
  using (sisacare.is_admin());
