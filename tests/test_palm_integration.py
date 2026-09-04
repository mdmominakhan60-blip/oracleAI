from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.deps import get_db
from app.api.main import app
from app.core import palm as palm_core
from app.core import tool_registry as skills
from app.core.agents.registry import get
from app.repo import palm as palm_repo, users


FIXTURE = Path(__file__).parent / "fixtures" / "palm" / "palm_hand.jpg"


@pytest.fixture
async def client(db, user):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                      headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.pop(get_db, None)


def _vision_payload() -> str:
    return json.dumps({
        "status": "complete",
        "image_quality": {"score": 0.93, "issues": []},
        "hand_detected": True,
        "hand_side": "unknown",
        "observations": [
            {"topic": "heart_line", "visibility": "clear",
             "summary": "На фото видна непрерывная дуга под основаниями пальцев.",
             "confidence": 0.84},
            {"topic": "head_line", "visibility": "partial",
             "summary": "Центральный участок линии головы различим, края кадра менее ясны.",
             "confidence": 0.66},
        ],
        "lines": {
            "heart": {"visibility": "clear", "continuity": "continuous", "confidence": 0.84},
            "head": {"visibility": "partial", "confidence": 0.66},
        },
        "mounts": {"venus": {"visibility": "partial", "confidence": 0.55}},
        "fingers": {},
        "interpretive_prompts": ["Где тебе проще показывать чувства действиями, а не словами?"],
        "limitations": ["На одном кадре нельзя уверенно оценить мелкие линии у края ладони."],
        "safety_flags": [],
    }, ensure_ascii=False)


@pytest.mark.asyncio
async def test_real_jpeg_upload_runs_palm_pipeline_and_agent_tools(client, db, user, monkeypatch):
    """Настоящий JPEG проходит HTTP → Pillow → vision boundary → SQLite → tool executor."""
    image = FIXTURE.read_bytes()
    seen: dict[str, object] = {}

    async def fake_complete_vision(system, user_text, image_data_url, **kwargs):
        seen["system"] = system
        seen["user_text"] = user_text
        seen["kwargs"] = kwargs
        assert image_data_url.startswith("data:image/jpeg;base64,")
        encoded = image_data_url.split(",", 1)[1]
        normalized_bytes = base64.b64decode(encoded)
        with Image.open(io.BytesIO(normalized_bytes)) as normalized:
            seen["normalized_size"] = normalized.size
            assert normalized.format == "JPEG"
            assert min(normalized.size) >= palm_core.MIN_SIDE
        return _vision_payload()

    monkeypatch.setattr(palm_core.llm, "complete_vision", fake_complete_vision)

    before = await client.get("/api/palm", params={"dev_user": user["tg_id"]})
    assert before.status_code == 200
    assert before.json() == {"items": [], "raw_image_stored": False}

    response = await client.post(
        "/api/palm",
        params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"},
        content=image,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    reading_id = result["id"]
    assert result["status"] == "complete"
    assert result["source"] == "vision_llm_observation"
    assert result["image_meta"]["raw_stored"] is False
    assert result["image_meta"]["width"] == 2592
    assert result["image_meta"]["height"] == 1728
    assert {row["topic"] for row in result["observations"]} == {"heart_line", "head_line"}
    assert seen["normalized_size"] == (2592, 1728)
    assert "видимыми признаками" in str(seen["system"])
    assert "[SHARED_CONTEXT]" in str(seen["system"])
    assert "[NATAL_CONTEXT_JSON]" in str(seen["system"])
    assert "DETERMINISTIC CAPTURE PRECHECK" in str(seen["user_text"])
    assert seen["kwargs"]["purpose"] == "palm:vision"
    assert seen["kwargs"]["tg_id"] == user["tg_id"]
    response_format = seen["kwargs"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert seen["kwargs"]["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert isinstance(seen["kwargs"]["additional_image_data_urls"], list)
    assert seen["kwargs"]["additional_image_data_urls"]
    assert all(url.startswith("data:image/jpeg;base64,") for url in seen["kwargs"]["additional_image_data_urls"])

    cursor = await db.execute(
        "SELECT id, tg_id, image_sha256, image_size, analysis_json FROM palm_readings WHERE id=?",
        (reading_id,),
    )
    stored = await cursor.fetchone()
    assert stored["id"] == reading_id
    assert stored["tg_id"] == user["tg_id"]
    assert stored["image_sha256"] == hashlib.sha256(image).hexdigest()
    assert stored["image_size"] == len(image)
    assert "heart_line" in stored["analysis_json"]
    assert "image_data" not in stored["analysis_json"]

    listed = await client.get("/api/palm", params={"dev_user": user["tg_id"]})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == reading_id
    fetched = await client.get(f"/api/palm/{reading_id}", params={"dev_user": user["tg_id"]})
    assert fetched.status_code == 200
    assert fetched.json()["id"] == reading_id

    chiromant = get("chiromant")
    tool_names = {tool["name"] for tool in skills.tools_for(chiromant.skills)}
    assert tool_names == {"activate_skill", "palm_scanner", "palm_photo_guide", "palm_history"}
    activated = await skills.execute(
        db, user, "activate_skill", {"skill_name": "relationship-lines", "_agent_code": "chiromant"})
    assert "[ACTIVATED_SKILL]" in activated
    assert "ACTIVE_SKILL: relationship-lines" in activated
    guarded = await skills.execute(
        db, user, "activate_skill", {"skill_name": "heart-line-depth", "_agent_code": "chiromant"})
    assert "ACTIVE_SKILL: anti-barnum-protocol" in guarded
    assert "ACTIVE_SKILL: heart-line-depth" in guarded
    unknown = await skills.execute(
        db, user, "activate_skill", {"skill_name": "not-a-real-skill", "_agent_code": "chiromant"})
    assert "unknown skill" in unknown
    evidence = await skills.execute(
        db, user, "palm_scanner", {"reading_id": reading_id})
    assert "heart_line" in evidence
    assert "Полное сканирование ладони" in evidence
    assert '"score":0.93' in evidence
    assert '"label":"линия сердца"' in evidence
    assert "hand_shape_element" in evidence
    assert "continuous" in evidence
    assert '"full_scope"' in evidence
    assert '"line_catalog"' in evidence
    assert '"raw_edge_map_stored":false' in evidence

    empty_args = await skills.execute(db, user, "palm_scanner", {})
    assert "heart_line" in empty_args

    second_id = await palm_repo.save_reading(
        db, user["tg_id"], result,
        image_sha256=hashlib.sha256(image + b"-second").hexdigest(),
        image_size=len(image), surface="integration",
    )
    by_id = await skills.execute(
        db, user, "palm_scanner", {"reading_id": second_id})
    assert f'"reading_id":{second_id}' in by_id

    deleted = await client.delete(f"/api/palm/{reading_id}", params={"dev_user": user["tg_id"]})
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert (await client.get(f"/api/palm/{reading_id}", params={"dev_user": user["tg_id"]})).status_code == 404
    cursor = await db.execute(
        "SELECT status, hand_side, image_sha256, image_size, analysis_json "
        "FROM palm_readings WHERE id=?", (reading_id,))
    scrubbed = await cursor.fetchone()
    assert dict(scrubbed) == {
        "status": "deleted", "hand_side": "unknown", "image_sha256": None,
        "image_size": None, "analysis_json": None,
    }
    deleted_second = await client.delete(f"/api/palm/{second_id}", params={"dev_user": user["tg_id"]})
    assert deleted_second.status_code == 200
    assert "чтений ладони пока нет" in await skills.execute(db, user, "palm_scanner", {})


@pytest.mark.asyncio
async def test_palm_reading_is_private_and_deleted_from_other_user(client, db, user, monkeypatch):
    """Чтение нельзя получить или удалить по чужому Telegram user id."""
    image = FIXTURE.read_bytes()

    async def fake_complete_vision(*args, **kwargs):
        return _vision_payload()

    monkeypatch.setattr(palm_core.llm, "complete_vision", fake_complete_vision)
    created = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"}, content=image,
    )
    reading_id = created.json()["id"]

    await users.ensure(db, 1003, "Другой пользователь")
    other_get = await client.get(f"/api/palm/{reading_id}", params={"dev_user": 1003})
    other_delete = await client.delete(f"/api/palm/{reading_id}", params={"dev_user": 1003})
    assert other_get.status_code == 404
    assert other_delete.status_code == 404

    owner_get = await client.get(f"/api/palm/{reading_id}", params={"dev_user": user["tg_id"]})
    assert owner_get.status_code == 200


@pytest.mark.asyncio
async def test_palm_upload_rejects_invalid_content_and_small_real_image(client, user):
    invalid_type = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "application/json"}, content=b"{}",
    )
    assert invalid_type.status_code == 415

    invalid_image = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"}, content=b"not-an-image",
    )
    assert invalid_image.status_code == 400

    with Image.open(FIXTURE) as source:
        small = source.resize((320, 240))
        buffer = io.BytesIO()
        small.save(buffer, format="JPEG")
    too_small = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"}, content=buffer.getvalue(),
    )
    assert too_small.status_code == 400
    assert "минимальная сторона" in too_small.json()["detail"]


@pytest.mark.asyncio
async def test_mira_chat_upload_accepts_png_and_webp(client, user, monkeypatch):
    """Фото из gallery/camera formats проходят тот же backend contract, что и JPEG."""
    async def fake_complete_vision(*args, **kwargs):
        return _vision_payload()

    monkeypatch.setattr(palm_core.llm, "complete_vision", fake_complete_vision)
    with Image.open(FIXTURE) as source:
        original = source.convert("RGB")
        for image_format, mime in (("PNG", "image/png"), ("WEBP", "image/webp")):
            buffer = io.BytesIO()
            original.save(buffer, format=image_format)
            response = await client.post(
                "/api/palm", params={"dev_user": user["tg_id"]},
                headers={"content-type": mime}, content=buffer.getvalue(),
            )
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["status"] == "complete"
            assert result["image_meta"]["raw_stored"] is False
            assert result["image_meta"]["width"] == 2592
            assert result["image_meta"]["height"] == 1728


@pytest.mark.asyncio
async def test_mira_upload_enforces_auth_and_declared_size(client, user):
    no_identity = await client.post("/api/palm", headers={"content-type": "image/jpeg"}, content=b"x")
    assert no_identity.status_code == 401

    unknown = await client.post(
        "/api/palm", params={"dev_user": 987654322},
        headers={"content-type": "image/jpeg"}, content=b"x",
    )
    assert unknown.status_code == 404

    too_large = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={
            "content-type": "image/jpeg",
            "content-length": str(palm_core.MAX_IMAGE_BYTES + 1),
        }, content=b"x",
    )
    assert too_large.status_code == 413
    assert "8 МБ" in too_large.json()["detail"]


@pytest.mark.asyncio
async def test_palm_vision_repairs_wrapped_json_after_retry(client, user, monkeypatch):
    image = FIXTURE.read_bytes()
    calls = []

    async def flaky_complete_vision(_system, user_text, _data_url, **kwargs):
        calls.append(user_text)
        if len(calls) == 1:
            return "not-json"
        return "prefix\n```json\n" + _vision_payload().rstrip("}") + ",\n}\n```"

    monkeypatch.setattr(palm_core.llm, "complete_vision", flaky_complete_vision)
    response = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"}, content=image,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(calls) == 2
    assert "ПОВТОРНАЯ ПОПЫТКА" in calls[1]
    assert result["status"] == "complete"
    assert result["image_meta"]["raw_stored"] is False


@pytest.mark.asyncio
async def test_palm_vision_provider_runtime_error_returns_safe_needs_photo(
    client, db, user, monkeypatch,
):
    image = FIXTURE.read_bytes()
    calls = 0

    async def unavailable_provider(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("upstream 403 provider body must not escape")

    monkeypatch.setattr(palm_core.llm, "complete_vision", unavailable_provider)
    response = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"}, content=image,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert calls == palm_core.PALM_JSON_ATTEMPTS
    assert result["status"] == "needs_photo"
    assert "upstream 403" not in response.text
    assert result["image_meta"]["raw_stored"] is False


@pytest.mark.asyncio
async def test_palm_vision_invalid_json_returns_safe_needs_photo_after_three_attempts(
    client, db, user, monkeypatch,
):
    image = FIXTURE.read_bytes()
    calls = 0

    async def invalid_complete_vision(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "provider raw content that must never be stored"

    monkeypatch.setattr(palm_core.llm, "complete_vision", invalid_complete_vision)
    response = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"}, content=image,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert calls == palm_core.PALM_JSON_ATTEMPTS == 3
    assert result["status"] == "needs_photo"
    assert "provider raw content" not in response.text
    assert "проверку формата" in " ".join(result["limitations"])
    assert result["image_meta"]["raw_stored"] is False

    cursor = await db.execute("SELECT analysis_json FROM palm_readings WHERE id=?", (result["id"],))
    stored = await cursor.fetchone()
    assert "provider raw content" not in stored["analysis_json"]


@pytest.mark.asyncio
async def test_palm_upload_rejects_mismatched_signature_and_animation_before_vision(client, user, monkeypatch):
    calls = 0

    async def should_not_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _vision_payload()

    monkeypatch.setattr(palm_core.llm, "complete_vision", should_not_run)
    with Image.open(FIXTURE) as source:
        png = io.BytesIO()
        source.save(png, format="PNG")
    mismatch = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"}, content=png.getvalue(),
    )
    assert mismatch.status_code == 400
    assert "не совпадает" in mismatch.json()["detail"]

    animated = io.BytesIO()
    frame = Image.new("RGB", (640, 640), "white")
    frame.save(animated, format="GIF", save_all=True, append_images=[frame.copy()], duration=100)
    rejected = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/png"}, content=animated.getvalue(),
    )
    assert rejected.status_code == 400
    assert "поддерживаются только JPEG, PNG и WebP" in rejected.json()["detail"]
    assert calls == 0


@pytest.mark.asyncio
async def test_multiple_hands_fail_early_without_vision_call(client, user, monkeypatch):
    calls = 0

    async def should_not_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _vision_payload()

    monkeypatch.setattr(palm_core.llm, "complete_vision", should_not_run)
    monkeypatch.setattr(palm_core.palm_landmarks, "analyze", lambda *_args, **_kwargs: {
        "status": "multiple_hands", "hand_count": 2, "hands": [], "issues": ["multiple_hands_in_frame"],
    })
    monkeypatch.setattr(palm_core.palm_full_scope, "analyze", lambda *_args, **_kwargs: {
        "status": "candidate_evidence", "view_type": "unclear", "line_catalog": [],
    })
    response = await client.post(
        "/api/palm", params={"dev_user": user["tg_id"]},
        headers={"content-type": "image/jpeg"}, content=FIXTURE.read_bytes(),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "needs_photo"
    assert calls == 0
    assert result["processing_metrics"]["vision_skipped"] is True
    assert any("несколько рук" in item for item in result["limitations"])
