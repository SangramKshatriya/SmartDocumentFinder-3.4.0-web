import hashlib
import hmac

import pytest

from services.digilocker_provider import DigiLockerClient


class FakeResponse:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, payload=None, content=b"PDF", headers=None):
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {"Content-Type": "application/pdf"}

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=1024):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index:index + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_query_terms_and_similarity():
    terms = DigiLockerClient._query_terms("show my PAN card")
    assert "pan" in terms
    assert "card" in terms
    assert "show" not in terms
    score = DigiLockerClient._document_similarity(
        {"name": "PAN Card", "description": "PAN Card", "doctype": "PANCR", "issuer": "Income Tax"},
        "pan",
        "pan card",
    )
    assert score > 0


def test_fetch_file_writes_pdf_and_validates_hmac(tmp_path):
    secret = "secret"
    content = b"PDF DATA"
    digest = hmac.new(secret.encode(), content, hashlib.sha256).digest()
    import base64
    response = FakeResponse(content=content, headers={
        "Content-Type": "application/pdf",
        "HMAC": base64.b64encode(digest).decode("ascii"),
    })
    client = DigiLockerClient("token", client_secret=secret, base_url="https://example.test")
    session = FakeSession(response)
    client.session = session

    path = client.fetch_file("uri-1", str(tmp_path), "pan_card")
    assert path.endswith("pan_card.pdf")
    assert (tmp_path / "pan_card.pdf").read_bytes() == content
    assert session.calls[0][0] == "GET"
    assert session.calls[0][1].endswith("/public/oauth2/1/file/uri-1")
    assert "params" not in session.calls[0][2]
    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer token"


def test_pull_document_requires_consent():
    client = DigiLockerClient("token")
    with pytest.raises(ValueError, match="explicit user consent"):
        client.pull_document("org", "doctype", "N", {})


def test_fetch_file_maps_xml_to_searchable_xml(tmp_path):
    response = FakeResponse(content=b"<certificate><name>Example</name><year>2024</year></certificate>", headers={"Content-Type": "application/xml"})
    client = DigiLockerClient("token", base_url="https://example.test")
    client.session = FakeSession(response)
    path = client.fetch_file("xml-1", str(tmp_path), "certificate")
    assert path.endswith("certificate.xml")
    assert (tmp_path / "certificate.xml").read_bytes() == response.content
    assert response.closed


def test_fetch_file_rejects_bad_hmac_without_final_file(tmp_path):
    response = FakeResponse(content=b"untrusted", headers={"Content-Type": "application/pdf", "HMAC": "not-the-right-hmac"})
    client = DigiLockerClient("token", client_secret="secret", base_url="https://example.test")
    client.session = FakeSession(response)
    with pytest.raises(RuntimeError, match="HMAC mismatch"):
        client.fetch_file("pdf-1", str(tmp_path), "certificate")
    assert not (tmp_path / "certificate.pdf").exists()
    assert not list(tmp_path.glob("*.part"))


class QueueFakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected extra request")
        return self.responses.pop(0)


def test_list_uploaded_documents_walks_nested_folders(tmp_path):
    root_response = FakeResponse(payload={"items": [
        {"name": "Folder A", "type": "dir", "id": "folder/a"},
        {"name": "root.txt", "type": "file", "uri": "urn:uploaded:root"},
    ]})
    folder_response = FakeResponse(payload={"items": [
        {"name": "Nested", "type": "dir", "id": "nested"},
        {"name": "child.pdf", "type": "file", "uri": "urn:uploaded:child"},
    ]})
    nested_response = FakeResponse(payload={"items": [
        {"name": "nested.png", "type": "file", "uri": "urn:uploaded:nested"},
    ]})
    client = DigiLockerClient("token", base_url="https://example.test")
    session = QueueFakeSession([root_response, folder_response, nested_response])
    client.session = session

    files = client.list_uploaded_documents()
    assert {item["uri"] for item in files} == {"urn:uploaded:root", "urn:uploaded:child", "urn:uploaded:nested"}
    assert all(item["_sdf_source_kind"] == "uploaded" for item in files)
    assert [call[1] for call in session.calls] == [
        "https://example.test/public/oauth2/1/files",
        "https://example.test/public/oauth2/1/files/folder%2Fa",
        "https://example.test/public/oauth2/1/files/nested",
    ]
