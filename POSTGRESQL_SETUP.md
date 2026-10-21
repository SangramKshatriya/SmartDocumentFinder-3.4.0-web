# PostgreSQL Setup — Smart Document Finder 3.3.3 Final

## Architecture

The local document index remains SQLite + FTS5 because it indexes files that live on the
user's computer. User/session/search/document activity is stored in PostgreSQL when
`DATABASE_URL` points to PostgreSQL.

This means the application does not upload local document contents into PostgreSQL;
PostgreSQL acts as the durable activity/history database.

## Windows setup

Install PostgreSQL 16 (or another supported PostgreSQL release), then create a database
and user, for example from `psql`:

```sql
CREATE USER smartdocument WITH PASSWORD 'change-this-password';
CREATE DATABASE smartdocumentfinder OWNER smartdocument;
```

Copy `.env.example` to `.env` and set:

```text
DATABASE_BACKEND=postgresql
DATABASE_URL=postgresql+psycopg://smartdocument:change-this-password@localhost:5432/smartdocumentfinder
```

Install dependencies:

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

The application creates the `activity_history` table and indexes automatically on startup. The equivalent manual SQL is in `migrations/postgresql_activity_history.sql`.

Check the configured backend:

```powershell
python scripts/check_setup.py
```

## Migrating existing 3.3.3 local history

After PostgreSQL is running and the `.env` variables are set:

```powershell
python scripts/migrate_sqlite_history_to_postgres.py
```

By default, the script refuses to overwrite an existing PostgreSQL history table.

To intentionally replace the PostgreSQL activity table from the local SQLite history:

```powershell
python scripts/migrate_sqlite_history_to_postgres.py --overwrite
```

## Docker

The supplied `docker-compose.yml` starts both PostgreSQL and the application environment.
The application receives a PostgreSQL `DATABASE_URL` automatically.

The desktop GUI itself is normally launched on the host so it can access the user's
Windows microphone and local document folder.
