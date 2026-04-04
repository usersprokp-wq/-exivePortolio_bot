"""
handlers/numismatics/parser.py — v4
Асинхронний парсер ua-coins.info на основі реальної HTML-структури.
"""
import logging
import re
import asyncio
from functools import partial

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk,en;q=0.9",
    "Referer": "https://www.ua-coins.info/ua/",
}

SEARCH_URL = "https://www.ua-coins.info/ua/search"
BASE_URL   = "https://www.ua-coins.info"


# ──────────────────────────────────────────────
# Утиліти
# ──────────────────────────────────────────────

def _parse_price(raw: str) -> float | None:
    """
    Конвертує рядок ціни у float.
    Після BeautifulSoup: "88 500", "13 227", "9 416"
    (пробіли можуть бути звичайні, \xa0, \u2009 — &thinsp;)
    """
    if not raw:
        return None
    cleaned = re.sub(r"[^\d]", "", raw)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_date(date_td) -> str:
    """
    Витягує дату з <td data-title="Дата" class="date">.
    Береться <span class="desktop"> → формат "29.12.2025".
    """
    span = date_td.select_one("span.desktop")
    if span:
        return span.get_text(strip=True)
    return date_td.get_text(strip=True)


def _date_matches(row_date: str, date_issued: str) -> bool:
    """
    Перевіряє чи дата рядка відповідає шуканій.
    date_issued може бути: "12.10.2017", "2017", "2024" тощо.
    """
    return date_issued in row_date or row_date == date_issued


# ──────────────────────────────────────────────
# Синхронний парсер (виконується в ThreadPoolExecutor)
# ──────────────────────────────────────────────

def _fetch_coin_price_sync(name: str, nominal: str | None, date_issued: str | None) -> dict:
    result = {"price": None, "price_num": None, "url": None, "error": None}

    if not name:
        result["error"] = "Назва монети відсутня"
        return result

    # ── 1. HTTP запит ────────────────────────────────────────────────
    try:
        resp = requests.get(
            SEARCH_URL,
            params={"search": name},
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Parser: помилка запиту для {name!r}: {e}")
        result["error"] = f"Помилка запиту: {e}"
        return result

    logger.debug(f"Parser: URL={resp.url}, status={resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── 2. Знаходимо таблицю ────────────────────────────────────────
    # <table class="... coin-list">
    table = soup.select_one("table.coin-list")
    if not table:
        logger.warning(f"Parser: таблиця coin-list не знайдена для {name!r}")
        result["error"] = "Результатів не знайдено"
        return result

    # ── 3. Збираємо тільки рядки з монетами ─────────────────────────
    # Пропускаємо: заголовок thead, рядки-розділювачі (colspan=5 з роком),
    # підсумковий рядок. Лишаємо тільки <tr> що мають <td data-title="Дата">
    coin_rows = [
        tr for tr in table.find_all("tr")
        if tr.find("td", attrs={"data-title": "Дата"})
    ]

    logger.debug(f"Parser: знайдено рядків з монетами={len(coin_rows)}")

    if not coin_rows:
        result["error"] = "Результатів не знайдено"
        return result

    # ── 4. Знаходимо потрібний рядок ────────────────────────────────
    matched_row   = None
    fallback_date = None

    if date_issued:
        for tr in coin_rows:
            date_td  = tr.find("td", attrs={"data-title": "Дата"})
            row_date = _extract_date(date_td)
            logger.debug(f"Parser: порівнюємо row_date={row_date!r} з {date_issued!r}")
            if _date_matches(row_date, date_issued):
                matched_row = tr
                break

        if not matched_row:
            # Fallback — перший (найновіший) рядок
            matched_row   = coin_rows[0]
            date_td       = matched_row.find("td", attrs={"data-title": "Дата"})
            fallback_date = _extract_date(date_td)
            logger.warning(
                f"Parser: дату {date_issued!r} не знайдено для {name!r}, "
                f"беремо перший рядок ({fallback_date})"
            )
            result["error"] = (
                f"⚠️ Дату {date_issued} не знайдено — "
                f"показано найновіший результат ({fallback_date})"
            )
    else:
        # Дата не задана — беремо перший (найновіший) рядок
        matched_row = coin_rows[0]

    # ── 5. Витягуємо ціну з a.list_price ────────────────────────────
    price_a = matched_row.select_one("a.list_price")
    if price_a:
        # Видаляємо <span> зі стрілками (↑↓) перед get_text
        for span in price_a.find_all("span"):
            span.decompose()
        price_text = price_a.get_text(strip=True)
        price_num  = _parse_price(price_text)

        result["price"]     = price_text
        result["price_num"] = price_num
    else:
        logger.warning(f"Parser: a.list_price не знайдено в рядку для {name!r}")
        if not result["error"]:
            result["error"] = "Ціну не знайдено"

    # ── 6. Посилання на сторінку монети ─────────────────────────────
    # Перший <a href> в рядку (є і в Назві, і в Ціні — вони однакові)
    link = matched_row.select_one("a[href]")
    if link:
        href = link.get("href", "").strip()
        result["url"] = f"{BASE_URL}{href}" if href.startswith("/") else href

    logger.info(
        f"Parser OK: {name!r} | date_issued={date_issued!r} | "
        f"price={result['price']!r} ({result['price_num']}) | url={result['url']!r}"
    )
    return result


# ──────────────────────────────────────────────
# Публічний async інтерфейс
# ──────────────────────────────────────────────

async def fetch_coin_price(
    name: str,
    nominal: str | None = None,
    date_issued: str | None = None,
) -> dict:
    """
    Асинхронна обгортка — не блокує event loop бота.

    Повертає dict:
      {
        "price":     str | None,    # текстовий вигляд "13 227"
        "price_num": float | None,  # число 13227.0
        "url":       str | None,    # https://www.ua-coins.info/ua/list/...
        "error":     str | None,    # None або текст помилки/попередження
      }
    """
    loop = asyncio.get_event_loop()
    fn   = partial(_fetch_coin_price_sync, name, nominal, date_issued)
    return await loop.run_in_executor(None, fn)