"""
handlers/numismatics/add.py

Флоу КУПІВЛЯ:
  0.  operation_type — кнопки (купівля / продаж)
  1.  name          — назва монети
  2.  nominal       — номінал
  3.  metal_code    — позначення металу (au900...)
  4.  metal_name    — назва металу (золото...)
  5.  metal_weight  — маса чистого металу, г
  6.  mint_year     — рік карбування
  7.  mintage       — тираж, шт.
  8.  diameter      — діаметр, мм
  9.  date_issued   — дата введення в обіг (DD.MM.YYYY)
  10. price_per_unit — ціна 1 шт., ₴
  11. quantity      — кількість
  12. delivery_cost — сума доставки, ₴
  → автоматично: total_amount, cost_per_unit
  13. confirm

Флоу ПРОДАЖ:
  0.  operation_type — кнопки (купівля / продаж)
  1.  Вибір монети з портфелю (кнопки)
  2.  sell_price    — ціна продажу за 1 шт.
  3.  confirm
"""

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext


def _kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Скасувати", callback_data="num_add_cancel")
    ]])


def _kb_operation_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛒 Купівля", callback_data="num_op_buy"),
            InlineKeyboardButton("💸 Продаж",  callback_data="num_op_sell"),
        ],
        [InlineKeyboardButton("❌ Скасувати", callback_data="num_add_cancel")],
    ])


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


def _summary_buy(d: dict) -> str:
    total, cost = _calc(d)
    W = 18

    def row(icon: str, label: str, value: str) -> str:
        pad = W - len(label)
        return f"{icon} <code>{label}{' ' * max(pad, 1)}{value}</code>\n"

    return (
        "📋 <b>Перевірте дані монети (купівля):</b>\n\n"
        + row("🪙", "Назва:",           d.get("name", "—"))
        + row("💲", "Номінал:",         d.get("nominal", "—"))
        + row("⚗️",  "Метал (код):",    d.get("metal_code", "—"))
        + row("🥇", "Метал (назва):",   d.get("metal_name", "—"))
        + row("⚖️",  "Маса металу:",    f"{d.get('metal_weight', 0)} г")
        + row("📅", "Рік карбування:",  str(d.get("mint_year", "—")))
        + row("🔢", "Тираж:",           f"{d.get('mintage', 0):,} шт.")
        + row("📐", "Діаметр:",         f"{d.get('diameter', 0)} мм")
        + row("🗓", "Дата в обіг:",     d.get("date_issued", "—"))
        + "─" * 24 + "\n"
        + row("💵", "Ціна 1 шт.:",      f"{d.get('price_per_unit', 0):,.2f} ₴")
        + row("🔢", "Кількість:",        f"{d.get('quantity', 1)} шт.")
        + row("🚚", "Доставка:",         f"{d.get('delivery_cost', 0):,.2f} ₴")
        + "─" * 24 + "\n"
        + row("💼", "Загальна сума:",    f"{total:,.2f} ₴")
        + row("📊", "Собівартість 1шт.", f"{cost:,.2f} ₴")
    )


def _summary_sell(d: dict) -> str:
    W = 18

    def row(icon: str, label: str, value: str) -> str:
        pad = W - len(label)
        return f"{icon} <code>{label}{' ' * max(pad, 1)}{value}</code>\n"

    sell_price = d.get("sell_price", 0) or 0
    cost       = d.get("cost_per_unit", 0) or 0
    qty        = d.get("quantity", 1) or 1
    pnl        = (sell_price - cost) * qty

    return (
        "📋 <b>Перевірте дані продажу:</b>\n\n"
        + row("🪙", "Монета:",          d.get("name", "—"))
        + row("💲", "Номінал:",         d.get("nominal", "—"))
        + row("🔢", "Кількість:",       f"{qty} шт.")
        + row("📊", "Собівартість:",    f"{cost:,.2f} ₴/шт.")
        + "─" * 24 + "\n"
        + row("💸", "Ціна продажу:",    f"{sell_price:,.2f} ₴/шт.")
        + row("💰", "P&L:",             f"{pnl:+,.2f} ₴")
    )


# ── Entry ─────────────────────────────────────────────────────────────────────

async def start_numismatics_add(update: Update, context: CallbackContext):
    context.user_data.clear()
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏛 <b>Додати запис</b>\n\nОберіть тип операції:",
        reply_markup=_kb_operation_type(),
        parse_mode="HTML",
    )


# ── Operation type callbacks ──────────────────────────────────────────────────

async def handle_num_op_buy(update: Update, context: CallbackContext):
    """Обрано купівля — починаємо флоу купівлі."""
    query = update.callback_query
    await query.answer()
    context.user_data["operation_type"] = "купівля"
    context.user_data["num_step"]       = "name"
    await query.edit_message_text(
        "🛒 <b>Купівля монети</b>\n\n"
        "Крок 1/12 — Введіть <b>назву</b> монети:",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


async def handle_num_op_sell(update: Update, context: CallbackContext):
    """Обрано продаж — показуємо список монет з портфелю."""
    query = update.callback_query
    await query.answer()
    context.user_data["operation_type"] = "продаж"

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        from models import Numismatic
        session   = Session()
        all_coins = session.query(Numismatic).filter(Numismatic.is_sold == 0).all()
        session.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Sell coin list error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not all_coins:
        await query.edit_message_text(
            "💸 <b>Продаж монети</b>\n\n📭 Портфель порожній — немає монет для продажу.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="num_add_cancel")
            ]]),
            parse_mode="HTML",
        )
        return

    keyboard = []
    for coin in all_coins:
        lbl = f"🪙 {coin.name} ({coin.mint_year or '—'}) • {coin.quantity}шт. • {coin.cost_per_unit or 0:,.0f}₴/шт."
        keyboard.append([InlineKeyboardButton(lbl, callback_data=f"num_sell_select_{coin.id}")])
    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="num_add_cancel")])

    await query.edit_message_text(
        "💸 <b>Продаж монети</b>\n\nОберіть монету з портфелю:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def handle_num_sell_coin_selected(update: Update, context: CallbackContext):
    """Монету обрано — запитуємо ціну продажу."""
    query   = update.callback_query
    await query.answer()
    coin_id = int(query.data.replace("num_sell_select_", ""))

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        from models import Numismatic
        session = Session()
        coin    = session.query(Numismatic).filter(Numismatic.id == coin_id).first()
        session.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Sell coin select error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not coin:
        await query.edit_message_text("❌ Монету не знайдено.")
        return

    # Зберігаємо дані монети для summary
    context.user_data["sell_coin_id"]  = coin_id
    context.user_data["name"]          = coin.name
    context.user_data["nominal"]       = coin.nominal
    context.user_data["quantity"]      = coin.quantity
    context.user_data["cost_per_unit"] = coin.cost_per_unit
    context.user_data["num_step"]      = "sell_price"

    await query.edit_message_text(
        f"🪙 <b>{coin.name}</b>  •  {coin.mint_year or '—'} р.\n"
        f"💲 {coin.nominal or '—'}  •  {coin.metal_name or '—'}\n"
        f"🛒 Кількість: {coin.quantity} шт.\n"
        f"📊 Собівартість: {coin.cost_per_unit or 0:,.2f} ₴/шт.\n\n"
        "💸 Введіть <b>ціну продажу за 1 шт.</b> у ₴:",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Confirm / Cancel ──────────────────────────────────────────────────────────

async def handle_num_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = context.user_data.copy()
    context.user_data.clear()

    op = data.get("operation_type", "купівля")

    try:
        from models import Numismatic
        Session = context.bot_data.get('Session')
        if Session:
            session = Session()

            if op == "купівля":
                total, cost = _calc(data)
                coin = Numismatic(
                    operation_type = "купівля",
                    name           = data.get("name"),
                    nominal        = data.get("nominal"),
                    metal_code     = data.get("metal_code"),
                    metal_name     = data.get("metal_name"),
                    metal_weight   = data.get("metal_weight"),
                    mint_year      = data.get("mint_year"),
                    mintage        = data.get("mintage"),
                    diameter       = data.get("diameter"),
                    date_issued    = data.get("date_issued"),
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

            else:  # продаж
                coin_id    = data.get("sell_coin_id")
                sell_price = data.get("sell_price", 0)
                coin = session.query(Numismatic).filter(Numismatic.id == coin_id).first()
                if coin:
                    coin.sell_price     = sell_price
                    coin.is_sold        = 1
                    coin.operation_type = "продаж"

            session.commit()
            session.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Coin save error: {e}")

    from handlers.numismatics.main_menu import get_numismatics_menu_keyboard
    msg = "✅ <b>Купівлю збережено!</b>" if op == "купівля" else "✅ <b>Продаж збережено!</b>"
    await query.edit_message_text(
        f"{msg}\n\n🏛 <b>Нумізматика</b> — оберіть дію:",
        reply_markup=get_numismatics_menu_keyboard(),
        parse_mode="HTML",
    )


async def handle_num_cancel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    from handlers.numismatics.main_menu import get_numismatics_menu_keyboard
    await query.edit_message_text(
        "❌ Скасовано.\n\n🏛 <b>Нумізматика</b> — оберіть дію:",
        reply_markup=get_numismatics_menu_keyboard(),
        parse_mode="HTML",
    )


# ── Text message router ───────────────────────────────────────────────────────

STEPS = [
    # (поточний_крок,  поле_збереження,  питання_наступного_кроку,  наступний_крок)
    ("nominal",        "nominal",        "3/12 — Введіть <b>позначення металу</b> (напр. <code>au900</code>, <code>ag925</code>):",   "metal_code"),
    ("metal_code",     "metal_code",     "4/12 — Введіть <b>назву металу</b> (напр. <code>золото</code>, <code>срібло</code>):",      "metal_name"),
    ("metal_name",     "metal_name",     "5/12 — Введіть <b>масу чистого металу</b> у грамах (напр. <code>7.78</code>):",            "metal_weight"),
    ("metal_weight",   "metal_weight",   "6/12 — Введіть <b>рік карбування</b> (напр. <code>2023</code>):",                          "mint_year"),
    ("mint_year",      "mint_year",      "7/12 — Введіть <b>тираж</b> у штуках (напр. <code>5000</code>):",                          "mintage"),
    ("mintage",        "mintage",        "8/12 — Введіть <b>діаметр</b> у мм (напр. <code>38.6</code>):",                            "diameter"),
    ("diameter",       "diameter",       "9/12 — Введіть <b>дату введення в обіг</b> у форматі <code>ДД.ММ.РРРР</code> (напр. <code>27.06.2025</code>):", "date_issued"),
    ("date_issued",    "date_issued",    "10/12 — Введіть <b>ціну 1 шт.</b> у ₴ (напр. <code>12500</code>):",                        "price_per_unit"),
    ("price_per_unit", "price_per_unit", "11/12 — Введіть <b>кількість</b> (напр. <code>1</code>):",                                  "quantity"),
    ("quantity",       "quantity",       "12/12 — Введіть <b>суму доставки</b> у ₴ (або <code>0</code> якщо без доставки):",         "delivery_cost"),
    ("delivery_cost",  "delivery_cost",  None,                                                                                        None),
]

FLOAT_FIELDS = {"metal_weight", "diameter", "price_per_unit", "delivery_cost", "sell_price"}
INT_FIELDS   = {"mint_year", "mintage", "quantity"}
DATE_FIELDS  = {"date_issued"}


async def handle_message_numismatics(update: Update, context: CallbackContext):
    step = context.user_data.get("num_step")
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()

    # ── Флоу продажу: крок введення ціни ─────────────────────────────────────
    if step == "sell_price":
        try:
            sell_price = float(text.replace(",", ".").replace(" ", ""))
            if sell_price <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть коректну ціну (додатнє число):", reply_markup=_kb_cancel()
            )
            return
        context.user_data["sell_price"] = sell_price
        context.user_data["num_step"]   = "confirm"
        await update.message.reply_text(
            _summary_sell(context.user_data),
            reply_markup=_kb_confirm(),
            parse_mode="HTML",
        )
        return

    # ── Флоу купівлі ──────────────────────────────────────────────────────────
    current = next((s for s in STEPS if s[0] == step), None)

    if step == "name":
        if not text:
            await update.message.reply_text("⚠️ Назва не може бути порожньою:", reply_markup=_kb_cancel())
            return
        context.user_data["name"]     = text
        context.user_data["num_step"] = "nominal"
        await update.message.reply_text(
            f"✅ Назва: <b>{text}</b>\n\n"
            "2/12 — Введіть <b>номінал</b> монети (напр. <code>2 грн</code>):",
            reply_markup=_kb_cancel(), parse_mode="HTML",
        )
        return

    if current is None:
        return

    _, current_field, next_question, next_step = current

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

    elif current_field in DATE_FIELDS:
        try:
            datetime.strptime(text, "%d.%m.%Y")
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть дату у форматі <code>ДД.ММ.РРРР</code> (напр. <code>27.06.2025</code>):",
                reply_markup=_kb_cancel(), parse_mode="HTML",
            )
            return
        context.user_data[current_field] = text

    else:
        if not text:
            await update.message.reply_text("⚠️ Поле не може бути порожнім:", reply_markup=_kb_cancel())
            return
        context.user_data[current_field] = text

    if next_step is None:
        context.user_data["num_step"] = "confirm"
        await update.message.reply_text(
            _summary_buy(context.user_data),
            reply_markup=_kb_confirm(),
            parse_mode="HTML",
        )
        return

    context.user_data["num_step"] = next_step
    await update.message.reply_text(
        next_question,
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )