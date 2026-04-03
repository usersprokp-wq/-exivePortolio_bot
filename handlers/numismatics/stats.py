"""
handlers/numismatics/stats.py
Статистика нумізматики.
"""
import logging
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Numismatic

logger = logging.getLogger(__name__)


async def show_num_stats(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session   = Session()
        all_coins = session.query(Numismatic).all()
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

    total_positions  = len(all_coins)
    active_qty       = sum(c.quantity or 0 for c in active)
    sold_qty         = sum(c.quantity or 0 for c in sold)

    total_invested   = sum(c.total_amount or 0 for c in all_coins)
    active_invested  = sum(c.total_amount or 0 for c in active)

    # P&L по проданих
    total_pnl = sum(
        ((c.sell_price or 0) - (c.cost_per_unit or 0)) * (c.quantity or 1)
        for c in sold if c.sell_price
    )

    # Найкраща угода
    best = None
    best_pnl = None
    for c in sold:
        if c.sell_price:
            pnl = (c.sell_price - (c.cost_per_unit or 0)) * (c.quantity or 1)
            if best_pnl is None or pnl > best_pnl:
                best_pnl = pnl
                best     = c

    # Топ металів
    by_metal: dict = defaultdict(lambda: {"qty": 0, "invested": 0})
    for c in all_coins:
        key = f"{c.metal_name or '—'} ({c.metal_code or '—'})"
        by_metal[key]["qty"]      += c.quantity or 0
        by_metal[key]["invested"] += c.total_amount or 0
    top_metals = sorted(by_metal.items(), key=lambda x: x[1]["qty"], reverse=True)[:5]

    # Топ років карбування
    by_year: dict = defaultdict(int)
    for c in all_coins:
        if c.mint_year:
            by_year[c.mint_year] += c.quantity or 0
    top_years = sorted(by_year.items(), key=lambda x: x[1], reverse=True)[:5]

    # ── Текст ──────────────────────────────────────────────────────────────
    text = "📊 <b>Статистика нумізматики</b>\n\n"

    text += (
        f"🪙 Всього позицій: <b>{total_positions}</b>\n"
        f"   🟢 Активних: <b>{active_qty} шт.</b>  •  ✅ Продано: <b>{sold_qty} шт.</b>\n\n"
        f"💼 Загалом вкладено: <b>{total_invested:,.2f} ₴</b>\n"
        f"   🟢 В портфелі: <b>{active_invested:,.2f} ₴</b>\n\n"
    )

    if sold:
        sign = "+" if total_pnl >= 0 else ""
        text += f"💰 Реалізований P&L: <b>{sign}{total_pnl:,.2f} ₴</b>\n\n"

    if best and best_pnl is not None:
        sign = "+" if best_pnl >= 0 else ""
        text += f"🏆 Найкраща угода: <b>{best.name}</b> — {sign}{best_pnl:,.2f} ₴\n\n"

    if top_metals:
        text += "⚗️ <b>Метали:</b>\n"
        for metal, info in top_metals:
            text += f"  • {metal} — {info['qty']} шт.  •  {info['invested']:,.0f} ₴\n"
        text += "\n"

    if top_years:
        text += "📅 <b>Топ років карбування:</b>\n"
        for year, qty in top_years:
            text += f"  • {year} р. — {qty} шт.\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="numismatics")
        ]]),
        parse_mode="HTML",
    )