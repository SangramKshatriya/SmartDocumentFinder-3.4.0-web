import os

from services.sarvam_provider import SarvamProvider


class FakeResponse:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith('/text-lid'):
            return FakeResponse({"language_code": "hi-IN", "script_code": "Deva", "confidence": 0.99})
        if url.endswith('/speech-to-text'):
            return FakeResponse({"transcript": "show my PAN card", "language_code": "hi-IN"})
        return FakeResponse({"translated_text": "show my PAN card"})


def test_sarvam_uses_document_pipeline_endpoints(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    provider = SarvamProvider()
    session = FakeSession()
    provider.session = session

    assert provider.detect_language("मेरा पैन कार्ड दिखाओ")["language_code"] == "hi-IN"
    assert provider.translate("मेरा पैन कार्ड दिखाओ", "hi-IN", "en-IN") == "show my PAN card"
    assert provider.translate_auto("mera pan card dikhao") == "show my PAN card"

    assert [call[1].split('api.sarvam.ai')[-1] for call in session.calls] == ['/text-lid', '/translate', '/translate']
    exact = session.calls[1][2]["json"]
    auto = session.calls[2][2]["json"]
    assert exact["model"] == "sarvam-translate:v1"
    assert exact["source_language_code"] == "hi-IN"
    assert exact["target_language_code"] == "en-IN"
    assert auto["model"] == "mayura:v1"
    assert auto["source_language_code"] == "auto"


def test_sarvam_stt_uses_auth_header_and_current_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    provider = SarvamProvider()
    session = FakeSession()
    provider.session = session

    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF")
    result = provider.speech_to_text(str(audio), language_code="unknown", mode="translate")

    call = session.calls[-1]
    assert call[0] == "POST"
    assert call[1].endswith("/speech-to-text")
    assert call[2]["headers"]["API-Subscription-Key"] == "test-key"
    assert call[2]["data"]["model"] == "saaras:v4"
    assert call[2]["data"]["language_code"] == "unknown"
    assert call[2]["data"]["mode"] == "translate"
    assert "PAN" in call[2]["data"]["keyterms"]
    assert result["transcript"] == "show my PAN card"
