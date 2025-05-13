from datetime import datetime

from dateutil import parser as dateparser


def parse_date(date_input) -> datetime:
    try:
        return dateparser.parse(str(date_input), fuzzy=True)
    except (ValueError, TypeError):
        return None


def date_distance_days(date1_input, date2_input) -> int:
    date1 = parse_date(date1_input)
    date2 = parse_date(date2_input)
    if date1 is None or date2 is None:
        return -1
    return abs((date1.date() - date2.date()).days)
