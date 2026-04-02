import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from .add import (
    start_stock_add, handle_stock_date_selection, handle_calendar_navigation,
    show_sell_stock_selection, handle_sell_stock_selected, save_stock, handle_message_add
)
from .records import show_stocks_list
from .portfolio import show_stocks_portfolio, handle_update_balance, handle_balance_platform, handle_message_balance
from .profit import show_stocks_profit, handle_message_profit
from .stats import show_stocks_stats
from .dividends import show_dividends_selection, handle_dividend_ticker, confirm_dividend, handle_message_dividends
from .sync import sync_stocks_to_sheets, sync_stocks_from_sheets

logger = logging.getLogger(__name__)


async def show_stocks_menu(update: Update, context: CallbackContext):
    """Показати меню Акцій"""
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("➕ Додати запис", callback_data='stocks_add')],
        [InlineKeyboardButton("📋 Мої записи", callback_data='stocks_list')],
        [InlineKeyboardButton("💼 Портфель", callback_data='stocks_portfolio')],
        [InlineKeyboardButton("💰 Прибуток", callback_data='stocks_profit')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stocks_stats')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
    ]
    await query.edit_message_text(
        "📊 *Акції*\n\nОберіть дію:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def button_handler_stocks(update: Update, context: CallbackContext):
    """Головний роутер кнопок для розділу Акцій"""
    query = update.callback_query
    await query.answer()
    data = query.data

    # --- Головне меню ---
    if data == 'stocks':
        await show_stocks_menu(update, context)

    # --- Додати запис ---
    elif data == 'stocks_add':
        await start_stock_add(update, context)
    elif data.startswith('stocks_date_'):
        await handle_stock_date_selection(update, context)
    elif data.startswith('stocks_cal_'):
        await handle_calendar_navigation(update, context)
    elif data == 'stock_buy':
        context.user_data['stock_operation_type'] = 'купівля'
        context.user_data['stock_step'] = 'ticker'
        await query.edit_message_text("📈 Введіть тікер акції (наприклад: GAZP):", parse_mode='Markdown')
    elif data == 'stock_sell':
        context.user_data['stock_operation_type'] = 'продаж'
        await show_sell_stock_selection(update, context)
    elif data.startswith('sell_stock_'):
        ticker = data.replace('sell_stock_', '')
        await handle_sell_stock_selected(update, context, ticker)
    elif data.startswith('stock_platform_'):
        platform = data.replace('stock_platform_', '')
        context.user_data['platform'] = platform.upper()
        await save_stock(update, context)

    # --- Мої записи ---
    elif data == 'stocks_list':
        await show_stocks_list(update, context)
    elif data.startswith('stocks_list_page_'):
        page = int(data.replace('stocks_list_page_', ''))
        await show_stocks_list(update, context, page=page)

    # --- Портфель ---
    elif data == 'stocks_portfolio':
        await show_stocks_portfolio(update, context)
    elif data == 'portfolio_ff':
        await show_stocks_portfolio(update, context, platform='FF')
    elif data == 'portfolio_ib':
        await show_stocks_portfolio(update, context, platform='IB')
    elif data == 'portfolio_all':
        await show_stocks_portfolio(update, context, platform=None)
    elif data == 'update_balance':
        await handle_update_balance(update, context)
    elif data.startswith('balance_platform_'):
        await handle_balance_platform(update, context)

    # --- Прибуток ---
    elif data == 'stocks_profit':
        await show_stocks_profit(update, context)
    elif data == 'stocks_write_off_profit':
        context.user_data['profit_step'] = 'enter_amount'
        await query.edit_message_text("💰 Введіть суму для списання:", parse_mode='Markdown')

    # --- Статистика ---
    elif data == 'stocks_stats':
        await show_stocks_stats(update, context)

    # --- Дивіденди ---
    elif data == 'stocks_dividends':
        await show_dividends_selection(update, context)
    elif data.startswith('dividend_') and data != 'dividend_confirm':
        ticker = data.replace('dividend_', '')
        await handle_dividend_ticker(update, context, ticker)
    elif data == 'dividend_confirm':
        await confirm_dividend(update, context)

    # --- PnL (в розробці) ---
    elif data == 'stocks_check_pnl':
        await query.edit_message_text(
            "🚧 Взнати PnL - в розробці",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]),
            parse_mode='Markdown'
        )

    # --- Синхронізація ---
    elif data == 'stocks_sync':
        await sync_stocks_to_sheets(update, context)
    elif data == 'stocks_sync_from_sheets':
        await sync_stocks_from_sheets(update, context)


async def handle_message_stocks(update: Update, context: CallbackContext):
    """Головний роутер текстових повідомлень для розділу Акцій"""
    has_stock_step = 'stock_step' in context.user_data
    has_profit_step = 'profit_step' in context.user_data
    has_dividend_step = 'dividend_step' in context.user_data

    if not (has_stock_step or has_profit_step or has_dividend_step):
        return

    try:
        if has_dividend_step:
            await handle_message_dividends(update, context)
        elif has_profit_step:
            await handle_message_profit(update, context)
        elif context.user_data.get('stock_step') == 'balance_amount':
            await handle_message_balance(update, context)
        else:
            await handle_message_add(update, context)

    except Exception as e:
        logger.error(f"Error in handle_message_stocks: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")
