import logging
from datetime import datetime

import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import CryptoPortfolio
from .utils import recalculate_percents

logger = logging.getLogger(__name__)

PORTFOLIO_PER_PAGE = 5
PNL_PER_PAGE = 5


def _back_kb(callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=callback)]])


def get_crypto_price(ticker: str) -> float | None:
    """Отримати поточну ціну монети через CoinGecko API (безкоштовно, без ключа)"""
    try:
        # Спочатку знаходимо id монети
        search_url = f"https://api.coingecko.com/api/v3/search?query={ticker}"
        r = requests.get(search_url, timeout=5)
        data = r.json()
        coins = data.get('coins', [])
        if not coins:
            return None
        coin_id = coins[0]['id']

        # Отримуємо ціну
        price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        r2 = requests.get(price_url, timeout=5)
        price_data = r2.json()
        return price_data.get(coin_id, {}).get('usd')
    except Exception as e:
        logger.error(f"CoinGecko error for {ticker}: {e}")
        return None


async def show_crypto_portfolio(update: Update, context: CallbackContext, page=1):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        session = Session()
        all_records = session.query(CryptoPortfolio).order_by(CryptoPortfolio.last_update.desc()).all()
        session.close()

        if not all_records:
            await query.edit_message_text("📭 Портфель пустий", reply_markup=_back_kb('crypto'))
            return

        stock_records = sorted(all_records, key=lambda r: r.total_amount, reverse=True)
        total_invested = sum(r.total_amount for r in stock_records)
        total_pages = max(1, (len(stock_records) + PORTFOLIO_PER_PAGE - 1) // PORTFOLIO_PER_PAGE)
        page = max(1, min(page, total_pages))
        page_records = stock_records[(page - 1) * PORTFOLIO_PER_PAGE: page * PORTFOLIO_PER_PAGE]

        text = f"💼 *Портфель Крипти* (стор. {page}/{total_pages})\n\n"
        for r in page_records:
            pct = r.percent or 0
            text += f"₿ *{r.ticker}* ({round(pct, 1)}%)\n"
            text += f"   📦 Кількість: {r.total_quantity:.8f}\n"
            text += f"   💰 Ціна: {r.avg_price:.4f} USDT\n"
            text += f"   💵 Сума: {r.total_amount:.2f} USDT\n"
            text += f"   📊 Біржа: {r.platform}\n\n"

        text += f"━━━━━━━━━━━━━━━━━━━━\n📊 *Всього інвестовано:* {total_invested:.2f} USDT"

        keyboard = []
        if total_pages > 1:
            keyboard.append([
                InlineKeyboardButton(f"[{p}]" if p == page else str(p), callback_data=f'crypto_portfolio_page_{p}')
                for p in range(1, total_pages + 1)
            ])
        keyboard.append([InlineKeyboardButton("📈 Взнати PnL", callback_data='crypto_check_pnl')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='crypto')])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_crypto_pnl(update: Update, context: CallbackContext, page: int = 1, use_cache: bool = True):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        session = Session()
        all_records = session.query(CryptoPortfolio).all()
        session.close()

        cached = context.user_data.get('crypto_pnl_cache') if use_cache else None

        if cached is None:
            await query.edit_message_text("⏳ Завантажую поточні ціни, зачекайте...")
            results = []
            errors = []
            for record in all_records:
                current_price = get_crypto_price(record.ticker)
                if current_price is None:
                    errors.append(record.ticker)
                    continue
                invested = record.avg_price * record.total_quantity
                current_total = current_price * record.total_quantity
                pnl_total = current_total - invested
                pnl_pct = (pnl_total / invested * 100) if invested else 0
                results.append({
                    'ticker': record.ticker,
                    'qty': record.total_quantity,
                    'avg': record.avg_price,
                    'current': current_price,
                    'invested': invested,
                    'current_total': current_total,
                    'pnl_total': pnl_total,
                    'pnl_pct': pnl_pct,
                })
            context.user_data['crypto_pnl_cache'] = {'results': results, 'errors': errors}
        else:
            results = cached['results']
            errors = cached['errors']

        if not results and not errors:
            await query.edit_message_text("📭 Портфель пустий", reply_markup=_back_kb('crypto_portfolio'))
            return

        total_pages = max(1, (len(results) + PNL_PER_PAGE - 1) // PNL_PER_PAGE)
        page = max(1, min(page, total_pages))
        page_results = results[(page - 1) * PNL_PER_PAGE: page * PNL_PER_PAGE]

        text = f"📊 *PnL по крипто-портфелю* (стор. {page}/{total_pages})\n\n"
        for r in page_results:
            emoji = "🟢" if r['pnl_total'] >= 0 else "🔴"
            sign = "+" if r['pnl_total'] >= 0 else ""
            text += f"{emoji} *{r['ticker']}* — {r['qty']:.8f}\n"
            text += f"   {r['avg']:.4f} → {r['current']:.4f} USDT\n"
            text += f"   Всього: {sign}{r['pnl_total']:.2f} USDT ({sign}{r['pnl_pct']:.2f}%)\n\n"

        if errors:
            text += f"⚠️ Не знайдено: {', '.join(errors)}\n\n"

        total_invested = sum(r['invested'] for r in results)
        total_current = sum(r['current_total'] for r in results)
        total_pnl = total_current - total_invested
        total_pct = (total_pnl / total_invested * 100) if total_invested else 0
        sign = "+" if total_pnl >= 0 else ""
        indicator = "🟢 ▲" if total_pnl >= 0 else "🔴 ▼"

        text += f"━━━━━━━━━━━━━━━━━━━━\n"
        text += f"💰 Всього інвестовано: {total_invested:.2f} USDT\n"
        text += f"💼 Поточні активи: {total_current:.2f} USDT\n"
        text += f"{indicator} *Поточний PnL: {sign}{total_pnl:.2f} USDT ({sign}{total_pct:.2f}%)*"

        keyboard = []
        if total_pages > 1:
            keyboard.append([
                InlineKeyboardButton(f"[{p}]" if p == page else str(p), callback_data=f'crypto_pnl_page_{p}')
                for p in range(1, total_pages + 1)
            ])
        keyboard.append([InlineKeyboardButton("🔄 Оновити", callback_data='crypto_pnl_refresh')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='crypto_portfolio')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in show_crypto_pnl: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}", reply_markup=_back_kb('crypto_portfolio'))