"""
handlers/deposit/add.py
Покрокове додавання депозиту через context.user_data (аналог stock_step у stocks).
"""
from datetime import date as date_type
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext


# ── Keyboards ────────────────────────────────────────────────────────────────

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


def _kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Підтвердити", callback_data="deposit_add_confirm"),
        InlineKeyboardButton("❌ Скасувати",   callback_data="deposit_add_cancel"),
    ]])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _summary(d: dict) -> str:
    return (
        "📋 <b>Перевірте дані депозиту:</b>\n\n"
        f"🏦 Банк: <b>{d.get('bank_name', '—')}</b>\n"
        f"💵 Сума: <b>{d.get('amount', '—')} {d.get('currency', '')}</b>\n"
        f"📈 Ставка: <b>{d.get('rate', '—')}% річних</b>\n"
        f"📅 Відкрито: <b>{d.get('start_date', '—')}</b>\n"
        f"📅 Закрито: <b>{d.get('end_date', '—')}</b>\n"
    )


def _parse_date(text: str):
    """DD.MM.YYYY або YYYY-MM-DD → YYYY-MM-DD або None."""
    import datetime
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ── Step 0: entry ────────────────────────────────────────────────────────────

async def start_deposit_add(update: Update, context: CallbackContext):
    """Запускає флоу додавання депозиту."""
    context.user_data.clear()
    context.user_data['deposit_step'] = 'bank_name'

    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏦 <b>Додати депозит</b>\n\n"
        "Введіть назву банку або фінансової установи:",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Text message router (викликається з handle_message_unified) ──────────────

async def handle_message_deposit(update: Update, context: CallbackContext):
    """Обробляє текстові повідомлення для флоу депозиту."""
    step = context.user_data.get('deposit_step')
    text = update.message.text.strip()

    # ── bank_name ──
    if step == 'bank_name':
        context.user_data['bank_name'] = text
        context.user_data['deposit_step'] = 'amount'
        await update.message.reply_text(
            "💵 Введіть суму депозиту (тільки число, напр. <code>50000</code>):",
            reply_markup=_kb_cancel(),
            parse_mode="HTML",
        )

    # ── amount ──
    elif step == 'amount':
        try:
            amount = float(text.replace(",", "."))
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть коректну суму (додатнє число):",
                reply_markup=_kb_cancel(),
            )
            return
        context.user_data['amount'] = amount
        context.user_data['deposit_step'] = 'currency'
        await update.message.reply_text(
            "💱 Оберіть валюту депозиту:",
            reply_markup=_kb_currency(),
        )

    # ── rate ──
    elif step == 'rate':
        try:
            rate = float(text.replace(",", "."))
            if not (0 < rate <= 100):
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Введіть коректну ставку (від 0 до 100):",
                reply_markup=_kb_cancel(),
            )
            return
        context.user_data['rate'] = rate
        context.user_data['deposit_step'] = 'start_date'
        await update.message.reply_text(
            "📅 Введіть дату <b>відкриття</b> депозиту (формат ДД.ММ.РРРР):",
            reply_markup=_kb_cancel(),
            parse_mode="HTML",
        )

    # ── start_date ──
    elif step == 'start_date':
        parsed = _parse_date(text)
        if not parsed:
            await update.message.reply_text(
                "⚠️ Невірний формат. Введіть дату у форматі <code>ДД.ММ.РРРР</code>:",
                reply_markup=_kb_cancel(),
                parse_mode="HTML",
            )
            return
        context.user_data['start_date'] = parsed
        context.user_data['deposit_step'] = 'end_date'
        await update.message.reply_text(
            "📅 Введіть дату <b>закриття</b> депозиту (формат ДД.ММ.РРРР):",
            reply_markup=_kb_cancel(),
            parse_mode="HTML",
        )

    # ── end_date ──
    elif step == 'end_date':
        parsed = _parse_date(text)
        if not parsed:
            await update.message.reply_text(
                "⚠️ Невірний формат. Введіть дату у форматі <code>ДД.ММ.РРРР</code>:",
                reply_markup=_kb_cancel(),
                parse_mode="HTML",
            )
            return
        if parsed <= context.user_data.get('start_date', ''):
            await update.message.reply_text(
                "⚠️ Дата закриття має бути <b>пізніше</b> дати відкриття.",
                reply_markup=_kb_cancel(),
                parse_mode="HTML",
            )
            return
        context.user_data['end_date'] = parsed
        context.user_data['deposit_step'] = 'confirm'
        await update.message.reply_text(
            _summary(context.user_data),
            reply_markup=_kb_confirm(),
            parse_mode="HTML",
        )


# ── Currency callback ────────────────────────────────────────────────────────

async def handle_deposit_currency(update: Update, context: CallbackContext):
    """Обробляє вибір валюти (deposit_currency_UAH / USD / EUR)."""
    query = update.callback_query
    await query.answer()
    currency = query.data.replace("deposit_currency_", "")
    context.user_data['currency'] = currency
    context.user_data['deposit_step'] = 'rate'
    await query.edit_message_text(
        f"✅ Валюта: <b>{currency}</b>\n\n"
        "📈 Введіть відсоткову ставку (річних, напр. <code>13.5</code>):",
        reply_markup=_kb_cancel(),
        parse_mode="HTML",
    )


# ── Confirm ──────────────────────────────────────────────────────────────────

async def handle_deposit_confirm(update: Update, context: CallbackContext):
    """Зберігає депозит після підтвердження."""
    query = update.callback_query
    await query.answer()

    data = context.user_data.copy()
    context.user_data.clear()

    # TODO: зберегти до БД / Google Sheets
    # session = context.bot_data['Session']()
    # db_deposit = Deposit(user_id=query.from_user.id, **data)
    # session.add(db_deposit); session.commit(); session.close()

    from handlers.deposit.main_menu import get_deposit_menu_keyboard
    await query.edit_message_text(
        f"✅ <b>Депозит збережено!</b>\n\n{_summary(data)}\n\n"
        "🏦 <b>Депозити</b> — оберіть дію:",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )


# ── Cancel ───────────────────────────────────────────────────────────────────

async def handle_deposit_cancel(update: Update, context: CallbackContext):
    """Скасовує флоу і повертає в меню депозитів."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    from handlers.deposit.main_menu import get_deposit_menu_keyboard
    await query.edit_message_text(
        "❌ Додавання скасовано.\n\n🏦 <b>Депозити</b> — оберіть дію:",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )