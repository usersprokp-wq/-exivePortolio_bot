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

# Імпортуємо обробники по категоріях
from handlers.ovdp import button_handler_ovdp, handle_message_ovdp
from handlers.stocks import button_handler_stocks, handle_message_stocks

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


async def handle_message_unified(update: Update, context: CallbackContext):
    """Обробка текстових повідомлень для всіх портфелів"""
    if 'bond_step' in context.user_data:
        await handle_message_ovdp(update, context)
    elif 'stock_step' in context.user_data:
        await handle_message_stocks(update, context)


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
    
    # Регіструємо обробники (ВАЖЛИВО: порядок має значення!)
    app.add_handler(CommandHandler("start", start))
    
    # ОВДП обробники (перед спільними, бо більш специфічні)
    app.add_handler(CallbackQueryHandler(button_handler_ovdp, pattern=r'^(ovdp|bond_|date_|platform_|portfolio_|write_off|confirm_write_off|pnl_portfolio|bonds_list_page_|sync_sheets_to_db)'))
    
    # Акції обробники (перед спільними, бо більш специфічні)
    app.add_handler(CallbackQueryHandler(button_handler_stocks, pattern=r'^(stocks|stocks_add|stocks_list|stocks_date_|stocks_portfolio|stocks_stats|stocks_profit|stocks_sync|stocks_sync_from_sheets|stocks_cal_|stock_buy|stock_sell|stock_platform_)'))
    
    # Головне меню та спільні функції (загальні кнопки)
    app.add_handler(CallbackQueryHandler(button_handler_main, pattern=r'^(back_to_menu|analysis|sync|stocks|deposit|crypto|numismatics)'))
    
    # Обробка текстових повідомлень (об'єднана для всіх портфелів)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_unified))
    
    logger.info("Бот запущений...")
    app.run_polling()


if __name__ == '__main__':
    main()