import logging
from collections import defaultdict
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Crypto, CryptoPortfolio

logger = logging.getLogger(__name__)


def _parse_date(date_str):
    try:
        return datetime.strptime(date_str, '%d.%m.%Y')
    except Exception:
        return None


def _build_general_stats(cryptos, portfolio) -> str:
    buys = [c for c in cryptos if c.operation_type == 'купівля']
    sells = [c for c in cryptos if c.operation_type == 'продаж']

    total_pnl = sum(c.pnl or 0 for c in sells)
    current_portfolio_value = sum(p.total_amount for p in portfolio)
    profitable_sells = [c for c in sells if (c.pnl or 0) > 0]
    win_rate = (len(profitable_sells) / len(sells) * 100) if sells else 0
    avg_pnl = (total_pnl / len(sells)) if sells else 0
    pnl_emoji = "📈" if total_pnl >= 0 else "📉"

    text = (
        f"📊 *Статистика Крипти — Загальне*\n\n"
        f"💼 *Портфель:*\n"
        f"₿ Поточна вартість: `{current_portfolio_value:.2f} USDT`\n"
        f"{pnl_emoji} Загальний P&L: `{total_pnl:+.2f} USDT`\n\n"
        f"📍 *Операції:*\n"
        f"✅ Win rate: `{win_rate:.1f}%` ({len(profitable_sells)}/{len(sells)})\n"
        f"📊 Середній P&L/угода: `{avg_pnl:+.2f} USDT`\n"
    )

    monthly_pnl = defaultdict(float)
    for c in sells:
        d = _parse_date(c.date)
        if d:
            monthly_pnl[d.strftime('%m.%Y')] += c.pnl or 0

    if monthly_pnl:
        text += "\n📅 *P&L по місяцях:*\n"
        for month in sorted(monthly_pnl.keys(), key=lambda m: datetime.strptime(m, '%m.%Y')):
            pnl = monthly_pnl[month]
            emoji = "📈" if pnl >= 0 else "📉"
            text += f"  {emoji} `{month}`: `{pnl:+.2f} USDT`\n"

    return text


def _build_top_stats(cryptos, portfolio) -> str:
    sells = [c for c in cryptos if c.operation_type == 'продаж']
    ticker_pnl = defaultdict(float)
    for c in sells:
        ticker_pnl[c.ticker] += c.pnl or 0

    text = "🏆 *Статистика Крипти — Топ Монети*\n\n"

    if ticker_pnl:
        sorted_tickers = sorted(ticker_pnl.items(), key=lambda x: x[1], reverse=True)
        best = sorted_tickers[0]
        worst = sorted_tickers[-1]
        text += (
            f"🥇 *Найприбутковіша:* `{best[0]}` — `{best[1]:+.2f} USDT`\n"
            f"📉 *Найзбитковіша:* `{worst[0]}` — `{worst[1]:+.2f} USDT`\n\n"
        )
        text += "📊 *Топ-5 по P&L:*\n"
        for i, (ticker, pnl) in enumerate(sorted_tickers[:5], 1):
            emoji = "📈" if pnl >= 0 else "📉"
            text += f"  {i}. `{ticker}`: {emoji} `{pnl:+.2f} USDT`\n"
    else:
        text += "📭 Немає закритих угод для аналізу\n"

    total_portfolio = sum(p.total_amount for p in portfolio)
    if portfolio and total_portfolio > 0:
        text += "\n💼 *Топ-3 по вазі в портфелі:*\n"
        for i, p in enumerate(sorted(portfolio, key=lambda p: p.total_amount, reverse=True)[:3], 1):
            weight = p.total_amount / total_portfolio * 100
            text += f"  {i}. `{p.ticker}`: `{weight:.1f}%` ({p.total_amount:.2f} USDT)\n"

    return text


def _keyboard(current: str) -> InlineKeyboardMarkup:
    tabs = [('🌐 Загальне', 'crypto_stats_general'), ('🏆 Топ монети', 'crypto_stats_top')]
    row = []
    for label, cb in tabs:
        if cb == current:
            label = f"[ {label} ]"
        row.append(InlineKeyboardButton(label, callback_data=cb))
    return InlineKeyboardMarkup([row, [InlineKeyboardButton("🔙 Назад", callback_data='crypto')]])


async def show_crypto_stats(update: Update, context: CallbackContext, tab: str = 'crypto_stats_general'):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        session = Session()
        cryptos = session.query(Crypto).all()
        portfolio = session.query(CryptoPortfolio).all()
        session.close()

        if not cryptos:
            await query.edit_message_text("📭 Немає даних про крипту", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto')]]))
            return

        text = _build_top_stats(cryptos, portfolio) if tab == 'crypto_stats_top' else _build_general_stats(cryptos, portfolio)
        await query.edit_message_text(text, reply_markup=_keyboard(tab), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in show_crypto_stats: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")