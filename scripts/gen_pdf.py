"""Генератор персональных PDF-разборов — товар для маркетплейсов.

    # один заказ
    python -m scripts.gen_pdf --name Анна --date 21.06.1999 --time 14:30 \
                              --city Казань

    # партия из CSV выгрузки заказов (name,birth_date,birth_time,birth_city,email)
    python -m scripts.gen_pdf --csv orders.csv --batch etsy-1

Каждому разбору выдаётся свой промокод («золотой билет») на 30 дней VIP и он
печатается внутри файла: это единственный мост между покупкой на площадке и
ботом. Партия (`--batch`) = листинг, по ней в админке видно, какой листинг
приводит платящих.

Без ключей LLM скрипт тоже работает: разделы собираются из реальных расчётов
без литературной части. Без WeasyPrint — сохраняет HTML и честно сообщает
об этом (файл открывается в браузере и печатается в PDF оттуда).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.data.session import connect  # noqa: E402
from app.pdfgen import builder, render  # noqa: E402
from app.repo import content, growth  # noqa: E402

DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")


def parse_date(value: str) -> str:
    value = (value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise SystemExit(f"не разобрала дату: «{value}» (нужно ДД.ММ.ГГГГ)")


def parse_time(value: str | None) -> str | None:
    """None означает «время неизвестно» — карта тогда строится без домов."""
    value = (value or "").strip()
    if not value or value.lower() in ("-", "не знаю", "unknown", "none"):
        return None
    match = re.match(r"^(\d{1,2})[:.](\d{2})$", value)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return f"{hour:02d}:{minute}"


def slugify(name: str) -> str:
    """Имя файла: латиница, цифры и дефисы. Кириллица в путях ломает выгрузки."""
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    out = "".join(table.get(ch, ch) for ch in (name or "").lower())
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    return out or "order"


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"в {path} нет строк")
    return rows


def order_from(row: dict) -> builder.Order:
    def pick(*names: str) -> str:
        for name in names:
            value = (row.get(name) or "").strip()
            if value:
                return value
        return ""

    name = pick("name", "имя", "first_name", "buyer")
    if not name:
        raise SystemExit(f"в строке нет имени: {row}")
    return builder.Order(
        name=name[:60],
        birth_date=parse_date(pick("birth_date", "date", "дата", "дата рождения")),
        birth_time=parse_time(pick("birth_time", "time", "время")),
        birth_city=pick("birth_city", "city", "город") or None,
        email=pick("email", "почта"),
        listing=pick("listing", "листинг", "sku"),
        lang=pick("lang", "language", "язык") or "ru",
    )


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Собрать персональный PDF-разбор")
    ap.add_argument("--csv", type=Path, help="файл заказов (CSV с заголовком)")
    ap.add_argument("--name", help="имя клиентки (для одного заказа)")
    ap.add_argument("--date", help="дата рождения ДД.ММ.ГГГГ")
    ap.add_argument("--time", help="время рождения ЧЧ:ММ (можно не указывать)")
    ap.add_argument("--city", help="город рождения")
    ap.add_argument("--lang", choices=("ru", "en"), default="ru",
                    help="язык отчёта: ru или en")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "pdf",
                    help="куда складывать файлы")
    ap.add_argument("--batch", default="pdf", help="партия промокодов = листинг")
    ap.add_argument("--promo-days", type=int, default=30,
                    help="сколько дней VIP даёт золотой билет")
    ap.add_argument("--no-promo", action="store_true",
                    help="собрать разбор без золотого билета")
    ap.add_argument("--html", action="store_true",
                    help="сохранить только HTML, без сборки PDF")
    return ap.parse_args()


async def build_one(db, order: builder.Order, args, bot_username: str) -> Path:
    if not args.no_promo:
        codes = await growth.create_codes(
            db, 1, kind="plan_days", days=args.promo_days, plan_code="vip",
            batch=args.batch, max_uses=1, prefix="ORA-")
        order.promo_code = codes[0] if codes else None

    html = await builder.generate(db, order, bot_username=bot_username)
    stem = f"{slugify(order.name)}-{order.birth_date}"
    if args.html:
        path = Path(args.out) / f"{stem}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return path
    return render.render_pdf(html, Path(args.out) / f"{stem}.pdf")


async def main() -> None:
    args = parse_args()
    if not args.csv and not (args.name and args.date):
        raise SystemExit("нужен --csv или пара --name и --date")

    orders: list[builder.Order] = []
    if args.csv:
        orders = [order_from(row) for row in read_csv(args.csv)]
    else:
        orders = [builder.Order(
            name=args.name.strip()[:60],
            birth_date=parse_date(args.date),
            birth_time=parse_time(args.time),
            birth_city=(args.city or "").strip() or None,
            lang=args.lang,
        )]

    if not args.html and not render.available():
        print("⚠️  WeasyPrint не установлен — сохраню HTML вместо PDF.")
        print("   pip install weasyprint  (нужны libcairo2 и libpango-1.0-0)\n")
    if not settings.llm_enabled:
        print("⚠️  Ключей LLM нет — разделы соберутся из расчётов без "
              "литературного текста.\n")

    db = await connect()
    try:
        bot_username = await content.get_setting(db, "brand.bot_username", "") or ""
        for i, order in enumerate(orders, 1):
            print(f"[{i}/{len(orders)}] {order.name} · {order.birth_date} … ",
                  end="", flush=True)
            try:
                path = await build_one(db, order, args, bot_username)
            except Exception as e:  # noqa: BLE001
                # один плохой заказ не должен останавливать всю партию
                print(f"ошибка: {e}")
                continue
            code = order.promo_code or "—"
            print(f"{path.name}  · билет {code}")
    finally:
        await db.close()

    print(f"\nГотово. Файлы в {Path(args.out).resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
