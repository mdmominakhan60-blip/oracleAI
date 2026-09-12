"""BUS-622/BUS-313 F2: плейбук-каркасы pb1..pb7 сеются в content_items.

RU-версии — строки в content_items (seed), EN — DEFAULT_EN_CONTENT в коде
(meta_json body_en перекрывает). Уникальный ключ (kind, code) не позволяет
физические дубли строк RU/EN — «14 строк» тикета = 7 ключей × 2 языка.
"""

from __future__ import annotations

import re

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import content  # noqa: E402


@pytest.fixture
async def client(db, user):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Dev-Key": TEST_DEV_KEY}
    ) as http:
        yield http
    app.dependency_overrides.clear()


PB_KEYS = [
    "pb1_vip_sleeping",
    "pb2_welcome_back",
    "pb3_offer_unclaimed",
    "pb4_plan_pain",
    "pb5_no_channel",
    "pb6_onboard_stuck",
    "pb7_refund",
]
# Все плейсхолдеры, которые fillTemplate (attention-queue.js) умеет подставлять.
PB_PLACEHOLDERS = {
    "name",
    "oracle_name",
    "code_until",
    "N",
    "plan",
    "next_plan",
    "diff",
    "deep_link",
    "display",
    "limit_hits_count",
    "offer_expires_at",
}


def placeholders(body: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", body))


@pytest.mark.asyncio
async def test_seed_creates_all_seven_playbook_keys(db):
    """seed_defaults (через фикстуру db) сеет pb1..pb7 kind=copy, активные."""
    for code in PB_KEYS:
        item = await content.get_content(db, "copy", code)
        assert item is not None, f"{code} не посеян seed_defaults"
        assert item["is_active"] == 1
        assert item["title"], f"{code}: пустой title"
        assert item["body"], f"{code}: пустой body"


@pytest.mark.asyncio
async def test_ru_texts_match_attention_queue_fallbacks(db):
    """RU-тексты ключей совпадают с RU-фоллбеками attention-queue.js 1:1 —
    сид ничего не меняет в поведении, только даёт переопределяемость."""
    expected_openings = {
        "pb1_vip_sleeping": "давно не виделись",
        "pb2_welcome_back": "снова здесь",
        "pb3_offer_unclaimed": "нераспечатанным",
        "pb4_plan_pain": "упёрлась в лимит",
        "pb5_no_channel": "forbidden",
        "pb6_onboard_stuck": "остановилось на середине",
        "pb7_refund": "возврат по твоему платежу",
    }
    for code, opening in expected_openings.items():
        body = await content.get_text(db, "copy", code, lang="ru")
        assert opening in body, f"{code}: RU-текст расходится с PB-фоллбеком"


@pytest.mark.asyncio
async def test_ru_en_placeholder_symmetry(db):
    """RU/EN симметрия: каждый ключ имеет EN-версию в DEFAULT_EN_CONTENT,
    и наборы плейсхолдеров RU и EN идентичны — иначе fillTemplate оставит
    {плейсхолдер} в одном из языков (критерий приёмки QA)."""
    for code in PB_KEYS:
        item = await content.get_content(db, "copy", code)
        ru_ph = placeholders(item["body"])
        en = content.DEFAULT_EN_CONTENT.get(("copy", code))
        assert en, f"{code}: нет EN-версии в DEFAULT_EN_CONTENT"
        en_ph = placeholders(en["body"])
        assert en_ph == ru_ph, f"{code}: плейсхолдеры расходятся RU={ru_ph} EN={en_ph}"
        assert (
            ru_ph <= PB_PLACEHOLDERS
        ), f"{code}: неизвестный fillTemplate плейсхолдер {ru_ph - PB_PLACEHOLDERS}"


@pytest.mark.asyncio
async def test_get_text_english_playbooks_from_defaults(db):
    """EN-оператор получает EN-каркас (не RU): get_text(lang=en) отдаёт
    тело из DEFAULT_EN_CONTENT; переопределение meta body_en приоритетнее."""
    text = await content.get_text(db, "copy", "pb1_vip_sleeping", lang="en")
    assert "been a while" in text
    assert "не виделись" not in text

    await content.upsert_content(
        db,
        "copy",
        "pb1_vip_sleeping",
        title="Плейбук PB-1: спящий VIP",
        body="RU-тело",
        meta={"body_en": "Custom EN override"},
    )
    assert (
        await content.get_text(db, "copy", "pb1_vip_sleeping", lang="en")
        == "Custom EN override"
    )
    assert (
        await content.get_text(db, "copy", "pb1_vip_sleeping", lang="ru") == "RU-тело"
    )


@pytest.mark.asyncio
async def test_admin_override_visible_in_content_api(client, db):
    """Переопределение через content_items (админка /api/admin/content)
    видно читателю карточек — критерий «переопределяемые»."""
    res = await client.post(
        "/api/admin/content",
        params={"dev_user": 1},
        json={"kind": "copy", "code": "pb7_refund", "body": "Переопределённый плейбук"},
    )
    assert res.status_code == 200
    assert (
        await content.get_text(db, "copy", "pb7_refund", lang="ru")
        == "Переопределённый плейбук"
    )
