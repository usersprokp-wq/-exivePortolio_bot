from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import date

router = Router()


# ── FSM States ──────────────────────────────────────────────────────────────

class DepositAddStates(StatesGroup):
    waiting_bank_name   = State()   # Назва банку / установи
    waiting_amount      = State()   # Сума депозиту
    waiting_currency    = State()   # Валюта (UAH / USD / EUR …)
    waiting_rate        = State()   # Відсоткова ставка, %
    waiting_start_date  = State()   # Дата відкриття
    waiting_end_date    = State()   # Дата закриття
    waiting_confirm     = State()   # Підтвердження


# ── Keyboards ────────────────────────────────────────────────────────────────

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="deposit:add:cancel")]
    ])


def kb_currency() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="₴ UAH", callback_data="deposit:currency:UAH"),
            InlineKeyboardButton(text="$ USD", callback_data="deposit:currency:USD"),
            InlineKeyboardButton(text="€ EUR", callback_data="deposit:currency:EUR"),
        ],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="deposit:add:cancel")],
    ])


def kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Підтвердити", callback_data="deposit:add:confirm"),
            InlineKeyboardButton(text="❌ Скасувати",   callback_data="deposit:add:cancel"),
        ]
    ])


# ── Helpers ──────────────────────────────────────────────────────────────────

def format_summary(data: dict) -> str:
    return (
        "📋 <b>Перевірте дані депозиту:</b>\n\n"
        f"🏦 Банк: <b>{data.get('bank_name', '—')}</b>\n"
        f"💵 Сума: <b>{data.get('amount', '—')} {data.get('currency', '')}</b>\n"
        f"📈 Ставка: <b>{data.get('rate', '—')}% річних</b>\n"
        f"📅 Відкрито: <b>{data.get('start_date', '—')}</b>\n"
        f"📅 Закрито: <b>{data.get('end_date', '—')}</b>\n"
    )


def parse_date(text: str) -> str | None:
    """Приймає DD.MM.YYYY або YYYY-MM-DD, повертає YYYY-MM-DD або None."""
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return date.fromisoformat(
                __import__("datetime").datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            ).isoformat()
        except ValueError:
            continue
    return None


# ── Step 0: entry point ──────────────────────────────────────────────────────

@router.callback_query(F.data == "deposit:add")
async def deposit_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositAddStates.waiting_bank_name)
    await callback.message.edit_text(
        "🏦 <b>Додати депозит</b>\n\n"
        "Введіть назву банку або фінансової установи:",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step 1: bank name ────────────────────────────────────────────────────────

@router.message(DepositAddStates.waiting_bank_name)
async def deposit_add_bank(message: Message, state: FSMContext):
    await state.update_data(bank_name=message.text.strip())
    await state.set_state(DepositAddStates.waiting_amount)
    await message.answer(
        "💵 Введіть суму депозиту (тільки число, напр. <code>50000</code>):",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )


# ── Step 2: amount ───────────────────────────────────────────────────────────

@router.message(DepositAddStates.waiting_amount)
async def deposit_add_amount(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введіть коректну суму (додатнє число):", reply_markup=kb_cancel())
        return

    await state.update_data(amount=amount)
    await state.set_state(DepositAddStates.waiting_currency)
    await message.answer(
        "💱 Оберіть валюту депозиту:",
        reply_markup=kb_currency(),
    )


# ── Step 3: currency (inline button) ────────────────────────────────────────

@router.callback_query(F.data.startswith("deposit:currency:"))
async def deposit_add_currency(callback: CallbackQuery, state: FSMContext):
    currency = callback.data.split(":")[-1]  # UAH / USD / EUR
    await state.update_data(currency=currency)
    await state.set_state(DepositAddStates.waiting_rate)
    await callback.message.edit_text(
        f"✅ Валюта: <b>{currency}</b>\n\n"
        "📈 Введіть відсоткову ставку (річних, напр. <code>13.5</code>):",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step 4: rate ─────────────────────────────────────────────────────────────

@router.message(DepositAddStates.waiting_rate)
async def deposit_add_rate(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        rate = float(text)
        if not (0 < rate <= 100):
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введіть коректну ставку (від 0 до 100):", reply_markup=kb_cancel())
        return

    await state.update_data(rate=rate)
    await state.set_state(DepositAddStates.waiting_start_date)
    await message.answer(
        "📅 Введіть дату <b>відкриття</b> депозиту (формат ДД.ММ.РРРР):",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )


# ── Step 5: start date ───────────────────────────────────────────────────────

@router.message(DepositAddStates.waiting_start_date)
async def deposit_add_start_date(message: Message, state: FSMContext):
    parsed = parse_date(message.text)
    if not parsed:
        await message.answer(
            "⚠️ Невірний формат. Введіть дату у форматі <code>ДД.ММ.РРРР</code>:",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
        return

    await state.update_data(start_date=parsed)
    await state.set_state(DepositAddStates.waiting_end_date)
    await message.answer(
        "📅 Введіть дату <b>закриття</b> (завершення) депозиту (формат ДД.ММ.РРРР):",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )


# ── Step 6: end date ─────────────────────────────────────────────────────────

@router.message(DepositAddStates.waiting_end_date)
async def deposit_add_end_date(message: Message, state: FSMContext):
    parsed = parse_date(message.text)
    if not parsed:
        await message.answer(
            "⚠️ Невірний формат. Введіть дату у форматі <code>ДД.ММ.РРРР</code>:",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    if parsed <= data["start_date"]:
        await message.answer(
            "⚠️ Дата закриття має бути <b>пізніше</b> дати відкриття.",
            reply_markup=kb_cancel(),
            parse_mode="HTML",
        )
        return

    await state.update_data(end_date=parsed)
    await state.set_state(DepositAddStates.waiting_confirm)

    full_data = await state.get_data()
    await message.answer(
        format_summary(full_data),
        reply_markup=kb_confirm(),
        parse_mode="HTML",
    )


# ── Step 7: confirm ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "deposit:add:confirm")
async def deposit_add_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    # TODO: зберегти data до бази / Google Sheets
    # Приклад: await db.save_deposit(user_id=callback.from_user.id, **data)

    await callback.message.edit_text(
        f"✅ <b>Депозит збережено!</b>\n\n{format_summary(data)}",
        parse_mode="HTML",
    )
    await callback.answer("Збережено ✅")

    # Повертаємо в меню депозитів через 1.5 с (або одразу)
    from handlers.deposit.main_menu import get_deposit_menu_keyboard
    await callback.message.answer(
        "🏦 <b>Депозити</b>\n\nОберіть дію:",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )


# ── Cancel ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "deposit:add:cancel")
async def deposit_add_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from handlers.deposit.main_menu import get_deposit_menu_keyboard
    await callback.message.edit_text(
        "❌ Додавання скасовано.\n\n🏦 <b>Депозити</b> — оберіть дію:",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()