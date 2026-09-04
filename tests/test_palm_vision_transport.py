from __future__ import annotations

import pytest

from app.core import palm


@pytest.mark.asyncio
async def test_custom_only_provider_drops_native_json_schema(monkeypatch):
    captured = {}

    async def fake_original(*args, **kwargs):
        captured.update(kwargs)
        return "{}"

    monkeypatch.setattr(palm.settings, "provider_chain", ["custom"])
    monkeypatch.setattr(palm, "_ORIGINAL_COMPLETE_VISION", fake_original)

    await palm._complete_vision_compat(
        "system", "user", "data:image/jpeg;base64,AA==", response_format={"type": "json_schema"}
    )
    assert captured["response_format"] is None


@pytest.mark.asyncio
async def test_native_schema_is_preserved_for_mixed_chain(monkeypatch):
    captured = {}

    async def fake_original(*args, **kwargs):
        captured.update(kwargs)
        return "{}"

    monkeypatch.setattr(palm.settings, "provider_chain", ["openai", "custom"])
    monkeypatch.setattr(palm, "_ORIGINAL_COMPLETE_VISION", fake_original)
    schema = {"type": "json_schema"}

    await palm._complete_vision_compat(
        "system", "user", "data:image/jpeg;base64,AA==", response_format=schema
    )
    assert captured["response_format"] == schema
