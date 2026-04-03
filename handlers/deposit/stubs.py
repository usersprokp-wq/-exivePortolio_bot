"""
Заглушки для розділів депозиту, які ще не реалізовані.
Кожна відповідає на свій callback і повертає меню.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

router = Router()

_STUBS = {
    "deposit:list":      ("📋", "Мої записи"),
    "deposit:portfolio": ("🏦", "Портфель"),
    "deposit:profit":    ("💰", "Прибуток"),
    "deposit:stats":     ("📊", "Статистика"),
}


def _register(cb_data: str, icon: str, label: str):
    @router.callback_query(F.data == cb_data)
    async def _handler(callback: CallbackQuery, state: FSMContext):
        from handlers.deposit.main_menu import get_deposit_menu_keyboard
        await callback.message.edit_text(
            f"{icon} <b>{label}</b>\n\n⏳ Розділ у розробці...",
            reply_markup=get_deposit_menu_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
    _handler.__name__ = f"stub_{cb_data.replace(':', '_')}"


for _cb, (_icon, _label) in _STUBS.items():
    _register(_cb, _icon, _label)