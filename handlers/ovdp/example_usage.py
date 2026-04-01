"""
Приклад інтеграції модуля ОВДП в основний бот
"""
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

# Імпортуємо функції з модуля ovdp
from ovdp import (
    # Головне меню
    show_ovdp_menu,
    
    # Додавання операцій
    start_bond_add,
    handle_date_selection,
    show_bond_calendar,
    handle_bond_calendar_navigation,
    show_sell_bond_selection,
    
    # Список
    show_bonds_list,
    
    # Портфель
    show_portfolio,
    update_balance_platform_selection,
    
    # Прибутки
    show_profit,
    write_off_profit,
    
    # PnL
    show_pnl_portfolio,
    
    # Статистика
    show_statistics,
)


def register_ovdp_handlers(application: Application):
    """
    Реєструє всі обробники для модуля ОВДП
    
    Args:
        application: Telegram Application instance
    """
    
    # ═══════════════════════════════════════════════════════════
    # ГОЛОВНЕ МЕНЮ
    # ═══════════════════════════════════════════════════════════
    application.add_handler(
        CallbackQueryHandler(show_ovdp_menu, pattern='^ovdp$')
    )
    
    # ═══════════════════════════════════════════════════════════
    # ДОДАВАННЯ ОПЕРАЦІЙ
    # ═══════════════════════════════════════════════════════════
    
    # Старт додавання
    application.add_handler(
        CallbackQueryHandler(start_bond_add, pattern='^ovdp_add$')
    )
    
    # Вибір дати
    application.add_handler(
        CallbackQueryHandler(handle_date_selection, pattern='^date_')
    )
    
    # Навігація по календарю
    application.add_handler(
        CallbackQueryHandler(handle_bond_calendar_navigation, pattern='^cal_(prev|next)_')
    )
    
    # Вибір типу операції (купівля/продаж)
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: handle_operation_type_selection(u, c, 'buy'),
            pattern='^bond_buy$'
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            show_sell_bond_selection,
            pattern='^bond_sell$'
        )
    )
    
    # Вибір облігації для продажу
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: handle_sell_selected(u, c),
            pattern='^sell_bond_'
        )
    )
    
    # Вибір платформи
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: handle_platform_selection(u, c, 'ICU'),
            pattern='^platform_icu$'
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: handle_platform_selection(u, c, 'SENSBANK'),
            pattern='^platform_sensbank$'
        )
    )
    
    # ═══════════════════════════════════════════════════════════
    # СПИСОК ОПЕРАЦІЙ
    # ═══════════════════════════════════════════════════════════
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: show_bonds_list(u, c, 1),
            pattern='^ovdp_list$'
        )
    )
    
    # Пагінація списку
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: handle_bonds_list_pagination(u, c),
            pattern='^bonds_list_page_'
        )
    )
    
    # ═══════════════════════════════════════════════════════════
    # ПОРТФЕЛЬ
    # ═══════════════════════════════════════════════════════════
    
    # Показ всього портфеля
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: show_portfolio(u, c),
            pattern='^ovdp_portfolio$'
        )
    )
    
    # Портфель по платформах
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: show_portfolio(u, c, 'ICU'),
            pattern='^portfolio_icu$'
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: show_portfolio(u, c, 'SENSBANK'),
            pattern='^portfolio_sensbank$'
        )
    )
    
    # Оновлення залишків
    application.add_handler(
        CallbackQueryHandler(
            update_balance_platform_selection,
            pattern='^ovdp_update_balance$'
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: handle_balance_platform(u, c, 'ICU'),
            pattern='^ovdp_balance_platform_icu$'
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            lambda u, c: handle_balance_platform(u, c, 'SENSBANK'),
            pattern='^ovdp_balance_platform_sensbank$'
        )
    )
    
    # ═══════════════════════════════════════════════════════════
    # ПРИБУТКИ
    # ═══════════════════════════════════════════════════════════
    application.add_handler(
        CallbackQueryHandler(show_profit, pattern='^ovdp_profit$')
    )
    application.add_handler(
        CallbackQueryHandler(write_off_profit, pattern='^write_off_profit$')
    )
    
    # ═══════════════════════════════════════════════════════════
    # PNL
    # ═══════════════════════════════════════════════════════════
    application.add_handler(
        CallbackQueryHandler(show_pnl_portfolio, pattern='^pnl_portfolio$')
    )
    
    # ═══════════════════════════════════════════════════════════
    # СТАТИСТИКА
    # ═══════════════════════════════════════════════════════════
    application.add_handler(
        CallbackQueryHandler(show_statistics, pattern='^ovdp_stats$')
    )
    
    # ═══════════════════════════════════════════════════════════
    # ОБРОБКА ТЕКСТОВИХ ПОВІДОМЛЕНЬ
    # ═══════════════════════════════════════════════════════════
    # TODO: Додати handle_message_ovdp для обробки введення даних
    # application.add_handler(
    #     MessageHandler(
    #         filters.TEXT & ~filters.COMMAND,
    #         handle_message_ovdp
    #     )
    # )


# Допоміжні функції (треба реалізувати):

async def handle_operation_type_selection(update, context, operation_type):
    """Обробка вибору типу операції"""
    # TODO: Реалізувати
    pass

async def handle_sell_selected(update, context):
    """Обробка вибору облігації для продажу"""
    # TODO: Реалізувати
    pass

async def handle_platform_selection(update, context, platform):
    """Обробка вибору платформи"""
    # TODO: Реалізувати
    pass

async def handle_bonds_list_pagination(update, context):
    """Обробка пагінації списку"""
    query = update.callback_query
    page = int(query.data.replace('bonds_list_page_', ''))
    await show_bonds_list(update, context, page)

async def handle_balance_platform(update, context, platform):
    """Обробка вибору платформи для оновлення залишку"""
    # TODO: Реалізувати
    pass


if __name__ == '__main__':
    print("Це приклад використання. Імпортуйте register_ovdp_handlers() у ваш основний бот.")
