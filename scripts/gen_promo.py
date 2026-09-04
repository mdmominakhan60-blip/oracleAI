"""Генератор промокодов («золотые билеты» для партий Etsy и рекламы).

    python -m scripts.gen_promo 20                          # 20 кодов по 30 дней VIP
    python -m scripts.gen_promo 50 --days 7 --batch etsy-1   # партия под листинг
    python -m scripts.gen_promo 10 --kind crystals --crystals 100
    python -m scripts.gen_promo 5 --kind product --sku spread_celtic
    python -m scripts.gen_promo 1 --max-uses 500 --batch tiktok  # один код на канал

Партия (`--batch`) — это канал привлечения: по ней в админке видно, какой
листинг приводит платящих, а какой только скачивающих.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.session import connect  # noqa: E402
from app.repo import growth  # noqa: E402


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Создать партию промокодов")
    ap.add_argument("count", type=int, help="сколько кодов создать")
    ap.add_argument("--kind", default="plan_days",
                    choices=("plan_days", "crystals", "product"),
                    help="что выдаёт код")
    ap.add_argument("--days", type=int, default=30, help="дней доступа")
    ap.add_argument("--plan", default="vip", help="код тарифа для plan_days")
    ap.add_argument("--crystals", type=int, default=0, help="сколько ✦ выдать")
    ap.add_argument("--sku", default=None, help="SKU товара для kind=product")
    ap.add_argument("--batch", default="manual", help="партия/канал")
    ap.add_argument("--max-uses", type=int, default=1,
                    help="сколько раз можно активировать каждый код")
    ap.add_argument("--valid-days", type=int, default=None,
                    help="через сколько дней код перестанет работать")
    ap.add_argument("--prefix", default="ORA-", help="префикс кода")
    return ap.parse_args()


async def main() -> None:
    args = parse_args()
    if args.kind == "product" and not args.sku:
        raise SystemExit("для --kind product нужен --sku")
    if args.kind == "crystals" and args.crystals <= 0:
        raise SystemExit("для --kind crystals нужен --crystals больше нуля")

    db = await connect()
    try:
        codes = await growth.create_codes(
            db, args.count, kind=args.kind, days=args.days, plan_code=args.plan,
            crystals=args.crystals, sku=args.sku, batch=args.batch,
            max_uses=args.max_uses, valid_days=args.valid_days, prefix=args.prefix)
    finally:
        await db.close()

    what = {"plan_days": f"{args.days} дн. тарифа {args.plan}",
            "crystals": f"✦{args.crystals}",
            "product": f"товар {args.sku}"}[args.kind]
    print(f"Создано кодов: {len(codes)} · выдаёт: {what} · партия: {args.batch}")
    if args.max_uses > 1:
        print(f"Каждый код активируется до {args.max_uses} раз\n")
    else:
        print()
    for code in codes:
        print(code)


if __name__ == "__main__":
    asyncio.run(main())
