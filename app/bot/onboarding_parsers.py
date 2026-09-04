"""Deterministic, forgiving onboarding input parsers.

The parser accepts common RU/EN forms but never guesses ambiguous day/month or
12-hour values. Domain engines remain authoritative after normalization.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {
    "ru": {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
           "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12},
    "en": {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
           "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12},
}
UNKNOWN_TIME = {"не знаю", "неизвестно", "нет", "unknown", "dont know", "i don't know", "i dont know"}
APPROX_TIME = {"примерно", "примерно 14:00", "около двух дня", "около двух", "approximately", "around 2 pm"}


@dataclass(frozen=True)
class ParsedDate:
    value: date
    normalized: str
    label: str


@dataclass(frozen=True)
class ParsedTime:
    value: str
    known: bool
    precision: str  # exact | approximate | unknown
    label: str


def _clean(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("ё", "е").split())


def _year(raw: str) -> int:
    value = int(raw)
    return value + 2000 if len(raw) == 2 else value


def parse_birth_date(raw: str, *, lang: str = "ru", today: date | None = None) -> ParsedDate:
    text = _clean(raw).replace(",", " ")
    if re.fullmatch(r"\d{1,2}[.\-/]\d{1,2}", text):
        raise ValueError("ambiguous_date")
    numeric = re.fullmatch(r"(\d{1,4})[.\-/ ](\d{1,2})[.\-/ ](\d{1,4})", text)
    if numeric:
        first, second, third = numeric.groups()
        if len(first) == 4:
            year, month, day = int(first), int(second), int(third)
        elif len(third) in {2, 4}:
            day, month, year = int(first), int(second), _year(third)
        else:
            raise ValueError("ambiguous_date")
    else:
        named = re.fullmatch(r"(\d{1,2})\s+([a-zа-я]+)\s+(\d{2,4})", text)
        if not named:
            named = re.fullmatch(r"([a-z]+)\s+(\d{1,2})\s+(\d{2,4})", text)
            if named:
                month_name, day, year_raw = named.groups()
                month = MONTHS["en"].get(month_name)
            else:
                raise ValueError("invalid_date")
        else:
            day, month_name, year_raw = named.groups()
            month = MONTHS.get(lang, MONTHS["ru"]).get(month_name) or MONTHS["en"].get(month_name)
        if not month:
            raise ValueError("unknown_month")
        day, year = int(day), _year(year_raw)
    try:
        value = date(year, month, day)
    except ValueError as exc:
        raise ValueError("invalid_calendar_date") from exc
    current = today or date.today()
    if not 1900 <= value.year <= current.year:
        raise ValueError("invalid_year")
    return ParsedDate(value, value.isoformat(), value.strftime("%d.%m.%Y"))


def parse_birth_time(raw: str, *, lang: str = "ru") -> ParsedTime:
    text = _clean(raw)
    if text in UNKNOWN_TIME:
        return ParsedTime("12:00", False, "unknown", "неизвестное время")
    if text in APPROX_TIME:
        return ParsedTime("14:00", False, "approximate", "примерно 14:00")
    match = re.fullmatch(r"(\d{1,2})\s*[:.]?\s*(\d{2})", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
    else:
        match = re.fullmatch(r"(\d{1,2})(?::|\.)?(\d{2})\s*(am|pm)", text)
        if not match:
            raise ValueError("invalid_time")
        hour, minute, suffix = int(match.group(1)), int(match.group(2)), match.group(3)
        if hour < 1 or hour > 12:
            raise ValueError("invalid_time")
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    if hour > 23 or minute > 59:
        raise ValueError("invalid_time")
    return ParsedTime(f"{hour:02d}:{minute:02d}", True, "exact", f"{hour:02d}:{minute:02d}")


def date_error_copy(code: str, lang: str) -> str:
    copies = {
        "invalid_calendar_date": ("Я поняла дату, но такого дня не бывает. Проверь число и месяц.", "I understood the date, but that day does not exist. Check the day and month."),
        "ambiguous_date": ("В этой записи не хватает ясности. Напиши дату с годом, например 21.06.1999.", "That date is ambiguous. Include the year, for example 21.06.1999."),
        "unknown_month": ("Я не узнала название месяца. Напиши его полностью или используй 21.06.1999.", "I did not recognize the month. Spell it out or use 21.06.1999."),
        "invalid_year": ("Проверь год рождения: он должен быть между 1900 и текущим годом.", "Check the birth year: it must be between 1900 and the current year."),
    }
    return copies.get(code, copies["ambiguous_date"])[1 if lang == "en" else 0]


def time_error_copy(code: str, lang: str) -> str:
    return ("Я не смогла распознать время точно. Напиши 14:30, 1430 или выбери вариант ниже."
            if lang != "en" else "I could not reliably read the time. Send 14:30, 1430, or choose an option below.")
