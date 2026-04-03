"""
handlers/numismatics/stats.py
Статистика нумізматики.
"""
import logging
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Coin

logger = logging.getLogger(__name__)


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


async def show_num_stats(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session   = Session()
        all_coins = session.query(Coin).all()
        session.close()
    except Exception as e:
        logger.error(f"Coin stats error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not all_coins:
        await query.edit_message_text(
            "📊 <b>Статистика нумізматики</b>\n\n📭 Монет ще немає.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="numismatics")
            ]]),
            parse_mode="HTML",
        )
        return

    active = [c for c in all_coins if not c.is_sold]
    sold   = [c for c in all_coins if c.is_sold]

    total_count  = len(all_coins)
    active_count = sum(c.quantity or 1 for c in active)
    sold_count   = sum(c.quantity or 1 for c in sold)

    # Інвестовано по валютах
    invested_by_cur: dict = defaultdict(float)
    for c in all_coins:
        invested_by_cur[c.currency or "UAH"] += (c.buy_price or 0) * (c.quantity or 1)

    # Реалізований P&L
    pnl_by_cur: dict = defaultdict(float)
    for c in sold:
        if c.sell_price:
            pnl_by_cur[c.currency or "UAH"] += (c.sell_price - (c.buy_price or 0)) * (c.quantity or 1)

    # Найкраща монета по прибутку
    best = None
    best_pnl = None
    for c in sold:
        if c.sell_price:
            pnl = (c.sell_price - (c.buy_price or 0)) * (c.quantity or 1)
            if best_pnl is None or pnl > best_pnl:
                best_pnl = pnl
                best     = c

    # Топ за роками
    by_year: dict = defaultdict(int)
    for c in all_coins:
        if c.year:
            by_year[c.year] += c.quantity or 1
    top_years = sorted(by_year.items(), key=lambda x: x[1], reverse=True)[:5]

    # ── Формуємо текст ──────────────────────────────────────────────────────
    text = "📊 <b>Статистика нумізматики</b>\n\n"

    text += (
        f"🪙 Всього позицій: <b>{total_count}</b>\n"
        f"   🟢 Активних монет: <b>{active_count} шт.</b>  •  "
        f"✅ Продано: <b>{sold_count} шт.</b>\n\n"
    )

    for cur, val in invested_by_cur.items():
        text += f"💼 Вкладено: <b>{val:,.2f} {_sign(cur)}</b>\n"

    text += "\n"

    if pnl_by_cur:
        for cur, pnl in pnl_by_cur.items():
            s    = _sign(cur)
            sign = "+" if pnl >= 0 else ""
            text += f"💰 Реалізований P&L: <b>{sign}{pnl:,.2f} {s}</b>\n"
        text += "\n"

    if best and best_pnl is not None:
        s = _sign(best.currency or "UAH")
        text += f"🏆 Найкраща угода: <b>{best.name}</b> — {best_pnl:+,.2f} {s}\n\n"

    if top_years:
        text += "📅 <b>Топ років випуску:</b>\n"
        for year, qty in top_years:
            text += f"  • {year} р. — {qty} шт.\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="numismatics")
        ]]),
        parse_mode="HTML",
    )