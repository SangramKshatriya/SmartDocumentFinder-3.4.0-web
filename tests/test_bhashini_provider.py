import base64

import pytest

from services.bhashini_provider import BhashiniProvider


def test_bhashini_requires_api_key(monkeypatch):
    monkeypatch.delenv("BHASHINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="BHASHINI_API_KEY"):
        BhashiniProvider()


def test_bhashini_translation_payload(monkeypatch):
    monkeypatch.setenv("BHASHINI_API_KEY", "key")
    monkeypatch.setenv("BHASHINI_TRANSLATION_SERVICE_ID", "translation-service")
    provider = BhashiniProvider()
    seen = {}

    def fake_compute(task, input_data):
        seen["task"] = task
        seen["input"] = input_data
        return {"pipelineResponse": [{"output": [{"target": "show my PAN card"}]}]}

    monkeypatch.setattr(provider, "_compute", fake_compute)
    assert provider.translate("मेरा पैन कार्ड", "hi-IN", "en-IN") == "show my PAN card"
    assert seen["task"]["taskType"] == "translation"
    assert seen["task"]["config"]["language"] == {"sourceLanguage": "hi", "targetLanguage": "en"}
    assert seen["input"]["input"][0]["source"] == "मेरा पैन कार्ड"


def test_bhashini_speech_to_text_encodes_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("BHASHINI_API_KEY", "key")
    monkeypatch.setenv("BHASHINI_ASR_SERVICE_ID", "asr-service")
    provider = BhashiniProvider()
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF")
    seen = {}

    def fake_compute(task, input_data):
        seen["task"] = task
        seen["input"] = input_data
        return {"pipelineResponse": [{"output": [{"source": "show my PAN card"}]}]}

    monkeypatch.setattr(provider, "_compute", fake_compute)
    response = provider.speech_to_text(str(audio), language_code="hi-IN")
    assert response["transcript"] == "show my PAN card"
    assert base64.b64decode(seen["input"]["audio"][0]["audioContent"]) == b"RIFF"
    assert seen["task"]["config"]["language"]["sourceLanguage"] == "hi"
