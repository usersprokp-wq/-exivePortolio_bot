"""
handlers/numismatics/parser.py — v2 з POST запитом
"""
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uk,en;q=0.9",
    "Referer": "https://www.ua-coins.info/ua",
}
BASE_URL = "https://www.ua-coins.info/ua"


def fetch_coin_price(name: str, nominal: str | None, date_issued: str | None) -> dict:
    result = {"price": None, "url": None, "error": None}

    if not name:
        result["error"] = "Назва монети відсутня"
        return result

    try:
        session = requests.Session()
        # Отримуємо головну сторінку — cookies + можливий CSRF токен
        main_resp = session.get(BASE_URL, headers=HEADERS, timeout=15)
        
        # Шукаємо форму пошуку — дізнаємось метод і action
        soup_main = BeautifulSoup(main_resp.text, "html.parser")
        form = soup_main.find("form")
        
        if form:
            method = form.get("method", "get").lower()
            action = form.get("action", BASE_URL)
            if not action.startswith("http"):
                action = f"https://www.ua-coins.info{action}"
            logger.warning(f"Form: method={method}, action={action}")
        else:
            method = "get"
            action = BASE_URL
            logger.warning("Form не знайдено — використовуємо GET")

        # Виконуємо пошук потрібним методом
        search_data = {"search": name}
        if method == "post":
            resp = session.post(action, data=search_data, headers=HEADERS, timeout=15)
        else:
            resp = session.get(action, params=search_data, headers=HEADERS, timeout=15)

        resp.raise_for_status()

    except requests.RequestException as e:
        logger.error(f"Parser request error: {e}")
        result["error"] = f"Помилка запиту: {e}"
        return result

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tbody tr")

    logger.warning(f"Parser: rows={len(rows)}, url={resp.url}")
    # Логуємо структуру першого рядка якщо є
    if rows:
        first = rows[0]
        for td in first.find_all("td"):
            logger.warning(f"  TD data-title={td.get('data-title')!r} text={td.get_text(strip=True)[:50]!r}")
        for a in first.find_all("a"):
            logger.warning(f"  A class={a.get('class')} text={a.get_text(strip=True)[:30]!r}")
    else:
        # Шукаємо будь-які таблиці
        all_tables = soup.find_all("table")
        logger.warning(f"Всього таблиць на сторінці: {len(all_tables)}")
        # Шукаємо input search щоб зрозуміти чи є форма
        inputs = soup.find_all("input")
        for inp in inputs:
            logger.warning(f"  INPUT name={inp.get('name')!r} type={inp.get('type')!r} value={inp.get('value','')[:30]!r}")

    if not rows:
        result["error"] = "Результатів не знайдено"
        return result

    for row in rows:
        for cell in row.find_all("td"):
            if cell.get("data-title") == "Дата":
                date_value = cell.get_text(strip=True)
                logger.info(f"Parser: дата={date_value!r}, шукаємо={date_issued!r}")

                date_match = True
                if date_issued:
                    date_match = (date_issued in date_value or date_value == date_issued)

                if date_match:
                    price_elements = row.select("a.list_price")
                    if price_elements:
                        price_text = price_elements[0].get_text(strip=True)
                        result["price"] = price_text.replace("↑", "").replace("↓", "").strip()

                    link = row.select_one("a[href]")
                    if link:
                        href = link.get("href", "")
                        result["url"] = f"https://www.ua-coins.info{href}" if href.startswith("/") else href

                    if result["price"]:
                        return result

    # Fallback
    first_price = soup.select_one("a.list_price")
    if first_price:
        result["price"] = first_price.get_text(strip=True).replace("↑", "").replace("↓", "").strip()
        result["error"] = "⚠️ Точний збіг по даті не знайдено, показано перший результат"
        first_link = soup.select_one("table tbody tr a[href]")
        if first_link:
            href = first_link.get("href", "")
            result["url"] = f"https://www.ua-coins.info{href}" if href.startswith("/") else href
        return result

    result["error"] = "Результатів не знайдено"
    return result