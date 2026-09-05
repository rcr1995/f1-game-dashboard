"""Memory-only screenshot intake for the Vercel-hosted Streamlit app.

The native Streamlit file uploader uses a separate HTTP PUT request.  That is
not suitable for the Vercel container deployment because a PUT can be routed
to a different instance than the authenticated WebSocket.  This small
bidirectional component sends a bounded payload through the already-connected
Streamlit session instead.

This module deliberately does not perform authentication.  Callers must render
it only after the existing Admin authentication boundary has succeeded.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import importlib.metadata
import os
import re
import secrets
import unicodedata
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

import streamlit as st


FEATURE_FLAG = "F1_WEBSOCKET_SCREENSHOT_UPLOAD"
SUPPORTED_STREAMLIT_VERSION = "1.59.2"
MIN_IMAGES = 2
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024

_COMPONENT_NAME = "f1_secure_image_upload_v1"
_PROTOCOL_VERSION = 1
_SUBMISSION_ID_RE = re.compile(r"\A[a-f0-9]{32}\Z")
_SHA256_RE = re.compile(r"\A[a-f0-9]{64}\Z")
_KEY_RE = re.compile(r"\A[A-Za-z0-9_.:-]{1,128}\Z")

_MIME_EXTENSIONS = {
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "image/webp": frozenset({".webp"}),
}

_COPY = {
    "en": {
        "label": "Race screenshots",
        "help": "Select 2 to 4 PNG, JPEG or WEBP screenshots.",
        "button": "Choose screenshots",
        "empty": "No screenshots selected",
        "ready": "{count} screenshots ready",
        "working": "Checking screenshots…",
        "count": "Select between 2 and 4 screenshots.",
        "type": "Only PNG, JPEG and WEBP screenshots are accepted.",
        "file_size": "Each screenshot must be 12 MB or smaller.",
        "total_size": "The screenshots must total 25 MB or less.",
        "duplicate": "Each screenshot must be different.",
        "read": "A screenshot could not be read. Please select the files again.",
        "invalid": "The screenshot selection could not be verified. Please select it again.",
    },
    "pt": {
        "label": "Capturas de ecrã da corrida",
        "help": "Selecione 2 a 4 capturas PNG, JPEG ou WEBP.",
        "button": "Escolher capturas",
        "empty": "Nenhuma captura selecionada",
        "ready": "{count} capturas prontas",
        "working": "A verificar as capturas…",
        "count": "Selecione entre 2 e 4 capturas de ecrã.",
        "type": "Apenas são aceites capturas PNG, JPEG e WEBP.",
        "file_size": "Cada captura deve ter no máximo 12 MB.",
        "total_size": "As capturas devem ter, no total, no máximo 25 MB.",
        "duplicate": "Cada captura de ecrã deve ser diferente.",
        "read": "Não foi possível ler uma captura. Selecione novamente os ficheiros.",
        "invalid": "Não foi possível verificar as capturas. Selecione-as novamente.",
    },
}


@dataclass(frozen=True, slots=True)
class UploadedImage:
    """An immutable, in-memory image compatible with the importer interface."""

    name: str
    content_type: str
    size: int
    sha256: str
    _content: bytes = field(repr=False)

    @property
    def type(self) -> str:
        """Match Streamlit's ``UploadedFile.type`` convenience attribute."""

        return self.content_type

    def getvalue(self) -> bytes:
        """Return the immutable image bytes without writing them to disk."""

        return self._content


class _PayloadError(ValueError):
    def __init__(self, code: str = "invalid") -> None:
        super().__init__(code)
        self.code = code


_HTML = """
<div class="upload-root">
  <label class="upload-label" for="secure-images"></label>
  <div class="upload-help"></div>
  <div class="upload-row">
    <label class="upload-button" for="secure-images"></label>
    <span class="upload-status" aria-live="polite"></span>
  </div>
  <input id="secure-images" class="upload-input" type="file" multiple
         accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" />
  <div class="upload-error" role="alert" aria-live="assertive"></div>
  <ul class="upload-files" aria-live="polite"></ul>
</div>
"""

_CSS = """
.upload-root {
  color: var(--st-text-color);
  font-family: var(--st-font);
  line-height: 1.35;
  padding: 0.15rem 0 0.25rem;
}
.upload-label {
  display: block;
  font-size: 0.875rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}
.upload-help {
  color: color-mix(in srgb, var(--st-text-color) 68%, transparent);
  font-size: 0.8rem;
  margin-bottom: 0.55rem;
}
.upload-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
}
.upload-input {
  height: 1px;
  opacity: 0;
  overflow: hidden;
  position: absolute;
  width: 1px;
}
.upload-button {
  background: var(--st-secondary-background-color);
  border: 1px solid var(--st-border-color);
  border-radius: var(--st-button-radius);
  cursor: pointer;
  display: inline-block;
  font-size: 0.875rem;
  font-weight: 600;
  padding: 0.45rem 0.85rem;
}
.upload-button:hover {
  border-color: var(--st-primary-color);
  color: var(--st-primary-color);
}
.upload-input:focus-visible + .upload-error,
.upload-button:focus-within {
  outline: 2px solid var(--st-primary-color);
  outline-offset: 2px;
}
.upload-status {
  font-size: 0.85rem;
}
.upload-error {
  color: var(--st-red-text-color);
  font-size: 0.85rem;
  min-height: 1.15rem;
  padding-top: 0.4rem;
}
.upload-files {
  font-size: 0.8rem;
  margin: 0.2rem 0 0;
  padding-left: 1.25rem;
}
"""

_JS = r"""
export default function(component) {
  const { data, parentElement, setStateValue } = component;
  const input = parentElement.querySelector('.upload-input');
  const label = parentElement.querySelector('.upload-label');
  const help = parentElement.querySelector('.upload-help');
  const button = parentElement.querySelector('.upload-button');
  const status = parentElement.querySelector('.upload-status');
  const error = parentElement.querySelector('.upload-error');
  const list = parentElement.querySelector('.upload-files');
  const messages = data.messages;
  const prior = parentElement.__f1SecureUpload;
  if (prior && prior.generation === data.generation && prior.context === data.context) {
    prior.messages = messages;
  }

  // All dynamic strings are assigned with textContent. No caller value is
  // interpreted as HTML or JavaScript.
  label.textContent = data.label;
  help.textContent = data.help_text;
  button.textContent = messages.button;

  const showSummaries = (files) => {
    const activeMessages = parentElement.__f1SecureUpload?.messages || messages;
    list.replaceChildren();
    for (const file of files) {
      const item = document.createElement('li');
      item.textContent = `${file.name} (${(file.size / 1048576).toFixed(1)} MB)`;
      list.appendChild(item);
    }
    status.textContent = files.length
      ? activeMessages.ready.replace('{count}', String(files.length))
      : activeMessages.empty;
  };

  const selectedFiles = Array.isArray(data.selected_files) ? data.selected_files : [];
  error.textContent = data.server_error || '';
  showSummaries(selectedFiles);

  if (prior && prior.generation === data.generation && prior.context === data.context) {
    if (prior.processing) {
      error.textContent = '';
      showSummaries(prior.pending_files || []);
      status.textContent = messages.working;
    }
    return prior.cleanup;
  }
  if (prior) {
    prior.cancelled = true;
    if (typeof prior.abort === 'function') prior.abort();
    input.onchange = null;
  }

  const controller = {
    cancelled: false,
    context: data.context,
    generation: data.generation,
    selection: 0,
    processing: false,
    pending_files: [],
    readers: new Set(),
    messages,
    abort: null,
    cleanup: null,
  };
  parentElement.__f1SecureUpload = controller;

  const emptyPayload = (errorCode = null) => ({
    version: data.version,
    context: data.context,
    nonce: data.nonce,
    generation: data.generation,
    submission_id: null,
    error: errorCode,
    files: [],
  });

  const showError = (code) => {
    controller.processing = false;
    controller.pending_files = [];
    const activeMessages = controller.messages;
    const message = activeMessages[code] || activeMessages.invalid;
    error.textContent = message;
    status.textContent = activeMessages.empty;
    list.replaceChildren();
    input.value = '';
    setStateValue('payload', emptyPayload(code));
  };

  const abortReaders = () => {
    for (const reader of controller.readers) {
      if (reader.readyState === FileReader.LOADING) reader.abort();
    }
    controller.readers.clear();
  };
  controller.abort = abortReaders;

  const readBytes = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    controller.readers.add(reader);
    const finish = (callback, value) => {
      controller.readers.delete(reader);
      reader.onerror = null;
      reader.onabort = null;
      reader.onload = null;
      callback(value);
    };
    reader.onerror = () => finish(reject, new Error('read'));
    reader.onabort = () => finish(reject, new Error('read'));
    reader.onload = () => finish(resolve, new Uint8Array(reader.result));
    reader.readAsArrayBuffer(file);
  });

  const bytesToBase64 = (bytes) => {
    const chunks = [];
    const chunkSize = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + chunkSize)));
    }
    return btoa(chunks.join(''));
  };

  const digestHex = async (bytes) => {
    if (!globalThis.crypto || !globalThis.crypto.subtle) {
      throw new Error('read');
    }
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest), (part) =>
      part.toString(16).padStart(2, '0')
    ).join('');
  };

  const submissionId = () => {
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    return Array.from(bytes, (part) => part.toString(16).padStart(2, '0')).join('');
  };

  const canonicalTypeForName = (name) => {
    const dot = name.lastIndexOf('.');
    const extension = dot >= 0 ? name.slice(dot).toLowerCase() : '';
    if (extension === '.jpg' || extension === '.jpeg') return 'image/jpeg';
    if (extension === '.png') return 'image/png';
    if (extension === '.webp') return 'image/webp';
    return null;
  };

  const detectMagicType = (bytes) => {
    if (bytes.length >= 8 &&
        [0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a].every((v, i) => bytes[i] === v)) {
      return 'image/png';
    }
    if (bytes.length >= 4 && bytes[0] === 0xff && bytes[1] === 0xd8 &&
        bytes[2] === 0xff && bytes[bytes.length - 2] === 0xff && bytes[bytes.length - 1] === 0xd9) {
      return 'image/jpeg';
    }
    if (bytes.length >= 12 &&
        String.fromCharCode(...bytes.subarray(0, 4)) === 'RIFF' &&
        String.fromCharCode(...bytes.subarray(8, 12)) === 'WEBP') {
      return 'image/webp';
    }
    return null;
  };

  const showFiles = (files) => {
    showSummaries(files);
  };

  input.value = '';
  error.textContent = data.server_error || '';
  showSummaries(selectedFiles);

  // A changed Python generation invalidates any browser-persisted selection
  // before it can be returned to the server again.
  if (prior) {
    setStateValue('payload', emptyPayload());
  }

  input.onchange = async () => {
    const selection = ++controller.selection;
    abortReaders();
    const files = Array.from(input.files || []);
    controller.processing = true;
    controller.pending_files = files.map((file) => ({name: file.name, size: file.size}));
    error.textContent = '';
    list.replaceChildren();

    // Invalidate a previously verified selection before any asynchronous
    // read. WebSocket message ordering then prevents an Extract click from
    // acting on old screenshots while the new selection is still processing.
    setStateValue('payload', emptyPayload());

    if (files.length < data.min_images || files.length > data.max_images) {
      showError('count');
      return;
    }
    // File.type is an untrusted browser hint. Windows/Edge can report a
    // genuine JPG as image/jpg, application/octet-stream, or an empty value.
    // Require an allowed extension here, then identify and match the actual
    // format from its bytes below before sending a canonical MIME to Python.
    const expectedTypes = files.map((file) => canonicalTypeForName(file.name));
    if (expectedTypes.some((type) => type === null)) {
      showError('type');
      return;
    }
    if (files.some((file) => file.size <= 0 || file.size > data.max_image_bytes)) {
      showError('file_size');
      return;
    }
    const total = files.reduce((sum, file) => sum + file.size, 0);
    if (total > data.max_total_bytes) {
      showError('total_size');
      return;
    }

    status.textContent = controller.messages.working;
    try {
      const encoded = [];
      const seen = new Set();
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        const bytes = await readBytes(file);
        if (controller.cancelled || selection !== controller.selection) return;
        const detectedType = detectMagicType(bytes);
        if (bytes.length !== file.size || detectedType !== expectedTypes[index]) {
          showError('type');
          return;
        }
        const sha256 = await digestHex(bytes);
        if (controller.cancelled || selection !== controller.selection) return;
        if (seen.has(sha256)) {
          showError('duplicate');
          return;
        }
        seen.add(sha256);
        encoded.push({
          name: file.name,
          type: detectedType,
          size: file.size,
          sha256,
          data: bytesToBase64(bytes),
        });
      }
      if (controller.cancelled || selection !== controller.selection) return;
      controller.processing = false;
      controller.pending_files = [];
      showFiles(files);
      status.textContent = controller.messages.ready.replace('{count}', String(files.length));
      setStateValue('payload', {
        version: data.version,
        context: data.context,
        nonce: data.nonce,
        generation: data.generation,
        submission_id: submissionId(),
        error: null,
        files: encoded,
      });
      input.value = '';
    } catch (_) {
      if (!controller.cancelled && selection === controller.selection) showError('read');
    }
  };

  controller.cleanup = () => {
    controller.cancelled = true;
    abortReaders();
    controller.pending_files = [];
    input.value = '';
    input.onchange = null;
    if (parentElement.__f1SecureUpload === controller) {
      delete parentElement.__f1SecureUpload;
    }
  };
  return controller.cleanup;
}
"""


def enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the Vercel-only, pinned component is explicitly enabled."""

    source = os.environ if environ is None else environ
    if source.get(FEATURE_FLAG) != "1":
        return False
    try:
        return importlib.metadata.version("streamlit") == SUPPORTED_STREAMLIT_VERSION
    except importlib.metadata.PackageNotFoundError:
        return False


def _normalise_lang(lang: str) -> str:
    return "pt" if isinstance(lang, str) and lang.lower().startswith("pt") else "en"


def _validate_key(key: str) -> str:
    if not isinstance(key, str) or _KEY_RE.fullmatch(key) is None:
        raise ValueError("secure upload key must be 1-128 ASCII identifier characters")
    return key


def _state_key(key: str) -> str:
    # Caller prefix is intentional: the importer and logout cleanup paths can
    # remove every byte associated with a workflow using their existing prefix.
    return f"{key}:secure_private"


def _component_key(key: str) -> str:
    return f"{key}:secure_component"


def _session_state() -> MutableMapping[str, Any]:
    return st.session_state


def _component_renderer():
    # The registry belongs to a Streamlit Runtime, not the Python process.
    # Re-registering this identical fixed definition keeps runtime recreation
    # and hot reload safe in the pinned version.
    return st.components.v2.component(
        _COMPONENT_NAME,
        html=_HTML,
        css=_CSS,
        js=_JS,
        isolate_styles=True,
    )


def _get_private_state(key: str) -> dict[str, Any]:
    session = _session_state()
    private_key = _state_key(key)
    state = session.get(private_key)
    if not isinstance(state, dict):
        state = {
            "nonce": secrets.token_urlsafe(32),
            "generation": 0,
            "cache": None,
            "seen": [],
        }
        session[private_key] = state
    nonce = state.get("nonce")
    generation = state.get("generation")
    if not isinstance(nonce, str) or len(nonce) < 32:
        state["nonce"] = secrets.token_urlsafe(32)
        state["cache"] = None
        state["seen"] = []
    if type(generation) is not int or generation < 0:
        state["generation"] = 0
        state["cache"] = None
    if not isinstance(state.get("seen"), list):
        state["seen"] = []
    return state


def _context_token(key: str, nonce: str) -> str:
    material = f"{_COMPONENT_NAME}\0{key}\0{nonce}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _safe_compare_text(candidate: Any, expected: str) -> bool:
    if not isinstance(candidate, str) or not isinstance(expected, str):
        return False
    if len(candidate) != len(expected):
        return False
    try:
        candidate.encode("ascii")
        expected.encode("ascii")
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(candidate, expected)


def _safe_text(value: str, fallback: str, *, limit: int) -> str:
    if not isinstance(value, str):
        return fallback
    value = unicodedata.normalize("NFC", value).strip()
    if not value or len(value) > limit or any(ord(char) < 32 for char in value):
        return fallback
    return value


def _valid_magic(content: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return (
            len(content) >= 4
            and content.startswith(b"\xff\xd8\xff")
            and content.endswith(b"\xff\xd9")
        )
    if content_type == "image/webp":
        return (
            len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        )
    return False


def _decode_file(raw: Any) -> UploadedImage:
    if not isinstance(raw, Mapping) or set(raw) != {
        "name",
        "type",
        "size",
        "sha256",
        "data",
    }:
        raise _PayloadError()

    name = raw["name"]
    content_type = raw["type"]
    size = raw["size"]
    expected_sha256 = raw["sha256"]
    encoded = raw["data"]

    if not isinstance(name, str) or not name or len(name) > 255:
        raise _PayloadError()
    name = unicodedata.normalize("NFC", name)
    try:
        encoded_name = name.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _PayloadError() from exc
    if (
        name in {".", ".."}
        or len(encoded_name) > 255
        or "/" in name
        or "\\" in name
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
    ):
        raise _PayloadError()

    if not isinstance(content_type, str) or content_type not in _MIME_EXTENSIONS:
        raise _PayloadError("type")
    suffix = os.path.splitext(name)[1].lower()
    if suffix not in _MIME_EXTENSIONS[content_type]:
        raise _PayloadError("type")
    if type(size) is not int or size <= 0 or size > MAX_IMAGE_BYTES:
        raise _PayloadError("file_size")
    if not isinstance(expected_sha256, str) or _SHA256_RE.fullmatch(expected_sha256) is None:
        raise _PayloadError()
    if not isinstance(encoded, str):
        raise _PayloadError()

    max_encoded = 4 * ((MAX_IMAGE_BYTES + 2) // 3)
    expected_encoded = 4 * ((size + 2) // 3)
    if len(encoded) != expected_encoded or len(encoded) > max_encoded:
        raise _PayloadError("file_size")
    try:
        ascii_encoded = encoded.encode("ascii")
        content = base64.b64decode(ascii_encoded, validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise _PayloadError() from exc
    # Reject non-canonical encodings, including non-zero padding bits.
    if base64.b64encode(content) != ascii_encoded:
        raise _PayloadError()
    if len(content) != size:
        raise _PayloadError("file_size")
    if not _valid_magic(content, content_type):
        raise _PayloadError("type")

    actual_sha256 = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise _PayloadError()
    return UploadedImage(name, content_type, size, actual_sha256, content)


def _decode_payload(
    raw: Any,
    *,
    expected_context: str,
    expected_nonce: str,
    expected_generation: int,
) -> tuple[str | None, tuple[UploadedImage, ...], str | None, str]:
    if not isinstance(raw, Mapping) or set(raw) != {
        "version",
        "context",
        "nonce",
        "generation",
        "submission_id",
        "error",
        "files",
    }:
        raise _PayloadError()
    if raw["version"] != _PROTOCOL_VERSION or type(raw["version"]) is not int:
        raise _PayloadError()
    if not _safe_compare_text(raw["context"], expected_context):
        raise _PayloadError()
    if not _safe_compare_text(raw["nonce"], expected_nonce):
        raise _PayloadError()
    if type(raw["generation"]) is not int or raw["generation"] != expected_generation:
        raise _PayloadError()

    error = raw["error"]
    submission_id = raw["submission_id"]
    files = raw["files"]
    if error is not None:
        if not isinstance(error, str) or error not in {
            "count",
            "type",
            "file_size",
            "total_size",
            "duplicate",
            "read",
        }:
            raise _PayloadError()
        if submission_id is not None or files != []:
            raise _PayloadError()
        fingerprint = hashlib.sha256(
            f"error\0{expected_context}\0{expected_generation}\0{error}".encode()
        ).hexdigest()
        return None, (), error, fingerprint

    if submission_id is None and files == []:
        fingerprint = hashlib.sha256(
            f"empty\0{expected_context}\0{expected_generation}".encode()
        ).hexdigest()
        return None, (), None, fingerprint
    if not isinstance(submission_id, str) or _SUBMISSION_ID_RE.fullmatch(submission_id) is None:
        raise _PayloadError()
    if not isinstance(files, list) or not MIN_IMAGES <= len(files) <= MAX_IMAGES:
        raise _PayloadError("count")

    declared_total = 0
    for item in files:
        if not isinstance(item, Mapping) or type(item.get("size")) is not int:
            raise _PayloadError()
        declared_total += item["size"]
    if declared_total > MAX_TOTAL_BYTES:
        raise _PayloadError("total_size")

    images = tuple(_decode_file(item) for item in files)
    if sum(image.size for image in images) > MAX_TOTAL_BYTES:
        raise _PayloadError("total_size")
    hashes = [image.sha256 for image in images]
    names = [image.name.casefold() for image in images]
    if len(set(hashes)) != len(hashes) or len(set(names)) != len(names):
        raise _PayloadError("duplicate")

    digest = hashlib.sha256()
    digest.update(expected_context.encode("ascii"))
    digest.update(str(expected_generation).encode("ascii"))
    digest.update(submission_id.encode("ascii"))
    for image in images:
        digest.update(image.sha256.encode("ascii"))
        digest.update(b"\0")
        digest.update(image.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(image.content_type.encode("ascii"))
    return submission_id, images, None, digest.hexdigest()


def _consume_payload(
    raw: Any,
    *,
    expected_context: str,
    expected_nonce: str,
    expected_generation: int,
    private_state: dict[str, Any],
) -> tuple[list[UploadedImage], str | None]:
    # A repeated Streamlit rerun carries the same component state. Reuse the
    # already-verified immutable objects without decoding their base64 again.
    if isinstance(raw, Mapping):
        candidate_id = raw.get("submission_id")
        cached = private_state.get("cache")
        if (
            isinstance(candidate_id, str)
            and isinstance(cached, dict)
            and cached.get("submission_id") == candidate_id
        ):
            if not _matches_cached_payload(
                raw,
                expected_context=expected_context,
                expected_nonce=expected_nonce,
                expected_generation=expected_generation,
                cached=cached,
            ):
                private_state["cache"] = None
                raise _PayloadError()
            cached_images = cached["images"]
            return list(cached_images), None

    submission_id, images, error, fingerprint = _decode_payload(
        raw,
        expected_context=expected_context,
        expected_nonce=expected_nonce,
        expected_generation=expected_generation,
    )
    if submission_id is None:
        private_state["cache"] = None
        return [], error

    seen = private_state.setdefault("seen", [])
    if not isinstance(seen, list):
        seen = []
        private_state["seen"] = seen
    if submission_id in seen:
        private_state["cache"] = None
        raise _PayloadError()
    seen.append(submission_id)

    private_state["cache"] = {
        "submission_id": submission_id,
        "fingerprint": fingerprint,
        "images": images,
        # Retain only small digests, not a second copy/reference to up to 33 MiB
        # of base64 component state.
        "encoded_sha256": tuple(
            hashlib.sha256(item["data"].encode("ascii")).hexdigest()
            for item in raw["files"]
        ),
    }
    return list(images), None


def _matches_cached_payload(
    raw: Mapping[str, Any],
    *,
    expected_context: str,
    expected_nonce: str,
    expected_generation: int,
    cached: Mapping[str, Any],
) -> bool:
    if set(raw) != {
        "version",
        "context",
        "nonce",
        "generation",
        "submission_id",
        "error",
        "files",
    }:
        return False
    if (
        type(raw["version"]) is not int
        or raw["version"] != _PROTOCOL_VERSION
        or not _safe_compare_text(raw["context"], expected_context)
        or not _safe_compare_text(raw["nonce"], expected_nonce)
        or type(raw["generation"]) is not int
        or raw["generation"] != expected_generation
        or raw["error"] is not None
        or not isinstance(raw["files"], list)
    ):
        return False
    images = cached.get("images")
    encoded_sha256 = cached.get("encoded_sha256")
    if (
        not isinstance(images, tuple)
        or not isinstance(encoded_sha256, tuple)
        or len(raw["files"]) != len(images)
        or len(images) != len(encoded_sha256)
    ):
        return False
    for item, image, cached_digest in zip(
        raw["files"], images, encoded_sha256, strict=True
    ):
        if not isinstance(item, Mapping) or set(item) != {
            "name",
            "type",
            "size",
            "sha256",
            "data",
        }:
            return False
        candidate_data = item.get("data")
        candidate_name = item.get("name")
        if not isinstance(candidate_name, str) or len(candidate_name) > 255:
            return False
        candidate_name = unicodedata.normalize("NFC", candidate_name)
        expected_encoded_length = (
            4 * ((image.size + 2) // 3) if isinstance(image, UploadedImage) else -1
        )
        if not isinstance(image, UploadedImage) or (
            candidate_name != image.name
            or item["type"] != image.content_type
            or type(item["size"]) is not int
            or item["size"] != image.size
            or item["sha256"] != image.sha256
            or not isinstance(candidate_data, str)
            or len(candidate_data) != expected_encoded_length
            or len(candidate_data) > 4 * ((MAX_IMAGE_BYTES + 2) // 3)
            or not isinstance(cached_digest, str)
            or _SHA256_RE.fullmatch(cached_digest) is None
        ):
            return False
        try:
            encoded_digest = hashlib.sha256(candidate_data.encode("ascii")).hexdigest()
        except UnicodeEncodeError:
            return False
        if not hmac.compare_digest(encoded_digest, cached_digest):
            return False
    return True


def _payload_from_component_state(value: Any) -> Any:
    return value.get("payload") if isinstance(value, Mapping) else None


def _consume_for_render(
    raw: Any,
    *,
    context: str,
    nonce: str,
    generation: int,
    state: dict[str, Any],
    copy: Mapping[str, str],
) -> tuple[list[UploadedImage], list[str]]:
    if raw is None:
        return [], []
    # A generation bump is the intentional clear protocol. The old widget
    # value can remain visible to Python for one run while the browser receives
    # the bump, so discard it silently rather than presenting it as tampering.
    if isinstance(raw, Mapping) and raw.get("generation") != generation:
        return [], []
    try:
        images, error_code = _consume_payload(
            raw,
            expected_context=context,
            expected_nonce=nonce,
            expected_generation=generation,
            private_state=state,
        )
    except _PayloadError as exc:
        state["cache"] = None
        error_code = exc.code if exc.code in copy else "invalid"
        return [], [copy[error_code]]
    return images, [copy[error_code]] if error_code else []


def render_uploader(
    label: str,
    *,
    help_text: str,
    key: str,
    lang: str,
) -> tuple[list[UploadedImage], list[str]]:
    """Render the secure image picker and return verified in-memory images.

    The component must only be called inside the already-authenticated Admin
    page.  A stable ``key`` preserves a valid selection across ordinary reruns.
    Call :func:`clear_uploader` after publishing, cancelling, or changing the
    event context.
    """

    key = _validate_key(key)
    language = _normalise_lang(lang)
    copy = _COPY[language]
    state = _get_private_state(key)
    nonce = state["nonce"]
    generation = state["generation"]
    context = _context_token(key, nonce)

    component_key = _component_key(key)
    prior_raw = _payload_from_component_state(_session_state().get(component_key))
    images, errors = _consume_for_render(
        prior_raw,
        context=context,
        nonce=nonce,
        generation=generation,
        state=state,
        copy=copy,
    )

    result = _component_renderer()(
        key=component_key,
        data={
            "version": _PROTOCOL_VERSION,
            "context": context,
            "nonce": nonce,
            "generation": generation,
            "min_images": MIN_IMAGES,
            "max_images": MAX_IMAGES,
            "max_image_bytes": MAX_IMAGE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "label": _safe_text(label, copy["label"], limit=300),
            "help_text": _safe_text(help_text, copy["help"], limit=1000),
            "messages": copy,
            "selected_files": [
                {"name": image.name, "size": image.size} for image in images
            ],
            "server_error": errors[0] if errors else "",
        },
        on_payload_change=lambda: None,
        width="stretch",
        height="content",
    )
    current_raw = _payload_from_component_state(result)
    if current_raw is None:
        return images, errors
    return _consume_for_render(
        current_raw,
        context=context,
        nonce=nonce,
        generation=generation,
        state=state,
        copy=copy,
    )


def clear_uploader(key: str) -> None:
    """Invalidate and clear a component selection on its next render."""

    key = _validate_key(key)
    state = _get_private_state(key)
    generation = state["generation"]
    state["generation"] = generation + 1 if generation < 2**31 - 1 else 0
    state["cache"] = None
    state["seen"] = []


__all__ = [
    "MAX_IMAGE_BYTES",
    "MAX_IMAGES",
    "MAX_TOTAL_BYTES",
    "MIN_IMAGES",
    "UploadedImage",
    "clear_uploader",
    "enabled",
    "render_uploader",
]
