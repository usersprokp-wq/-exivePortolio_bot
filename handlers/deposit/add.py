"""
handlers/deposit/add.py
Покрокове додавання депозиту через context.user_data.

Флоу:
  1. bank_name    — текст
  2. amount       — число
  3. currency     — кнопки UAH / USD / EUR
  4. rate         — текст (число)
  5. start_date   — кнопки «Сьогодні» або inline-календар
  6. term_type    — кнопки «Дні» або «Місяці»
  7. term_value   — текст (число), end_date розраховується автоматично
  8. confirm      — підтвердження з розрахунками
"""

from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

TAX_RATE = 0.23  # 23% від суми прибутку

UA_MONTHS = {
    1: "Січень",  2: "Лютий",    3: "Березень", 4: "Квітень",
    5: "Травень", 6: "Червень",  7: "Липень",   8: "Серпень",
    9: "Вересень",10: "Жовтень", 11: "Листопад",12: "Грудень",
}


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Скасувати", callback_data="deposit_add_cancel")
    ]])


def _kb_currency() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("₴ UAH", callback_data="deposit_currency_UAH"),
            InlineKeyboardButton("$ USD", callback_data="deposit_currency_USD"),
            InlineKeyboardButton("€ EUR", callback_data="deposit_currency_EUR"),
        ],
        [InlineKeyboardButton("❌ Скасувати", callback_data="deposit_add_cancel")],
    ])


def _kb_start_date() -> InlineKeyboardMarkup:
    today = datetime.now().strftime("%d.%m.%Y")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📅 Сьогодні ({today})", callback_data=f"dep_date_{today}")],
        [InlineKeyboardButton("🗓 Вибрати дату",         callback_data="dep_date_calendar")],
        [InlineKeyboardButton("❌ Скасувати",            callback_data="deposit_add_cancel")],
    ])


def _kb_term_type() -> InlineKeyboardMarkup:
    """Вибір одиниці терміну: дні або місяці."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📆 Дні",    callback_data="dep_term_days"),
            InlineKeyboardButton("🗓 Місяці", callback_data="dep_term_months"),
        ],
        [InlineKeyboardButton("❌ Скасувати", callback_data="deposit_add_cancel")],
    ])


def _kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Підтвердити", callback_data="deposit_add_confirm"),
        InlineKeyboardButton("❌ Скасувати",   callback_data="deposit_add_cancel"),
    ]])


# ── Calendar builder ──────────────────────────────────────────────────────────

def _build_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    start_weekday = first_day.weekday()

    nav_row = [
        InlineKeyboardButton("◀️", callback_data=f"dep_cal_prev_{year}_{month}"),
        InlineKeyboardButton(f"{UA_MONTHS[month]} {year}", callback_data="dep_cal_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"dep_cal_next_{year}_{month}"),
    ]
    dow_row = [
        InlineKeyboardButton(d, callback_data="dep_cal_ignore")
        for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    ]

    day_buttons = [InlineKeyboardButton(" ", callback_data="dep_cal_ignore")] * start_weekday
    for day in range(1, last_day.day + 1):
        date_str = f"{day:02d}.{month:02d}.{year}"
        day_buttons.append(InlineKeyboardButton(str(day), callback_data=f"dep_date_{date_str}"))

    rows = [day_buttons[i:i+7] for i in range(0, len(day_buttons), 7)]
    keyboard = [nav_row, dow_row] + rows
    keyboard.append([InlineKeyboardButton("❌ Скасувати", callback_data="deposit_add_cancel")])
    return InlineKeyboardMarkup(keyboard)


# ── Calculations ──────────────────────────────────────────────────────────────

def _calc(amount: float, rate: float, term_days: int) -> dict:
    gross_profit  = amount * (rate / 100) * (term_days / 365)
    tax           = gross_profit * TAX_RATE
    net_profit    = gross_profit - tax
    net_rate      = rate * (1 - TAX_RATE)
    months        = term_days / 30.44
    net_per_month = net_profit / months if months > 0 else 0
    return {
        "gross_profit":  gross_profit,
        "tax":           tax,
        "net_profit":    net_profit,
        "net_rate":      net_rate,
        "net_per_month": net_per_month,
    }


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _fmt_term(term_days: int, term_type: str, term_value: int) -> str:
    """Відображення терміну: '90 днів' або '3 місяці (91 дн.)'."""
    if term_type == "months":
        return f"{term_value} міс. ({term_days} дн.)"
    return f"{term_days} дн."


def _summary(d: dict) -> str:
    currency   = d.get("currency", "")
    s          = _sign(currency)
    amount     = d.get("amount", 0)
    rate       = d.get("rate", 0)
    term_days  = d.get("term_days", 0)
    term_type  = d.get("term_type", "days")
    term_value = d.get("term_value", term_days)
    c          = _calc(amount, rate, term_days)

    # Вирівнювання через пробіли — використовуємо моноширний шрифт через <code>
    # Але Telegram HTML не підтримує таблиці, тому вирівнюємо вручну табуляцією
    # через однакову довжину міток + жирне значення
    W = 17  # ширина лівої колонки (символів)

    def row(icon: str, label: str, value: str) -> str:
        # Доповнюємо label пробілами до W символів
        pad = W - len(label)
        return f"{icon} {label}{'·' * max(pad, 1)}  <b>{value}</b>\n"

    return (
        "📋 <b>Перевірте дані депозиту:</b>\n\n"
        + row("🏦", "Банк:",        d.get("bank_name", "—"))
        + row("💵", "Сума:",        f"{amount:,.2f} {s}")
        + row("💱", "Валюта:",      currency)
        + row("📈", "Ставка:",      f"{rate}% річних")
        + row("📅", "Відкриття:",   d.get("start_date", "—"))
        + row("📅", "Закриття:",    d.get("end_date", "—"))
        + row("⏳", "Термін:",      _fmt_term(term_days, term_type, term_value))
        + "\n"
        + row("📉", "Чиста ставка:", f"{c['net_rate']:.2f}% річних")
        + row("📆", "Чист./місяць:", f"{c['net_per_month']:,.2f} {s}")
        + row("💰", "Чистий дохід:", f"{c['net_profit']:,.2f} {s}")
        + row("🏁", "На руки:",      f"{amount + c['net_profit']:,.2f} {s}")
        + "\n"
        + row("📊", "Валов. дохід:", f"{c['gross_profit']:,.2f} {s}")
        + row("🧾", f"Податок {int(TAX_RATE*100)}%:", f"{c['tax']:,.2f} {s}")
    )


# ── Step 0: entry ─────────────────────────────────────────────────────────────

async def start_deposit_add(update: Update, context: CallbackContext):
    context.user_data.clear()
    context.user_data["deposit_step"] = "bank_name"
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏦 <b>Додати депозит</b>\n\n"
        "Введіть назву банку або фінансової установи:",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Calendar callbacks ────────────────────────────────────────────────────────

async def handle_deposit_calendar_show(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    now = context.user_data.get("dep_calendar_month", datetime.now())
    await query.edit_message_text(
        "🗓 <b>Виберіть дату відкриття:</b>",
        reply_markup=_build_calendar(now.year, now.month),
        parse_mode="HTML",
    )


async def handle_deposit_calendar_nav(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("dep_cal_prev_"):
        year, month = map(int, data.replace("dep_cal_prev_", "").split("_"))
        month -= 1
        if month < 1:
            month, year = 12, year - 1
    else:
        year, month = map(int, data.replace("dep_cal_next_", "").split("_"))
        month += 1
        if month > 12:
            month, year = 1, year + 1

    context.user_data["dep_calendar_month"] = datetime(year, month, 1)
    await query.edit_message_text(
        "🗓 <b>Виберіть дату відкриття:</b>",
        reply_markup=_build_calendar(year, month),
        parse_mode="HTML",
    )


async def handle_deposit_date_selected(update: Update, context: CallbackContext):
    """dep_date_DD.MM.YYYY — дата відкриття обрана, питаємо одиницю терміну."""
    query = update.callback_query
    await query.answer()
    date_str = query.data.replace("dep_date_", "")
    context.user_data["start_date"]   = date_str
    context.user_data["deposit_step"] = "term_type"
    await query.edit_message_text(
        f"✅ Дата відкриття: <b>{date_str}</b>\n\n"
        "⏳ Вкажіть термін депозиту у:",
        reply_markup=_kb_term_type(),
        parse_mode="HTML",
    )


# ── Term type callbacks ───────────────────────────────────────────────────────

async def handle_deposit_term_type(update: Update, context: CallbackContext):
    """dep_term_days або dep_term_months — вибір одиниці терміну."""
    query = update.callback_query
    await query.answer()

    term_type = "days" if query.data == "dep_term_days" else "months"
    context.user_data["term_type"]    = term_type
    context.user_data["deposit_step"] = "term_value"

    if term_type == "days":
        hint = "днях (напр. <code>30</code>, <code>90</code>, <code>180</code>, <code>365</code>)"
    else:
        hint = "місяцях (напр. <code>1</code>, <code>3</code>, <code>6</code>, <code>12</code>)"

    await query.edit_message_text(
        f"✅ Дата відкриття: <b>{context.user_data['start_date']}</b>\n\n"
        f"⏳ Введіть термін у {hint}:",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Currency callback ─────────────────────────────────────────────────────────

async def handle_deposit_currency(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    currency = query.data.replace("deposit_currency_", "")
    context.user_data["currency"]     = currency
    context.user_data["deposit_step"] = "rate"
    await query.edit_message_text(
        f"✅ Валюта: <b>{currency}</b>\n\n"
        "📈 Введіть відсоткову ставку річних (напр. <code>15.5</code>):",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Text message router ───────────────────────────────────────────────────────

async def handle_message_deposit(update: Update, context: CallbackContext):
    step = context.user_data.get("deposit_step")
    text = update.message.text.strip()

    # ── bank_name ──────────────────────────────────────────────────────────────
    if step == "bank_name":
        context.user_data["bank_name"]    = text
        context.user_data["deposit_step"] = "amount"
        await update.message.reply_text(
            "💵 Введіть суму депозиту (напр. <code>50000</code>):",
            reply_markup=_kb_cancel(),
            parse_mode="HTML",
        )

    # ── amount ─────────────────────────────────────────────────────────────────
    elif step == "amount":
        try:
            amount = float(text.replace(",", ".").replace(" ", ""))
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Введіть коректну суму (додатнє число):", reply_markup=_kb_cancel())
            return
        context.user_data["amount"]       = amount
        context.user_data["deposit_step"] = "currency"
        await update.message.reply_text("💱 Оберіть валюту депозиту:", reply_markup=_kb_currency())

    # ── rate ───────────────────────────────────────────────────────────────────
    elif step == "rate":
        try:
            rate = float(text.replace(",", "."))
            if not (0 < rate <= 100):
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть коректну ставку від 0 до 100 (напр. <code>15.5</code>):",
                reply_markup=_kb_cancel(),
                parse_mode="HTML",
            )
            return
        context.user_data["rate"]         = rate
        context.user_data["deposit_step"] = "start_date"
        await update.message.reply_text(
            f"✅ Ставка: <b>{rate}%</b>\n\n"
            "📅 Виберіть дату відкриття депозиту:",
            reply_markup=_kb_start_date(),
            parse_mode="HTML",
        )

    # ── term_value (дні або місяці) ────────────────────────────────────────────
    elif step == "term_value":
        term_type = context.user_data.get("term_type", "days")
        try:
            term_value = int(text.replace(" ", ""))
            if term_value <= 0:
                raise ValueError
        except ValueError:
            unit = "днів" if term_type == "days" else "місяців"
            await update.message.reply_text(
                f"⚠️ Введіть ціле число {unit} більше 0:",
                reply_markup=_kb_cancel(),
            )
            return

        start_dt = datetime.strptime(context.user_data["start_date"], "%d.%m.%Y")

        if term_type == "days":
            term_days = term_value
            end_dt    = start_dt + timedelta(days=term_days)
        else:
            # Місяці → точна дата через заміну місяця
            end_month = start_dt.month + term_value
            end_year  = start_dt.year + (end_month - 1) // 12
            end_month = (end_month - 1) % 12 + 1
            # Обробка кінця місяця (напр. 31 берез. + 1 міс. → 30 квіт.)
            import calendar
            max_day   = calendar.monthrange(end_year, end_month)[1]
            end_day   = min(start_dt.day, max_day)
            end_dt    = datetime(end_year, end_month, end_day)
            term_days = (end_dt - start_dt).days

        end_date_str = end_dt.strftime("%d.%m.%Y")

        context.user_data["term_value"]   = term_value
        context.user_data["term_days"]    = term_days
        context.user_data["end_date"]     = end_date_str
        context.user_data["deposit_step"] = "confirm"

        await update.message.reply_text(
            _summary(context.user_data),
            reply_markup=_kb_confirm(),
            parse_mode="HTML",
        )


# ── Confirm ───────────────────────────────────────────────────────────────────

async def handle_deposit_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = context.user_data.copy()
    context.user_data.clear()

    # TODO: зберегти до БД / Google Sheets
    # session = context.bot_data['Session']()
    # deposit = Deposit(user_id=query.from_user.id, **data)
    # session.add(deposit); session.commit(); session.close()

    from handlers.deposit.main_menu import get_deposit_menu_keyboard
    await query.edit_message_text(
        f"✅ <b>Депозит збережено!</b>\n\n{_summary(data)}\n\n"
        "🏦 <b>Депозити</b> — оберіть дію:",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )


# ── Cancel ────────────────────────────────────────────────────────────────────

async def handle_deposit_cancel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    from handlers.deposit.main_menu import get_deposit_menu_keyboard
    await query.edit_message_text(
        "❌ Додавання скасовано.\n\n🏦 <b>Депозити</b> — оберіть дію:",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )