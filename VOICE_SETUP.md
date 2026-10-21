# Voice Search Setup

Voice search in Smart Document Finder 3.3.1 now performs the complete microphone-capture step before transcription. It calibrates the ambient noise level, listens with a timeout/phrase limit, converts the captured clip to a standard 16 kHz / 16-bit WAV, and then tries the configured language provider followed by a Google SpeechRecognition fallback for common English/Hindi use.

## Normal use

1. Make sure your Windows input device is the microphone you want to use.
2. Install the project requirements so `SpeechRecognition` and `PyAudio` are available.
3. Keep `AUDIO_DEVICE_INDEX` empty in `.env` to use the Windows default microphone.
4. Start the application and click the microphone button.
5. Speak after the status changes to `Listening…`.

## Selecting a specific microphone

Run:

```text
python scripts/test_microphone.py
```

The script prints microphone indexes, captures a test clip, reports RMS/duration, and writes `data/voice_test.wav`.

To force a specific device, set for example:

```text
AUDIO_DEVICE_INDEX=2
```

Then restart the application.

## Voice timing controls

Optional `.env` settings:

```text
VOICE_LISTEN_TIMEOUT=8
VOICE_PHRASE_TIME_LIMIT=15
VOICE_AMBIENT_CALIBRATION=0.6
```

## Provider behavior

When `LANGUAGE_PROVIDER=sarvam`, Saaras v4 is tried in `translate` mode first so the application receives an English-normalized document request. If that fails, `codemix` and `transcribe` are tried before the Google SpeechRecognition fallback.

When `LANGUAGE_PROVIDER=bhashini`, the selected language in the UI is required for the ASR call. If no language is selected, the app explains this and uses the fallback recognition path.

A provider/network/authentication failure no longer prevents the application from attempting the fallback recognizer.
## 3.3.2 voice stability fix

The microphone capture settings are now read through a safe numeric configuration helper. Missing or malformed `VOICE_LISTEN_TIMEOUT`, `VOICE_PHRASE_TIME_LIMIT`, or `VOICE_AMBIENT_CALIBRATION` values automatically use safe defaults instead of aborting voice search before the microphone opens. Existing text search, history, indexing, and document handling are unchanged.

