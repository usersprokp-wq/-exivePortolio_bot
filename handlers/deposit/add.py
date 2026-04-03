"""
handlers/deposit/add.py

Флоу:
  1. bank_name   — текст
  2. amount      — число
  3. currency    — кнопки UAH / USD / EUR
  4. rate        — текст (число)
  5. start_date  — кнопки «Сьогодні» або календар
  6. end_date    — календар (дата закриття)
  7. confirm     — підтвердження з розрахунками
"""

from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

TAX_RATE = 0.23

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
        [InlineKeyboardButton(f"📅 Сьогодні ({today})", callback_data=f"dep_start_{today}")],
        [InlineKeyboardButton("🗓 Вибрати дату",         callback_data="dep_start_calendar")],
        [InlineKeyboardButton("❌ Скасувати",            callback_data="deposit_add_cancel")],
    ])


def _kb_end_date() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗓 Вибрати дату закриття", callback_data="dep_end_calendar")],
        [InlineKeyboardButton("❌ Скасувати",              callback_data="deposit_add_cancel")],
    ])


def _kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Підтвердити", callback_data="deposit_add_confirm"),
        InlineKeyboardButton("❌ Скасувати",   callback_data="deposit_add_cancel"),
    ]])


# ── Calendar builder ──────────────────────────────────────────────────────────

def _build_calendar(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    """prefix = 'dep_start' або 'dep_end' — для різних callback."""
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    start_weekday = first_day.weekday()

    nav_row = [
        InlineKeyboardButton("◀️", callback_data=f"{prefix}_cal_prev_{year}_{month}"),
        InlineKeyboardButton(f"{UA_MONTHS[month]} ({month:02d}) {year}", callback_data="dep_cal_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"{prefix}_cal_next_{year}_{month}"),
    ]
    dow_row = [
        InlineKeyboardButton(d, callback_data="dep_cal_ignore")
        for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    ]

    day_buttons = [InlineKeyboardButton(" ", callback_data="dep_cal_ignore")] * start_weekday
    for day in range(1, last_day.day + 1):
        date_str = f"{day:02d}.{month:02d}.{year}"
        day_buttons.append(InlineKeyboardButton(str(day), callback_data=f"{prefix}_{date_str}"))

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


def _summary(d: dict) -> str:
    currency  = d.get("currency", "")
    s         = _sign(currency)
    amount    = d.get("amount", 0)
    rate      = d.get("rate", 0)
    term_days = d.get("term_days", 0)
    c         = _calc(amount, rate, term_days)

    W = 15

    def row(icon: str, label: str, value: str) -> str:
        pad = W - len(label)
        return f"{icon} <code>{label}{' ' * max(pad, 1)}{value}</code>\n"

    tax_label = f"Податок {int(TAX_RATE*100)}%:"

    return (
        "📋 <b>Перевірте дані депозиту:</b>\n\n"
        + row("🏦", "Банк:",         d.get("bank_name", "—"))
        + row("💵", "Сума:",         f"{amount:,.2f} {s}")
        + row("💱", "Валюта:",       currency)
        + row("📈", "Ставка:",       f"{rate}% річних")
        + row("📅", "Відкриття:",    d.get("start_date", "—"))
        + row("📅", "Закриття:",     d.get("end_date", "—"))
        + row("⏳", "Термін:",       f"{term_days} дн.")
        + "\n"
        + row("📉", "Чиста ставка:", f"{c['net_rate']:.2f}% річних")
        + row("📆", "Чист./місяць:", f"{c['net_per_month']:,.2f} {s}")
        + row("💰", "Чистий дохід:", f"{c['net_profit']:,.2f} {s}")
        + row("🏁", "На руки:",      f"{amount + c['net_profit']:,.2f} {s}")
        + "\n"
        + row("📊", "Валов. дохід:", f"{c['gross_profit']:,.2f} {s}")
        + row("🧾", tax_label,       f"{c['tax']:,.2f} {s}")
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


# ── START DATE callbacks ──────────────────────────────────────────────────────

async def handle_deposit_calendar_show(update: Update, context: CallbackContext):
    """dep_start_calendar — відкрити календар дати відкриття."""
    query = update.callback_query
    await query.answer()
    now = context.user_data.get("dep_start_cal_month", datetime.now())
    await query.edit_message_text(
        "🗓 <b>Виберіть дату відкриття:</b>",
        reply_markup=_build_calendar(now.year, now.month, "dep_start"),
        parse_mode="HTML",
    )


async def handle_deposit_calendar_nav(update: Update, context: CallbackContext):
    """Навігація по місяцях — і для start і для end."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # визначаємо prefix і напрямок
    if "dep_start_cal_prev_" in data:
        prefix = "dep_start"
        year, month = map(int, data.replace("dep_start_cal_prev_", "").split("_"))
        month -= 1
    elif "dep_start_cal_next_" in data:
        prefix = "dep_start"
        year, month = map(int, data.replace("dep_start_cal_next_", "").split("_"))
        month += 1
    elif "dep_end_cal_prev_" in data:
        prefix = "dep_end"
        year, month = map(int, data.replace("dep_end_cal_prev_", "").split("_"))
        month -= 1
    else:
        prefix = "dep_end"
        year, month = map(int, data.replace("dep_end_cal_next_", "").split("_"))
        month += 1

    if month < 1:
        month, year = 12, year - 1
    if month > 12:
        month, year = 1, year + 1

    cal_key = f"{prefix}_cal_month"
    context.user_data[cal_key] = datetime(year, month, 1)

    label = "відкриття" if prefix == "dep_start" else "закриття"
    await query.edit_message_text(
        f"🗓 <b>Виберіть дату {label}:</b>",
        reply_markup=_build_calendar(year, month, prefix),
        parse_mode="HTML",
    )


async def handle_deposit_start_selected(update: Update, context: CallbackContext):
    """dep_start_DD.MM.YYYY — дата відкриття обрана."""
    query = update.callback_query
    await query.answer()
    date_str = query.data.replace("dep_start_", "")
    context.user_data["start_date"]   = date_str
    context.user_data["deposit_step"] = "end_date"

    now = context.user_data.get("dep_end_cal_month", datetime.now())
    await query.edit_message_text(
        f"✅ Дата відкриття: <b>{date_str}</b>\n\n"
        "📅 Тепер виберіть дату <b>закриття</b> депозиту:",
        reply_markup=_build_calendar(now.year, now.month, "dep_end"),
        parse_mode="HTML",
    )


# ── END DATE callbacks ────────────────────────────────────────────────────────

async def handle_deposit_end_calendar_show(update: Update, context: CallbackContext):
    """dep_end_calendar — відкрити календар дати закриття."""
    query = update.callback_query
    await query.answer()
    now = context.user_data.get("dep_end_cal_month", datetime.now())
    await query.edit_message_text(
        "🗓 <b>Виберіть дату закриття:</b>",
        reply_markup=_build_calendar(now.year, now.month, "dep_end"),
        parse_mode="HTML",
    )


async def handle_deposit_end_selected(update: Update, context: CallbackContext):
    """dep_end_DD.MM.YYYY — дата закриття обрана."""
    query = update.callback_query
    await query.answer()
    date_str = query.data.replace("dep_end_", "")

    start_dt = datetime.strptime(context.user_data["start_date"], "%d.%m.%Y")
    end_dt   = datetime.strptime(date_str, "%d.%m.%Y")

    if end_dt <= start_dt:
        await query.answer("⚠️ Дата закриття має бути пізніше відкриття!", show_alert=True)
        return

    term_days = (end_dt - start_dt).days
    context.user_data["end_date"]     = date_str
    context.user_data["term_days"]    = term_days
    context.user_data["term_type"]    = "days"
    context.user_data["term_value"]   = term_days
    context.user_data["deposit_step"] = "contract"

    await query.edit_message_text(
        f"✅ Дата закриття: <b>{date_str}</b>  •  Термін: <b>{term_days} дн.</b>\n\n"
        "📄 Завантажте договір депозиту у форматі <b>PDF</b>\n"
        "або пропустіть цей крок:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭ Пропустити", callback_data="deposit_contract_skip")],
            [InlineKeyboardButton("❌ Скасувати",  callback_data="deposit_add_cancel")],
        ]),
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


# ── Text / Document message router ───────────────────────────────────────────

async def handle_message_deposit(update: Update, context: CallbackContext):
    step = context.user_data.get("deposit_step")

    # Крок contract — обробляємо документ
    if step == "contract":
        await handle_message_deposit_contract(update, context)
        return

    # Для решти кроків потрібен текст
    if not update.message.text:
        return
    text = update.message.text.strip()

    if step == "bank_name":
        context.user_data["bank_name"]    = text
        context.user_data["deposit_step"] = "amount"
        await update.message.reply_text(
            "💵 Введіть суму депозиту (напр. <code>50000</code>):",
            reply_markup=_kb_cancel(),
            parse_mode="HTML",
        )

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


# ── Contract callbacks ────────────────────────────────────────────────────────

async def handle_deposit_contract_skip(update: Update, context: CallbackContext):
    """Пропустити завантаження договору."""
    query = update.callback_query
    await query.answer()
    context.user_data["contract_file_id"] = None
    context.user_data["deposit_step"]     = "confirm"
    await query.edit_message_text(
        _summary(context.user_data),
        reply_markup=_kb_confirm(),
        parse_mode="HTML",
    )


async def handle_message_deposit_contract(update: Update, context: CallbackContext):
    """Отримує PDF файл договору."""
    doc = update.message.document

    if not doc:
        await update.message.reply_text(
            "⚠️ Надішліть файл у форматі <b>PDF</b> або натисніть «Пропустити»:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭ Пропустити", callback_data="deposit_contract_skip")],
                [InlineKeyboardButton("❌ Скасувати",  callback_data="deposit_add_cancel")],
            ]),
            parse_mode="HTML",
        )
        return

    if doc.mime_type != "application/pdf":
        await update.message.reply_text(
            "⚠️ Приймається тільки <b>PDF</b> файл. Спробуйте ще раз або пропустіть:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭ Пропустити", callback_data="deposit_contract_skip")],
                [InlineKeyboardButton("❌ Скасувати",  callback_data="deposit_add_cancel")],
            ]),
            parse_mode="HTML",
        )
        return

    context.user_data["contract_file_id"] = doc.file_id
    context.user_data["deposit_step"]     = "confirm"

    await update.message.reply_text(
        f"✅ Договір <b>{doc.file_name}</b> завантажено!\n\n"
        + _summary(context.user_data),
        reply_markup=_kb_confirm(),
        parse_mode="HTML",
    )


# ── Confirm ───────────────────────────────────────────────────────────────────

async def handle_deposit_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = context.user_data.copy()
    context.user_data.clear()

    try:
        from models import Deposit
        Session = context.bot_data.get('Session')
        if Session:
            c       = _calc(data.get('amount', 0), data.get('rate', 0), data.get('term_days', 0))
            # Якщо дата закриття вже минула — одразу закритий
            end_dt    = datetime.strptime(data.get('end_date', ''), "%d.%m.%Y")
            is_active = 1 if end_dt.date() >= datetime.now().date() else 0
            session = Session()
            deposit = Deposit(
                bank_name        = data.get('bank_name'),
                amount           = data.get('amount'),
                currency         = data.get('currency'),
                interest_rate    = data.get('rate'),
                start_date       = data.get('start_date'),
                end_date         = data.get('end_date'),
                term_days        = data.get('term_days'),
                term_type        = data.get('term_type', 'days'),
                term_value       = data.get('term_value', data.get('term_days')),
                gross_profit     = round(c['gross_profit'], 2),
                tax_amount       = round(c['tax'], 2),
                net_profit       = round(c['net_profit'], 2),
                net_per_month    = round(c['net_per_month'], 2),
                is_active        = is_active,
                contract_file_id = data.get('contract_file_id'),
                created_at       = datetime.now().isoformat(),
            )
            session.add(deposit)
            session.commit()
            session.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Deposit save error: {e}")

    from handlers.deposit.main_menu import get_deposit_menu_keyboard
    await query.edit_message_text(
        "✅ <b>Депозит збережено!</b>\n\n"
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