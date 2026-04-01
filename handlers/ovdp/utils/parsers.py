"""
Парсери для отримання цін облігацій з різних джерел
"""
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available")


def fetch_bond_price_icu(bond_number):
    """
    Парсить ціну облігації з uainvest.com.ua для ICU
    Повертає ціну або None
    """
    try:
        url = "https://uainvest.com.ua/ukrbonds"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table')
        if not table:
            return None
        
        rows = table.find_all('tr')
        if not rows:
            return None
        
        # Знаходимо індекси колонок
        headers_row = rows[0].find_all('th')
        isin_col = broker_col = price_col = None
        
        for i, th in enumerate(headers_row):
            text = th.text.strip()
            if text == 'ISIN':
                isin_col = i
            if text == 'Брокер':
                broker_col = i
            if text == 'Ціна':
                price_col = i
        
        if None in (isin_col, broker_col, price_col):
            return None
        
        isin = f"UA{bond_number}"
        
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) > max(isin_col, broker_col, price_col):
                current_isin = cells[isin_col].text.strip()
                if current_isin.startswith(isin):
                    broker = cells[broker_col].text.strip().lower()
                    price = cells[price_col].text.strip()
                    if broker == 'icu' and price != '-':
                        return float(price.replace(',', '.'))
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching bond price: {e}")
        return None
