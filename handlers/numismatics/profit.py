"""
handlers/numismatics/profit.py
Прибуток — відмітити монету як продану, ввести ціну продажу.
P&L рахується від собівартості (cost_per_unit).
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Numismatic

logger = logging.getLogger(__name__)


async def show_num_profit(update: Update, context: CallbackContext):
    """Показує загальний P&L та список активних монет для продажу."""
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
        logger.error(f"Coin profit error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    active = [c for c in all_coins if not c.is_sold]
    sold   = [c for c in all_coins if c.is_sold and c.sell_price]

    lines = ["💰 <b>Прибуток — Нумізматика</b>\n"]

    if sold:
        total_pnl = sum(
            ((c.sell_price or 0) - (c.cost_per_unit or 0)) * (c.quantity or 1)
            for c in sold
        )
        total_invested = sum((c.total_amount or 0) for c in sold)
        sign = "+" if total_pnl >= 0 else ""
        lines.append(
            f"📊 <b>Реалізований P&L:</b> <b>{sign}{total_pnl:,.2f} ₴</b>\n"
            f"   Вкладено (продані): {total_invested:,.2f} ₴  •  Угод: {len(sold)}\n"
        )

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
        lbl = f"🪙 {coin.name} ({coin.mint_year or '—'}) • {coin.quantity}шт. • {coin.cost_per_unit or 0:,.0f}₴/шт."
        keyboard.append([InlineKeyboardButton(lbl, callback_data=f"num_sell_{coin.id}")])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="numismatics")])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def handle_num_sell_selected(update: Update, context: CallbackContext):
    """Обрана монета — запитуємо ціну продажу."""
    query   = update.callback_query
    await query.answer()
    coin_id = int(query.data.replace("num_sell_", ""))

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session = Session()
        coin    = session.query(Numismatic).filter(Numismatic.id == coin_id).first()
        session.close()
    except Exception as e:
        logger.error(f"Coin sell select error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not coin:
        await query.edit_message_text("❌ Монету не знайдено.")
        return

    context.user_data["num_sell_coin_id"] = coin_id
    context.user_data["num_profit_step"]  = "sell_price"

    await query.edit_message_text(
        f"🪙 <b>{coin.name}</b>  •  {coin.mint_year or '—'} р.\n"
        f"💲 {coin.nominal or '—'}  •  {coin.metal_name or '—'}\n"
        f"🛒 Кількість: {coin.quantity} шт.\n"
        f"📊 Собівартість: {coin.cost_per_unit or 0:,.2f} ₴/шт.\n\n"
        "💰 Введіть <b>ціну продажу за 1 шт.</b> у ₴:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Скасувати", callback_data="num_profit")
        ]]),
        parse_mode="HTML",
    )


async def handle_message_num_profit(update: Update, context: CallbackContext):
    """Отримуємо ціну продажу і зберігаємо."""
    if context.user_data.get("num_profit_step") != "sell_price":
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
        coin    = session.query(Numismatic).filter(Numismatic.id == coin_id).first()
        if coin:
            pnl             = (sell_price - (coin.cost_per_unit or 0)) * (coin.quantity or 1)
            coin.sell_price = sell_price
            coin.is_sold    = 1
            session.commit()
            name = coin.name
            qty  = coin.quantity
            cost = coin.cost_per_unit or 0
        session.close()
    except Exception as e:
        logger.error(f"Coin sell save error: {e}")
        await update.message.reply_text(f"❌ Помилка: {e}")
        return

    sign = "+" if pnl >= 0 else ""
    from handlers.numismatics.main_menu import get_numismatics_menu_keyboard
    await update.message.reply_text(
        f"✅ <b>Продано!</b>\n\n"
        f"🪙 {name}  •  {qty} шт.\n"
        f"📊 Собів.: {cost:,.2f} ₴ → Продано: {sell_price:,.2f} ₴/шт.\n"
        f"💰 P&L: <b>{sign}{pnl:,.2f} ₴</b>\n\n"
        "🏛 <b>Нумізматика</b> — оберіть дію:",
        reply_markup=get_numismatics_menu_keyboard(),
        parse_mode="HTML",
    )