"""
handlers/numismatics/add.py

Флоу:
  1. name      — назва монети
  2. year      — рік випуску
  3. quantity  — кількість
  4. currency  — кнопки UAH / USD / EUR
  5. buy_price — ціна купівлі за одиницю
  6. confirm   — підтвердження
"""

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Скасувати", callback_data="num_add_cancel")
    ]])


def _kb_currency() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("₴ UAH", callback_data="num_currency_UAH"),
            InlineKeyboardButton("$ USD", callback_data="num_currency_USD"),
            InlineKeyboardButton("€ EUR", callback_data="num_currency_EUR"),
        ],
        [InlineKeyboardButton("❌ Скасувати", callback_data="num_add_cancel")],
    ])


def _kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Підтвердити", callback_data="num_add_confirm"),
        InlineKeyboardButton("❌ Скасувати",   callback_data="num_add_cancel"),
    ]])


def _summary(d: dict) -> str:
    s         = _sign(d.get("currency", "UAH"))
    qty       = d.get("quantity", 1)
    buy_price = d.get("buy_price", 0)
    total     = buy_price * qty

    W = 16

    def row(icon: str, label: str, value: str) -> str:
        pad = W - len(label)
        return f"{icon} <code>{label}{' ' * max(pad, 1)}{value}</code>\n"

    return (
        "📋 <b>Перевірте дані монети:</b>\n\n"
        + row("🪙", "Назва:",         d.get("name", "—"))
        + row("📅", "Рік:",           str(d.get("year", "—")))
        + row("🔢", "Кількість:",     str(qty))
        + row("💱", "Валюта:",        d.get("currency", "—"))
        + row("💵", "Ціна (1 шт.):", f"{buy_price:,.2f} {s}")
        + row("💼", "Загалом:",       f"{total:,.2f} {s}")
    )


# ── Step 0: entry ─────────────────────────────────────────────────────────────

async def start_numismatics_add(update: Update, context: CallbackContext):
    context.user_data.clear()
    context.user_data["num_step"] = "name"
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏛 <b>Додати монету</b>\n\n"
        "Введіть назву монети:",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Currency callback ─────────────────────────────────────────────────────────

async def handle_num_currency(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = query.data.replace("num_currency_", "")
    context.user_data["currency"] = currency
    context.user_data["num_step"] = "buy_price"
    await query.edit_message_text(
        f"✅ Валюта: <b>{currency}</b>\n\n"
        "💵 Введіть ціну купівлі за одиницю (напр. <code>250.50</code>):",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Confirm ───────────────────────────────────────────────────────────────────

async def handle_num_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = context.user_data.copy()
    context.user_data.clear()

    try:
        from models import Numismatic as Coin
        Session = context.bot_data.get('Session')
        if Session:
            session = Session()
            coin = Coin(
                name       = data.get("name"),
                year       = data.get("year"),
                quantity   = data.get("quantity", 1),
                currency   = data.get("currency"),
                buy_price  = data.get("buy_price"),
                sell_price = None,
                is_sold    = 0,
                created_at = datetime.now().isoformat(),
            )
            session.add(coin)
            session.commit()
            session.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Coin save error: {e}")

    from handlers.numismatics.main_menu import get_numismatics_menu_keyboard
    await query.edit_message_text(
        "✅ <b>Монету збережено!</b>\n\n"
        "🏛 <b>Нумізматика</b> — оберіть дію:",
        reply_markup=get_numismatics_menu_keyboard(),
        parse_mode="HTML",
    )


# ── Cancel ────────────────────────────────────────────────────────────────────

async def handle_num_cancel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    from handlers.numismatics.main_menu import get_numismatics_menu_keyboard
    await query.edit_message_text(
        "❌ Додавання скасовано.\n\n🏛 <b>Нумізматика</b> — оберіть дію:",
        reply_markup=get_numismatics_menu_keyboard(),
        parse_mode="HTML",
    )


# ── Text message router ───────────────────────────────────────────────────────

async def handle_message_numismatics(update: Update, context: CallbackContext):
    step = context.user_data.get("num_step")
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()

    if step == "name":
        context.user_data["name"]     = text
        context.user_data["num_step"] = "year"
        await update.message.reply_text(
            f"✅ Назва: <b>{text}</b>\n\n"
            "📅 Введіть рік випуску монети (напр. <code>1990</code>):",
            reply_markup=_kb_cancel(),
            parse_mode="HTML",
        )

    elif step == "year":
        try:
            year = int(text)
            if not (1 <= year <= datetime.now().year):
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                f"⚠️ Введіть коректний рік (від 1 до {datetime.now().year}):",
                reply_markup=_kb_cancel(),
                parse_mode="HTML",
            )
            return
        context.user_data["year"]     = year
        context.user_data["num_step"] = "quantity"
        await update.message.reply_text(
            f"✅ Рік: <b>{year}</b>\n\n"
            "🔢 Введіть кількість монет (напр. <code>1</code>):",
            reply_markup=_kb_cancel(),
            parse_mode="HTML",
        )

    elif step == "quantity":
        try:
            qty = int(text)
            if qty <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть коректну кількість (ціле число > 0):",
                reply_markup=_kb_cancel(),
            )
            return
        context.user_data["quantity"] = qty
        context.user_data["num_step"] = "currency"
        await update.message.reply_text(
            f"✅ Кількість: <b>{qty} шт.</b>\n\n"
            "💱 Оберіть валюту:",
            reply_markup=_kb_currency(),
        )

    elif step == "buy_price":
        try:
            price = float(text.replace(",", ".").replace(" ", ""))
            if price <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть коректну ціну (додатнє число):",
                reply_markup=_kb_cancel(),
            )
            return
        context.user_data["buy_price"] = price
        context.user_data["num_step"]  = "confirm"
        await update.message.reply_text(
            _summary(context.user_data),
            reply_markup=_kb_confirm(),
            parse_mode="HTML",
        )