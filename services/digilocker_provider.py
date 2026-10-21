"""DigiLocker Requester client for authorized issued and self-uploaded documents.

The browser portal can enumerate issued documents and the files exposed by a user's
authorized locker API. Pulling a new issuer record is distinct and may require
issuer-specific parameters and explicit user consent; this client does not guess
personal identifiers or attempt to bypass those authorization requirements.
"""
import base64
import hashlib
import hmac as hmac_lib
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode

import requests

from document_catalog import aliases_for, display_name
from query_processor import normalize_text, tokenize_text


class DigiLockerClient:
    def __init__(
        self,
        access_token: str,
        client_id: str = "",
        client_secret: str = "",
        base_url: Optional[str] = None,
        timeout: int = 45,
    ):
        self.access_token = access_token.strip()
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.base_url = (base_url or os.getenv(
            "DIGILOCKER_BASE_URL", "https://digilocker.meripehchaan.gov.in"
        )).rstrip("/")
        self.issued_path = os.getenv("DIGILOCKER_ISSUED_PATH", "/public/oauth2/2/files/issued")
        self.uploaded_files_path = os.getenv("DIGILOCKER_FILES_PATH", "/public/oauth2/1/files").rstrip("/")
        self.file_path = os.getenv("DIGILOCKER_FILE_PATH", "/public/oauth2/1/file").rstrip("/")
        self.pull_issuers_path = os.getenv("DIGILOCKER_PULL_ISSUERS_PATH", "/public/oauth2/1/pull/issuers")
        self.pull_doctype_path = os.getenv("DIGILOCKER_PULL_DOCTYPE_PATH", "/public/oauth2/1/pull/doctype")
        self.pull_parameters_path = os.getenv("DIGILOCKER_PULL_PARAMETERS_PATH", "/public/oauth2/1/pull/parameters")
        self.pull_document_path = os.getenv("DIGILOCKER_PULL_DOCUMENT_PATH", "/public/oauth2/1/pull/pulldocument")
        self.timeout = timeout
        self.session = requests.Session()
        self._issued_cache = None
        self._issued_cache_at = 0.0

    @classmethod
    def from_env(cls):
        token = os.getenv("DIGILOCKER_ACCESS_TOKEN", "").strip()
        if not token:
            return None
        return cls(
            access_token=token,
            client_id=os.getenv("DIGILOCKER_CLIENT_ID", ""),
            client_secret=os.getenv("DIGILOCKER_CLIENT_SECRET", ""),
        )

    def _request(self, method: str, path: str, *, authenticated: bool = True, **kwargs):
        headers = kwargs.pop("headers", {})
        if authenticated:
            headers["Authorization"] = f"Bearer {self.access_token}"
        response = self.session.request(
            method, self.base_url + path, headers=headers, timeout=self.timeout, **kwargs
        )
        if not response.ok:
            detail = response.text[:800]
            if response.status_code == 401:
                raise RuntimeError("DigiLocker authorization is invalid or expired. Re-authorize the user and refresh DIGILOCKER_ACCESS_TOKEN.")
            if response.status_code == 403:
                raise RuntimeError("DigiLocker authorization does not include the required scope for this operation.")
            raise RuntimeError(f"DigiLocker API {response.status_code}: {detail}")
        return response

    def list_issued_documents(self, force: bool = False) -> List[Dict]:
        if not force and self._issued_cache is not None and time.time() - self._issued_cache_at < 300:
            return list(self._issued_cache)
        payload = self._request("GET", self.issued_path).json()
        items = payload.get("items") or payload.get("documents") or []
        self._issued_cache = items
        self._issued_cache_at = time.time()
        return list(items)

    def list_uploaded_documents(self, force: bool = False, max_documents: int = 5000, max_folders: int = 1000) -> List[Dict]:
        """List self-uploaded files recursively from the user's authorized DigiLocker locker.

        DigiLocker represents folders and files in the same ``items`` response. Folder IDs
        are treated as path segments and are never followed as arbitrary URLs. Bounds prevent
        malformed or unusually large folder trees from causing unbounded work.
        """
        del force  # This method intentionally performs a fresh bounded walk for each sync.
        max_documents = max(1, min(int(max_documents), 5000))
        max_folders = max(1, min(int(max_folders), 1000))
        pending: list[str | None] = [None]
        visited: set[str] = set()
        documents: list[Dict] = []
        folders_checked = 0
        while pending and folders_checked < max_folders and len(documents) < max_documents:
            folder_id = pending.pop(0)
            path = self.uploaded_files_path if folder_id is None else f"{self.uploaded_files_path}/{quote(folder_id, safe='')}"
            payload = self._request("GET", path).json()
            folders_checked += 1
            items = payload.get("items") or [] if isinstance(payload, dict) else []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").strip().lower()
                child_id = str(item.get("id") or "").strip()
                if item_type == "dir" and child_id and child_id not in visited and len(visited) < max_folders:
                    visited.add(child_id)
                    pending.append(child_id)
                    continue
                uri = str(item.get("uri") or item.get("docUri") or item.get("doc_uri") or "").strip()
                if uri and item_type not in {"dir", "folder"}:
                    documents.append({**item, "uri": uri, "_sdf_source_kind": "uploaded"})
                    if len(documents) >= max_documents:
                        break
        return documents

    _QUERY_STOPWORDS = {
        "show", "give", "get", "fetch", "find", "open", "download", "retrieve",
        "my", "me", "mine", "please", "kindly", "can", "you", "could", "would",
        "want", "need", "to", "the", "a", "an", "for", "of", "from", "is", "are",
        "hai", "mera", "meri", "mere", "mujhe", "dikhao", "dikhaiye", "dikha",
    }

    @classmethod
    def _query_terms(cls, text: str) -> set[str]:
        return {
            token for token in tokenize_text(normalize_text(text))
            if token and token not in cls._QUERY_STOPWORDS and len(token) > 1
        }

    @classmethod
    def _document_similarity(cls, item: Dict, document_type: Optional[str], document_name: str) -> int:
        haystack = normalize_text(" ".join(
            str(item.get(key, "")) for key in ("name", "description", "doctype", "issuer")
        ))
        target = normalize_text(document_name)
        score = 0
        if target and target == normalize_text(item.get("description", "")):
            score += 240
        if target and target in haystack:
            score += 140

        target_terms = cls._query_terms(document_name)
        item_terms = cls._query_terms(
            " ".join(str(item.get(key, "")) for key in ("name", "description"))
        )
        if target_terms and item_terms:
            overlap = len(target_terms & item_terms)
            score += overlap * 30
            if overlap == len(target_terms):
                score += 80

        if document_type:
            aliases = [normalize_text(x) for x in aliases_for(document_type)]
            if any(alias and alias in haystack for alias in aliases):
                score += 80
            expected = {
                "pan": {"PANCR"}, "driving_license": {"DRVLC"},
                "rc": {"RVCER"}, "marksheet": {"HSCER", "SSCER", "DMCER"},
            }.get(document_type, set())
            if str(item.get("doctype", "")).upper() in expected:
                score += 120
        return score

    def search_issued_documents(self, document_type: Optional[str] = None, document_name: str = "", limit: int = 5) -> List[Dict]:
        items = self.list_issued_documents()
        ranked = []
        for item in items:
            score = self._document_similarity(item, document_type, document_name)
            if score > 0 and item.get("uri"):
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], normalize_text(str(pair[1].get("name", "")))))
        return [dict(item, score=score, source="digilocker") for score, item in ranked[:limit]]

    def fetch_file(
        self,
        uri: str,
        destination_dir: str,
        suggested_name: str = "document",
        expected_mime_type: Optional[str] = None,
    ) -> str:
        """Download a DigiLocker file with a size limit and optional HMAC verification.

        The file is streamed to a temporary path first; it becomes visible to the indexer
        only after the download and any supplied integrity signature have been verified.
        """
        if not uri:
            raise ValueError("DigiLocker document URI is missing")
        endpoint = self.file_path
        if endpoint.endswith("/uri"):
            endpoint = endpoint[:-4]
        response = self._request("GET", f"{endpoint.rstrip('/')}/{quote(uri, safe='')}", stream=True)
        try:
            content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type in {"", "application/octet-stream"} and expected_mime_type:
                if isinstance(expected_mime_type, str):
                    content_type = expected_mime_type.split(";", 1)[0].strip().lower()
            explicit_extensions = {
                "application/pdf": ".pdf",
                "application/xml": ".xml",
                "text/xml": ".xml",
                "image/jpg": ".jpg",
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "text/plain": ".txt",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                "application/vnd.ms-excel": ".xls",
            }
            extension = explicit_extensions.get(content_type) or mimetypes.guess_extension(content_type)
            if not extension:
                raise RuntimeError(f"Unsupported document media type: {content_type or 'missing'}")
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", suggested_name).strip("._") or "document"
            if not safe_name.lower().endswith(extension):
                safe_name += extension
            destination = Path(destination_dir)
            destination.mkdir(parents=True, exist_ok=True)
            path = destination / safe_name
            if path.exists():
                path = destination / f"{path.stem}_{hashlib.sha1(uri.encode('utf-8')).hexdigest()[:8]}{path.suffix}"
            temporary_path = path.with_name(path.name + ".part")

            try:
                max_bytes = int(os.getenv("DIGILOCKER_MAX_DOCUMENT_BYTES", str(50 * 1024 * 1024)))
            except (TypeError, ValueError):
                max_bytes = 50 * 1024 * 1024
            max_bytes = max(1 * 1024 * 1024, min(max_bytes, 200 * 1024 * 1024))
            provided_hmac = response.headers.get("hmac") or response.headers.get("HMAC")
            digest = hmac_lib.new(self.client_secret.encode("utf-8"), digestmod=hashlib.sha256) if provided_hmac and self.client_secret else None
            byte_count = 0
            try:
                iterator = response.iter_content(chunk_size=1024 * 1024) if callable(getattr(response, "iter_content", None)) else (getattr(response, "content", b""),)
                with temporary_path.open("wb") as handle:
                    for chunk in iterator:
                        if not chunk:
                            continue
                        byte_count += len(chunk)
                        if byte_count > max_bytes:
                            raise RuntimeError(f"DigiLocker document exceeds the configured {max_bytes // (1024 * 1024)} MiB download limit")
                        handle.write(chunk)
                        if digest:
                            digest.update(chunk)
                if digest and provided_hmac:
                    expected = base64.b64encode(digest.digest()).decode("ascii")
                    if not hmac_lib.compare_digest(expected, provided_hmac):
                        raise RuntimeError("DigiLocker file integrity check failed (HMAC mismatch)")
                temporary_path.replace(path)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
            if byte_count == 0:
                path.unlink(missing_ok=True)
                raise RuntimeError("DigiLocker returned an empty document")
            return str(path)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def discover_issuers(self) -> List[Dict]:
        self._require_client_credentials()
        ts = str(int(time.time()))
        signature = hashlib.sha256((self.client_secret + self.client_id + ts).encode("utf-8")).hexdigest()
        response = self._request(
            "POST", self.pull_issuers_path, authenticated=False,
            data={"clientid": self.client_id, "ts": ts, "hmac": signature},
        ).json()
        return response.get("issuers") or []

    def discover_document_types(self, orgid: str) -> List[Dict]:
        self._require_client_credentials()
        ts = str(int(time.time()))
        signature = hashlib.sha256((self.client_secret + self.client_id + str(orgid) + ts).encode("utf-8")).hexdigest()
        path = self.pull_doctype_path
        response = self._request(
            "POST", path, authenticated=False,
            data={"clientid": self.client_id, "orgid": str(orgid), "ts": ts, "hmac": signature},
        ).json()
        return response.get("documents") or []

    def discover_search_parameters(self, orgid: str, doctype: str) -> List[Dict]:
        self._require_client_credentials()
        ts = str(int(time.time()))
        signature = hashlib.sha256((self.client_secret + self.client_id + str(orgid) + str(doctype) + ts).encode("utf-8")).hexdigest()
        response = self._request(
            "POST", self.pull_parameters_path, authenticated=False,
            data={"clientid": self.client_id, "orgid": str(orgid), "doctype": str(doctype), "ts": ts, "hmac": signature},
        ).json()
        return response.get("parameters") or []

    def pull_document(self, orgid: str, doctype: str, consent: str, parameters: Dict[str, str]) -> str:
        """Pull a new issuer document. Callers must provide issuer-required fields and consent."""
        if consent != "Y":
            raise ValueError("DigiLocker Pull Document requires explicit user consent (Y)")
        payload = {
            "orgid": str(orgid), "doctype": str(doctype), "consent": consent,
            **{str(key): str(value) for key, value in parameters.items()},
        }
        response = self._request("POST", self.pull_document_path, data=payload)
        self._issued_cache = None
        self._issued_cache_at = 0.0
        return str(response.json().get("uri") or "")

    def _require_client_credentials(self):
        if not self.client_id or not self.client_secret:
            raise RuntimeError("DIGILOCKER_CLIENT_ID and DIGILOCKER_CLIENT_SECRET are required for issuer metadata discovery")
