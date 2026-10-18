# Community and municipal migration

This migration changes application behavior, not historical ownership or
classification. Supabase user IDs, report IDs, image files, analysis drafts,
recycling actions, reward events, matric reviews, and E-Merit records remain
intact. No production Supabase role or account is changed by the code migration.

## Dependency and permission review

- Supabase `app_metadata.role` is the backend authority for an administrator.
  Student or staff metadata and email domains are never administrator grants.
- Existing `user` accounts, whether formerly labelled student or staff, use
  Community User access. Existing `admin` grants need an authorized manual
  review before any live role migration; no automatic grant is performed.
- The local identity tables contain historical Google provider subjects,
  affiliation, matric and E-Merit audits. They must be backed up and retained.
  New onboarding does not collect matric or create E-Merit claims.
- The reward ledger and recycling actions reference reports, analyses, station
  rows and image assets. Keep those rows and references. New community report
  reviews and any remaining legacy action reviews create no reward events.
- New report workflow fields and status audit records are additive. Legacy
  `in_progress` and `completed` statuses remain as stored; they are not
  silently called verified or resolved.
- Existing campus station records have no public-facility verification flag.
  Their public listing is disabled until a municipal administrator reviews
  each location, acceptance list and access information.

## Rollout

1. Back up Supabase Auth metadata and the application SQLite database and
   report assets. Record row counts and asset references.
2. Deploy the additive schema and new application while retaining the
   historical tables. Review the permission report for existing `admin` roles
   with an authorized operator before changing any live role.
3. Configure the actual Google OAuth client and Supabase provider. Test new,
   returning, linked-password, unverified and unsupported credentials.
4. Configure any real municipal routing team names and service area only after
   an authority supplies them. The application does not assume a municipal
   boundary or partnership.
5. Review station records individually before marking them public. Historical
   campus and demo stations remain private and keep their old references.
6. Reconcile report and asset counts after deployment. Test owner-only report
   access and administrator transitions on a development database copy.

No email campaign, live permission rewrite, or deletion is part of this
migration. Historical reward totals remain audit data and have no promised
monetary or municipal value.
