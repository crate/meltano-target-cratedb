# Changelog for Meltano/Singer Target for CrateDB

## In progress
- Downgraded to `requests` 0.32, to fix `NameError: name 'RequestsCookieJar' is not defined`

## 2026-04-22 v0.1.0
- Meltano: Started using `SQLConnector.jsonschema_to_sql` to map
  schema types to SQL types
- Type mapping: Started to verify mapping `ARRAY(OBJECT)` works well

## 2026-01-23 v0.0.2
- Added support for container types `ARRAY` and `OBJECT`.
- Improved write operations to be closer to `target-postgres`.
- Switched to new SQLAlchemy dialect for CrateDB.
- Removed workaround for `_`-prefixed column names.
  The package now requires CrateDB 6.2 or higher.
- Updated to vanilla `meltanolabs-target-postgres` 0.6.

## 2023-12-08 v0.0.1
- Make it work. It can run the canonical Meltano GitHub -> DB example.
