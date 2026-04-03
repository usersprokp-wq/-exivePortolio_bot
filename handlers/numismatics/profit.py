"""
handlers/numismatics/profit.py
Прибуток — відмітити монету як продану, ввести ціну продажу.
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Numismatic as Coin

logger = logging.getLogger(__name__)


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


async def show_num_profit(update: Update, context: CallbackContext):
    """Показує список активних монет для продажу."""
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
        active = [c for c in all_coins if not c.is_sold]
    except Exception as e:
        logger.error(f"Coin profit error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    # Загальний P&L по проданих
    try:
        session    = Session()
        all_coins2 = session.query(Coin).all()
        session.close()
        sold       = [c for c in all_coins2 if c.is_sold and c.sell_price]
    except Exception:
        sold = []

    total_pnl_by_cur: dict = {}
    for c in sold:
        cur = c.currency or "UAH"
        pnl = ((c.sell_price or 0) - (c.buy_price or 0)) * (c.quantity or 1)
        total_pnl_by_cur[cur] = total_pnl_by_cur.get(cur, 0) + pnl

    lines = ["💰 <b>Прибуток — Нумізматика</b>\n"]

    if total_pnl_by_cur:
        lines.append("📊 <b>Реалізований P&L:</b>")
        for cur, pnl in total_pnl_by_cur.items():
            s = _sign(cur)
            lines.append(f"  • {pnl:+,.2f} {s}")
        lines.append("")

    if not active:
        lines.append("📭 Немає активних монет для продажу.")
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="numismatics")
            ]]),
            parse_mode="HTML",
        )
        return

    lines.append("🟢 <b>Оберіть монету для продажу:</b>")

    keyboard = []
    for coin in active:
        s   = _sign(coin.currency or "UAH")
        lbl = f"🪙 {coin.name} ({coin.year or '—'}) • {coin.quantity}шт. • {coin.buy_price:,.0f}{s}"
        keyboard.append([InlineKeyboardButton(lbl, callback_data=f"num_sell_{coin.id}")])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="numismatics")])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def handle_num_sell_selected(update: Update, context: CallbackContext):
    """Обрана монета для продажу — запитуємо ціну."""
    query   = update.callback_query
    await query.answer()
    coin_id = int(query.data.replace("num_sell_", ""))

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session = Session()
        coin    = session.query(Coin).filter(Coin.id == coin_id).first()
        session.close()
    except Exception as e:
        logger.error(f"Coin sell select error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not coin:
        await query.edit_message_text("❌ Монету не знайдено.")
        return

    s = _sign(coin.currency or "UAH")
    context.user_data["num_sell_coin_id"] = coin_id
    context.user_data["num_profit_step"]  = "sell_price"

    await query.edit_message_text(
        f"🪙 <b>{coin.name}</b>  •  {coin.year or '—'} р.\n"
        f"🔢 Кількість: {coin.quantity} шт.\n"
        f"💵 Ціна купівлі: {coin.buy_price:,.2f} {s}/шт.\n\n"
        f"💰 Введіть ціну продажу за одиницю (у {coin.currency or 'UAH'}):",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Скасувати", callback_data="num_profit")
        ]]),
        parse_mode="HTML",
    )


async def handle_message_num_profit(update: Update, context: CallbackContext):
    """Отримуємо ціну продажу і зберігаємо."""
    step = context.user_data.get("num_profit_step")
    if step != "sell_price":
        return
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    try:
        sell_price = float(text.replace(",", ".").replace(" ", ""))
        if sell_price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Введіть коректну ціну (додатнє число):",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Скасувати", callback_data="num_profit")
            ]]),
        )
        return

    coin_id = context.user_data.get("num_sell_coin_id")
    context.user_data.pop("num_profit_step", None)
    context.user_data.pop("num_sell_coin_id", None)

    Session = context.bot_data.get('Session')
    if not Session:
        await update.message.reply_text("❌ Помилка підключення до бази даних")
        return

    try:
        session = Session()
        coin    = session.query(Coin).filter(Coin.id == coin_id).first()
        if coin:
            pnl            = (sell_price - (coin.buy_price or 0)) * (coin.quantity or 1)
            coin.sell_price = sell_price
            coin.is_sold   = 1
            session.commit()
            s = _sign(coin.currency or "UAH")
            name, qty, buy = coin.name, coin.quantity, coin.buy_price
        session.close()
    except Exception as e:
        logger.error(f"Coin sell save error: {e}")
        await update.message.reply_text(f"❌ Помилка: {e}")
        return

    from handlers.numismatics.main_menu import get_numismatics_menu_keyboard
    await update.message.reply_text(
        f"✅ <b>Продано!</b>\n\n"
        f"🪙 {name}  •  {qty} шт.\n"
        f"💵 {buy:,.2f} → {sell_price:,.2f} {s}/шт.\n"
        f"💰 P&L: <b>{pnl:+,.2f} {s}</b>\n\n"
        "🏛 <b>Нумізматика</b> — оберіть дію:",
        reply_markup=get_numismatics_menu_keyboard(),
        parse_mode="HTML",
    )