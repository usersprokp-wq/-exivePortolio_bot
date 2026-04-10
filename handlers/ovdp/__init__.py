"""
Модуль для роботи з ОВДП (облігаціями внутрішньої державної позики)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    handle_sell_bond_selected,
    handle_message_ovdp,
    save_bond_sell,
    save_bond,
)

# Список операцій
from .list_operations import show_bonds_list, handle_bond_delete

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

    platform = query.data.replace('ovdp_balance_platform_', '').upper()

    context.user_data['ovdp_balance_platform'] = platform
    context.user_data['bond_step'] = 'ovdp_balance_amount'

    Session = context.bot_data.get('Session')
    current_amount = 0
    if Session:
        from models import BondPortfolio
        session = Session()
        ticker = f"{platform}uah"
        current = session.query(BondPortfolio).filter(BondPortfolio.bond_number == ticker).first()
        session.close()
        current_amount = current.total_amount if current else 0

    await query.edit_message_text(
        f"💵 *Залишок {platform}*\n\n"
        f"Поточний залишок: {current_amount:.2f} грн\n\n"
        f"Введіть нову суму залишку:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data='ovdp_update_balance')
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
    'handle_sell_bond_selected',
    'handle_message_ovdp',
    'save_bond_sell',
    'save_bond',

    # Список
    'show_bonds_list',
    'handle_bond_delete',

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
    'handle_balance_platform_selection',
]