"""
handlers/numismatics/parser.py
Парсер ціни монети з ua-coins.info за назвою, номіналом і датою введення в обіг.
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


def _normalize(text: str) -> str:
    """Нормалізуємо рядок для порівняння."""
    return text.strip().lower().replace("\xa0", " ")


def fetch_coin_price(name: str, nominal: str | None, date_issued: str | None) -> dict:
    """
    Шукає монету на ua-coins.info і повертає словник:
      {
        "price": "12 500 грн",   # або None якщо не знайдено
        "url":   "https://...",  # або None
        "error": None            # або текст помилки
      }
    """
    result = {"price": None, "url": None, "error": None}

    if not name:
        result["error"] = "Назва монети відсутня"
        return result

    try:
        session = requests.Session()

        # Спочатку заходимо на головну щоб отримати cookies
        session.get(BASE_URL, headers=HEADERS, timeout=15)

        # Пошук по назві
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

    if not rows:
        result["error"] = "Результатів не знайдено"
        return result

    # Нормалізуємо пошукові критерії
    norm_name    = _normalize(name)
    norm_nominal = _normalize(nominal or "")
    norm_date    = _normalize(date_issued or "")

    for row in rows:
        cells = row.find_all("td")
        cell_map: dict[str, str] = {}

        for cell in cells:
            dt  = cell.get("data-title", "").strip()
            val = cell.get_text(strip=True)
            if dt:
                cell_map[dt] = val

        # Перевіряємо збіг по даті
        date_match = False
        if norm_date:
            row_date = _normalize(cell_map.get("Дата", ""))
            if norm_date in row_date or row_date == norm_date:
                date_match = True
        else:
            date_match = True  # якщо дата не задана — не фільтруємо

        # Перевіряємо збіг по номіналу
        nominal_match = False
        if norm_nominal:
            row_nominal = _normalize(cell_map.get("Номінал", "") + " " + cell_map.get("Гривня", ""))
            if norm_nominal in row_nominal or row_nominal in norm_nominal:
                nominal_match = True
            # також перевіряємо в назві рядка
            row_name_cell = _normalize(cell_map.get("Назва", ""))
            if norm_nominal in row_name_cell:
                nominal_match = True
        else:
            nominal_match = True  # якщо номінал не задано — не фільтруємо

        if not (date_match and nominal_match):
            continue

        # Шукаємо ціну — спробуємо різні варіанти
        price_tag = row.select_one("a.list_price")
        if not price_tag:
            price_tag = row.select_one(".price, .list_price, [data-title='Ціна']")

        if price_tag:
            result["price"] = price_tag.get_text(strip=True)

        # Шукаємо посилання на монету
        link_tag = row.select_one("a[href]")
        if link_tag:
            href = link_tag.get("href", "")
            if href.startswith("http"):
                result["url"] = href
            elif href.startswith("/"):
                result["url"] = f"https://www.ua-coins.info{href}"

        if result["price"]:
            return result

    # Якщо фільтри не спрацювали — повертаємо ціну першого результату
    first_price = soup.select_one("a.list_price, .price")
    if first_price:
        result["price"]  = first_price.get_text(strip=True)
        result["error"]  = "⚠️ Точний збіг не знайдено, показано перший результат"
        first_link       = soup.select_one("table tbody tr a[href]")
        if first_link:
            href = first_link.get("href", "")
            result["url"] = f"https://www.ua-coins.info{href}" if href.startswith("/") else href

    if not result["price"]:
        result["error"] = "Монету не знайдено на ua-coins.info"

    return result