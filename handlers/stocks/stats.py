import logging
from collections import defaultdict
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock, StockPortfolio

logger = logging.getLogger(__name__)


def _parse_date(date_str: str):
    try:
        return datetime.strptime(date_str, '%d.%m.%Y')
    except Exception:
        return None


def _build_general_stats(stocks, portfolio) -> str:
    buys = [s for s in stocks if s.operation_type == 'купівля']
    sells = [s for s in stocks if s.operation_type == 'продаж']

    total_pnl = sum(s.pnl or 0 for s in sells)
    current_portfolio_value = sum(p.total_amount for p in portfolio if not p.ticker.endswith('usd'))
    total_invested = sum(s.total_amount for s in buys)
    pnl_percent = (total_pnl * 100 / current_portfolio_value) if current_portfolio_value > 0 else 0

    profitable_sells = [s for s in sells if (s.pnl or 0) > 0]
    win_rate = (len(profitable_sells) / len(sells) * 100) if sells else 0
    avg_pnl = (total_pnl / len(sells)) if sells else 0

    pnl_emoji = "📈" if total_pnl >= 0 else "📉"

    text = (
        f"📊 *Статистика Акцій — Загальне*\n\n"
        f"💼 *Портфель:*\n"
        f"📈 Поточна вартість: `{current_portfolio_value:.2f} $`\n"
        f"{pnl_emoji} Загальний P&L: `{total_pnl:+.2f} $` ({pnl_percent:+.2f}%)\n\n"
        f"📍 *Операції:*\n"
        f"✅ Win rate: `{win_rate:.1f}%` ({len(profitable_sells)}/{len(sells)})\n"
        f"📊 Середній P&L/угода: `{avg_pnl:+.2f} $`\n"
    )

    # Блок по біржах
    platforms = {}
    for s in stocks:
        if s.operation_type == 'продаж':
            if s.platform not in platforms:
                platforms[s.platform] = {'invested': 0, 'pnl': 0, 'operations': 0, 'wins': 0}
            platforms[s.platform]['pnl'] += s.pnl or 0
            platforms[s.platform]['operations'] += 1
            if (s.pnl or 0) > 0:
                platforms[s.platform]['wins'] += 1
    for p in portfolio:
        if not p.ticker.endswith('usd'):
            if p.platform not in platforms:
                platforms[p.platform] = {'invested': 0, 'pnl': 0, 'operations': 0, 'wins': 0}
            platforms[p.platform]['invested'] += p.total_amount

    if platforms:
        text += "\n🏛️ *По Біржах:*\n"
        for platform, data in sorted(platforms.items()):
            pnl_e = "📈" if data['pnl'] >= 0 else "📉"
            wr = (data['wins'] / data['operations'] * 100) if data['operations'] > 0 else 0
            pnl_pct = (data['pnl'] * 100 / data['invested']) if data['invested'] > 0 else 0
            text += f"\n*{platform}:*\n"
            text += f"  💼 В портфелі: `{data['invested']:.2f} $`\n"
            text += f"  {pnl_e} P&L: `{data['pnl']:+.2f} $` ({pnl_pct:+.2f}%)\n"
            if data['operations'] > 0:
                text += f"  🔢 Операцій: `{data['operations']}` | ✅ Win rate: `{wr:.1f}%`\n"

    # PnL по всіх місяцях — від старих до нових
    monthly_pnl = defaultdict(float)
    for s in sells:
        d = _parse_date(s.date)
        if d:
            key = d.strftime('%m.%Y')
            monthly_pnl[key] += s.pnl or 0

    if monthly_pnl:
        text += "\n📅 *P&L по місяцях:*\n"
        for month in sorted(monthly_pnl.keys(), key=lambda m: datetime.strptime(m, '%m.%Y')):
            pnl = monthly_pnl[month]
            emoji = "📈" if pnl >= 0 else "📉"
            text += f"  {emoji} `{month}`: `{pnl:+.2f} $`\n"

    return text


def _build_top_stocks_stats(stocks, portfolio) -> str:
    sells = [s for s in stocks if s.operation_type == 'продаж']

    ticker_pnl = defaultdict(float)
    for s in sells:
        ticker_pnl[s.ticker] += s.pnl or 0

    text = "🏆 *Статистика Акцій — Топ Акції*\n\n"

    if ticker_pnl:
        sorted_tickers = sorted(ticker_pnl.items(), key=lambda x: x[1], reverse=True)
        best = sorted_tickers[0]
        worst = sorted_tickers[-1]

        text += (
            f"🥇 *Найприбутковіша:* `{best[0]}` — `{best[1]:+.2f} $`\n"
            f"📉 *Найзбитковіша:* `{worst[0]}` — `{worst[1]:+.2f} $`\n\n"
        )

        text += "📊 *Топ-5 по P&L:*\n"
        for i, (ticker, pnl) in enumerate(sorted_tickers[:5], 1):
            emoji = "📈" if pnl >= 0 else "📉"
            text += f"  {i}. `{ticker}`: {emoji} `{pnl:+.2f} $`\n"
    else:
        text += "📭 Немає закритих угод для аналізу\n"

    active = [p for p in portfolio if not p.ticker.endswith('usd')]
    total_portfolio = sum(p.total_amount for p in active)

    if active and total_portfolio > 0:
        text += "\n💼 *Топ-3 по вазі в портфелі:*\n"
        for i, p in enumerate(sorted(active, key=lambda p: p.total_amount, reverse=True)[:3], 1):
            weight = p.total_amount / total_portfolio * 100
            text += f"  {i}. `{p.ticker}`: `{weight:.1f}%` ({p.total_amount:.2f} $)\n"

    buy_dates = {}
    hold_days = []
    for s in stocks:
        if s.operation_type == 'купівля':
            buy_dates.setdefault(s.ticker, [])
            d = _parse_date(s.date)
            if d:
                buy_dates[s.ticker].append(d)

    for s in sells:
        d = _parse_date(s.date)
        if d and s.ticker in buy_dates and buy_dates[s.ticker]:
            days = (d - min(buy_dates[s.ticker])).days
            if days >= 0:
                hold_days.append(days)

    if hold_days:
        avg_days = sum(hold_days) / len(hold_days)
        text += f"\n⏱️ *Середній час утримання:* `{avg_days:.0f} днів`\n"

    return text


def _keyboard(current: str) -> InlineKeyboardMarkup:
    tabs = [
        ('🌐 Загальне', 'stocks_stats_general'),
        ('🏆 Топ акції', 'stocks_stats_top'),
    ]
    row = []
    for label, cb in tabs:
        if cb == current:
            label = f"[ {label} ]"
        row.append(InlineKeyboardButton(label, callback_data=cb))

    return InlineKeyboardMarkup([
        row,
        [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
    ])


async def show_stocks_stats(update: Update, context: CallbackContext, tab: str = 'stocks_stats_general'):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        stocks = session.query(Stock).all()
        portfolio = session.query(StockPortfolio).all()
        session.close()

        if not stocks:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
            await query.edit_message_text("📭 Немає даних про акції", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if tab == 'stocks_stats_top':
            text = _build_top_stocks_stats(stocks, portfolio)
        else:
            text = _build_general_stats(stocks, portfolio)

        await query.edit_message_text(
            text,
            reply_markup=_keyboard(tab),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in show_stocks_stats: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")