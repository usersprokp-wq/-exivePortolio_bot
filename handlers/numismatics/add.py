"""
handlers/numismatics/add.py

Флоу:
  1.  name          — назва монети
  2.  nominal       — номінал (текст, напр. "2 грн")
  3.  metal_code    — позначення металу (au900, ag925...)
  4.  metal_name    — назва металу (золото, срібло...)
  5.  metal_weight  — маса чистого металу, г
  6.  mint_year     — рік карбування
  7.  mintage       — тираж, шт.
  8.  diameter      — діаметр, мм
  9.  price_per_unit — ціна 1 шт., ₴
  10. quantity      — кількість
  11. delivery_cost — сума доставки, ₴
  → автоматично: total_amount, cost_per_unit
  12. confirm
"""

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext


def _kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Скасувати", callback_data="num_add_cancel")
    ]])


def _kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Підтвердити", callback_data="num_add_confirm"),
        InlineKeyboardButton("❌ Скасувати",   callback_data="num_add_cancel"),
    ]])


def _calc(d: dict) -> tuple[float, float]:
    """Повертає (total_amount, cost_per_unit)."""
    price    = d.get("price_per_unit", 0) or 0
    qty      = d.get("quantity", 1) or 1
    delivery = d.get("delivery_cost", 0) or 0
    total    = price * qty + delivery
    cost     = total / qty if qty else 0
    return round(total, 2), round(cost, 2)


def _summary(d: dict) -> str:
    total, cost = _calc(d)
    W = 18

    def row(icon: str, label: str, value: str) -> str:
        pad = W - len(label)
        return f"{icon} <code>{label}{' ' * max(pad, 1)}{value}</code>\n"

    return (
        "📋 <b>Перевірте дані монети:</b>\n\n"
        + row("🪙", "Назва:",           d.get("name", "—"))
        + row("💲", "Номінал:",         d.get("nominal", "—"))
        + row("⚗️",  "Метал (код):",    d.get("metal_code", "—"))
        + row("🥇", "Метал (назва):",   d.get("metal_name", "—"))
        + row("⚖️",  "Маса металу:",    f"{d.get('metal_weight', 0)} г")
        + row("📅", "Рік карбування:",  str(d.get("mint_year", "—")))
        + row("🔢", "Тираж:",           f"{d.get('mintage', 0):,} шт.")
        + row("📐", "Діаметр:",         f"{d.get('diameter', 0)} мм")
        + "─" * 24 + "\n"
        + row("💵", "Ціна 1 шт.:",      f"{d.get('price_per_unit', 0):,.2f} ₴")
        + row("🔢", "Кількість:",        f"{d.get('quantity', 1)} шт.")
        + row("🚚", "Доставка:",         f"{d.get('delivery_cost', 0):,.2f} ₴")
        + "─" * 24 + "\n"
        + row("💼", "Загальна сума:",    f"{total:,.2f} ₴")
        + row("📊", "Собівартість 1шт.", f"{cost:,.2f} ₴")
    )


# ── Entry ─────────────────────────────────────────────────────────────────────

async def start_numismatics_add(update: Update, context: CallbackContext):
    context.user_data.clear()
    context.user_data["num_step"] = "name"
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏛 <b>Додати монету</b>\n\n"
        "Крок 1/11 — Введіть <b>назву</b> монети:",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Confirm / Cancel ──────────────────────────────────────────────────────────

async def handle_num_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = context.user_data.copy()
    context.user_data.clear()

    total, cost = _calc(data)

    try:
        from models import Numismatic
        Session = context.bot_data.get('Session')
        if Session:
            session = Session()
            coin = Numismatic(
                name           = data.get("name"),
                nominal        = data.get("nominal"),
                metal_code     = data.get("metal_code"),
                metal_name     = data.get("metal_name"),
                metal_weight   = data.get("metal_weight"),
                mint_year      = data.get("mint_year"),
                mintage        = data.get("mintage"),
                diameter       = data.get("diameter"),
                price_per_unit = data.get("price_per_unit"),
                quantity       = data.get("quantity"),
                delivery_cost  = data.get("delivery_cost", 0),
                total_amount   = total,
                cost_per_unit  = cost,
                sell_price     = None,
                is_sold        = 0,
                created_at     = datetime.now().isoformat(),
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

STEPS = [
    ("name",           "2/11 — Введіть <b>номінал</b> монети (напр. <code>2 грн</code>):",                          "nominal"),
    ("nominal",        "3/11 — Введіть <b>позначення металу</b> (напр. <code>au900</code>, <code>ag925</code>):",   "metal_code"),
    ("metal_code",     "4/11 — Введіть <b>назву металу</b> (напр. <code>золото</code>, <code>срібло</code>):",      "metal_name"),
    ("metal_name",     "5/11 — Введіть <b>масу чистого металу</b> у грамах (напр. <code>7.78</code>):",            "metal_weight"),
    ("metal_weight",   "6/11 — Введіть <b>рік карбування</b> (напр. <code>2023</code>):",                          "mint_year"),
    ("mint_year",      "7/11 — Введіть <b>тираж</b> у штуках (напр. <code>5000</code>):",                          "mintage"),
    ("mintage",        "8/11 — Введіть <b>діаметр</b> у мм (напр. <code>38.6</code>):",                            "diameter"),
    ("diameter",       "9/11 — Введіть <b>ціну 1 шт.</b> у ₴ (напр. <code>12500</code>):",                         "price_per_unit"),
    ("price_per_unit", "10/11 — Введіть <b>кількість</b> (напр. <code>1</code>):",                                  "quantity"),
    ("quantity",       "11/11 — Введіть <b>суму доставки</b> у ₴ (або <code>0</code> якщо без доставки):",         "delivery_cost"),
]

# Поля що мають бути числами (float)
FLOAT_FIELDS  = {"metal_weight", "diameter", "price_per_unit", "delivery_cost"}
# Поля що мають бути цілими числами
INT_FIELDS    = {"mint_year", "mintage", "quantity"}


async def handle_message_numismatics(update: Update, context: CallbackContext):
    step = context.user_data.get("num_step")
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()

    # Знаходимо поточний крок у STEPS
    current = next((s for s in STEPS if s[0] == step), None)

    if step == "name":
        if not text:
            await update.message.reply_text("⚠️ Назва не може бути порожньою:", reply_markup=_kb_cancel())
            return
        context.user_data["name"]     = text
        context.user_data["num_step"] = "nominal"
        await update.message.reply_text(
            f"✅ Назва: <b>{text}</b>\n\n"
            "2/11 — Введіть <b>номінал</b> монети (напр. <code>2 грн</code>):",
            reply_markup=_kb_cancel(), parse_mode="HTML",
        )
        return

    if current is None:
        return

    # Визначаємо поточне поле для збереження
    current_field = current[2]  # key у user_data
    next_step_idx = STEPS.index(current) + 1

    # Валідація числових полів
    if current_field in FLOAT_FIELDS:
        try:
            value = float(text.replace(",", ".").replace(" ", ""))
            if value < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть коректне число (≥ 0):", reply_markup=_kb_cancel()
            )
            return
        context.user_data[current_field] = value

    elif current_field in INT_FIELDS:
        try:
            value = int(text.replace(" ", ""))
            if value <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть коректне ціле число (> 0):", reply_markup=_kb_cancel()
            )
            return
        context.user_data[current_field] = value

    else:
        # Текстові поля
        if not text:
            await update.message.reply_text("⚠️ Поле не може бути порожнім:", reply_markup=_kb_cancel())
            return
        context.user_data[current_field] = text

    # Останній крок — показуємо підтвердження
    if next_step_idx >= len(STEPS):
        total, cost = _calc(context.user_data)
        context.user_data["num_step"] = "confirm"
        await update.message.reply_text(
            _summary(context.user_data),
            reply_markup=_kb_confirm(),
            parse_mode="HTML",
        )
        return

    # Переходимо до наступного кроку
    next_step = STEPS[next_step_idx]
    context.user_data["num_step"] = next_step[0]
    await update.message.reply_text(
        next_step[1],
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )