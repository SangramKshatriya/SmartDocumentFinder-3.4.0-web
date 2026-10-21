"""Multi-user browser application for SmartDocumentFinder.

The PySide6 desktop application remains available through app.py. This Flask
application adds individual accounts, tenant-scoped document storage, browser
voice search, a date-evidence timeline, audit history, and an OAuth-based
DigiLocker requester connection. DigiLocker features require approved partner
credentials and a registered callback URL supplied by the operator.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import time
import threading
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import text

load_dotenv()

from config import SUPPORTED_EXTENSIONS
from content_extractor import extract_text
from database import get_document_by_path, using_database
from indexer import index_file
from language.manager import LanguageManager
from portal_store import (
    add_audit_event, add_connection, add_document, add_search, count_documents, count_timeline_events,
    create_sync_job, create_user, disconnect_provider, end_user_session, get_active_sync_job, get_connection,
    get_document, get_document_by_uri, get_engine, get_latest_sync_job, get_sync_job, get_user_by_id, get_user_by_login,
    initialize_store, list_audit_events, list_documents, list_recent_documents,
    list_all_audit_events, list_searches, list_timeline, mark_document_access, mark_user_login,
    start_user_session, update_connection_tokens, update_sync_job, user_stats, utcnow,
)
from query_processor import detect_document_type, extract_constraints
from search_engine import search_documents_multilingual
from services.digilocker_provider import DigiLockerClient
from services.provider_factory import build_provider
from timeline_builder import build_timeline_for_document

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_SYNC_THREADS: dict[int, threading.Thread] = {}
_SYNC_THREADS_LOCK = threading.Lock()
ALLOWED_EXTENSIONS = set(SUPPORTED_EXTENSIONS)
LANGUAGE_OPTIONS = [
    ("", "Auto detect"), ("en-IN", "English"), ("hi-IN", "Hindi"),
    ("bn-IN", "Bengali"), ("gu-IN", "Gujarati"), ("kn-IN", "Kannada"),
    ("ml-IN", "Malayalam"), ("mr-IN", "Marathi"), ("or-IN", "Odia"),
    ("pa-IN", "Punjabi"), ("ta-IN", "Tamil"), ("te-IN", "Telugu"),
]


def _document_root() -> Path:
    """Resolve the configured storage root at runtime (also supports tests/dev env changes)."""
    return Path(os.getenv("DOCUMENT_FOLDER", "/documents")).expanduser().resolve()


def _user_root(user_id: int) -> Path:
    """A distinct on-disk document root for every portal account."""
    return (_document_root() / "users" / str(int(user_id))).resolve()


def _user_index_path(user_id: int) -> Path:
    """Return the private full-text index path for a single portal account."""
    return _user_root(user_id) / ".index" / "documents.db"


def _safe_filename(filename: str) -> str:
    raw_name = (filename or "document").replace("\\", "/").split("/")[-1]
    normalized = unicodedata.normalize("NFKC", raw_name)
    normalized = "".join(ch for ch in normalized if ord(ch) >= 32 and ch not in "\x7f")
    normalized = normalized.strip(" .")[:180]
    # Do not allow empty, dot paths, or platform-reserved path syntax.
    normalized = re.sub(r'[<>:"|?*]', "_", normalized).strip(" .")
    return normalized or "document"


def _json_safe_item(item: dict) -> dict:
    """Keep only display metadata; never persist full issuer payloads blindly."""
    keys = ("name", "description", "issuer", "issuerName", "doctype", "docType", "date", "issuedOn", "dateissued")
    return {key: str(item.get(key, ""))[:500] for key in keys if item.get(key) is not None and str(item.get(key, "")).strip()}


def _encryption_key(app: Flask) -> bytes:
    # Derive a stable Fernet key from WEB_APP_SECRET_KEY; never use a per-process key for stored tokens.
    secret = str(app.config["SECRET_KEY"]).encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(b"SmartDocumentFinder/oauth/v1/" + secret).digest())


def _encrypt_token(app: Flask, token: str) -> str:
    return Fernet(_encryption_key(app)).encrypt(token.encode("utf-8")).decode("ascii")


def _decrypt_token(app: Flask, token: str | None) -> str:
    if not token:
        return ""
    try:
        return Fernet(_encryption_key(app)).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        raise RuntimeError("The stored DigiLocker token cannot be decrypted. Check WEB_APP_SECRET_KEY; reconnect DigiLocker after correcting it.") from None


def _digilocker_settings() -> dict[str, str]:
    return {
        "client_id": os.getenv("DIGILOCKER_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("DIGILOCKER_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("DIGILOCKER_REDIRECT_URI", "").strip(),
        "authorize_url": os.getenv("DIGILOCKER_AUTHORIZE_URL", "https://digilocker.meripehchaan.gov.in/public/oauth2/1/authorize").strip(),
        "token_url": os.getenv("DIGILOCKER_TOKEN_URL", "https://digilocker.meripehchaan.gov.in/public/oauth2/2/token").strip(),
        "revoke_url": os.getenv("DIGILOCKER_REVOKE_URL", "https://digilocker.meripehchaan.gov.in/public/oauth2/1/revoke").strip(),
        "api_base_url": os.getenv("DIGILOCKER_API_BASE_URL", os.getenv("DIGILOCKER_BASE_URL", "https://digilocker.meripehchaan.gov.in")).rstrip("/"),
        "scopes": os.getenv("DIGILOCKER_SCOPES", "").strip(),
        "use_pkce": os.getenv("DIGILOCKER_USE_PKCE", "true").strip().lower() in {"1", "true", "yes", "on"},
    }


def _digilocker_configured() -> bool:
    settings = _digilocker_settings()
    return bool(settings["client_id"] and settings["client_secret"] and settings["redirect_uri"])


def create_app() -> Flask:
    app = Flask(__name__)
    stable_secret = os.getenv("WEB_APP_SECRET_KEY") or os.getenv("SECRET_KEY")
    app.secret_key = stable_secret or secrets.token_urlsafe(48)
    app.config["SDF_STABLE_SECRET_CONFIGURED"] = bool(stable_secret)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "true" if os.getenv("RENDER") else "false").lower() == "true"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    @app.context_processor
    def inject_template_helpers():
        def csrf_token() -> str:
            token = session.get("_csrf_token")
            if not token:
                token = secrets.token_urlsafe(32)
                session["_csrf_token"] = token
            return token
        admin_names = {item.strip().lower() for item in os.getenv("ADMIN_USERNAMES", "").split(",") if item.strip()}
        return {
            "csrf_token": csrf_token,
            "digilocker_configured": _digilocker_configured(),
            "app_version": "3.4.0-web",
            "stable_secret_configured": app.config["SDF_STABLE_SECRET_CONFIGURED"],
            "is_admin": (session.get("username", "").lower() in admin_names),
        }

    @app.before_request
    def enforce_csrf_and_load_user():
        if request.method == "POST":
            expected = session.get("_csrf_token", "")
            supplied = request.form.get("_csrf_token", "")
            if not expected or not supplied or not hmac.compare_digest(expected, supplied):
                abort(400, description="The form expired or failed its security check. Refresh the page and try again.")
        user_id = session.get("user_id")
        g.current_user = get_user_by_id(int(user_id)) if user_id is not None else None
        if user_id is not None and (not g.current_user or not g.current_user.get("is_active")):
            session.clear()
            g.current_user = None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "microphone=(self)")
        if request.endpoint not in {"health", "static"}:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def login_required(view: Callable):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def current_user() -> dict:
        user = getattr(g, "current_user", None)
        if not user:
            abort(401)
        return user

    def record_event(event_type: str, status: str = "PASS", details: dict | None = None, user: dict | None = None):
        user = user or getattr(g, "current_user", None)
        add_audit_event(user.get("id") if user else None, user.get("username", "") if user else "", event_type, status, details or {})

    def owned_document_paths(user_id: int) -> tuple[set[str], dict[str, dict]]:
        root = _user_root(user_id)
        allowed: set[str] = set()
        metadata: dict[str, dict] = {}
        for doc in list_documents(user_id, limit=5000):
            try:
                path = Path(doc["path"]).resolve()
                path.relative_to(root)
            except (ValueError, OSError, KeyError):
                app.logger.warning("Ignored document path outside account root (document id=%s)", doc.get("id"))
                continue
            if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS:
                normalized = str(path)
                allowed.add(normalized)
                metadata[normalized] = doc
        return allowed, metadata

    def ensure_user_document_root(user_id: int) -> Path:
        root = _user_root(user_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @app.get("/health")
    def health():
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            app.logger.warning("Health check found the portal database unavailable")
            return {"status": "degraded", "service": "Smart Document Finder", "detail": "database_unavailable"}, 503
        return {"status": "ok", "service": "Smart Document Finder", "version": "3.4.0-web"}, 200

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if getattr(g, "current_user", None):
            return redirect(url_for("index"))
        if request.method == "POST":
            display_name = (request.form.get("display_name") or "").strip()[:120]
            username_raw = (request.form.get("username") or "").strip().lower()
            email = (request.form.get("email") or "").strip().lower()[:254]
            password = request.form.get("password") or ""
            confirmation = request.form.get("confirm_password") or ""
            username = re.sub(r"[^a-z0-9_.-]+", "", username_raw)
            if not display_name:
                flash("Enter your name.", "error")
            elif not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", username):
                flash("Choose a username 3–40 characters long using letters, numbers, dot, underscore, or hyphen.", "error")
            elif email and ("@" not in email or email.startswith("@") or email.endswith("@")):
                flash("Enter a valid email address or leave the email field blank.", "error")
            elif len(password) < 10:
                flash("Choose a password with at least 10 characters.", "error")
            elif password != confirmation:
                flash("The passwords do not match.", "error")
            else:
                try:
                    user = create_user(username, display_name, email, generate_password_hash(password))
                    session.clear()
                    session.permanent = True
                    session["_csrf_token"] = secrets.token_urlsafe(32)
                    session["user_id"] = int(user["id"])
                    session["username"] = user["username"]
                    session["display_name"] = user["display_name"]
                    session_id = str(uuid.uuid4())
                    session["web_session_id"] = session_id
                    start_user_session(int(user["id"]), session_id,
                                       hmac.new(str(app.secret_key).encode("utf-8"), (request.remote_addr or "").encode("utf-8"), hashlib.sha256).hexdigest(),
                                       request.user_agent.string[:300])
                    record_event("ACCOUNT_SIGNUP", "PASS", {"method": "password"}, user)
                    record_event("WEB_LOGIN", "PASS", {"method": "signup"}, user)
                    return redirect(url_for("index"))
                except ValueError as error:
                    flash(str(error), "error")
                except Exception:
                    app.logger.exception("Account creation failed")
                    flash("Could not create your account. Please try again later.", "error")
        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if getattr(g, "current_user", None):
            return redirect(url_for("index"))
        if request.method == "POST":
            identifier = (request.form.get("identifier") or "").strip().lower()[:254]
            password = request.form.get("password") or ""
            user = get_user_by_login(identifier) if identifier else None
            if not user or not user.get("is_active") or not check_password_hash(user.get("password_hash", ""), password):
                add_audit_event(user.get("id") if user else None, user.get("username", "") if user else identifier[:40], "WEB_LOGIN", "FAIL", {"reason": "invalid_credentials"})
                flash("The username/email or password is incorrect.", "error")
                return render_template("login.html"), 401
            session.clear()
            session.permanent = True
            session["_csrf_token"] = secrets.token_urlsafe(32)
            session["user_id"] = int(user["id"])
            session["username"] = user["username"]
            session["display_name"] = user["display_name"]
            session_id = str(uuid.uuid4())
            session["web_session_id"] = session_id
            try:
                start_user_session(int(user["id"]), session_id,
                                   hmac.new(str(app.secret_key).encode("utf-8"), (request.remote_addr or "").encode("utf-8"), hashlib.sha256).hexdigest(),
                                   request.user_agent.string[:300])
                mark_user_login(int(user["id"]))
                record_event("WEB_LOGIN", "PASS", {"method": "password"}, user)
            except Exception:
                app.logger.exception("Unable to initialize account session or audit history")
                session.clear()
                flash("Sign-in is temporarily unavailable because the account database could not be initialized.", "error")
                return render_template("login.html"), 503
            target = request.args.get("next", "")
            if target.startswith("/") and not target.startswith("//"):
                return redirect(target)
            return redirect(url_for("index"))
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        user = current_user()
        try:
            end_user_session(session.get("web_session_id"))
            record_event("WEB_LOGOUT", "PASS", {"method": "password"}, user)
        except Exception:
            app.logger.exception("Unable to close account session")
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def index():
        user = current_user()
        connection = get_connection(int(user["id"]))
        docs = list_documents(int(user["id"]), 100)
        recent = list_recent_documents(int(user["id"]), 5)
        # Mark a job as interrupted when an earlier web worker died or restarted.
        get_active_sync_job(int(user["id"]))
        sync_job = get_latest_sync_job(int(user["id"]))
        pending_voice_query = ""
        if session.get("pending_voice_query") and (not sync_job or sync_job.get("status") not in {"queued", "running"}):
            pending_voice_query = str(session.pop("pending_voice_query", ""))[:1000]
        return render_template(
            "index.html", document_count=count_documents(int(user["id"])),
            documents=docs, recent_documents=recent, timeline_count=count_timeline_events(int(user["id"])), languages=LANGUAGE_OPTIONS,
            selected_language="", results=None, query="", canonical_query="",
            language_message="", connection=connection, sync_job=sync_job,
            pending_voice_query=pending_voice_query,
            connection_active=bool(connection and connection.get("status") == "connected" and connection.get("access_token_encrypted")),
        )

    @app.post("/search")
    @login_required
    def search():
        user = current_user()
        user_id = int(user["id"])
        query = (request.form.get("query") or "").strip()[:1000]
        preferred_language = (request.form.get("language") or "").strip()
        input_mode = "voice" if request.form.get("input_mode") == "voice" else "text"
        auto_after_fetch = request.form.get("auto_after_fetch") == "1"
        normalized_command = query.lower().strip()
        if input_mode == "voice" and re.search(r"\b(timeline|chronology|chronological|dated events|my events)\b", normalized_command):
            try:
                record_event("VOICE_NAVIGATION", "PASS", {"destination": "timeline"}, user)
            except Exception:
                app.logger.exception("Unable to record voice navigation")
            flash("Showing your timeline. Entries are candidate events linked to evidence in your documents.", "info")
            return redirect(url_for("timeline"))
        if input_mode == "voice" and re.search(r"\b(history|activity|recent activity|my records|previous searches|search history|what did i fetch|what documents did i fetch)\b", normalized_command):
            try:
                record_event("VOICE_NAVIGATION", "PASS", {"destination": "history"}, user)
            except Exception:
                app.logger.exception("Unable to record voice navigation")
            return redirect(url_for("history"))
        fetch_intent = bool(re.search(r"\b(fetch|download|retrieve|get|sync|show|list|display|open)\b", normalized_command))
        generic_fetch_command = input_mode == "voice" and fetch_intent and not detect_document_type(query) and bool(re.search(r"\b(document|documents|files)\b", normalized_command))
        specific_fetch_command = input_mode == "voice" and fetch_intent and bool(detect_document_type(query))
        if generic_fetch_command and not auto_after_fetch:
            try:
                _job, created = start_digilocker_sync(user)
                flash("Document synchronization started. Progress will appear in your workspace; you do not need to upload files one at a time.", "success" if created else "info")
            except Exception:
                flash("The voice command could not start a fetch. Connect DigiLocker and check its requester configuration first.", "error")
            try:
                record_event("VOICE_FETCH_COMMAND", "PASS", {"query": query, "action": "sync_documents"}, user)
            except Exception:
                app.logger.exception("Unable to record voice fetch command")
            return redirect(url_for("index"))
        if specific_fetch_command and not auto_after_fetch:
            # Remove command phrasing so the follow-up search targets the document itself.
            target_query = re.sub(r"^\s*(?:please\s+)?(?:fetch|download|retrieve|get|sync)\s+(?:my\s+)?", "", query, flags=re.I).strip()
            session["pending_voice_query"] = target_query or query
            try:
                _job, created = start_digilocker_sync(user)
                flash("I’ll fetch authorized documents first, then automatically search for your requested document.", "success" if created else "info")
            except Exception:
                session.pop("pending_voice_query", None)
                flash("The voice fetch request could not start. Search your already fetched documents or check DigiLocker configuration.", "warning")
                return redirect(url_for("index"))
            return redirect(url_for("index"))
        started = time.perf_counter()
        results: list[dict] = []
        canonical_query = ""
        language_message = ""
        error_message = ""
        prepared = None
        allowed_paths, document_map = owned_document_paths(user_id)
        if not query:
            flash("Say or enter what document you are looking for.", "error")
        elif not allowed_paths:
            flash("Connect DigiLocker and fetch your documents to start searching.", "info")
        else:
            try:
                provider = build_provider()
                manager = LanguageManager(provider)
                prepared = manager.prepare_query(query, preferred_language=preferred_language or None)
                canonical_query = prepared.canonical_english or query
                with using_database(_user_index_path(user_id)):
                    found = search_documents_multilingual(
                        prepared.original, canonical_query=prepared.canonical_english,
                        transliterated_query=prepared.transliterated,
                        document_type=prepared.document_type,
                        constraints=extract_constraints(prepared.canonical_english or prepared.original),
                        limit=20, allowed_paths=allowed_paths,
                    )
                for result in found:
                    path = str(Path(result["path"]).resolve())
                    metadata = document_map.get(path)
                    if not metadata or not Path(path).is_file():
                        continue
                    clone = dict(result)
                    clone["id"] = int(metadata["id"])
                    clone["source_name"] = metadata.get("source", "DigiLocker")
                    results.append(clone)
                language_message = f"Detected: {getattr(prepared, 'language_code', '') or 'unknown'} · Language provider: {getattr(prepared, 'provider_used', '') or 'local'}"
                if getattr(prepared, "provider_error", ""):
                    language_message += " · Translation service unavailable; local matching was used where possible."
            except Exception:
                app.logger.exception("Search failed for account %s", user_id)
                error_message = "search_error"
                flash("Search could not be completed. Check the configured language services and try again.", "error")
        duration_ms = int((time.perf_counter() - started) * 1000)
        language_code = getattr(prepared, "language_code", "") if prepared else ""
        provider_used = getattr(prepared, "provider_used", "") if prepared else ""
        try:
            add_search(user_id, query, input_mode, language_code or preferred_language, provider_used,
                       len(results), "PASS" if results and not error_message else "FAIL", duration_ms)
            record_event("DOCUMENT_SEARCH", "PASS" if results and not error_message else "FAIL",
                         {"query": query, "input_mode": input_mode, "results_count": len(results), "duration_ms": duration_ms}, user)
        except Exception:
            app.logger.exception("Unable to save search audit for account %s", user_id)
        connection = get_connection(user_id)
        return render_template(
            "index.html", document_count=count_documents(user_id),
            documents=list_documents(user_id, 100), recent_documents=list_recent_documents(user_id, 5),
            timeline_count=count_timeline_events(user_id), languages=LANGUAGE_OPTIONS, selected_language=preferred_language, results=results,
            query=query, canonical_query=canonical_query, language_message=language_message,
            connection=connection, sync_job=get_latest_sync_job(user_id), pending_voice_query="",
            connection_active=bool(connection and connection.get("status") == "connected" and connection.get("access_token_encrypted")),
            input_mode=input_mode,
        )

    @app.get("/documents/<int:document_id>")
    @login_required
    def view_document(document_id: int):
        user = current_user()
        row = get_document(int(user["id"]), document_id)
        if row is None:
            abort(404)
        path = Path(row["path"]).resolve()
        try:
            path.relative_to(_user_root(int(user["id"])))
        except ValueError:
            app.logger.error("Blocked cross-account document path access for account %s", user["id"])
            abort(404)
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            abort(404)
        mark_document_access(int(user["id"]), document_id)
        record_event("DOCUMENT_OPEN", "PASS", {"document_id": document_id, "document_name": row["name"], "source": row["source"]}, user)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        inline = path.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png"}
        return send_file(path, mimetype=mime_type, as_attachment=not inline, download_name=path.name, conditional=True)

    @app.post("/digilocker/connect")
    @login_required
    def digilocker_connect():
        user = current_user()
        settings = _digilocker_settings()
        if not app.config["SDF_STABLE_SECRET_CONFIGURED"]:
            record_event("DIGILOCKER_CONNECT", "FAIL", {"reason": "stable_app_secret_not_configured"}, user)
            flash("The operator must set a persistent WEB_APP_SECRET_KEY before connecting DigiLocker, so encrypted tokens remain readable after restarts.", "error")
            return redirect(url_for("index"))
        if not _digilocker_configured():
            record_event("DIGILOCKER_CONNECT", "FAIL", {"reason": "partner_credentials_not_configured"}, user)
            flash("DigiLocker is not configured yet. The operator must register SmartDocumentFinder as an approved requester and set its client ID, client secret and exact registered callback URL in Render.", "error")
            return redirect(url_for("index"))
        state = secrets.token_urlsafe(32)
        session["digilocker_oauth_state"] = state
        session["digilocker_oauth_user_id"] = int(user["id"])
        params = {"response_type": "code", "client_id": settings["client_id"], "redirect_uri": settings["redirect_uri"], "state": state}
        if settings["scopes"]:
            params["scope"] = settings["scopes"]
        if settings["use_pkce"]:
            # PKCE protects the authorization code from being reused by an interceptor.
            verifier = secrets.token_urlsafe(64)
            digest = hashlib.sha256(verifier.encode("ascii")).digest()
            challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            session["digilocker_pkce_verifier"] = verifier
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
        record_event("DIGILOCKER_CONNECT_START", "PASS", {"provider": "digilocker", "pkce": settings["use_pkce"]}, user)
        return redirect(settings["authorize_url"] + ("&" if "?" in settings["authorize_url"] else "?") + urlencode(params))

    @app.get("/digilocker/callback")
    @login_required
    def digilocker_callback():
        user = current_user()
        settings = _digilocker_settings()
        returned_state = request.args.get("state", "")
        expected_state = session.pop("digilocker_oauth_state", "")
        expected_user = session.pop("digilocker_oauth_user_id", None)
        if not expected_state or not returned_state or not hmac.compare_digest(expected_state, returned_state) or expected_user != int(user["id"]):
            record_event("DIGILOCKER_OAUTH_CALLBACK", "FAIL", {"reason": "state_validation_failed"}, user)
            flash("DigiLocker authorization could not be verified. Please start the connection again.", "error")
            return redirect(url_for("index"))
        if request.args.get("error"):
            record_event("DIGILOCKER_OAUTH_CALLBACK", "FAIL", {"reason": "authorization_denied"}, user)
            flash("DigiLocker authorization was cancelled or denied.", "warning")
            return redirect(url_for("index"))
        code = (request.args.get("code") or "").strip()
        code_verifier = session.pop("digilocker_pkce_verifier", "")
        if not code or not _digilocker_configured():
            flash("DigiLocker did not return an authorization code, or the requester configuration is incomplete.", "error")
            return redirect(url_for("index"))
        try:
            token_form = {
                "grant_type": "authorization_code", "code": code,
                "client_id": settings["client_id"], "client_secret": settings["client_secret"],
                "redirect_uri": settings["redirect_uri"],
            }
            if settings["use_pkce"]:
                if not code_verifier:
                    raise RuntimeError("The PKCE verifier is missing; restart the DigiLocker connection.")
                token_form["code_verifier"] = code_verifier
            response = requests.post(settings["token_url"], data=token_form,
                                     headers={"Accept": "application/json"}, timeout=25)
            if not response.ok:
                # Do not display upstream response bodies; they can contain details.
                raise RuntimeError(f"Token endpoint returned HTTP {response.status_code}.")
            token_payload = response.json()
            access_token = str(token_payload.get("access_token") or "").strip()
            refresh_token = str(token_payload.get("refresh_token") or "").strip()
            if not access_token:
                raise RuntimeError("The token response did not contain an access token.")
            expiry = None
            try:
                expiry = utcnow() + timedelta(seconds=max(60, int(token_payload.get("expires_in", 3600))))
            except (TypeError, ValueError):
                pass
            add_connection(int(user["id"]), _encrypt_token(app, access_token),
                           _encrypt_token(app, refresh_token) if refresh_token else "", expiry,
                           str(token_payload.get("scope") or settings["scopes"]))
            record_event("DIGILOCKER_CONNECTED", "PASS", {"expires_at": expiry.isoformat() if expiry else None}, user)
            flash("DigiLocker is connected. Choose ‘Fetch my documents’ to synchronize documents authorized for this requester.", "success")
        except Exception as error:
            app.logger.warning("DigiLocker OAuth exchange failed (%s)", type(error).__name__)
            record_event("DIGILOCKER_CONNECTED", "FAIL", {"reason": type(error).__name__}, user)
            flash("DigiLocker authorization could not be completed. Verify the approved app credentials, callback URL and API environment with the partner documentation.", "error")
        return redirect(url_for("index"))

    def refresh_digilocker_token(user_id: int, connection: dict, settings: dict[str, str]) -> tuple[str, dict]:
        access = _decrypt_token(app, connection.get("access_token_encrypted"))
        expiry = connection.get("expires_at")
        # Some DB drivers return naive timestamps even for timezone columns.
        if expiry and getattr(expiry, "tzinfo", None) is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if access and (not expiry or expiry > utcnow() + timedelta(seconds=90)):
            return access, connection
        refresh = _decrypt_token(app, connection.get("refresh_token_encrypted"))
        if not refresh:
            raise RuntimeError("DigiLocker authorization has expired. Disconnect and reconnect your account.")
        response = requests.post(settings["token_url"], data={
            "grant_type": "refresh_token", "refresh_token": refresh,
            "client_id": settings["client_id"], "client_secret": settings["client_secret"],
        }, headers={"Accept": "application/json"}, timeout=25)
        if not response.ok:
            raise RuntimeError("DigiLocker token refresh failed. Reconnect your account.")
        payload = response.json()
        new_access = str(payload.get("access_token") or "").strip()
        if not new_access:
            raise RuntimeError("DigiLocker refresh response omitted an access token.")
        new_refresh = str(payload.get("refresh_token") or "").strip()
        new_expiry = None
        try:
            new_expiry = utcnow() + timedelta(seconds=max(60, int(payload.get("expires_in", 3600))))
        except (TypeError, ValueError):
            pass
        update_connection_tokens(user_id, _encrypt_token(app, new_access), _encrypt_token(app, new_refresh) if new_refresh else None, new_expiry)
        updated = get_connection(user_id) or connection
        return new_access, updated

    def synchronize_digilocker_documents(user: dict, job_id: str | None = None) -> dict:
        """Fetch the user's authorized issued documents, recording persistent progress."""
        user_id = int(user["id"])
        connection = get_connection(user_id)
        if not connection or connection.get("status") != "connected" or not connection.get("access_token_encrypted"):
            raise RuntimeError("DigiLocker is not connected. Connect your account first.")
        settings = _digilocker_settings()
        fetched = skipped = failures = processed = 0
        try:
            token, _connection = refresh_digilocker_token(user_id, connection, settings)
            client = DigiLockerClient(
                access_token=token, client_id=settings["client_id"], client_secret=settings["client_secret"],
                base_url=settings["api_base_url"], timeout=15,
            )
            issued_items = client.list_issued_documents(force=True)
            issued_items = issued_items if isinstance(issued_items, list) else []
            issued_items = [{**item, "_sdf_source_kind": "issued"} for item in issued_items if isinstance(item, dict)]
            uploaded_listing_error = ""
            try:
                uploaded_items = client.list_uploaded_documents(force=True)
                uploaded_items = uploaded_items if isinstance(uploaded_items, list) else []
            except Exception as error:
                # Issued-document access remains useful if the partner scope/API does not
                # permit a self-uploaded locker listing; make the incomplete coverage visible.
                uploaded_items = []
                uploaded_listing_error = type(error).__name__
                app.logger.warning("DigiLocker self-uploaded document listing was unavailable (%s)", uploaded_listing_error)
            items = issued_items + [item for item in uploaded_items if isinstance(item, dict)]
            _document_root().mkdir(parents=True, exist_ok=True)
            user_root = ensure_user_document_root(user_id) / "digilocker"
            user_root.mkdir(parents=True, exist_ok=True)
            try:
                configured_max_new = int(os.getenv("DIGILOCKER_SYNC_MAX_NEW_DOCUMENTS", "500"))
            except (TypeError, ValueError):
                configured_max_new = 500
            max_new = max(1, min(configured_max_new, 5000))
            new_attempts = 0
            eligible_count = sum(1 for item in items if isinstance(item, dict) and str(item.get("uri") or item.get("docUri") or item.get("doc_uri") or "").strip())
            more_remaining = 0
            if job_id:
                update_sync_job(job_id, user_id, status="running", total=len(items), processed=0,
                                fetched=0, skipped=0, failed=0, more_remaining=False,
                                message=(f"Found {len(issued_items)} issued and {len(uploaded_items)} self-uploaded record(s). "
                                         "Preparing to fetch available documents…"))

            for item in items:
                if not isinstance(item, dict):
                    skipped += 1
                    processed += 1
                    if job_id:
                        update_sync_job(job_id, user_id, processed=processed, fetched=fetched, skipped=skipped, failed=failures,
                                        message=f"Checked {processed} of {len(items)} records.")
                    continue
                uri = str(item.get("uri") or item.get("docUri") or item.get("doc_uri") or "").strip()
                if not uri:
                    skipped += 1
                    processed += 1
                    if job_id:
                        update_sync_job(job_id, user_id, processed=processed, fetched=fetched, skipped=skipped, failed=failures,
                                        message=f"Checked {processed} of {len(items)} records.")
                    continue
                prior_document = get_document_by_uri(user_id, "digilocker", uri)
                if prior_document and Path(prior_document.get("path", "")).is_file():
                    skipped += 1
                    processed += 1
                    if job_id:
                        update_sync_job(job_id, user_id, processed=processed, fetched=fetched, skipped=skipped, failed=failures,
                                        message=f"Checked {processed} of {len(items)} records; {fetched} newly fetched.")
                    continue
                if new_attempts >= max_new:
                    more_remaining = len(items) - processed
                    break
                new_attempts += 1
                raw_name = str(item.get("name") or item.get("description") or item.get("doctype") or item.get("docType") or "DigiLocker document")
                suggested_name = _safe_filename(raw_name)
                saved_path: Path | None = None
                document_saved = False
                try:
                    expected_mime = item.get("mime")
                    if isinstance(expected_mime, list):
                        flattened_mimes = []
                        for mime_value in expected_mime:
                            if isinstance(mime_value, dict):
                                flattened_mimes.extend(str(value) for value in mime_value.values() if value)
                            elif mime_value:
                                flattened_mimes.append(str(mime_value))
                        expected_mime = next((value for value in flattened_mimes if value), None)
                    elif isinstance(expected_mime, dict):
                        expected_mime = next((str(value) for value in expected_mime.values() if value), None)
                    saved_path = Path(client.fetch_file(uri, str(user_root), suggested_name, expected_mime_type=expected_mime)).resolve()
                    try:
                        saved_path.relative_to(user_root.resolve())
                    except ValueError:
                        saved_path.unlink(missing_ok=True)
                        raise RuntimeError("DigiLocker returned an unsafe file path.")
                    extension = saved_path.suffix.lower()
                    if extension not in ALLOWED_EXTENSIONS:
                        saved_path.unlink(missing_ok=True)
                        raise RuntimeError(f"Unsupported document format returned by source: {extension or 'unknown'}")
                    stat = saved_path.stat()
                    index_info = {"name": saved_path.name, "path": str(saved_path), "extension": extension,
                                  "size": stat.st_size, "modified_time": stat.st_mtime}
                    with using_database(_user_index_path(user_id)):
                        index_result = index_file(index_info, force=True)
                    document = add_document(
                        user_id, saved_path.name, str(saved_path), extension, stat.st_size,
                        source="digilocker", source_uri=uri,
                        issuer=str(item.get("issuer") or item.get("issuerName") or ""),
                        document_type=str(item.get("doctype") or item.get("docType") or item.get("type") or item.get("description") or "")[:80],
                        remote_metadata=_json_safe_item(item),
                    )
                    document_saved = True
                    try:
                        build_timeline_for_document(user_id, int(document["id"]), str(saved_path))
                    except Exception:
                        app.logger.exception("Timeline extraction failed for document id=%s", document.get("id"))
                    # Once the file and its tenant-owned metadata are saved, count it as fetched
                    # even if a secondary audit/timeline operation encounters an error.
                    fetched += 1
                    try:
                        record_event("DIGILOCKER_DOCUMENT_FETCH", "PASS" if not index_result.get("error") else "WARN",
                                     {"document_id": document["id"], "name": saved_path.name, "extraction_error": bool(index_result.get("error"))}, user)
                    except Exception:
                        app.logger.exception("Could not write fetch audit for document id=%s", document.get("id"))
                except Exception as error:
                    failures += 1
                    # Do not leave a partial file behind if its ownership metadata was not committed.
                    if saved_path and saved_path.exists() and not document_saved:
                        try:
                            saved_path.unlink(missing_ok=True)
                        except OSError:
                            app.logger.warning("Could not remove partial downloaded file")
                    app.logger.warning("DigiLocker document fetch failed (%s)", type(error).__name__)
                    try:
                        record_event("DIGILOCKER_DOCUMENT_FETCH", "FAIL", {"reason": type(error).__name__}, user)
                    except Exception:
                        app.logger.exception("Could not write failure audit for DigiLocker document")
                processed += 1
                if job_id:
                    update_sync_job(job_id, user_id, processed=processed, fetched=fetched, skipped=skipped, failed=failures,
                                    message=f"Processed {processed} of {len(items)} records; fetched {fetched} new document(s).")

            if not more_remaining:
                more_remaining = max(0, len(items) - processed)
            summary = {"available": len(items), "eligible": eligible_count, "processed": processed,
                       "fetched": fetched, "skipped": skipped, "failed": failures,
                       "more_remaining": more_remaining, "more_may_remain": more_remaining > 0,
                       "uploaded_listing_error": uploaded_listing_error}
            record_event("DIGILOCKER_SYNC", "PASS" if failures == 0 and more_remaining == 0 and not uploaded_listing_error else "WARN", summary, user)
            return summary
        except Exception as error:
            app.logger.warning("DigiLocker sync failed (%s)", type(error).__name__)
            record_event("DIGILOCKER_SYNC", "FAIL", {"reason": type(error).__name__}, user)
            raise

    def _run_digilocker_sync_job(user: dict, job_id: str) -> None:
        user_id = int(user["id"])
        try:
            with app.app_context():
                update_sync_job(job_id, user_id, status="running", message="Connecting to DigiLocker and checking authorized documents…")
                summary = synchronize_digilocker_documents(user, job_id=job_id)
                if summary.get("more_may_remain"):
                    status = "partial"
                    message = (f"Fetched {summary['fetched']} new document(s); {summary['failed']} failed. "
                               f"{summary['more_remaining']} record(s) remain beyond the configured per-sync safety limit. Start another fetch to continue.")
                elif summary.get("failed"):
                    status = "partial"
                    message = f"Sync finished with {summary['failed']} failed document request(s). {summary['fetched']} document(s) were fetched successfully. You can retry the sync."
                elif summary.get("uploaded_listing_error"):
                    status = "partial"
                    message = (f"Fetched {summary['fetched']} document(s) available through the issued-document list, "
                               "but could not list self-uploaded DigiLocker files. Check the approved requester permissions/API configuration.")
                else:
                    status = "completed"
                    message = f"Sync complete: fetched {summary['fetched']} new document(s), skipped {summary['skipped']} already stored or unavailable record(s)."
                update_sync_job(job_id, user_id, status=status, total=summary.get("available", 0),
                                processed=summary.get("processed", 0), fetched=summary.get("fetched", 0),
                                skipped=summary.get("skipped", 0), failed=summary.get("failed", 0),
                                more_remaining=summary.get("more_remaining", 0) > 0, message=message)
        except Exception:
            app.logger.exception("DigiLocker sync job failed for account %s", user_id)
            try:
                update_sync_job(job_id, user_id, status="failed", message="Sync could not finish. Check authorization and requester API configuration, then try again.")
                add_audit_event(user_id, user.get("username", ""), "DIGILOCKER_SYNC_JOB", "FAIL", {"job_id": job_id, "reason": "sync_failed"})
            except Exception:
                app.logger.exception("Unable to save failed sync state")
        finally:
            with _SYNC_THREADS_LOCK:
                current = _SYNC_THREADS.get(user_id)
                if current is threading.current_thread():
                    _SYNC_THREADS.pop(user_id, None)

    def start_digilocker_sync(user: dict) -> tuple[dict, bool]:
        """Start an account-isolated background job, or reuse the running job."""
        user_id = int(user["id"])
        if not app.config["SDF_STABLE_SECRET_CONFIGURED"]:
            raise RuntimeError("WEB_APP_SECRET_KEY must be configured before document synchronization.")
        if not _digilocker_configured():
            raise RuntimeError("Approved DigiLocker requester credentials are not configured.")
        connection = get_connection(user_id)
        if not connection or connection.get("status") != "connected" or not connection.get("access_token_encrypted"):
            raise RuntimeError("DigiLocker is not connected for this user.")
        with _SYNC_THREADS_LOCK:
            existing_thread = _SYNC_THREADS.get(user_id)
            if existing_thread and existing_thread.is_alive():
                latest = get_latest_sync_job(user_id)
                if latest and latest.get("status") in {"queued", "running"}:
                    return latest, False
            active = get_active_sync_job(user_id)
            if active:
                # The DB row outlived its worker (e.g., a process restart); don't leave users stuck.
                update_sync_job(active["id"], user_id, status="failed", message="The previous sync worker stopped. A new fetch is being started.")
            job_id = str(uuid.uuid4())
            job = create_sync_job(user_id, job_id)
            slim_user = {"id": user_id, "username": user.get("username", ""), "display_name": user.get("display_name", "")}
            thread = threading.Thread(target=_run_digilocker_sync_job, args=(slim_user, job_id),
                                      name=f"sdf-sync-{user_id}", daemon=True)
            _SYNC_THREADS[user_id] = thread
            thread.start()
            return job, True

    @app.get("/digilocker/sync/status")
    @login_required
    def digilocker_sync_status():
        user_id = int(current_user()["id"])
        active = get_active_sync_job(user_id)
        job = active or get_latest_sync_job(user_id)
        if not job:
            return jsonify({"status": "idle", "message": "No document fetch has been started."})
        total = int(job.get("total") or 0)
        processed = int(job.get("processed") or 0)
        percent = min(100, int(processed * 100 / total)) if total else (100 if job.get("status") in {"completed", "partial", "failed"} else 0)
        return jsonify({"id": job["id"], "status": job["status"], "total": total,
                        "processed": processed, "fetched": int(job.get("fetched") or 0),
                        "skipped": int(job.get("skipped") or 0), "failed": int(job.get("failed") or 0),
                        "more_remaining": bool(job.get("more_remaining")), "message": job.get("message", ""),
                        "progress_percent": percent})

    @app.post("/digilocker/sync")
    @login_required
    def digilocker_sync():
        user = current_user()
        try:
            _job, created = start_digilocker_sync(user)
            flash("Started fetching your authorized DigiLocker documents. You can watch the progress below.", "success" if created else "info")
        except Exception:
            app.logger.exception("Unable to start DigiLocker sync")
            flash("A document fetch could not be started. Connect DigiLocker and verify the requester configuration.", "error")
        return redirect(url_for("index"))

    @app.post("/digilocker/disconnect")
    @login_required
    def digilocker_disconnect():
        user = current_user()
        user_id = int(user["id"])
        connection = get_connection(user_id)
        provider_revoked = False
        revocation_status = "not_attempted"
        settings = _digilocker_settings()
        encrypted_token = connection.get("access_token_encrypted") if connection else None
        # Revoke at DigiLocker where possible, then always clear local encrypted tokens.
        # A failed/expired provider token must not trap the user in a connected state.
        if encrypted_token and settings["client_id"] and settings["client_secret"]:
            try:
                access_token = _decrypt_token(app, encrypted_token)
                if access_token:
                    response = requests.post(
                        settings["revoke_url"],
                        data={"token": access_token, "token_type_hint": "access_token"},
                        auth=(settings["client_id"], settings["client_secret"]),
                        headers={"Accept": "application/json"}, timeout=12,
                    )
                    provider_revoked = response.status_code == 200
                    revocation_status = "revoked" if provider_revoked else f"http_{response.status_code}"
                else:
                    revocation_status = "token_unavailable"
            except Exception as error:
                revocation_status = type(error).__name__
                app.logger.warning("DigiLocker token revocation could not be confirmed (%s)", revocation_status)
        else:
            revocation_status = "credentials_or_token_unavailable"
        disconnect_provider(user_id)
        record_event("DIGILOCKER_DISCONNECTED", "PASS" if provider_revoked else "WARN",
                     {"local_tokens_cleared": True, "provider_token_revoked": provider_revoked,
                      "revocation_status": revocation_status}, user)
        if provider_revoked:
            flash("DigiLocker was disconnected and token revocation was confirmed. Previously fetched local copies remain in your workspace.", "success")
        else:
            flash("DigiLocker was disconnected from SmartDocumentFinder and stored tokens were cleared locally. DigiLocker could not confirm token revocation, so review connected apps in DigiLocker if needed. Previously fetched local copies remain in your workspace.", "warning")
        return redirect(url_for("index"))

    @app.get("/admin/audit")
    @login_required
    def admin_audit():
        user = current_user()
        admin_names = {item.strip().lower() for item in os.getenv("ADMIN_USERNAMES", "").split(",") if item.strip()}
        if user.get("username", "").lower() not in admin_names:
            abort(404)
        return render_template("admin_audit.html", events=list_all_audit_events(500))


    @app.get("/timeline")
    @login_required
    def timeline():
        user = current_user()
        events = list_timeline(int(user["id"]), 300)
        return render_template("timeline.html", events=events, stats=user_stats(int(user["id"])))

    @app.get("/history")
    @login_required
    def history():
        user = current_user()
        user_id = int(user["id"])
        return render_template(
            "history.html", searches=list_searches(user_id, 50),
            events=list_audit_events(user_id, 100), stats=user_stats(user_id),
            documents=list_documents(user_id, 50),
        )

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_error):
        flash("Request too large.", "error")
        return redirect(url_for("index"))

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", code=400, message=getattr(error, "description", "Bad request")), 400

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="The requested page or document was not found."), 404

    @app.errorhandler(503)
    def service_unavailable(error):
        return render_template("error.html", code=503, message=getattr(error, "description", "Service temporarily unavailable")), 503

    # Create schema during startup so missing SQL configuration fails at deployment, not first login.
    try:
        initialize_store()
    except Exception:
        app.logger.exception("Web portal database initialization failed; check DATABASE_URL")
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
