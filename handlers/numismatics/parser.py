"""
handlers/numismatics/parser.py — v3
Асинхронний парсер ua-coins.info з run_in_executor.
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
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.ua-coins.info/ua/",
}

SEARCH_URL = "https://www.ua-coins.info/ua/catalog/"
BASE_URL   = "https://www.ua-coins.info"


# ──────────────────────────────────────────────
# Утиліти
# ──────────────────────────────────────────────

def _parse_price(raw: str) -> float | None:
    """
    Конвертує рядок ціни у float.
    Підтримує формати:
      "12 500 грн", "12\xa0500\xa0грн", "1,500.00", "1500.50", "12500"
    """
    if not raw:
        return None

    # Прибираємо пробіли, \xa0, валютні позначки і стрілки
    cleaned = raw.replace("\xa0", "").replace(" ", "").replace("↑", "").replace("↓", "")
    cleaned = re.sub(r"[^\d.,]", "", cleaned)

    if not cleaned:
        return None

    # Формат "12.500,00" (крапка — роздільник тисяч, кома — дробова)
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")

    # Формат "12,500.00" (кома — роздільник тисяч, крапка — дробова)
    elif re.match(r"^\d{1,3}(,\d{3})+(\.\d+)?$", cleaned):
        cleaned = cleaned.replace(",", "")

    # Інакше просто замінюємо кому на крапку
    else:
        cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    """Прибирає зайві пробіли і приводить до нижнього регістру для порівняння."""
    return re.sub(r"\s+", " ", name.strip()).lower()


# ──────────────────────────────────────────────
# Синхронний парсер (запускається в executor)
# ──────────────────────────────────────────────

def _fetch_coin_price_sync(name: str, nominal: str | None, date_issued: str | None) -> dict:
    result = {"price": None, "price_num": None, "url": None, "error": None}

    if not name:
        result["error"] = "Назва монети відсутня"
        return result

    session = requests.Session()
    session.headers.update(HEADERS)

    # ── 1. Пошуковий запит ──────────────────────────────────────────
    params = {"search": name}
    try:
        resp = session.get(SEARCH_URL, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Parser: помилка запиту: {e}")
        result["error"] = f"Помилка запиту: {e}"
        return result

    logger.debug(f"Parser: URL={resp.url}, status={resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── 2. Знаходимо рядки таблиці ──────────────────────────────────
    # Пробуємо кілька селекторів — сайт може мати різну структуру
    rows = (
        soup.select("table.catalog-list tbody tr")
        or soup.select("table tbody tr")
        or soup.select(".catalog-table tr")
        or soup.select("tr[class*='coin']")
    )

    logger.debug(f"Parser: знайдено рядків={len(rows)}")

    if not rows:
        # Діагностика — що взагалі є на сторінці
        all_tables = soup.find_all("table")
        logger.warning(f"Parser: таблиць на сторінці={len(all_tables)}, пробуємо альт. пошук")

        # Fallback: шукаємо будь-який елемент з ціною
        result = _fallback_search(soup, resp.url)
        if not result["price"] and not result["error"]:
            result["error"] = "Результатів не знайдено. Можливо, змінилась структура сайту."
        return result

    # ── 3. Перебираємо рядки ────────────────────────────────────────
    norm_name = _normalize_name(name)

    for row in rows:
        cells = {
            (td.get("data-title") or "").strip(): td
            for td in row.find_all("td")
        }
        tds = row.find_all("td")

        # Отримуємо дату з рядка
        date_cell = (
            cells.get("Дата")
            or cells.get("Рік")
            or cells.get("Рік випуску")
            or (tds[1] if len(tds) > 1 else None)
        )
        row_date = date_cell.get_text(strip=True) if date_cell else ""

        # Перевіряємо відповідність дати
        if date_issued:
            if date_issued not in row_date and row_date != date_issued:
                continue

        # Ціна
        price_el = (
            row.select_one("a.list_price")
            or row.select_one(".price")
            or row.select_one("[class*='price']")
            or row.select_one("td.price")
        )

        price_text = None
        if price_el:
            price_text = price_el.get_text(strip=True).replace("↑", "").replace("↓", "").strip()

        # Якщо ціни нема явно — шукаємо в усіх td
        if not price_text:
            for td in tds:
                text = td.get_text(strip=True)
                if re.search(r"\d[\d\s\xa0]*грн", text, re.IGNORECASE):
                    price_text = text
                    break

        # Посилання
        link = row.select_one("a[href]")
        url  = None
        if link:
            href = link.get("href", "")
            url  = f"{BASE_URL}{href}" if href.startswith("/") else href

        if price_text:
            price_num = _parse_price(price_text)
            result["price"]     = price_text
            result["price_num"] = price_num
            result["url"]       = url
            logger.info(f"Parser: знайдено → name={name!r}, date={row_date!r}, price={price_text!r}")
            return result

    # ── 4. Fallback — перший результат ─────────────────────────────
    first_price = soup.select_one("a.list_price, .price, [class*='price']")
    if first_price:
        price_text  = first_price.get_text(strip=True).replace("↑", "").replace("↓", "").strip()
        price_num   = _parse_price(price_text)
        first_link  = soup.select_one("table tbody tr a[href], tr a[href]")
        url = None
        if first_link:
            href = first_link.get("href", "")
            url  = f"{BASE_URL}{href}" if href.startswith("/") else href

        result["price"]     = price_text
        result["price_num"] = price_num
        result["url"]       = url
        result["error"]     = "⚠️ Точний збіг по даті не знайдено — показано перший результат"
        return result

    result["error"] = "Результатів не знайдено"
    return result


def _fallback_search(soup: BeautifulSoup, page_url: str) -> dict:
    """Альтернативний пошук якщо основний не спрацював."""
    result = {"price": None, "price_num": None, "url": None, "error": None}

    # Пробуємо знайти будь-який блок з ціною
    price_patterns = [
        "a.list_price", ".coin-price", ".item-price",
        "[class*='price']", "span.price", ".catalog-price",
    ]
    for pat in price_patterns:
        el = soup.select_one(pat)
        if el:
            text = el.get_text(strip=True)
            if re.search(r"\d", text):
                result["price"]     = text
                result["price_num"] = _parse_price(text)
                result["error"]     = "⚠️ Знайдено через fallback-пошук"
                return result

    return result


# ──────────────────────────────────────────────
# Публічний асинхронний інтерфейс
# ──────────────────────────────────────────────

async def fetch_coin_price(
    name: str,
    nominal: str | None = None,
    date_issued: str | None = None,
    loop=None,
) -> dict:
    """
    Асинхронна обгортка — запускає синхронний парсер у ThreadPoolExecutor
    щоб не блокувати event loop бота.

    Повертає dict:
      {
        "price":     str | None,   # текстова ціна "12 500 грн"
        "price_num": float | None, # числова ціна 12500.0
        "url":       str | None,   # посилання на сторінку монети
        "error":     str | None,   # повідомлення про помилку
      }
    """
    if loop is None:
        loop = asyncio.get_event_loop()

    fn = partial(_fetch_coin_price_sync, name, nominal, date_issued)
    return await loop.run_in_executor(None, fn)