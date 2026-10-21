# Smart Document Finder 3.2.0 — Audit and Fixes

## What was audited

The full source tree was reviewed for language detection, Sarvam API calls, query normalization, document-type extraction, local search, DigiLocker wiring, error handling, configuration, and automated tests.

## Main problems found

1. There was **no DigiLocker API integration** in the original project. The app was a local SQLite/FTS5 document finder only.
2. Sarvam calls were present, but provider failures were swallowed and the original untranslated query was allowed to continue, which could look like a successful multilingual search.
3. The application exposed the broader 22-language set, while Sarvam's text-LID capability is narrower than the translation model.
4. Romanized/Hinglish input could be classified as English even when it contained clear Indic-language hints.
5. Search used the original query and transliteration as relevance signals, instead of enforcing the requested document-name-only pipeline.
6. Document aliases were limited and could not cover arbitrary DigiLocker document names.
7. Remote DigiLocker errors were not surfaced clearly.

## New request pipeline

```text
User text / voice
  -> language detection + local script/hint fallback
  -> English translation
  -> document-name extraction only
  -> optional grade/year/semester constraints
  -> local document search
  -> optional DigiLocker issued-document match
  -> download the matched DigiLocker URI only
```

For an exact known document, examples of the canonical output are:

- `मेरा पैन कार्ड दिखाओ` -> `pan card`
- `show my PAN card right now` -> `pan card`
- `माझी बारावीची मार्कशीट दाखवा` -> `12th marksheet`

For a DigiLocker document not in the static fallback catalog, the app can still match the translated query against the user's issued-document metadata (name/description) and fetch that URI.

## Sarvam integration

The Sarvam adapter uses the documented REST endpoints:

- `POST /text-lid` for language/script identification.
- `POST /translate` for English normalization.
- `mayura:v1` with `source_language_code=auto` for Romanized/code-mixed inputs when local hints identify a non-English Indic language.
- `sarvam-translate:v1` for exact known source-language translation, including the expanded 22 scheduled Indian languages.

The implementation now retries transient 429/5xx/network errors and reports persistent provider failures.

## DigiLocker integration

The new `services/digilocker_provider.py` implements the documented Requester flow for already-issued documents:

- `GET /public/oauth2/2/files/issued` with a Bearer access token.
- `GET /public/oauth2/1/file/uri` with the document URI.
- Optional HMAC integrity verification when the requester client secret is configured.
- Issuer/document-type/search-parameter discovery and consent-gated pull-document helpers are included, without guessing personal identity parameters.

A valid DigiLocker user OAuth access token is required. The project does **not** contain a fake token and cannot be end-to-end tested against a real user's locker without real authorized credentials.

## Tests

Current local suite: **31 passed**.

Coverage added for:

- multilingual document-name extraction
- provider failure fallback and error reporting
- Romanized/Hinglish Sarvam auto-translation path
- Sarvam endpoint/model/payload wiring
- DigiLocker issued-document search and file download
- unknown/unmapped DigiLocker document names
- existing local-search behavior

The audit container does not have PySide6 installed, so a real desktop-window launch could not be executed there. `requirements.txt` correctly declares `PySide6>=6.8,<7`. Python compilation and all non-GUI tests pass.

## Required local configuration

Copy `.env.example` to `.env` and provide:

```text
LANGUAGE_PROVIDER=sarvam
SARVAM_API_KEY=...
DIGILOCKER_ACCESS_TOKEN=...
```

For DigiLocker issuer metadata discovery/pull-document workflows, also provide the registered requester client ID and secret.


## Voice diagnostic improvements (3.2.2)

- Real microphone RMS/clip-duration checks distinguish silent capture from provider failures.
- Saaras STT retries `codemix` with `transcribe` when the first successful request returns an empty transcript.
- Default document-name keyterms are sent to Saaras v4 to bias recognition toward the app's retrieval vocabulary.
- `VOICE_MICROPHONE_INDEX` can select a specific Windows/PyAudio input device.
- `scripts/list_microphones.py` lists available input devices.
- `scripts/test_live_sarvam_stt.py` captures a real microphone clip and tests it against Sarvam.
