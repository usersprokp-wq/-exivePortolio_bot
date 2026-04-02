import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from models import Base
from google_sheets import GoogleSheetsManager
from handlers.common import start, button_handler_main

# Імпортуємо обробники акцій (старі, не чіпаємо)
from handlers.stocks import button_handler_stocks, handle_message_stocks

# Імпортуємо НОВІ обробники ОВДП
from handlers.ovdp import (
    # Головне меню
    show_ovdp_menu,
    
    # Додавання
    start_bond_add,
    handle_date_selection,
    handle_bond_calendar_navigation,
    show_sell_bond_selection,
    handle_sell_bond_selected,
    handle_message_ovdp,
    save_bond,
    
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
    
    # Синхронізація
    sync_bonds_from_sheets,
)


load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Глобальна сесія
Session = None
sheets_manager = None


def initialize_database():
    """Ініціалізація БД"""
    global Session
    
    if not DATABASE_URL:
        logger.error("DATABASE_URL не знайдено")
        return False
    
    try:
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        logger.info("База даних підключена")
        return True
    except Exception as e:
        logger.error(f"Помилка підключення до БД: {e}")
        return False


def initialize_sheets():
    """Ініціалізація Google Sheets"""
    global sheets_manager
    
    try:
        sheets_manager = GoogleSheetsManager()
        logger.info("Google Sheets підключено")
        return True
    except Exception as e:
        logger.error(f"Google Sheets помилка: {e}")
        return False


async def post_init(app: Application):
    """Викликається після ініціалізації Application"""
    app.bot_data['sheets_manager'] = sheets_manager
    app.bot_data['Session'] = Session


# ═══════════════════════════════════════════════════════════
# ДОПОМІЖНІ ФУНКЦІЇ ДЛЯ ОВДП
# ═══════════════════════════════════════════════════════════

async def handle_operation_buy(update: Update, context: CallbackContext):
    """Обробка вибору купівлі"""
    context.user_data['bond_operation_type'] = 'купівля'
    context.user_data['bond_step'] = 'bond_number'
    await update.callback_query.edit_message_text(
        "🔢 Введіть номер облігації:",
        parse_mode='Markdown'
    )


async def handle_platform_buy(update: Update, context: CallbackContext, platform: str):
    """Обробка вибору платформи для купівлі"""
    context.user_data['platform'] = platform
    await save_bond(update, context)


# ═══════════════════════════════════════════════════════════
# РЕЄСТРАЦІЯ ОБРОБНИКІВ ОВДП
# ═══════════════════════════════════════════════════════════

def register_ovdp_handlers(application: Application):
    """Реєструє всі обробники ОВДП"""
    
    logger.info("Реєструємо обробники ОВДП...")
    
    # ───────────────────────────────────────────────────────
    # ГОЛОВНЕ МЕНЮ
    # ───────────────────────────────────────────────────────
    application.add_handler(CallbackQueryHandler(show_ovdp_menu, pattern='^ovdp$'))
    
    # ───────────────────────────────────────────────────────
    # ДОДАВАННЯ ОПЕРАЦІЙ
    # ───────────────────────────────────────────────────────
    
    # Старт додавання
    application.add_handler(CallbackQueryHandler(start_bond_add, pattern='^ovdp_add$'))
    
    # Вибір дати
    application.add_handler(CallbackQueryHandler(handle_date_selection, pattern='^date_'))
    
    # Навігація по календарю
    application.add_handler(CallbackQueryHandler(
        handle_bond_calendar_navigation, 
        pattern='^cal_(prev|next)_'
    ))
    
    # Вибір типу операції
    application.add_handler(CallbackQueryHandler(
        handle_operation_buy,
        pattern='^bond_buy$'
    ))
    
    # Продаж - показати список
    application.add_handler(CallbackQueryHandler(
        show_sell_bond_selection,
        pattern='^bond_sell$'
    ))
    
    # Продаж - вибрано облігацію
    application.add_handler(CallbackQueryHandler(
        lambda u, c: handle_sell_bond_selected(u, c, u.callback_query.data.replace('sell_bond_', '')),
        pattern='^sell_bond_'
    ))
    
    # Вибір платформи (для купівлі)
    application.add_handler(CallbackQueryHandler(
        lambda u, c: handle_platform_buy(u, c, 'ICU'),
        pattern='^platform_icu$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: handle_platform_buy(u, c, 'SENSBANK'),
        pattern='^platform_sensbank$'
    ))
    
    # ───────────────────────────────────────────────────────
    # СПИСОК ОПЕРАЦІЙ
    # ───────────────────────────────────────────────────────
    
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_bonds_list(u, c, 1),
        pattern='^ovdp_list$'
    ))
    
    # Пагінація списку
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_bonds_list(u, c, int(u.callback_query.data.replace('bonds_list_page_', ''))),
        pattern='^bonds_list_page_'
    ))
    
    # ───────────────────────────────────────────────────────
    # ПОРТФЕЛЬ
    # ───────────────────────────────────────────────────────
    
    # Показ всього портфеля
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_portfolio(u, c),
        pattern='^ovdp_portfolio$'
    ))
    
    # Портфель по платформах
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_portfolio(u, c, 'ICU'),
        pattern='^portfolio_icu$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_portfolio(u, c, 'SENSBANK'),
        pattern='^portfolio_sensbank$'
    ))
    
    # Оновлення залишків
    application.add_handler(CallbackQueryHandler(
        update_balance_platform_selection,
        pattern='^ovdp_update_balance$'
    ))
    
    # ───────────────────────────────────────────────────────
    # ПРИБУТКИ
    # ───────────────────────────────────────────────────────
    
    application.add_handler(CallbackQueryHandler(show_profit, pattern='^ovdp_profit$'))
    application.add_handler(CallbackQueryHandler(write_off_profit, pattern='^write_off_profit$'))
    application.add_handler(CallbackQueryHandler(write_off_profit, pattern='^confirm_write_off$'))
    
    # ───────────────────────────────────────────────────────
    # PNL
    # ───────────────────────────────────────────────────────
    
    application.add_handler(CallbackQueryHandler(show_pnl_portfolio, pattern='^pnl_portfolio$'))
    
    # ───────────────────────────────────────────────────────
    # СТАТИСТИКА
    # ───────────────────────────────────────────────────────
    
    application.add_handler(CallbackQueryHandler(show_statistics, pattern='^ovdp_stats$'))
    
    # ───────────────────────────────────────────────────────
    # СИНХРОНІЗАЦІЯ
    # ───────────────────────────────────────────────────────
    
    application.add_handler(CallbackQueryHandler(
        sync_bonds_from_sheets, 
        pattern='^(sync_ovdp_sheets_to_db|sync_sheets_to_db)$'
    ))
    
    logger.info("✅ Обробники ОВДП зареєстровано!")


# ═══════════════════════════════════════════════════════════
# ОБРОБКА ТЕКСТОВИХ ПОВІДОМЛЕНЬ
# ═══════════════════════════════════════════════════════════

async def handle_message_unified(update: Update, context: CallbackContext):
    """Обробка текстових повідомлень для всіх портфелів"""
    if 'bond_step' in context.user_data or 'profit_step' in context.user_data:
        await handle_message_ovdp(update, context)
    elif 'stock_step' in context.user_data or 'dividend_step' in context.user_data:
        await handle_message_stocks(update, context)


# ═══════════════════════════════════════════════════════════
# ГОЛОВНА ФУНКЦІЯ
# ═══════════════════════════════════════════════════════════

def main():
    """Головна функція запуску бота"""
    
    # Ініціалізуємо БД та Google Sheets
    if not initialize_database():
        logger.error("Не вдалося підключитися до БД. Вихід.")
        return
    
    initialize_sheets()
    
    # Створюємо Application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Встановлюємо post_init
    app.post_init = post_init
    
    # ═══════════════════════════════════════════════════════════
    # РЕЄСТРУЄМО ВСІ ОБРОБНИКИ (ВАЖЛИВО: порядок має значення!)
    # ═══════════════════════════════════════════════════════════
    
    # 1. Команда /start
    app.add_handler(CommandHandler("start", start))
    
    # 2. ОВДП обробники (НОВІ, модульні) 👈 ЦЕ НОВОЕ!
    register_ovdp_handlers(app)
    
    # 3. Акції обробники (старі, не чіпаємо)
    app.add_handler(CallbackQueryHandler(
        button_handler_stocks, 
        pattern=r'^(stocks|stocks_add|stocks_list|stocks_list_page_|stocks_date_|stocks_portfolio|stocks_stats|stocks_dividends|stocks_check_pnl|stocks_profit|stocks_write_off_profit|stocks_sync|stocks_sync_from_sheets|stocks_cal_|stock_buy|stock_sell|sell_stock_|stock_platform_|update_balance|balance_platform_|dividend_)'
    ))
    
    # 4. Головне меню та спільні функції
    app.add_handler(CallbackQueryHandler(
        button_handler_main, 
        pattern=r'^(back_to_menu|analysis|sync|sync_ovdp|sync_stocks|sync_deposit|sync_crypto|sync_numismatics|sync_ovdp_db_to_sheets|sync_stocks_db_to_sheets|sync_stocks_sheets_to_db|sync_deposit_db_to_sheets|sync_deposit_sheets_to_db|sync_crypto_db_to_sheets|sync_crypto_sheets_to_db|sync_numismatics_db_to_sheets|sync_numismatics_sheets_to_db|stocks|deposit|crypto|numismatics)'
    ))
    
    # 5. Обробка текстових повідомлень (об'єднана для всіх портфелів)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_unified))
    
    logger.info("🚀 Бот запущений...")
    app.run_polling()


if __name__ == '__main__':
    main()