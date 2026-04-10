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

from handlers.stocks import button_handler_stocks, handle_message_stocks

from handlers.ovdp import (
    show_ovdp_menu,
    start_bond_add,
    handle_date_selection,
    handle_bond_calendar_navigation,
    show_sell_bond_selection,
    handle_sell_bond_selected,
    handle_message_ovdp,
    save_bond,
    show_bonds_list,
    handle_bond_delete,
    show_portfolio,
    update_balance_platform_selection,
    handle_balance_platform_selection,
    show_profit,
    write_off_profit,
    show_pnl_portfolio,
    show_statistics,
    sync_bonds_from_sheets,
)

from handlers.deposit import (
    show_deposit_menu,
    start_deposit_add,
    handle_message_deposit,
    handle_deposit_currency,
    handle_deposit_calendar_show,
    handle_deposit_calendar_nav,
    handle_deposit_start_selected,
    handle_deposit_end_calendar_show,
    handle_deposit_end_selected,
    handle_deposit_contract_skip,
    handle_deposit_confirm,
    handle_deposit_cancel,
    show_deposit_list,
    show_deposit_portfolio,
    handle_deposit_close,
    handle_deposit_send_contract,
    show_deposit_past,
    show_deposit_profit,
    handle_deposit_write_off,
    handle_message_deposit_profit,
    show_deposit_stats,
)

from handlers.numismatics import (
    show_numismatics_menu,
    start_numismatics_add,
    handle_num_op_buy,
    handle_num_op_sell,
    handle_num_sell_coin_selected,
    handle_num_confirm,
    handle_num_cancel,
    handle_message_numismatics,
    show_num_list,
    show_num_portfolio,
    show_num_sold,
    show_num_pnl,
    handle_num_pnl_coin_selected,
    handle_message_num_pnl,
    show_num_profit,
    handle_num_sell_selected,
    handle_num_write_off,
    handle_message_num_profit,
    show_num_stats,
)


load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

Session        = None
sheets_manager = None


def initialize_database():
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
    global sheets_manager
    try:
        sheets_manager = GoogleSheetsManager()
        logger.info("Google Sheets підключено")
        return True
    except Exception as e:
        logger.error(f"Google Sheets помилка: {e}")
        return False


async def post_init(app: Application):
    app.bot_data['sheets_manager'] = sheets_manager
    app.bot_data['Session']        = Session


# ═══════════════════════════════════════════════════════════
# ДОПОМІЖНІ ФУНКЦІЇ ДЛЯ ОВДП
# ═══════════════════════════════════════════════════════════

async def handle_operation_buy(update: Update, context: CallbackContext):
    context.user_data['bond_operation_type'] = 'купівля'
    context.user_data['bond_step']           = 'bond_number'
    await update.callback_query.edit_message_text(
        "🔢 Введіть номер облігації:", parse_mode='Markdown'
    )


async def handle_platform_buy(update: Update, context: CallbackContext, platform: str):
    context.user_data['platform'] = platform
    await save_bond(update, context)


# ═══════════════════════════════════════════════════════════
# РЕЄСТРАЦІЯ ОБРОБНИКІВ ОВДП
# ═══════════════════════════════════════════════════════════

def register_ovdp_handlers(application: Application):
    logger.info("Реєструємо обробники ОВДП...")

    application.add_handler(CallbackQueryHandler(show_ovdp_menu,   pattern='^ovdp$'))
    application.add_handler(CallbackQueryHandler(start_bond_add,   pattern='^ovdp_add$'))
    application.add_handler(CallbackQueryHandler(handle_date_selection, pattern='^date_'))
    application.add_handler(CallbackQueryHandler(handle_bond_calendar_navigation, pattern='^cal_(prev|next)_'))
    application.add_handler(CallbackQueryHandler(handle_operation_buy, pattern='^bond_buy$'))
    application.add_handler(CallbackQueryHandler(show_sell_bond_selection, pattern='^bond_sell$'))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: handle_sell_bond_selected(u, c, u.callback_query.data.replace('sell_bond_', '')),
        pattern='^sell_bond_'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: handle_platform_buy(u, c, 'ICU'), pattern='^platform_icu$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: handle_platform_buy(u, c, 'SENSBANK'), pattern='^platform_sensbank$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_bonds_list(u, c, 1), pattern='^ovdp_list$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_bonds_list(u, c, int(u.callback_query.data.replace('bonds_list_page_', ''))),
        pattern='^bonds_list_page_'
    ))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_portfolio(u, c),             pattern='^ovdp_portfolio$'))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_portfolio(u, c, 'ICU'),      pattern='^portfolio_icu$'))
    application.add_handler(CallbackQueryHandler(lambda u, c: show_portfolio(u, c, 'SENSBANK'), pattern='^portfolio_sensbank$'))
    application.add_handler(CallbackQueryHandler(update_balance_platform_selection,             pattern='^ovdp_update_balance$'))
    application.add_handler(CallbackQueryHandler(handle_balance_platform_selection,             pattern='^ovdp_balance_platform_'))
    application.add_handler(CallbackQueryHandler(show_profit,        pattern='^ovdp_profit$'))
    application.add_handler(CallbackQueryHandler(write_off_profit,   pattern='^write_off_profit$'))
    application.add_handler(CallbackQueryHandler(write_off_profit,   pattern='^confirm_write_off$'))
    application.add_handler(CallbackQueryHandler(show_pnl_portfolio, pattern='^pnl_portfolio$'))
    application.add_handler(CallbackQueryHandler(show_statistics,    pattern='^ovdp_stats$'))
    application.add_handler(CallbackQueryHandler(
        sync_bonds_from_sheets, pattern='^(sync_ovdp_sheets_to_db|sync_sheets_to_db)$'
    ))
    application.add_handler(CallbackQueryHandler(
        handle_bond_delete, pattern='^bond_delete_'
    ))

    logger.info("✅ Обробники ОВДП зареєстровано!")


# ═══════════════════════════════════════════════════════════
# РЕЄСТРАЦІЯ ОБРОБНИКІВ ДЕПОЗИТУ
# ═══════════════════════════════════════════════════════════

def register_deposit_handlers(application: Application):
    logger.info("Реєструємо обробники Депозиту...")

    application.add_handler(CallbackQueryHandler(show_deposit_menu,               pattern='^deposit$'))
    application.add_handler(CallbackQueryHandler(start_deposit_add,               pattern='^deposit_add$'))
    application.add_handler(CallbackQueryHandler(handle_deposit_currency,         pattern='^deposit_currency_'))
    application.add_handler(CallbackQueryHandler(handle_deposit_calendar_show,    pattern='^dep_start_calendar$'))
    application.add_handler(CallbackQueryHandler(handle_deposit_calendar_nav,     pattern='^dep_(start|end)_cal_(prev|next)_'))
    application.add_handler(CallbackQueryHandler(handle_deposit_start_selected,   pattern='^dep_start_\d'))
    application.add_handler(CallbackQueryHandler(handle_deposit_end_calendar_show, pattern='^dep_end_calendar$'))
    application.add_handler(CallbackQueryHandler(handle_deposit_end_selected,     pattern='^dep_end_\d'))
    application.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern='^dep_cal_ignore$'))
    application.add_handler(CallbackQueryHandler(handle_deposit_contract_skip,    pattern='^deposit_contract_skip$'))
    application.add_handler(CallbackQueryHandler(handle_deposit_send_contract,    pattern='^deposit_contract_\d+$'))
    application.add_handler(CallbackQueryHandler(handle_deposit_confirm,          pattern='^deposit_add_confirm$'))
    application.add_handler(CallbackQueryHandler(handle_deposit_cancel,           pattern='^deposit_add_cancel$'))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_deposit_list(u, c, 1), pattern='^deposit_list$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_deposit_list(u, c, int(u.callback_query.data.replace('deposit_list_page_', ''))),
        pattern='^deposit_list_page_'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_deposit_portfolio(u, c, 1), pattern='^deposit_portfolio$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_deposit_portfolio(u, c, int(u.callback_query.data.replace('deposit_portfolio_page_', ''))),
        pattern='^deposit_portfolio_page_'
    ))
    application.add_handler(CallbackQueryHandler(handle_deposit_close,            pattern='^deposit_close_'))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_deposit_past(u, c, 1), pattern='^deposit_past$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_deposit_past(u, c, int(u.callback_query.data.replace('deposit_past_page_', ''))),
        pattern='^deposit_past_page_'
    ))
    application.add_handler(CallbackQueryHandler(show_deposit_profit,             pattern='^deposit_profit$'))
    application.add_handler(CallbackQueryHandler(handle_deposit_write_off,        pattern='^deposit_write_off_profit$'))
    application.add_handler(CallbackQueryHandler(show_deposit_stats,              pattern='^deposit_stats$'))

    logger.info("✅ Обробники Депозиту зареєстровано!")


# ═══════════════════════════════════════════════════════════
# РЕЄСТРАЦІЯ ОБРОБНИКІВ НУМІЗМАТИКИ
# ═══════════════════════════════════════════════════════════

def register_numismatics_handlers(application: Application):
    logger.info("Реєструємо обробники Нумізматики...")

    application.add_handler(CallbackQueryHandler(show_numismatics_menu,        pattern='^numismatics$'))

    # Додати запис — тип операції
    application.add_handler(CallbackQueryHandler(start_numismatics_add,        pattern='^num_add$'))
    application.add_handler(CallbackQueryHandler(handle_num_op_buy,             pattern='^num_op_buy$'))
    application.add_handler(CallbackQueryHandler(handle_num_op_sell,            pattern='^num_op_sell$'))
    application.add_handler(CallbackQueryHandler(handle_num_sell_coin_selected, pattern='^num_sell_select_'))

    # Підтвердження / скасування
    application.add_handler(CallbackQueryHandler(handle_num_confirm,            pattern='^num_add_confirm$'))
    application.add_handler(CallbackQueryHandler(handle_num_cancel,             pattern='^num_add_cancel$'))

    # Мої записи
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_num_list(u, c, 1), pattern='^num_list$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_num_list(u, c, int(u.callback_query.data.replace('num_list_page_', ''))),
        pattern='^num_list_page_'
    ))

    # Портфель
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_num_portfolio(u, c, 1), pattern='^num_portfolio$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_num_portfolio(u, c, int(u.callback_query.data.replace('num_portfolio_page_', ''))),
        pattern='^num_portfolio_page_'
    ))

    # P&L портфелю
    application.add_handler(CallbackQueryHandler(show_num_pnl,                  pattern='^num_pnl$'))
    application.add_handler(CallbackQueryHandler(handle_num_pnl_coin_selected,  pattern='^num_pnl_coin_'))

    # Продані монети
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_num_sold(u, c, 1), pattern='^num_sold$'
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: show_num_sold(u, c, int(u.callback_query.data.replace('num_sold_page_', ''))),
        pattern='^num_sold_page_'
    ))

    # Прибуток
    application.add_handler(CallbackQueryHandler(show_num_profit,               pattern='^num_profit$'))
    application.add_handler(CallbackQueryHandler(handle_num_sell_selected,      pattern='^num_sell_\d'))
    application.add_handler(CallbackQueryHandler(handle_num_write_off,          pattern='^num_write_off_profit$'))  # ← НОВЕ

    # Статистика
    application.add_handler(CallbackQueryHandler(show_num_stats,                pattern='^num_stats$'))

    logger.info("✅ Обробники Нумізматики зареєстровано!")


# ═══════════════════════════════════════════════════════════
# ОБРОБКА ПОВІДОМЛЕНЬ
# ═══════════════════════════════════════════════════════════

async def handle_message_unified(update: Update, context: CallbackContext):
    step = context.user_data.get('num_profit_step')

    if context.user_data.get('num_pnl_step') == 'market_price':
        await handle_message_num_pnl(update, context)
    elif step in ('sell_price', 'write_off'):          # ← додано 'write_off'
        await handle_message_num_profit(update, context)
    elif 'num_step' in context.user_data:
        await handle_message_numismatics(update, context)
    elif context.user_data.get('deposit_profit_step') == 'write_off':
        await handle_message_deposit_profit(update, context)
    elif 'deposit_step' in context.user_data:
        await handle_message_deposit(update, context)
    elif 'bond_step' in context.user_data or 'profit_step' in context.user_data:
        await handle_message_ovdp(update, context)
    elif 'stock_step' in context.user_data or 'dividend_step' in context.user_data:
        await handle_message_stocks(update, context)


# ═══════════════════════════════════════════════════════════
# ГОЛОВНА ФУНКЦІЯ
# ═══════════════════════════════════════════════════════════

def main():
    if not initialize_database():
        logger.error("Не вдалося підключитися до БД. Вихід.")
        return

    initialize_sheets()

    app = Application.builder().token(BOT_TOKEN).build()
    app.post_init = post_init

    app.add_handler(CommandHandler("start", start))

    register_ovdp_handlers(app)
    register_deposit_handlers(app)
    register_numismatics_handlers(app)

    app.add_handler(CallbackQueryHandler(
        button_handler_stocks,
        pattern=(
            r'^('
            r'stocks|stocks_add|stocks_list|stocks_list_page_\d+|'
            r'stocks_date_|stocks_date_step|stocks_portfolio|stocks_stats|stocks_stats_general|stocks_stats_top|stocks_dividends|'
            r'stocks_check_pnl|stocks_profit|stocks_write_off_profit|'
            r'stocks_sync|stocks_sync_from_sheets|stocks_cal_|'
            r'stock_buy|stock_sell|stock_dividend|sell_stock_|stock_platform_|'
            r'update_balance|balance_platform_|dividend_|'
            r'portfolio_ff|portfolio_ib|portfolio_all|pnl_page_|pnl_refresh|'
            r'portfolio_page_\d+|portfolio_ff_page_\d+|portfolio_ib_page_\d+'
            r').*$'
        )
    ))

    app.add_handler(CallbackQueryHandler(
        button_handler_main,
        pattern=(
            r'^('
            r'back_to_menu|analysis|sync|sync_ovdp|sync_stocks|sync_deposit|'
            r'sync_crypto|sync_numismatics|sync_ovdp_db_to_sheets|'
            r'sync_stocks_db_to_sheets|sync_stocks_sheets_to_db|'
            r'sync_deposit_db_to_sheets|sync_deposit_sheets_to_db|'
            r'sync_crypto_db_to_sheets|sync_crypto_sheets_to_db|'
            r'sync_numismatics_db_to_sheets|sync_numismatics_sheets_to_db|'
            r'stocks|deposit|crypto|numismatics'
            r')$'
        )
    ))

    app.add_handler(MessageHandler(
        (filters.TEXT | filters.Document.PDF) & ~filters.COMMAND,
        handle_message_unified
    ))

    logger.info("🚀 Бот запущений...")
    app.run_polling()


if __name__ == '__main__':
    main()