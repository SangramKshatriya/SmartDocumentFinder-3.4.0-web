# Upgrade Notes — 3.3.1

## Voice search reliability fix

- Fixed the microphone capture bug that caused `name 'audio' is not defined`.
- Added explicit microphone capture/calibration before STT.
- Added configurable microphone selection with `AUDIO_DEVICE_INDEX`.
- Added configurable listening/calibration timings.
- Standardized provider audio input to 16 kHz, 16-bit WAV.
- Added non-silent audio validation without rejecting normal quiet speech too aggressively.
- Sarvam now gets `codemix` then `transcribe` attempts.
- Provider failures fall back to Google SpeechRecognition for common English/Hindi cases.
- Added `scripts/test_microphone.py` for device/capture diagnostics.
