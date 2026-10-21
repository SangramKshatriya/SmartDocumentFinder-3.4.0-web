# SmartDocumentFinder Web Portal — Render Deployment

This deploys the **browser portal** (`web_app.py`). The original PySide6 desktop app (`app.py`) remains in the repository but is not the Render web entry point.

## 1. Push the complete project

The GitHub repository root should contain `Dockerfile`, `web_app.py`, `app.py`, `requirements.txt`, `requirements-dev.txt`, `templates/`, `static/`, `services/`, and `tests/`. If the repository only shows a few README/metadata files, the source project was not committed from the correct folder.

## 2. Create or update the Render Web Service

- Runtime: **Docker**.
- Dockerfile path: `./Dockerfile`.
- Root directory: leave blank when the Dockerfile is at the repository root.
- Start command: leave blank so Render uses the Dockerfile `CMD`. Do not set it to `pytest`, `python app.py`, or a PySide6 desktop command.
- Health check path (optional): `/health`.

The Dockerfile runs the tests during image build and starts Gunicorn bound to `0.0.0.0:$PORT`.

## 3. Configure persistent data

Recommended for real user accounts and personal documents:

1. Create a Render PostgreSQL database and copy its **internal** connection URL.
2. Set `WEB_PORTAL_DATABASE_URL` to that URL (or use `DATABASE_URL` if you intentionally want to share a database). PostgreSQL stores accounts, login sessions, audit events, document metadata, sync job progress, searches, and timeline entries.
3. Attach a persistent disk to the web service mounted at `/documents`. The downloaded documents and each user's SQLite full-text index are stored below `/documents/users/<user_id>/`.

If `/documents` is not persistent, downloaded files and the per-user search indexes can disappear when Render replaces the instance. If no PostgreSQL URL is configured, the portal falls back to `/app/data/web_portal.db`, which is not durable without a persistent disk on `/app/data`.

## 4. Required environment variables

Add these under **Render → service → Environment**. Generate values privately; never commit them to GitHub.

| Key | Value |
|---|---|
| `WEB_APP_SECRET_KEY` | Long random secret; keep stable across deploys because it signs sessions and encrypts stored OAuth tokens. |
| `SESSION_COOKIE_SECURE` | `true` |
| `DOCUMENT_FOLDER` | `/documents` |
| `WEB_PORTAL_DATABASE_URL` | PostgreSQL internal URL (recommended) |
| `LANGUAGE_PROVIDER` | `local`, `sarvam`, or `bhashini` depending on configured services |

Generate a secret on your own computer with PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output into `WEB_APP_SECRET_KEY` as a secret environment value. Do not paste the output into a public chat or a source file.

For a first deploy before DigiLocker partner approval, leave the `DIGILOCKER_*` client credential values empty. The web application and sign-up/login can be tested, but real document fetching will remain disabled.

## 5. Enable DigiLocker only after requester approval

DigiLocker access is **not** enabled merely by deploying the website. Register the service as an approved DigiLocker Requester through the official API Setu / DigiLocker partner process. Obtain the client credentials and exact approved scope/environment details, then set:

| Key | Value |
|---|---|
| `DIGILOCKER_CLIENT_ID` | Approved requester client ID |
| `DIGILOCKER_CLIENT_SECRET` | Approved requester client secret |
| `DIGILOCKER_REDIRECT_URI` | Exact registered HTTPS callback, e.g. `https://YOUR-SERVICE.onrender.com/digilocker/callback` |
| `DIGILOCKER_AUTHORIZE_URL` | Approved environment's authorization URL; default is in `.env.example` |
| `DIGILOCKER_TOKEN_URL` | Approved environment's token URL; default is in `.env.example` |
| `DIGILOCKER_REVOKE_URL` | Approved environment's token-revocation URL; default is in `.env.example` |
| `DIGILOCKER_API_BASE_URL` | Approved environment API base URL |
| `DIGILOCKER_SCOPES` | Scope string explicitly supplied for the requester integration |
| `DIGILOCKER_USE_PKCE` | `true` unless the approved integration instructions specify otherwise |

The website redirects users to DigiLocker for authorization. It must never ask users to type their DigiLocker password into SmartDocumentFinder. Keep the callback URL in Render identical to the URL registered with DigiLocker.

The default URLs in `.env.example` are based on the published Authorized Partner API Specification v2.0. The integration must be tested in the partner-provided test environment with approved credentials before real user documents are handled. Some API permissions may not be enabled for every requester; the dashboard reports partial sync when an allowed endpoint is unavailable.

## 6. Validate after deployment

1. Open `https://YOUR-SERVICE.onrender.com/health`; expect JSON with `"status": "ok"`.
2. Visit `/signup`, create a test account, sign out, and sign in again.
3. Confirm one account cannot access another account's document IDs or history.
4. Confirm the dashboard shows the DigiLocker setup message until client credentials and the registered callback have been configured.
5. After requester approval, authorize a designated test account, run a document sync, and inspect progress, document search, evidence-linked timeline entries, and history.
6. Restart/redeploy once in the test environment and verify that accounts, records, index files, and documents persist before production use.

## Security and production limitations

This is a functional implementation baseline, not a security certification. Before opening broadly to the public, add email verification/password reset, stronger abuse and login rate limits, account deletion/export workflows, operational monitoring, and a durable background-job system for multi-worker deployments. Treat fetched documents as sensitive personal data, restrict staff/admin access, and have appropriate legal, security, privacy, and data-retention policies in place.
