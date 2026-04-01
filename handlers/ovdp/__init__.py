"""
Модуль для роботи з ОВДП (облігаціями внутрішньої державної позики)
"""

# Головне меню
from .main_menu import show_ovdp_menu

# Додавання операцій
from .add_operations import (
    start_bond_add,
    handle_date_selection,
    show_bond_calendar,
    handle_bond_calendar_navigation,
    show_sell_bond_selection,
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

__all__ = [
    # Головне меню
    'show_ovdp_menu',
    
    # Додавання операцій
    'start_bond_add',
    'handle_date_selection',
    'show_bond_calendar',
    'handle_bond_calendar_navigation',
    'show_sell_bond_selection',
    
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
]
