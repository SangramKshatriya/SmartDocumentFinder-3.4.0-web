# Smart Document Finder — History Tracking (v3.3.3)

## What is tracked

All activity is stored in one activity table, `activity_history`. PostgreSQL is the production/shared backend when `DATABASE_URL` is configured; the existing SQLite activity store remains available as a local-development fallback. It stores:

- Username and display name
- Login time, logout time, login status, logout status and session status
- Search query, canonical query, language, input mode, provider, document type, result count and duration
- Document-open metadata including local/DigiLocker source and action
- PASS/FAIL status, error messages, event reason and JSON details

The document index remains separate in `documents` and its FTS5 virtual table because those tables contain the searchable document corpus rather than activity logs. `app_settings` remains separate for application configuration.

## Single-table schema

`activity_history` contains the session and event fields needed by the application. A session row is created at login and updated at logout, so login and logout timestamps/statuses are available together. Search, document-open and other audit rows use the same table and reference the session with `session_id`.

Status values are explicit: `PASS`, `FAIL`, and `PENDING` for a session that is currently active. If a previous session was left open because the application did not close cleanly, the next login marks that old session as `ABNORMAL` with `logout_status = FAIL`.

## Migration

Existing pre-3.3.3 activity tables are still migrated automatically when the local SQLite activity store is used.

For an existing 3.3.3 SQLite `activity_history` database, use `scripts/migrate_sqlite_history_to_postgres.py` after configuring PostgreSQL. The migration preserves activity IDs and references and refuses to overwrite an existing PostgreSQL history table unless `--overwrite` is explicitly supplied.

The searchable local `documents`/FTS5 tables remain in SQLite because their paths point to the user's local filesystem.

## History UI

Use the **History** button to view:

- Search History
- Document History
- Sessions

The Sessions view shows Login Time, Logout Time, Login Status, Logout Status, Session Status and Reason. Search-history entries can be double-clicked to run again. History can be exported to JSON.

## Privacy design

The activity table stores document metadata and activity timestamps; it does not copy document contents into history and does not store DigiLocker access tokens.
