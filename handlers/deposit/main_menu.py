from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

router = Router()


def get_deposit_menu_keyboard() -> InlineKeyboardMarkup:
    """Головне меню розділу Депозит."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Додати запис", callback_data="deposit:add"),
            InlineKeyboardButton(text="📋 Мої записи",  callback_data="deposit:list"),
        ],
        [
            InlineKeyboardButton(text="🏦 Портфель",    callback_data="deposit:portfolio"),
            InlineKeyboardButton(text="💰 Прибуток",    callback_data="deposit:profit"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика",  callback_data="deposit:stats"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад",       callback_data="main_menu"),
        ],
    ])


@router.callback_query(F.data == "deposit")
async def deposit_menu(callback: CallbackQuery, state: FSMContext):
    """Відкриває головне меню депозитів."""
    await state.clear()
    await callback.message.edit_text(
        "🏦 <b>Депозити</b>\n\nОберіть дію:",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()