import logging
from collections import defaultdict

import yfinance as yf

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock, StockPortfolio

logger = logging.getLogger(__name__)

ENTRY_PER_PAGE = 5


async def show_entry_points(update: Update, context: CallbackContext, page: int = 1, use_cache: bool = False):
    """Моніторинг точок входу — акції яких немає в портфелі зараз"""
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        all_stocks = session.query(Stock).filter(Stock.operation_type == 'купівля').all()
        portfolio = session.query(StockPortfolio).all()
        session.close()

        if not all_stocks:
            await query.edit_message_text(
                "📭 Немає записів про покупки",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]),
            )
            return

        # Тікери які є в портфелі зараз
        portfolio_tickers = {
            p.ticker.split('.')[0].upper()
            for p in portfolio
            if not p.ticker.endswith('usd')
        }

        # Середня ціна входу по кожному тікеру (тільки ті яких немає в портфелі)
        ticker_data = defaultdict(lambda: {'total_amount': 0.0, 'total_qty': 0})
        for s in all_stocks:
            t = s.ticker.split('.')[0].upper() if s.ticker else None
            if not t:
                continue
            if t in portfolio_tickers:
                continue
            ticker_data[t]['total_amount'] += (s.price_per_unit or 0) * (s.quantity or 0)
            ticker_data[t]['total_qty'] += (s.quantity or 0)
            ticker_data[t]['raw_ticker'] = s.ticker  # зберігаємо оригінал для yfinance

        if not ticker_data:
            await query.edit_message_text(
                "✅ Всі відстежувані акції зараз у портфелі",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]),
            )
            return

        # Кеш
        cached = context.user_data.get('entry_cache') if use_cache else None

        if cached is None:
            await query.edit_message_text("⏳ Завантажую поточні ціни, зачекайте...")

            results = []
            for ticker, data in ticker_data.items():
                if data['total_qty'] == 0:
                    continue
                avg_entry = data['total_amount'] / data['total_qty']

                # Отримуємо поточну ціну
                ticker_clean = ticker.split('.')[0]
                current_price = None
                try:
                    stock = yf.Ticker(ticker_clean)
                    try:
                        current_price = stock.fast_info.last_price
                    except Exception:
                        pass
                    if not current_price:
                        info = stock.info
                        current_price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose')
                except Exception as e:
                    logger.error(f"yfinance error for {ticker_clean}: {e}")

                results.append({
                    'ticker': ticker,
                    'avg_entry': avg_entry,
                    'current_price': current_price,
                })

            # Сортуємо: спочатку найближчі до точки входу (найменший % від входу, негативні першими)
            def sort_key(r):
                if r['current_price'] and r['avg_entry']:
                    return (r['current_price'] - r['avg_entry']) / r['avg_entry']
                return 999
            results.sort(key=sort_key)

            context.user_data['entry_cache'] = results
        else:
            results = cached

        total_pages = max(1, (len(results) + ENTRY_PER_PAGE - 1) // ENTRY_PER_PAGE)
        page = max(1, min(page, total_pages))
        page_results = results[(page - 1) * ENTRY_PER_PAGE: page * ENTRY_PER_PAGE]

        text = f"🎯 *Точки входу* (стор. {page}/{total_pages})\n\n"

        for r in page_results:
            avg = r['avg_entry']
            cur = r['current_price']
            text += f"📊 *{r['ticker']}*\n"
            text += f"   ⬆️ Середній вхід: {avg:.2f} $\n"

            if cur:
                diff_pct = ((cur - avg) / avg) * 100
                diff_abs = cur - avg

                if diff_pct <= -15:
                    signal = "🟢 Гарна точка входу!"
                elif diff_pct <= -5:
                    signal = "🟡 Близько до входу"
                else:
                    signal = "🔴 Ще не час"

                sign = "+" if diff_abs >= 0 else ""
                text += f"   📍 Зараз: {cur:.2f} $\n"
                text += f"   🎯 Від входу: {sign}{diff_pct:.1f}% ({sign}{diff_abs:.2f} $)\n"
                text += f"   {signal}\n\n"
            else:
                text += f"   📍 Ціна недоступна\n\n"

        keyboard = []
        if total_pages > 1:
            keyboard.append([
                InlineKeyboardButton(
                    f"[{p}]" if p == page else str(p),
                    callback_data=f"entry_page_{p}"
                )
                for p in range(1, total_pages + 1)
            ])
        keyboard.append([InlineKeyboardButton("🔄 Оновити", callback_data='entry_refresh')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks')])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in show_entry_points: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")