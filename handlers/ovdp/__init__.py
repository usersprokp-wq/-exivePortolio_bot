"""
Модуль для роботи з ОВДП (облігаціями внутрішньої державної позики)
"""
from telegram import Update
from telegram.ext import CallbackContext

# Головне меню
from .main_menu import show_ovdp_menu

# Додавання операцій
from .add_operations import (
    start_bond_add,
    handle_date_selection,
    show_bond_calendar,
    handle_bond_calendar_navigation,
    show_sell_bond_selection,
    handle_sell_bond_selected,    # 👈 ЦЕ ВАЖЛИВО!
    handle_message_ovdp,
    save_bond_sell,
    save_bond,
)

# Список операцій
from .list_operations import show_bonds_list

# Портфель
from .portfolio import (
    show_portfolio,
    update_balance_platform_selection,
)

# Прибутки
from .profit import (
    show_profit,
    write_off_profit,
)

# PnL
from .pnl import show_pnl_portfolio

# Статистика
from .statistics import show_statistics

# Синхронізація
from .sync import sync_bonds_from_sheets


async def handle_balance_platform_selection(update: Update, context: CallbackContext):
    """Обробка вибору платформи для оновлення залишку"""
    query = update.callback_query
    await query.answer()
    
    # Отримуємо платформу з callback_data
    platform = query.data.replace('ovdp_balance_platform_', '').upper()
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    await query.edit_message_text(
        f"🔄 *Оновлення залишку для {platform}*\n\n"
        f"⏳ Функція в розробці...\n\n"
        f"Тут буде логіка отримання актуального залишку з {platform}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад до портфеля", callback_data='ovdp_portfolio')
        ]]),
        parse_mode='Markdown'
    )


__all__ = [
    # Головне меню
    'show_ovdp_menu',
    
    # Додавання операцій
    'start_bond_add',
    'handle_date_selection',
    'show_bond_calendar',
    'handle_bond_calendar_navigation',
    'show_sell_bond_selection',
    'handle_sell_bond_selected',    # 👈 І ТУТ ТЕЖЕ!
    'handle_message_ovdp',
    'save_bond_sell',
    'save_bond',
    
    # Список
    'show_bonds_list',
    
    # Портфель
    'show_portfolio',
    'update_balance_platform_selection',
    
    # Прибутки
    'show_profit',
    'write_off_profit',
    
    # PnL
    'show_pnl_portfolio',
    
    # Статистика
    'show_statistics',
    
    # Синхронізація
    'sync_bonds_from_sheets',
    
    # Оновлення залишку
    'handle_balance_platform_selection',  # 👈 ДОДАНО!
]