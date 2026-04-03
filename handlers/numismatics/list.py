"""
handlers/numismatics/list.py
Список монет з БД з пагінацією.
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Numismatic

logger = logging.getLogger(__name__)
PAGE_SIZE = 5


def _status(coin: Numismatic) -> str:
    return "✅" if coin.is_sold else "🟢"


def _kb_list(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"num_list_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"num_list_page_{page + 1}"))
    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="numismatics")])
    return InlineKeyboardMarkup(keyboard)


async def show_num_list(update: Update, context: CallbackContext, page: int = 1):
    query = update.callback_query
    await query.answer()

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session   = Session()
        all_coins = session.query(Numismatic).order_by(Numismatic.id.desc()).all()
        session.close()
    except Exception as e:
        logger.error(f"Coin list error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not all_coins:
        await query.edit_message_text(
            "📋 <b>Мої записи</b>\n\n📭 Монет ще немає.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="numismatics")
            ]]),
            parse_mode="HTML",
        )
        return

    total       = len(all_coins)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(1, min(page, total_pages))
    slice_      = all_coins[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    lines = [f"📋 <b>Мої записи</b>  <i>({total} поз.)</i>\n"]
    for coin in slice_:
        stat = _status(coin)
        line = (
            f"{stat} <b>{coin.name}</b>  •  {coin.mint_year or '—'} р.\n"
            f"   💲 {coin.nominal or '—'}  •  {coin.metal_name or '—'} ({coin.metal_code or '—'})\n"
            f"   ⚖️ {coin.metal_weight or 0} г  •  📐 {coin.diameter or 0} мм  •  🔢 {coin.mintage or 0:,} шт. тираж\n"
            f"   🛒 {coin.quantity} шт.  •  💵 {coin.price_per_unit or 0:,.2f} ₴/шт.\n"
            f"   💼 Собів.: <b>{coin.cost_per_unit or 0:,.2f} ₴/шт.</b>  •  Разом: <b>{coin.total_amount or 0:,.2f} ₴</b>\n"
        )
        if coin.is_sold and coin.sell_price:
            profit = (coin.sell_price - (coin.cost_per_unit or 0)) * (coin.quantity or 1)
            line += f"   💰 Продано: {coin.sell_price:,.2f} ₴/шт.  •  P&L: <b>{profit:+,.2f} ₴</b>\n"
        lines.append(line)

    lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=_kb_list(page, total_pages),
        parse_mode="HTML",
    )