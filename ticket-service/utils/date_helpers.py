"""Date formatting helpers for Jinja2 templates. Registered as filters in site-regenerator."""
from datetime import datetime

_MONTHS_ABBR = {
    1: 'ЯНВ', 2: 'ФЕВ', 3: 'МАР', 4: 'АПР',
    5: 'МАЙ', 6: 'ИЮН', 7: 'ИЮЛ', 8: 'АВГ',
    9: 'СЕН', 10: 'ОКТ', 11: 'НОЯ', 12: 'ДЕК',
}

_MONTHS_FULL = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
    5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
    9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря',
}

_DAYS_RU = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']


def _parse(date_str: str) -> datetime:
    """Parses ISO date string stored as Israel local time (naive)."""
    return datetime.fromisoformat(date_str.replace('Z', '').split('+')[0])


def date_num(date_str: str) -> str:
    """Returns zero-padded day number: '07'."""
    return f"{_parse(date_str).day:02d}"


def month_abbr(date_str: str) -> str:
    """Returns Russian month abbreviation: 'ДЕК'."""
    return _MONTHS_ABBR[_parse(date_str).month]


def month_full(date_str: str) -> str:
    """Returns Russian month name in genitive: 'декабря'."""
    return _MONTHS_FULL[_parse(date_str).month]


def day_of_week(date_str: str) -> str:
    """Returns Russian day-of-week abbreviation: 'вс'."""
    return _DAYS_RU[_parse(date_str).weekday()]


def format_date_full(date_str: str) -> str:
    """Returns formatted date: '7 декабря 2025'."""
    dt = _parse(date_str)
    return f"{dt.day} {_MONTHS_FULL[dt.month]} {dt.year}"


def format_time(date_str: str) -> str:
    """Returns HH:MM time string: '19:00'."""
    return _parse(date_str).strftime('%H:%M')


def year(date_str: str) -> str:
    return str(_parse(date_str).year)


def ru_plural(n: int, one: str, few: str, many: str) -> str:
    """Russian pluralization: ru_plural(3, 'билет', 'билета', 'билетов') → 'билета'."""
    if 11 <= (n % 100) <= 19:
        return many
    r = n % 10
    if r == 1:
        return one
    if 2 <= r <= 4:
        return few
    return many
