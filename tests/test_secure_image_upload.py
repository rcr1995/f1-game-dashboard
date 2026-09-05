from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib

import pytest

import secure_image_upload as upload


CONTEXT = "c" * 64
NONCE = "n" * 43
GENERATION = 7


def _content(kind: str, marker: int) -> bytes:
    body = bytes([marker]) * (marker + 1)
    if kind == "png":
        return b"\x89PNG\r\n\x1a\n" + body
    if kind == "jpeg":
        return b"\xff\xd8\xff\xe0" + body + b"\xff\xd9"
    if kind == "webp":
        return b"RIFF" + len(body).to_bytes(4, "little") + b"WEBP" + body
    raise AssertionError(kind)


def _raw_file(kind: str, marker: int, *, name: str | None = None) -> dict[str, object]:
    mime = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}[kind]
    extension = {"png": "png", "jpeg": "jpg", "webp": "webp"}[kind]
    content = _content(kind, marker)
    return {
        "name": name or f"shot-{marker}.{extension}",
        "type": mime,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "data": base64.b64encode(content).decode("ascii"),
    }


def _payload(
    files: list[dict[str, object]],
    *,
    submission_id: str = "a" * 32,
    context: object = CONTEXT,
    nonce: object = NONCE,
    generation: object = GENERATION,
) -> dict[str, object]:
    return {
        "version": 1,
        "context": context,
        "nonce": nonce,
        "generation": generation,
        "submission_id": submission_id,
        "error": None,
        "files": files,
    }


def _decode(raw: object):
    return upload._decode_payload(
        raw,
        expected_context=CONTEXT,
        expected_nonce=NONCE,
        expected_generation=GENERATION,
    )


def test_enabled_requires_exact_flag_and_pinned_streamlit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(upload.importlib.metadata, "version", lambda _: "1.59.2")
    assert upload.enabled({}) is False
    assert upload.enabled({upload.FEATURE_FLAG: "true"}) is False
    assert upload.enabled({upload.FEATURE_FLAG: "1"}) is True

    monkeypatch.setattr(upload.importlib.metadata, "version", lambda _: "1.60.0")
    assert upload.enabled({upload.FEATURE_FLAG: "1"}) is False


def test_enabled_fails_closed_when_streamlit_is_not_installed(monkeypatch: pytest.MonkeyPatch):
    def missing(_: str) -> str:
        raise upload.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(upload.importlib.metadata, "version", missing)
    assert upload.enabled({upload.FEATURE_FLAG: "1"}) is False


@pytest.mark.parametrize("count", [2, 3, 4])
def test_accepts_two_three_or_four_supported_images(count: int):
    kinds = ["png", "jpeg", "webp", "png"]
    files = [_raw_file(kinds[index], index + 1) for index in range(count)]

    submission_id, images, error, fingerprint = _decode(_payload(files))

    assert submission_id == "a" * 32
    assert error is None
    assert len(images) == count
    assert len(fingerprint) == 64
    assert [image.name for image in images] == [item["name"] for item in files]
    assert all(image.getvalue() for image in images)


@pytest.mark.parametrize("count", [1, 5])
def test_rejects_image_counts_outside_bounds(count: int):
    files = [_raw_file("png", index + 1) for index in range(count)]
    with pytest.raises(upload._PayloadError, match="count"):
        _decode(_payload(files))


def test_uploaded_image_is_immutable_and_streamlit_compatible():
    _, images, _, _ = _decode(_payload([_raw_file("png", 1), _raw_file("jpeg", 2)]))
    image = images[0]

    assert image.type == "image/png"
    assert image.getvalue() == _content("png", 1)
    assert "_content" not in repr(image)
    with pytest.raises(dataclasses.FrozenInstanceError):
        image.name = "changed.png"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("context", "wrong"),
        ("context", "é"),
        ("nonce", "wrong"),
        ("nonce", "é"),
        ("generation", 8),
        ("generation", True),
    ],
)
def test_rejects_cross_context_nonce_and_generation(field: str, value: object):
    raw = _payload([_raw_file("png", 1), _raw_file("jpeg", 2)])
    raw[field] = value
    with pytest.raises(upload._PayloadError):
        _decode(raw)


def test_rejects_unknown_envelope_and_file_fields():
    raw = _payload([_raw_file("png", 1), _raw_file("jpeg", 2)])
    raw["unexpected"] = "value"
    with pytest.raises(upload._PayloadError):
        _decode(raw)

    raw = _payload([_raw_file("png", 1), _raw_file("jpeg", 2)])
    raw["files"][0]["unexpected"] = "value"
    with pytest.raises(upload._PayloadError):
        _decode(raw)


@pytest.mark.parametrize(
    "name",
    [
        "../shot.png",
        "folder/shot.png",
        "folder\\shot.png",
        "bad\x00.png",
        f"{'x' * 256}.png",
    ],
)
def test_rejects_unsafe_filenames(name: str):
    with pytest.raises(upload._PayloadError):
        _decode(_payload([_raw_file("png", 1, name=name), _raw_file("jpeg", 2)]))


def test_rejects_mime_extension_and_magic_mismatches():
    wrong_extension = _raw_file("png", 1, name="shot.jpg")
    with pytest.raises(upload._PayloadError, match="type"):
        _decode(_payload([wrong_extension, _raw_file("jpeg", 2)]))

    wrong_magic = _raw_file("png", 1)
    content = b"not a real png"
    wrong_magic.update(
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        data=base64.b64encode(content).decode("ascii"),
    )
    with pytest.raises(upload._PayloadError, match="type"):
        _decode(_payload([wrong_magic, _raw_file("jpeg", 2)]))


def test_rejects_declared_size_hash_and_noncanonical_base64():
    bad_size = _raw_file("png", 1)
    bad_size["size"] += 1
    with pytest.raises(upload._PayloadError, match="file_size"):
        _decode(_payload([bad_size, _raw_file("jpeg", 2)]))

    bad_hash = _raw_file("png", 1)
    bad_hash["sha256"] = "0" * 64
    with pytest.raises(upload._PayloadError):
        _decode(_payload([bad_hash, _raw_file("jpeg", 2)]))

    # This fixture forces == padding; change only ignored padding bits.
    noncanonical = _raw_file("png", 1)
    content = _content("png", 1)
    encoded = base64.b64encode(content).decode("ascii")
    assert encoded.endswith("==")
    replacement = "B" if encoded[-3] == "A" else "A"
    noncanonical.update(
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        data=encoded[:-3] + replacement + "==",
    )
    with pytest.raises(upload._PayloadError):
        _decode(_payload([noncanonical, _raw_file("jpeg", 2)]))


def test_rejects_per_file_and_declared_total_limits_before_decoding():
    too_large = _raw_file("png", 1)
    too_large["size"] = upload.MAX_IMAGE_BYTES + 1
    with pytest.raises(upload._PayloadError, match="file_size"):
        _decode(_payload([too_large, _raw_file("jpeg", 2)]))

    files = [_raw_file("png", index + 1) for index in range(3)]
    for item in files:
        item["size"] = 9 * 1024 * 1024
    with pytest.raises(upload._PayloadError, match="total_size"):
        _decode(_payload(files))


def test_rejects_duplicate_content_and_duplicate_casefolded_names():
    duplicate_content = [_raw_file("png", 1), _raw_file("png", 1, name="other.png")]
    with pytest.raises(upload._PayloadError, match="duplicate"):
        _decode(_payload(duplicate_content))

    duplicate_names = [_raw_file("png", 1, name="Shot.png"), _raw_file("png", 2, name="shot.PNG")]
    with pytest.raises(upload._PayloadError, match="duplicate"):
        _decode(_payload(duplicate_names))


def test_client_error_is_bounded_and_must_echo_context():
    raw = _payload([])
    raw.update(submission_id=None, error="count")
    submission_id, images, error, _ = _decode(raw)
    assert submission_id is None
    assert images == ()
    assert error == "count"

    raw["error"] = "arbitrary"
    with pytest.raises(upload._PayloadError):
        _decode(raw)


def test_malformed_error_and_surrogate_filename_fail_closed():
    raw = _payload([])
    raw.update(submission_id=None, error=[])
    with pytest.raises(upload._PayloadError):
        _decode(raw)

    raw = _payload([_raw_file("png", 1, name="bad\ud800.png"), _raw_file("jpeg", 2)])
    with pytest.raises(upload._PayloadError):
        _decode(raw)


def test_duplicate_rerun_uses_cached_objects_and_tampering_fails_closed():
    raw = _payload([_raw_file("png", 1), _raw_file("jpeg", 2)])
    state = {"cache": None, "seen": []}
    first, error = upload._consume_payload(
        raw,
        expected_context=CONTEXT,
        expected_nonce=NONCE,
        expected_generation=GENERATION,
        private_state=state,
    )
    assert error is None

    second, error = upload._consume_payload(
        copy.deepcopy(raw),
        expected_context=CONTEXT,
        expected_nonce=NONCE,
        expected_generation=GENERATION,
        private_state=state,
    )
    assert error is None
    assert second[0] is first[0]

    tampered = copy.deepcopy(raw)
    tampered["files"][0]["name"] = "tampered.png"
    with pytest.raises(upload._PayloadError):
        upload._consume_payload(
            tampered,
            expected_context=CONTEXT,
            expected_nonce=NONCE,
            expected_generation=GENERATION,
            private_state=state,
        )
    assert state["cache"] is None


def test_cached_rerun_accepts_decomposed_unicode_filename_as_same_normalized_name():
    raw = _payload(
        [
            _raw_file("png", 1, name="Cafe\u0301.png"),
            _raw_file("jpeg", 2),
        ]
    )
    state = {"cache": None, "seen": []}

    first, _ = upload._consume_payload(
        raw,
        expected_context=CONTEXT,
        expected_nonce=NONCE,
        expected_generation=GENERATION,
        private_state=state,
    )
    second, _ = upload._consume_payload(
        copy.deepcopy(raw),
        expected_context=CONTEXT,
        expected_nonce=NONCE,
        expected_generation=GENERATION,
        private_state=state,
    )

    assert first[0].name == "Café.png"
    assert second[0] is first[0]


def test_cached_fast_path_rejects_non_ascii_without_type_error():
    raw = _payload([_raw_file("png", 1), _raw_file("jpeg", 2)])
    state = {"cache": None, "seen": []}
    upload._consume_payload(
        raw,
        expected_context=CONTEXT,
        expected_nonce=NONCE,
        expected_generation=GENERATION,
        private_state=state,
    )
    tampered = copy.deepcopy(raw)
    encoded_length = len(tampered["files"][0]["data"])
    tampered["files"][0]["data"] = "é" * encoded_length

    with pytest.raises(upload._PayloadError):
        upload._consume_payload(
            tampered,
            expected_context=CONTEXT,
            expected_nonce=NONCE,
            expected_generation=GENERATION,
            private_state=state,
        )

    assert state["cache"] is None


@pytest.mark.parametrize("replacement", ["é" * 16, "A" * 17])
def test_cached_fast_path_bounds_and_ascii_checks_payload_data(replacement: str):
    raw = _payload([_raw_file("png", 1), _raw_file("jpeg", 2)])
    state = {"cache": None, "seen": []}
    upload._consume_payload(
        raw,
        expected_context=CONTEXT,
        expected_nonce=NONCE,
        expected_generation=GENERATION,
        private_state=state,
    )
    malformed = copy.deepcopy(raw)
    malformed["files"][0]["data"] = replacement
    with pytest.raises(upload._PayloadError):
        upload._consume_payload(
            malformed,
            expected_context=CONTEXT,
            expected_nonce=NONCE,
            expected_generation=GENERATION,
            private_state=state,
        )


def test_previously_seen_submission_cannot_replace_newer_selection():
    first_raw = _payload(
        [_raw_file("png", 1), _raw_file("jpeg", 2)], submission_id="a" * 32
    )
    second_raw = _payload(
        [_raw_file("png", 3), _raw_file("webp", 4)], submission_id="b" * 32
    )
    state = {"cache": None, "seen": []}
    for raw in (first_raw, second_raw):
        images, error = upload._consume_payload(
            raw,
            expected_context=CONTEXT,
            expected_nonce=NONCE,
            expected_generation=GENERATION,
            private_state=state,
        )
        assert len(images) == 2 and error is None

    with pytest.raises(upload._PayloadError):
        upload._consume_payload(
            first_raw,
            expected_context=CONTEXT,
            expected_nonce=NONCE,
            expected_generation=GENERATION,
            private_state=state,
        )


def test_first_submission_cannot_replay_after_more_than_thirty_two_reselections():
    state = {"cache": None, "seen": []}
    first_raw = None
    for index in range(34):
        submission_id = f"{index:032x}"
        raw = _payload(
            [_raw_file("png", index + 1), _raw_file("jpeg", index + 2)],
            submission_id=submission_id,
        )
        if first_raw is None:
            first_raw = copy.deepcopy(raw)
        images, error = upload._consume_payload(
            raw,
            expected_context=CONTEXT,
            expected_nonce=NONCE,
            expected_generation=GENERATION,
            private_state=state,
        )
        assert len(images) == 2 and error is None

    with pytest.raises(upload._PayloadError):
        upload._consume_payload(
            first_raw,
            expected_context=CONTEXT,
            expected_nonce=NONCE,
            expected_generation=GENERATION,
            private_state=state,
        )


def test_render_api_uses_server_context_and_returns_localised_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    session: dict[str, object] = {}
    captured: dict[str, object] = {}

    def component(**kwargs):
        captured.update(kwargs)
        data = kwargs["data"]
        return {
            "payload": {
                "version": 1,
                "context": data["context"],
                "nonce": data["nonce"],
                "generation": data["generation"],
                "submission_id": None,
                "error": "count",
                "files": [],
            }
        }

    monkeypatch.setattr(upload, "_session_state", lambda: session)
    monkeypatch.setattr(upload, "_component_renderer", lambda: component)

    images, errors = upload.render_uploader(
        "Capturas",
        help_text="Ajuda",
        key="race_results",
        lang="pt-PT",
    )

    assert images == []
    assert errors == [upload._COPY["pt"]["count"]]
    data = captured["data"]
    assert data["context"] == upload._context_token("race_results", data["nonce"])
    assert captured["key"] == "race_results:secure_component"
    assert captured["on_payload_change"] is not None


def test_render_restores_verified_summaries_from_session_before_mount(
    monkeypatch: pytest.MonkeyPatch,
):
    session: dict[str, object] = {}
    captured: dict[str, object] = {}
    key = "race_import_uploads_v2_event"
    monkeypatch.setattr(upload, "_session_state", lambda: session)
    state = upload._get_private_state(key)
    state["nonce"] = NONCE
    state["generation"] = GENERATION
    context = upload._context_token(key, NONCE)
    raw = _payload(
        [_raw_file("png", 1), _raw_file("jpeg", 2)],
        context=context,
        nonce=NONCE,
        generation=GENERATION,
    )
    session[upload._component_key(key)] = {"payload": raw}

    def component(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(upload, "_component_renderer", lambda: component)
    images, errors = upload.render_uploader(
        "Screenshots",
        help_text="Select files",
        key=key,
        lang="en",
    )

    assert len(images) == 2
    assert errors == []
    assert captured["data"]["selected_files"] == [
        {"name": "shot-1.png", "size": len(_content("png", 1))},
        {"name": "shot-2.jpg", "size": len(_content("jpeg", 2))},
    ]
    assert captured["data"]["server_error"] == ""


def test_clear_uploader_rotates_generation_and_drops_memory_cache(
    monkeypatch: pytest.MonkeyPatch,
):
    session: dict[str, object] = {}
    monkeypatch.setattr(upload, "_session_state", lambda: session)
    state = upload._get_private_state("race_results")
    state["cache"] = {"images": (object(),)}
    state["seen"] = ["a" * 32]

    upload.clear_uploader("race_results")

    assert state["generation"] == 1
    assert state["cache"] is None
    assert state["seen"] == []


def test_component_uses_fixed_safe_dom_and_browser_side_bounds():
    assert "FileReader" in upload._JS
    assert "setStateValue('payload'" in upload._JS
    assert "textContent" in upload._JS
    assert "innerHTML" not in upload._JS
    assert "data.min_images" in upload._JS
    assert "data.max_images" in upload._JS
    assert "data.max_image_bytes" in upload._JS
    assert "data.max_total_bytes" in upload._JS
    assert "validateMagic" in upload._JS
    assert "SHA-256" in upload._JS
    assert "prior.messages = messages" in upload._JS
    assert "controller.messages" in upload._JS
    onchange = upload._JS.index("input.onchange = async")
    invalidate = upload._JS.index("setStateValue('payload', emptyPayload());", onchange)
    first_await = upload._JS.index("await readBytes", onchange)
    assert onchange < invalidate < first_await
    assert "selection === controller.selection" in upload._JS


def test_caller_prefix_cleanup_removes_widget_payload_and_decoded_bytes(
    monkeypatch: pytest.MonkeyPatch,
):
    session: dict[str, object] = {}
    monkeypatch.setattr(upload, "_session_state", lambda: session)
    key = "race_import_images"
    state = upload._get_private_state(key)
    secret_bytes = b"screenshot bytes must not survive cleanup"
    state["cache"] = {"images": (secret_bytes,)}
    session[upload._component_key(key)] = {
        "payload": {"files": [{"data": base64.b64encode(secret_bytes).decode()}]}
    }

    assert upload._state_key(key).startswith(key)
    assert upload._component_key(key).startswith(key)
    for session_key in list(session):
        if session_key.startswith(key):
            del session[session_key]

    assert not any(session_key.startswith(key) for session_key in session)
    assert secret_bytes not in repr(session).encode()
