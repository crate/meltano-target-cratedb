# Changelog for Meltano/Singer Target for CrateDB

## In progress
- Added support for container types `ARRAY` and `OBJECT`.
- Improved write operations to be closer to `target-postgres`.
- Switched to new SQLAlchemy dialect for CrateDB.
- Removed workaround for `_`-prefixed column names.
  The package now requires CrateDB 6.2 or higher.
- Updated to vanilla `meltanolabs-target-postgres` 0.6.

## 2023-12-08 v0.0.1
- Make it work. It can run the canonical Meltano GitHub -> DB example.
