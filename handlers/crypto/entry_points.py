import logging
from collections import defaultdict

import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Crypto, CryptoPortfolio

logger = logging.getLogger(__name__)

ENTRY_PER_PAGE = 5


def get_crypto_price(ticker: str) -> float | None:
    try:
        search_url = f"https://api.coingecko.com/api/v3/search?query={ticker}"
        r = requests.get(search_url, timeout=5)
        coins = r.json().get('coins', [])
        if not coins:
            return None
        coin_id = coins[0]['id']
        price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        r2 = requests.get(price_url, timeout=5)
        return r2.json().get(coin_id, {}).get('usd')
    except Exception as e:
        logger.error(f"CoinGecko error for {ticker}: {e}")
        return None


async def show_crypto_entry_points(update: Update, context: CallbackContext, page: int = 1, use_cache: bool = False):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        session = Session()
        all_cryptos = session.query(Crypto).filter(Crypto.operation_type == 'купівля').all()
        portfolio = session.query(CryptoPortfolio).all()
        session.close()

        if not all_cryptos:
            await query.edit_message_text(
                "📭 Немає записів про покупки",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto')]]),
            )
            return

        portfolio_tickers = {p.ticker.upper() for p in portfolio}

        ticker_data = defaultdict(lambda: {'total_amount': 0.0, 'total_qty': 0.0})
        for c in all_cryptos:
            t = c.ticker.upper() if c.ticker else None
            if not t or t in portfolio_tickers:
                continue
            ticker_data[t]['total_amount'] += (c.price_per_unit or 0) * (c.quantity or 0)
            ticker_data[t]['total_qty'] += (c.quantity or 0)

        if not ticker_data:
            await query.edit_message_text(
                "✅ Всі відстежувані монети зараз у портфелі",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto')]]),
            )
            return

        cached = context.user_data.get('crypto_entry_cache') if use_cache else None

        if cached is None:
            await query.edit_message_text("⏳ Завантажую поточні ціни, зачекайте...")
            results = []
            for ticker, data in ticker_data.items():
                if data['total_qty'] == 0:
                    continue
                avg_entry = data['total_amount'] / data['total_qty']
                current_price = get_crypto_price(ticker)
                if not current_price:
                    continue
                results.append({'ticker': ticker, 'avg_entry': avg_entry, 'current_price': current_price})

            results.sort(key=lambda r: (r['current_price'] - r['avg_entry']) / r['avg_entry'] if r['avg_entry'] else 999)
            context.user_data['crypto_entry_cache'] = results
        else:
            results = cached

        total_pages = max(1, (len(results) + ENTRY_PER_PAGE - 1) // ENTRY_PER_PAGE)
        page = max(1, min(page, total_pages))
        page_results = results[(page - 1) * ENTRY_PER_PAGE: page * ENTRY_PER_PAGE]

        text = f"🎯 *Точки входу — Крипта* (стор. {page}/{total_pages})\n\n"
        for r in page_results:
            avg = r['avg_entry']
            cur = r['current_price']
            diff_pct = ((cur - avg) / avg) * 100
            diff_abs = cur - avg
            if diff_pct <= -15:
                signal = "🟢 Гарна точка входу!"
            elif diff_pct <= -5:
                signal = "🟡 Близько до входу"
            else:
                signal = "🔴 Ще не час"
            sign = "+" if diff_abs >= 0 else ""
            text += f"₿ *{r['ticker']}*\n"
            text += f"   ⬆️ Середній вхід: {avg:.4f} USDT\n"
            text += f"   📍 Зараз: {cur:.4f} USDT\n"
            text += f"   🎯 Від входу: {sign}{diff_pct:.1f}% ({sign}{diff_abs:.4f} USDT)\n"
            text += f"   {signal}\n\n"

        keyboard = []
        if total_pages > 1:
            keyboard.append([
                InlineKeyboardButton(f"[{p}]" if p == page else str(p), callback_data=f'crypto_entry_page_{p}')
                for p in range(1, total_pages + 1)
            ])
        keyboard.append([InlineKeyboardButton("🔄 Оновити", callback_data='crypto_entry_refresh')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='crypto')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in show_crypto_entry_points: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")