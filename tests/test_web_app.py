"""Routing, account isolation, and CSRF checks for the browser portal."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

flask = pytest.importorskip("flask")

import web_app
import portal_store
from indexer import index_file


def _csrf(client, url="/signup"):
    response = client.get(url)
    assert response.status_code == 200
    match = re.search(rb'name="_csrf_token" value="([^"]+)"', response.data)
    assert match, response.data[:500]
    return match.group(1).decode()


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_PORTAL_DATABASE_URL", f"sqlite:///{(tmp_path / 'portal.db').as_posix()}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SMARTDOCUMENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DOCUMENT_FOLDER", str(tmp_path / "documents"))
    monkeypatch.setenv("WEB_APP_SECRET_KEY", "test-secret-for-portal-tests-2026-very-long")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LANGUAGE_PROVIDER", "local")


def _signup(client, username, display_name):
    token = _csrf(client)
    response = client.post("/signup", data={
        "_csrf_token": token,
        "display_name": display_name,
        "username": username,
        "email": f"{username}@example.test",
        "password": "correct-horse-battery-staple-2026",
        "confirm_password": "correct-horse-battery-staple-2026",
    })
    assert response.status_code == 302
    return response


def test_health_endpoint_is_public(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    client = web_app.create_app().test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_index_requires_individual_login(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    client = web_app.create_app().test_client()
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_each_account_uses_a_dedicated_document_index(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DOCUMENT_FOLDER", str(tmp_path / "documents"))
    path_a = web_app._user_index_path(12)
    path_b = web_app._user_index_path(13)
    assert path_a == (tmp_path / "documents" / "users" / "12" / ".index" / "documents.db").resolve()
    assert path_b == (tmp_path / "documents" / "users" / "13" / ".index" / "documents.db").resolve()
    assert path_a != path_b


def test_signup_and_login_with_hashed_password(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    app = web_app.create_app()
    client = app.test_client()
    _signup(client, "alice-user", "Alice User")
    with client.session_transaction() as session:
        assert session["username"] == "alice-user"
        user_id = session["user_id"]
    user = portal_store.get_user_by_id(user_id)
    assert user["password_hash"] != "correct-horse-battery-staple-2026"
    assert client.get("/").status_code == 200

    logout_csrf = _csrf(client, "/")
    assert client.post("/logout", data={"_csrf_token": logout_csrf}).status_code == 302
    login_csrf = _csrf(client, "/login")
    response = client.post("/login", data={
        "_csrf_token": login_csrf,
        "identifier": "alice-user",
        "password": "correct-horse-battery-staple-2026",
    })
    assert response.status_code == 302
    assert client.get("/").status_code == 200


def test_invalid_password_does_not_authenticate(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    app = web_app.create_app()
    client = app.test_client()
    _signup(client, "bob-user", "Bob User")
    # Log out, then use an invalid password.
    token = _csrf(client, "/")
    client.post("/logout", data={"_csrf_token": token})
    token = _csrf(client, "/login")
    response = client.post("/login", data={"_csrf_token": token, "identifier": "bob-user", "password": "wrong-password"})
    assert response.status_code == 401
    assert client.get("/").status_code == 302


def test_csrf_is_required_for_mutating_routes(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    client = web_app.create_app().test_client()
    response = client.post("/signup", data={
        "display_name": "Mallory", "username": "mallory",
        "password": "correct-horse-battery-staple-2026",
        "confirm_password": "correct-horse-battery-staple-2026",
    })
    assert response.status_code == 400


def test_search_uses_only_the_signed_in_users_index(monkeypatch, tmp_path):
    import database
    _configure(monkeypatch, tmp_path)
    app = web_app.create_app()
    client_a = app.test_client()
    _signup(client_a, "search-owner-a", "Search Owner A")
    with client_a.session_transaction() as sess:
        user_a = int(sess["user_id"])

    client_b = app.test_client()
    _signup(client_b, "search-owner-b", "Search Owner B")
    with client_b.session_transaction() as sess:
        user_b = int(sess["user_id"])

    file_a = tmp_path / "documents" / "users" / str(user_a) / "digilocker" / "my-pan-record.txt"
    file_b = tmp_path / "documents" / "users" / str(user_b) / "digilocker" / "other-pan-record.txt"
    file_a.parent.mkdir(parents=True, exist_ok=True)
    file_b.parent.mkdir(parents=True, exist_ok=True)
    file_a.write_text("PAN card document belonging to account A", encoding="utf-8")
    file_b.write_text("PAN card document belonging to account B secret", encoding="utf-8")

    for user_id, path in ((user_a, file_a), (user_b, file_b)):
        stat = path.stat()
        metadata = {"name": path.name, "path": str(path.resolve()), "extension": ".txt",
                    "size": stat.st_size, "modified_time": stat.st_mtime}
        with database.using_database(web_app._user_index_path(user_id)):
            index_file(metadata, force=True)
        portal_store.add_document(user_id, path.name, str(path.resolve()), ".txt", stat.st_size,
                                  source="digilocker", source_uri=f"urn:test:{user_id}:pan")

    csrf = _csrf(client_a, "/")
    response = client_a.post("/search", data={
        "_csrf_token": csrf, "query": "PAN card", "input_mode": "text", "language": "en-IN",
    })
    assert response.status_code == 200
    assert b"my-pan-record.txt" in response.data
    assert b"other-pan-record.txt" not in response.data
    assert b"account B secret" not in response.data


def test_users_cannot_open_each_others_documents(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    app = web_app.create_app()
    client_a = app.test_client()
    _signup(client_a, "private-user-a", "User A")
    with client_a.session_transaction() as sess:
        user_a = int(sess["user_id"])

    # Create an independent second account and document record.
    client_b = app.test_client()
    _signup(client_b, "private-user-b", "User B")
    with client_b.session_transaction() as sess:
        user_b = int(sess["user_id"])

    file_b = tmp_path / "documents" / "users" / str(user_b) / "digilocker" / "private.txt"
    file_b.parent.mkdir(parents=True, exist_ok=True)
    file_b.write_text("private record only for user B", encoding="utf-8")
    doc = portal_store.add_document(user_b, "private.txt", str(file_b.resolve()), ".txt", file_b.stat().st_size, source="digilocker", source_uri="urn:test:private-b")
    response = client_a.get(f"/documents/{doc['id']}")
    assert response.status_code == 404


def test_digilocker_oauth_redirect_uses_state_and_pkce(monkeypatch, tmp_path):
    from urllib.parse import parse_qs, urlparse
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DIGILOCKER_CLIENT_ID", "requester-client")
    monkeypatch.setenv("DIGILOCKER_CLIENT_SECRET", "requester-secret")
    monkeypatch.setenv("DIGILOCKER_REDIRECT_URI", "https://example.test/digilocker/callback")
    monkeypatch.setenv("DIGILOCKER_USE_PKCE", "true")
    app = web_app.create_app()
    client = app.test_client()
    _signup(client, "pkce-user", "PKCE User")
    csrf = _csrf(client, "/")
    response = client.post("/digilocker/connect", data={"_csrf_token": csrf})
    assert response.status_code == 302
    params = parse_qs(urlparse(response.headers["Location"]).query)
    assert params["client_id"] == ["requester-client"]
    assert params["response_type"] == ["code"]
    assert params["code_challenge_method"] == ["S256"]
    assert len(params["state"][0]) >= 32
    with client.session_transaction() as sess:
        assert sess["digilocker_oauth_state"] == params["state"][0]
        assert sess["digilocker_pkce_verifier"]


def test_digilocker_connect_requires_stable_secret(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.delenv("WEB_APP_SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DIGILOCKER_CLIENT_ID", "requester-client")
    monkeypatch.setenv("DIGILOCKER_CLIENT_SECRET", "requester-secret")
    monkeypatch.setenv("DIGILOCKER_REDIRECT_URI", "https://example.test/digilocker/callback")
    app = web_app.create_app()
    client = app.test_client()
    _signup(client, "stable-secret-user", "Stable Secret User")
    csrf = _csrf(client, "/")
    response = client.post("/digilocker/connect", data={"_csrf_token": csrf})
    assert response.status_code == 302
    assert "digilocker.meripehchaan.gov.in" not in response.headers["Location"]
    assert b"persistent WEB_APP_SECRET_KEY" in client.get("/").data


def test_digilocker_connect_requires_approved_credentials(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.delenv("DIGILOCKER_CLIENT_ID", raising=False)
    monkeypatch.delenv("DIGILOCKER_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("DIGILOCKER_REDIRECT_URI", raising=False)
    app = web_app.create_app()
    client = app.test_client()
    _signup(client, "source-user", "Source User")
    token = _csrf(client, "/")
    response = client.post("/digilocker/connect", data={"_csrf_token": token})
    assert response.status_code == 302
    assert b"approved DigiLocker requester" in client.get("/").data


def test_disconnect_revokes_provider_token_and_always_clears_local_state(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DIGILOCKER_CLIENT_ID", "requester-client")
    monkeypatch.setenv("DIGILOCKER_CLIENT_SECRET", "requester-secret")
    monkeypatch.setenv("DIGILOCKER_REDIRECT_URI", "https://example.test/digilocker/callback")
    app = web_app.create_app()
    client = app.test_client()
    _signup(client, "disconnect-oauth-user", "Disconnect OAuth User")
    with client.session_transaction() as sess:
        user_id = int(sess["user_id"])
    portal_store.add_connection(user_id, web_app._encrypt_token(app, "access-token-for-revocation"), "", None, "files.issueddocs")

    class RevokedResponse:
        status_code = 200

    calls = []
    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return RevokedResponse()
    monkeypatch.setattr(web_app.requests, "post", fake_post)

    csrf = _csrf(client, "/")
    response = client.post("/digilocker/disconnect", data={"_csrf_token": csrf})
    assert response.status_code == 302
    assert calls[0][0] == "https://digilocker.meripehchaan.gov.in/public/oauth2/1/revoke"
    assert calls[0][1]["auth"] == ("requester-client", "requester-secret")
    assert calls[0][1]["data"]["token"] == "access-token-for-revocation"
    disconnected = portal_store.get_connection(user_id)
    assert disconnected["status"] == "disconnected"
    assert disconnected["access_token_encrypted"] is None


def test_official_digilocker_token_endpoint_default(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.delenv("DIGILOCKER_TOKEN_URL", raising=False)
    from web_app import _digilocker_settings
    assert _digilocker_settings()["token_url"] == "https://digilocker.meripehchaan.gov.in/public/oauth2/2/token"


def test_voice_commands_navigate_to_timeline_and_history(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    app = web_app.create_app()
    client = app.test_client()
    _signup(client, "voice-nav-user", "Voice Navigation User")

    token = _csrf(client, "/")
    timeline_response = client.post("/search", data={
        "_csrf_token": token, "query": "show my timeline", "input_mode": "voice", "language": "",
    })
    assert timeline_response.status_code == 302
    assert timeline_response.headers["Location"].endswith("/timeline")

    token = _csrf(client, "/")
    history_response = client.post("/search", data={
        "_csrf_token": token, "query": "show my activity history", "input_mode": "voice", "language": "",
    })
    assert history_response.status_code == 302
    assert history_response.headers["Location"].endswith("/history")
