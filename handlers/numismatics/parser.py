"""
handlers/numismatics/parser.py
Парсер ціни монети з ua-coins.info.
Логіка повністю відповідає оригінальному selenium-скрипту,
але використовує requests + BeautifulSoup замість браузера.
"""
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uk,en;q=0.9",
}
BASE_URL = "https://www.ua-coins.info/ua"


def fetch_coin_price(name: str, nominal: str | None, date_issued: str | None) -> dict:
    result = {"price": None, "url": None, "error": None}

    if not name:
        result["error"] = "Назва монети відсутня"
        return result

    try:
        session = requests.Session()
        session.get(BASE_URL, headers=HEADERS, timeout=15)
        resp = session.get(
            BASE_URL,
            params={"search": name},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Parser request error: {e}")
        result["error"] = f"Помилка запиту: {e}"
        return result

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tbody tr")

    # ДІАГНОСТИКА — видали після налагодження
    logger.warning(f"=== PARSER DEBUG ===")
    logger.warning(f"URL: {resp.url}")
    logger.warning(f"Status: {resp.status_code}")
    logger.warning(f"Rows знайдено: {len(rows)}")
    logger.warning(f"HTML (перші 3000):\n{resp.text[:3000]}")
    logger.warning(f"===================")

    if not rows:
        result["error"] = "Результатів не знайдено"
        return result

    logger.info(f"Parser: знайдено {len(rows)} рядків для '{name}'")

    for row in rows:
        for cell in row.find_all("td"):
            if cell.get("data-title") == "Дата":
                date_value = cell.get_text(strip=True)
                logger.info(f"Parser: дата в рядку = {date_value!r}, шукаємо {date_issued!r}")

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
                        logger.info(f"Parser OK: {result['price']!r}")
                        return result

    # Fallback — перший результат
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