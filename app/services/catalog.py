"""Каталог раскладов: встроенные + добавленные из админки.

Структура расклада (позиции) — часть логики, поэтому базовый набор живёт в
`core/tarot.py` и работает без БД. Админка может добавить свой расклад или
переименовать существующий через `content_items(kind='spread')`; такие записи
перекрывают встроенные. Это позволяет заводить сезонные расклады («Расклад на
Самайн») без деплоя, не теряя работоспособности при пустой базе.
"""
from __future__ import annotations

import logging

from ..core import tarot
from ..repo import billing, content

log = logging.getLogger("oracle.catalog")


def _from_content(item: dict) -> dict | None:
    meta = content.content_meta(item)
    positions = meta.get("positions")
    if not isinstance(positions, list) or not positions:
        log.warning("расклад %s без позиций — пропускаю", item.get("code"))
        return None
    return {
        "code": item["code"],
        "title": item.get("title") or item["code"],
        "positions": [str(p) for p in positions][:16],
        "tier": meta.get("tier", "premium"),
        "emoji": meta.get("emoji", "🎴"),
        "hint": item.get("body") or meta.get("hint", ""),
        "custom": True,
    }


async def spreads(db) -> dict[str, dict]:
    """Все доступные расклады: код → описание."""
    out = {code: {**item, "code": code, "custom": False}
           for code, item in tarot.SPREADS.items()}
    try:
        for item in await content.list_content(db, "spread", active_only=True):
            parsed = _from_content(item)
            if parsed:
                out[parsed["code"]] = parsed
    except Exception as e:  # noqa: BLE001
        log.warning("расклады из БД недоступны, беру встроенные: %s", e)
    return out


async def get_spread(db, code: str) -> dict:
    return (await spreads(db)).get(code) or tarot.spread(code)


async def spread_list(db, user=None) -> list[dict]:
    """Витрина раскладов с ценой и признаком «уже куплен»."""
    all_spreads = await spreads(db)
    products = {p["grant_code"]: p for p in await billing.list_products(db, "spread")}
    out = []
    for code, item in all_spreads.items():
        product = products.get(code)
        owned = 0
        if user is not None and item["tier"] == "premium":
            owned = await billing.available_entitlements(
                db, user["tg_id"], "spread", code)
        out.append({
            "code": code,
            "title": item["title"],
            "positions": item["positions"],
            "cards": len(item["positions"]),
            "tier": item["tier"],
            "emoji": item.get("emoji", "🎴"),
            "hint": item.get("hint", ""),
            "sku": product["sku"] if product else None,
            "price_stars": product["price_stars"] if product else 0,
            "price_crystals": product["price_crystals"] if product else 0,
            "owned": owned,
        })
    out.sort(key=lambda s: (s["tier"] != "included", s["cards"]))
    return out


async def is_available(db, user, code: str) -> bool:
    """Доступен ли расклад без покупки: входит в тариф или уже куплен."""
    item = await get_spread(db, code)
    if item["tier"] == "included":
        return True
    return bool(await billing.available_entitlements(
        db, user["tg_id"], "spread", code))
