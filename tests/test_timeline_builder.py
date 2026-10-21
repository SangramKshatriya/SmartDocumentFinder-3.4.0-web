from pathlib import Path

from portal_store import create_user, list_timeline
from timeline_builder import build_timeline_for_document
import portal_store


def test_timeline_extracts_dated_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_PORTAL_DATABASE_URL", f"sqlite:///{(tmp_path / 'timeline.db').as_posix()}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SMARTDOCUMENT_DATA_DIR", str(tmp_path / "data"))
    user = create_user("timeline-user", "Timeline User", None, "hash")
    document_path = tmp_path / "timeline.txt"
    document_path.write_text("Certificate issued on 12/08/2024. Examination date: 2023-05-07.", encoding="utf-8")
    record = portal_store.add_document(user["id"], "certificate.txt", str(document_path.resolve()), ".txt", document_path.stat().st_size, source="digilocker", source_uri="urn:timeline:test")
    count = build_timeline_for_document(user["id"], record["id"], str(document_path))
    events = list_timeline(user["id"])
    assert count == 2
    assert {item["event_date"] for item in events} == {"2024-08-12", "2023-05-07"}
    assert all(item["evidence"] for item in events)
