# Smart Document Finder 3.1 — Indic Multilingual Edition

A local-first PySide6 desktop document finder with OCR, FTS5 search, live indexing, recent-document history and an Indian-language service layer.

## What this version adds

- Language selector with Auto Detect plus English and the 22 scheduled Indian languages.
- Provider abstraction: `sarvam`, `bhashini`, or `none/local`.
- Sarvam REST integration for language identification, translation, speech-to-text and text-to-speech. Transliteration remains available for non-critical UI/voice use.
- Generic BHASHINI pipeline adapter with service IDs kept in environment variables.
- Strict multilingual document flow: detect → translate to English → extract document name only → search/fetch.
- Code-mix friendly voice path when the Sarvam provider is configured.
- Indic-script detection fallback when remote language detection is unavailable.
- Safer multilingual OCR configuration that uses only Tesseract language packs actually installed.
- Asynchronous search/language processing so remote API calls do not block the PySide6 UI.
- Provider/API smoke-test scripts and a setup checker.
- Minimal search-first UI: no folder picker, no speak-result control, and a collapsible Recent panel.
- The document folder is supplied in the terminal when starting the app.

## Provider choice

### Recommended first setup: Sarvam

Set in `.env`:

```text
LANGUAGE_PROVIDER=sarvam
SARVAM_API_KEY=your_key
```

Sarvam currently documents REST endpoints for:

- `POST /text-lid` for language identification
- `POST /translate` for translation
- `POST /transliterate` for script conversion
- `POST /speech-to-text` for speech recognition
- `POST /text-to-speech` for speech output

The provider layer uses these endpoints and keeps API keys out of source code.

### BHASHINI

Set:

```text
LANGUAGE_PROVIDER=bhashini
BHASHINI_API_KEY=your_key
```

Then fill in the service IDs discovered from your selected BHASHINI pipelines:

```text
BHASHINI_TRANSLATION_SERVICE_ID=
BHASHINI_ASR_SERVICE_ID=
BHASHINI_TTS_SERVICE_ID=
BHASHINI_LID_SERVICE_ID=
BHASHINI_TRANSLITERATION_SERVICE_ID=
```

Do not copy service IDs from an old tutorial blindly; choose the current pipeline/model from the BHASHINI developer portal.

## Windows setup

1. Install Python 3.11.
2. Install Tesseract OCR and the Indic language packs you intend to OCR.
3. Open the extracted project folder in VS Code.
4. Create the environment:

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

5. Copy `.env.example` to `.env`.
6. Add your provider API key.
7. Run the setup check:

```powershell
python scripts/check_setup.py
```

8. Start the app. The terminal will ask for the document folder:

```powershell
python app.py
```

Or supply the folder directly:

```powershell
python app.py "C:\Users\YourName\Documents"
```

For a full rebuild of the index:

```powershell
python app.py "C:\Users\YourName\Documents" --reindex
```

`run.ps1` and `run.bat` forward the same arguments to `app.py`. The desktop UI intentionally does not contain a folder picker.

## Tesseract

The application reads `TESSERACT_CMD` and `OCR_LANGUAGES` from `.env`.
Only languages installed in your local Tesseract installation are used. For a first Indic rollout, install English, Hindi, Marathi, Gujarati, Tamil, Telugu, Kannada, Malayalam, Bengali, Punjabi, Odia and Assamese packs and configure:

```text
OCR_LANGUAGES=eng+hin+mar+guj+tam+tel+kan+mal+ben+pan+ori+asm
```

## API smoke test

After adding your key:

```powershell
python scripts/test_remote_language_services.py
```

This tests LID, translation, transliteration and TTS. Voice STT requires a real microphone recording, so test it through the application or with your own audio fixture.

## Search flow

A document request now follows one strict path:

```text
user text / voice
    ↓
language detection
    ↓
translate the request to English
    ↓
extract ONLY the document name (plus grade/year constraints)
    ↓
match that document against local files and, when configured, DigiLocker issued documents
    ↓
fetch/open only the matched document
```

For DigiLocker, the app searches the authenticated user's already-issued-document list and downloads only the selected URI. It does not invent issuer-specific identifiers.

The document itself is not translated just to make search work. Original OCR/text remains local; translation is primarily used to normalize the user's request. This avoids sending an entire personal document library to a translation service.

## DigiLocker configuration (original desktop client)

The original PySide6 desktop client can optionally use a manually configured `DIGILOCKER_ACCESS_TOKEN`. This is separate from the browser portal's user-by-user OAuth connection described in **DigiLocker connection setup** below. Do not use one shared access token for a multi-user public web service.

Pulling a new issuer document is deliberately separate because issuers can require different parameters and explicit user consent. The project exposes discovery/pull methods but does not guess identity fields.

## Important production note

For a desktop prototype, `.env` is convenient. For a product distributed to many users, do not embed provider or DigiLocker client secrets in the executable. Put credentialed calls behind a backend or a properly registered OAuth desktop integration, and apply user-level authentication, rate limits and audit logging.

## Tests

```powershell
pytest -q
pytest --cov=. --cov-report=term-missing
```

The test suite is offline-safe: external language APIs, DigiLocker calls, OCR, and microphone-dependent paths are mocked or covered with deterministic unit tests.

The PostgreSQL integration test is enabled when `TEST_POSTGRES_URL` is set; otherwise it is skipped so the normal unit suite does not require a running server.


## Browser deployment (Render)

The project contains two entry points: `app.py` for the original PySide6 desktop application and `web_app.py` for the multi-user browser portal. Render should deploy the Dockerfile, which starts `gunicorn` with `web_app:app`; it must not run `pytest` as the container's start command.

### Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:WEB_APP_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:DOCUMENT_FOLDER = "$PWD\documents"
python web_app.py
```

Open `http://localhost:5000/signup`, create a personal account, and sign in with your username/email and password. Each account has a private document workspace; DigiLocker is connected by user authorization when approved requester credentials are configured.

### Render setup

1. Connect the repository to a Render **Web Service** and choose Docker.
2. Set `WEB_APP_SECRET_KEY` to a strong, persistent random secret. Do not rotate it while encrypted DigiLocker tokens remain stored, unless users will reconnect.
3. Add a PostgreSQL database and set `DATABASE_URL` to its internal connection URL.
4. Configure a persistent disk for `/documents` and `/app/data` if your Render plan supports the required mounts; without persistent file storage, downloaded documents and the local SQLite search index can be lost on redeploy.
5. Configure DigiLocker credentials only after the requester integration has been approved; see “DigiLocker connection setup” below.

Do not add secrets, `.env` files, user documents, or runtime database files to GitHub.

### Docker local run

```powershell
docker build -t smart-document-finder .
docker run --rm -p 10000:10000 `
  -e WEB_APP_SECRET_KEY="replace-with-a-long-random-secret" `
  -e DOCUMENT_FOLDER=/documents `
  -e SMARTDOCUMENT_DATA_DIR=/app/data `
  -v "${PWD}\documents:/documents" `
  -v "${PWD}\data:/app/data" `
  smart-document-finder
```

Open `http://localhost:10000`. For tests, use `docker run --rm --entrypoint pytest smart-document-finder -q`.

## UI behavior

- Search Results are hidden when the app starts.
- A successful search automatically opens the results drawer.
- The `Recent` button toggles the results drawer; clicking it again hides the drawer.
- `Speak Result`, `Open Folder`, and `Rebuild Index` are intentionally removed from the UI.
- Document-folder selection is terminal-only to keep the UI focused on search.

## Main folders

```text
language/     language codes, script detection, query preparation
services/     provider adapters and speech services
ui/           PySide6 interface and voice handling
extraction/  document extraction/OCR helpers
storage/      SQLite data layer
scripts/      setup and API smoke tests
data/         generated local index (not distributed)
```

### Voice Search Reliability

The 3.3.3 build retains the microphone capture fix and standard voice diagnostic. Voice input now calibrates the microphone, records a bounded phrase, validates the captured audio, creates a standard 16 kHz/16-bit WAV for remote STT, and falls back to Google recognition for common English/Hindi cases when the configured provider is unavailable.

Run `python scripts/test_microphone.py` to list microphone devices and verify capture before troubleshooting STT credentials. See `VOICE_SETUP.md` for optional `AUDIO_DEVICE_INDEX` and voice timing settings.

## v3.3.3 — Activity, Session Status & PostgreSQL

The document index remains local SQLite/FTS5 because it indexes files that live on the user's machine. User activity and history are PostgreSQL-backed when `DATABASE_URL` points to PostgreSQL; otherwise the application uses the existing local SQLite activity store as a development fallback.

The PostgreSQL `activity_history` schema stores login/logout times, session PASS/FAIL status, searches, document opens, errors and audit events. API keys and document contents are not written to history.

Set:

```text
DATABASE_BACKEND=postgresql
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/smartdocumentfinder
```

See `POSTGRESQL_SETUP.md` for setup and migration of existing local history.

Use **History** in the application to inspect Search History, Document History and Sessions. Search-history entries can be double-clicked to run again, and the full history can be exported to JSON.

The existing local document index, FTS5 search and multilingual/DigiLocker flow are preserved.



## Multi-user browser portal (v3.4.0-web)

The browser app is served by `web_app.py`; keep `app.py` for the PySide6 desktop client. The portal provides individual sign-up/login (Werkzeug password hashes), a separate document directory per account, personal search and audit history, a timeline based on dates and nearby evidence extracted from documents, and browser-based voice input using the Web Speech API where the browser supports it.

### Local browser run

1. Create a virtual environment and install `requirements.txt`.
2. Set `WEB_APP_SECRET_KEY` to a long random secret. For example: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Set `DOCUMENT_FOLDER` to a directory writable by the process, then run `python -m flask --app web_app run --host 127.0.0.1 --port 5000` or `python web_app.py`.
4. Visit `/signup` and create a personal account. Use the account's username or email and password at `/login`.

### Render and persistent data

The Dockerfile starts Gunicorn with `web_app:app`. Configure `WEB_APP_SECRET_KEY` and connect `DATABASE_URL` (or `WEB_PORTAL_DATABASE_URL`) to PostgreSQL for durable accounts, per-user metadata, timeline entries and audit history. For the local document index and downloaded document files, mount persistent storage at `/app/data` and `/documents` when the Render service/plan supports persistent disks. Without persistent storage, local files and the SQLite search index may disappear when an instance is replaced. Do not bundle `data/documents.db`, user documents, `.env`, or credentials into Git.

### DigiLocker connection setup

SmartDocumentFinder does not ask for or store a DigiLocker password. The user starts OAuth authorization at DigiLocker and returns to `/digilocker/callback`; access tokens are encrypted in the portal database using a key derived from the persistent `WEB_APP_SECRET_KEY`. Register SmartDocumentFinder as an approved DigiLocker Requester through the [official API Setu partner portal](https://api.apisetu.gov.in/), obtain credentials, and register the exact HTTPS callback URL before enabling a real connection. The official [Authorized Partner API Specification v2.0](https://meripehchaan.gov.in/assets/img/chose/Digital%20Locker%20Authorized%20Partner%20API%20Specification%20v2.0.pdf) documents the `/public/oauth2/1/authorize` authorization endpoint, `/public/oauth2/2/token` code exchange, `/public/oauth2/2/files/issued` issued-document list, `/public/oauth2/1/file/{uri}` document retrieval, and `/public/oauth2/1/revoke` token revocation. Configure `DIGILOCKER_CLIENT_ID`, `DIGILOCKER_CLIENT_SECRET`, `DIGILOCKER_REDIRECT_URI`, `DIGILOCKER_AUTHORIZE_URL`, `DIGILOCKER_TOKEN_URL`, and `DIGILOCKER_API_BASE_URL` in Render to exactly match the approved requester environment. PKCE is enabled by default (`DIGILOCKER_USE_PKCE=true`); the supported partner specification documents `S256`. The integration cannot be verified live without approved credentials and an authorization granted by a test user.

The sync action runs in a background thread and fetches available issued-document records plus self-uploaded files exposed by the authorized DigiLocker files API, up to `DIGILOCKER_SYNC_MAX_NEW_DOCUMENTS` new download attempts per run (default 500). If the partner configuration cannot list self-uploaded files, that limitation is shown as a partial sync rather than silently reported as complete. Each file download is streamed to a temporary file, capped at `DIGILOCKER_MAX_DOCUMENT_BYTES` (default 50 MiB), and HMAC-verified when DigiLocker supplies an HMAC header. The dashboard shows persistent per-account progress; records already fetched for that account are skipped, and the user can run another sync if the configured safety cap is reached. User files and each account's isolated full-text/FTS index are stored below `DOCUMENT_FOLDER/users/<user_id>/`. Search queries, account events, document opens and fetch outcomes are recorded under the owning account. Timeline items preserve an evidence excerpt and source document; inferred titles are descriptive candidates, not independent verification of the event. Set `ADMIN_USERNAMES` to a comma-separated allowlist of registered SmartDocumentFinder usernames to expose the system-wide metadata-only `/admin/audit` page; only explicitly listed accounts can open it.

### Voice assistant

The microphone button uses the browser's SpeechRecognition/Web Speech API when supported (typically a current Chromium-based browser over HTTPS). Speech is transcribed in the browser, then sent as the same query as typed search. The browser's speech recognition availability/processing depends on the browser and its policies; this is separate from the Sarvam/Bhashini API credentials used for language-provider features.

### Important limitations

- DigiLocker access is consent-based and available only after requester-partner approval and API setup. A successful website deploy does not mean partner access is active.
- This web version does not yet provide password-reset email, multi-factor authentication, a user-facing deletion/export center, or an external durable job queue. The current background worker is an in-process thread and the Dockerfile intentionally runs one Gunicorn worker; a process restart can interrupt an active sync (the UI marks a stale job and allows retry). Keep access restricted while handling sensitive documents and add these controls before broad public rollout.
- Use HTTPS, a strong persistent `WEB_APP_SECRET_KEY`, PostgreSQL, persistent document storage, and least-privilege database credentials in production.
