# Smart Document Finder 3.3.3 — Final Hardening

## Targeted fixes

### Voice document fetching
- Sarvam Saaras v4 now uses `translate` mode first for document-retrieval voice requests.
- `codemix` and `transcribe` remain as provider fallbacks.
- Microphone capture no longer forces an arbitrary device sample rate; `AUDIO_SAMPLE_RATE` is optional.
- Captured audio is normalized to 16 kHz / 16-bit WAV before remote STT.
- Empty/near-silent recordings are rejected with actionable messages.
- Voice mode configuration and malformed microphone settings are handled safely.
- Sarvam keyterm prompting is only sent for Saaras v4.
- Live Sarvam STT diagnostic script follows the same translation-first path.

### PostgreSQL activity database
- Added PostgreSQL-backed activity/history storage using SQLAlchemy + psycopg v3.
- Added `DATABASE_BACKEND` and `DATABASE_URL` configuration.
- Automatic backend selection: PostgreSQL when configured, existing SQLite fallback otherwise.
- Local document indexing remains SQLite/FTS5 because it references files on the local filesystem.
- Added PostgreSQL schema and indexes for activity history.
- Added explicit migration utility for existing SQLite `activity_history`.
- Added clear startup error when PostgreSQL is selected but cannot be initialized.
- Existing SQLite history migration behavior remains intact for backward compatibility.

### History UI
- Fixed document-history timestamp handling so both SQLite and PostgreSQL backends work.
- Existing History, Search History, Document History, Sessions, repeat-search, and JSON export behavior is preserved.

### Testing
- Added PostgreSQL backend-selection and routing tests.
- Added parameterization and PostgreSQL history-store unit tests with a deterministic fake engine.
- Added Sarvam voice-mode regression tests.
- Existing multilingual, DigiLocker, indexer, OCR, search, and history tests remain in place.
- `pytest -q` passes in the available runtime; tests requiring unavailable local GUI/microphone dependencies or a live PostgreSQL server are explicitly skipped.

## Important configuration

Copy `.env.example` to `.env`.

For PostgreSQL:

```text
DATABASE_BACKEND=postgresql
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/smartdocumentfinder
```

Then run:

```powershell
python scripts/check_setup.py
python scripts/migrate_sqlite_history_to_postgres.py
pytest -q
python app.py "C:\path\to\documents" --reindex
```

Do not commit `.env` or real API keys.
