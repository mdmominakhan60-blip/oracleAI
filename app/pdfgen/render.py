"""HTML → PDF.

WeasyPrint выбран по ТЗ: он читает тот же HTML/CSS, что и Mini App, поэтому у
печатной и экранной версии один визуальный язык, а не две независимые вёрстки.

Библиотека тянет системные зависимости (cairo, pango), и на голой машине её
может не быть. Тогда сохраняем HTML рядом и честно об этом сообщаем: заказ
всё равно выполним — файл открывается в браузере и печатается в PDF оттуда.
Молча подсовывать HTML с расширением .pdf нельзя: покупательница получит
битый файл.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("oracle.pdfgen.render")


class PdfUnavailable(RuntimeError):
    """WeasyPrint не установлен — PDF собрать нечем."""


def available() -> bool:
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 — на битых системных библиотеках падает ImportError-ом наружу
        return False


def to_pdf_bytes(html: str, *, base_url: str | None = None) -> bytes:
    """HTML → PDF в память. Поднимает `PdfUnavailable`, если рендерить нечем."""
    if not available():
        raise PdfUnavailable(
            "WeasyPrint не установлен. Поставь: pip install weasyprint "
            "(нужны системные libcairo2 и libpango-1.0-0)")
    from weasyprint import HTML
    return HTML(string=html, base_url=base_url).write_pdf()


def render_pdf(html: str, out_path: str | Path) -> Path:
    """Пишет PDF на диск. Если WeasyPrint нет — сохраняет HTML и говорит об этом.

    Возвращает фактический путь: он может оказаться .html, и вызывающий код
    обязан это увидеть, а не считать, что PDF готов.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = to_pdf_bytes(html)
    except PdfUnavailable as e:
        fallback = out_path.with_suffix(".html")
        fallback.write_text(html, encoding="utf-8")
        log.warning("PDF не собран (%s). Сохранён HTML: %s", e, fallback)
        return fallback
    out_path.write_bytes(data)
    return out_path
