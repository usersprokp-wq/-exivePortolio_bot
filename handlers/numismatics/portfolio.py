"""
handlers/numismatics/portfolio.py
Портфель — активні монети (is_sold = 0).
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Numismatic as Coin

logger    = logging.getLogger(__name__)
PAGE_SIZE = 5


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _coin_block(coin: Coin) -> str:
    s     = _sign(coin.currency or "UAH")
    total = (coin.buy_price or 0) * (coin.quantity or 1)
    return (
        f"🟢 <b>{coin.name}</b>  •  {coin.year or '—'} р.\n"
        f"   🔢 {coin.quantity} шт.  •  💵 {coin.buy_price:,.2f} {s}/шт.\n"
        f"   💼 Вкладено: <b>{total:,.2f} {s}</b>\n"
    )


def _build_text(coins: list, page: int, total_pages: int) -> str:
    slice_ = coins[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    lines  = [f"🏛 <b>Портфель монет</b>  <i>({len(coins)} активних)</i>\n"]

    for coin in slice_:
        lines.append(_coin_block(coin))

    # Зведення по валютах
    by_cur: dict = {}
    for c in coins:
        cur = c.currency or "UAH"
        by_cur.setdefault(cur, {"invested": 0, "count": 0, "s": _sign(cur)})
        by_cur[cur]["invested"] += (c.buy_price or 0) * (c.quantity or 1)
        by_cur[cur]["count"]    += c.quantity or 1

    lines.append("─" * 24)
    for v in by_cur.values():
        lines.append(
            f"💼 Всього вкладено: <b>{v['invested']:,.2f} {v['s']}</b>  |  "
            f"Монет: <b>{v['count']} шт.</b>"
        )

    if total_pages > 1:
        lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    return "\n".join(lines)


def _kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"num_portfolio_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"num_portfolio_page_{page + 1}"))

    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("✅ Продані монети", callback_data="num_sold")])
    keyboard.append([InlineKeyboardButton("🔙 Назад",         callback_data="numismatics")])
    return InlineKeyboardMarkup(keyboard)


async def show_num_portfolio(update: Update, context: CallbackContext, page: int = 1):
    query = update.callback_query
    await query.answer()

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session = Session()
        all_coins = session.query(Coin).all()
        session.close()
        active = [c for c in all_coins if not c.is_sold]
    except Exception as e:
        logger.error(f"Coin portfolio error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not active:
        await query.edit_message_text(
            "🏛 <b>Портфель монет</b>\n\n📭 Активних монет немає.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Продані монети", callback_data="num_sold")],
                [InlineKeyboardButton("🔙 Назад",         callback_data="numismatics")],
            ]),
            parse_mode="HTML",
        )
        return

    total_pages = max(1, (len(active) + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(1, min(page, total_pages))

    await query.edit_message_text(
        _build_text(active, page, total_pages),
        reply_markup=_kb(page, total_pages),
        parse_mode="HTML",
    )


async def show_num_sold(update: Update, context: CallbackContext, page: int = 1):
    """Список проданих монет."""
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
        sold = [c for c in all_coins if c.is_sold]
    except Exception as e:
        logger.error(f"Coin sold error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not sold:
        await query.edit_message_text(
            "✅ <b>Продані монети</b>\n\n📭 Проданих монет ще немає.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="num_portfolio")
            ]]),
            parse_mode="HTML",
        )
        return

    total_pages = max(1, (len(sold) + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(1, min(page, total_pages))
    slice_      = sold[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    lines = [f"✅ <b>Продані монети</b>  <i>({len(sold)} шт.)</i>\n"]
    for coin in slice_:
        s      = _sign(coin.currency or "UAH")
        profit = ((coin.sell_price or 0) - (coin.buy_price or 0)) * (coin.quantity or 1)
        lines.append(
            f"⚪️ <b>{coin.name}</b>  •  {coin.year or '—'} р.\n"
            f"   🔢 {coin.quantity} шт.  •  💵 {coin.buy_price:,.2f} → {coin.sell_price:,.2f} {s}\n"
            f"   P&L: <b>{profit:+,.2f} {s}</b>\n"
        )

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"num_sold_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"num_sold_page_{page + 1}"))
    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="num_portfolio")])

    if total_pages > 1:
        lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )