"""
handlers/numismatics/list.py
Список монет з БД з пагінацією.
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Numismatic as Coin

logger = logging.getLogger(__name__)

PAGE_SIZE = 5


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _status(coin: Coin) -> str:
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
        session = Session()
        all_coins = session.query(Coin).order_by(Coin.id.desc()).all()
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

    lines = [f"📋 <b>Мої записи</b>  <i>({total} шт.)</i>\n"]
    for coin in slice_:
        s      = _sign(coin.currency or "UAH")
        stat   = _status(coin)
        total_invested = (coin.buy_price or 0) * (coin.quantity or 1)
        line = (
            f"{stat} <b>{coin.name}</b>  •  {coin.year or '—'} р.\n"
            f"   🔢 {coin.quantity} шт.  •  💵 {coin.buy_price:,.2f} {s}/шт.\n"
            f"   💼 Вкладено: <b>{total_invested:,.2f} {s}</b>\n"
        )
        if coin.is_sold and coin.sell_price:
            profit = (coin.sell_price - coin.buy_price) * coin.quantity
            line += f"   💰 Продано: {coin.sell_price:,.2f} {s}/шт.  •  P&L: <b>{profit:+,.2f} {s}</b>\n"
        lines.append(line)

    lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=_kb_list(page, total_pages),
        parse_mode="HTML",
    )