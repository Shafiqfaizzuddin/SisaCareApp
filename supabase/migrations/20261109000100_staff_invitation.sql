-- Keep a small, auditable display snapshot for administrator invitations.
-- Supabase Auth remains the identity authority; role_grants remains the permission authority.
alter table sisacare.role_grants add column if not exists email text;
alter table sisacare.role_grants add column if not exists display_name text;
alter table sisacare.role_grants add column if not exists invited_at timestamptz;
