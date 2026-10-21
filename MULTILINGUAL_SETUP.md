# Multilingual implementation process

## Phase 1 — Get the base app running

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
python scripts/check_setup.py
python app.py
```

## Phase 2 — Configure Sarvam

1. Create/access your Sarvam developer workspace and API key.
2. Copy `.env.example` to `.env`.
3. Set:

```text
LANGUAGE_PROVIDER=sarvam
SARVAM_API_KEY=YOUR_KEY
```

4. Test:

```powershell
python scripts/test_remote_language_services.py
```

The code uses the current Sarvam REST paths documented for language ID, translation, transliteration, STT and TTS.

## Phase 3 — Configure OCR

1. Install Tesseract OCR for Windows.
2. Install the language packs matching your target scripts.
3. Set `TESSERACT_CMD` if Tesseract is not on PATH.
4. Set `OCR_LANGUAGES` to the Tesseract language codes you actually installed.
5. Rebuild your document index.

## Phase 4 — Test text search

Use these examples:

```text
show my PAN card
मेरा पैन कार्ड दिखाओ
माझी बारावीची मार्कशीट दाखवा
મારી 12મીની માર્કશીટ બતાવો
என் பான் கார்டை காட்டு
నా పాన్ కార్డు చూపించు
আমার মার্কশিট দেখাও
ನನ್ನ ಅಂಕಪಟ್ಟಿ ತೋರಿಸು
```

Sarvam translation and language-identification coverage are not identical capabilities. The application therefore keeps local lexical/script fallback and reports provider failures instead of silently treating an untranslated request as successful. For the broadest language set, select the language explicitly when auto-LID does not recognize it.

## Phase 5 — Configure DigiLocker (optional)

1. Register/onboard the application as a DigiLocker Requester through the official integration process.
2. Obtain the user's OAuth access token and put it in `DIGILOCKER_ACCESS_TOKEN`.
3. Put requester credentials in `DIGILOCKER_CLIENT_ID` and `DIGILOCKER_CLIENT_SECRET` when issuer/document metadata discovery is needed.
4. Search only after the user has authorized access.
5. The app will list issued documents, match the English document name, and download the matched file URI.

The application does not bypass DigiLocker consent and does not fabricate issuer-specific parameters.

## Phase 6 — Test voice search

1. Connect a microphone.
2. Select a language or leave `Auto Detect`.
3. Press **Voice**.
4. Speak one request.
5. Confirm that the transcript appears in the search box.
6. Confirm the detected language status.
7. Confirm the same document is found as it would be with equivalent English input.

## Phase 7 — Add the full language set

The UI already exposes the broader scheduled-language set. For each added language, validate these separately:

- text language identification
- text translation
- transliteration / Romanized input
- speech recognition
- OCR script pack and OCR accuracy
- TTS voice availability
- document-specific vocabulary

Do not assume that support for one capability automatically means the same coverage exists for another capability.

## Phase 8 — Improve document understanding

Once retrieval is reliable, add:

- document-type ontology
- class/semester/year extraction
- names, IDs and dates as metadata
- FTS5 query expansion
- multilingual embeddings
- vector similarity + lexical search hybrid retrieval
- reranking

Keep the original-language document content as the source of truth.

## Phase 9 — Production hardening

Move provider calls behind a server-side API if distributing the app. Add rate limiting, API-key protection, structured logs, privacy controls, retries with backoff, local caching, observability and automated language regression tests.
