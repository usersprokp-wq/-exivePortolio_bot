"""
Допоміжні функції для роботи з датами та форматуванням
"""
from datetime import datetime


def parse_date(date_str):
    """Парсує дату з формату ДД.ММ.РРРР або ДД.ММ.РРРРр."""
    try:
        cleaned = str(date_str).strip().replace('р.', '').replace('р', '').strip()
        return datetime.strptime(cleaned, '%d.%m.%Y')
    except:
        return datetime.max


def get_month_year(date_str):
    """Витягує місяць.рік з дати"""
    parsed = parse_date(date_str)
    if parsed == datetime.max:
        return "невідома дата"
    return f"{parsed.month:02d}.{parsed.year}"


def format_number(number, decimals=0):
    """Форматує число з розділювачем тисяч"""
    if decimals == 0:
        return f"{number:,.0f}".replace(',', ' ')
    return f"{number:,.{decimals}f}".replace(',', ' ')
