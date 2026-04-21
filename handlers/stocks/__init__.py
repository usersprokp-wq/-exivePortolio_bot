import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from .add import (
    start_stock_add, handle_stock_date_selection, handle_calendar_navigation,
    show_sell_stock_selection, handle_sell_stock_selected, save_stock, handle_message_add,
    show_dividend_selection_from_add, handle_dividend_manual, handle_dividend_ticker_confirm,
    show_date_step
)
from .records import show_stocks_list
from .portfolio import show_stocks_portfolio, show_stocks_pnl, handle_update_balance, handle_balance_platform, handle_message_balance
from .profit import show_stocks_profit, handle_message_profit, write_off_stocks_profit
from .stats import show_stocks_stats
from .dividends import show_dividends_selection, handle_dividend_ticker, confirm_dividend, handle_message_dividends
from .sync import sync_stocks_to_sheets, sync_stocks_from_sheets

logger = logging.getLogger(__name__)


async def show_stocks_menu(update: Update, context: CallbackContext):
    """Показати меню Акцій"""
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("➕ Додати запис", callback_data='stocks_add'),
         InlineKeyboardButton("📋 Мої записи", callback_data='stocks_list')],
        [InlineKeyboardButton("💼 Портфель", callback_data='stocks_portfolio'),
         InlineKeyboardButton("💰 Прибуток", callback_data='stocks_profit')],
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
        context.user_data['stock_step'] = 'operation_type'
        await show_date_step(update, context)
    elif data == 'stock_sell':
        context.user_data['stock_operation_type'] = 'продаж'
        context.user_data['stock_step'] = 'operation_type'
        await show_date_step(update, context)
    elif data == 'stock_dividend':
        context.user_data['stock_operation_type'] = 'дивіденди'
        context.user_data['stock_step'] = 'operation_type'
        await show_date_step(update, context)
    elif data == 'stocks_date_step':
        await show_date_step(update, context)
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

    # Пагінація портфеля (без фільтру)
    elif data.startswith('portfolio_page_'):
        page = int(data.replace('portfolio_page_', ''))
        await show_stocks_portfolio(update, context, page=page)
    # Пагінація портфеля FF
    elif data.startswith('portfolio_ff_page_'):
        page = int(data.replace('portfolio_ff_page_', ''))
        await show_stocks_portfolio(update, context, platform='FF', page=page)
    # Пагінація портфеля IB
    elif data.startswith('portfolio_ib_page_'):
        page = int(data.replace('portfolio_ib_page_', ''))
        await show_stocks_portfolio(update, context, platform='IB', page=page)

    elif data == 'update_balance':
        await handle_update_balance(update, context)
    elif data.startswith('balance_platform_'):
        await handle_balance_platform(update, context)

    # --- Прибуток ---
    elif data == 'stocks_profit':
        await show_stocks_profit(update, context)
    # stocks_write_off_profit обробляється окремим handler в bot.py через write_off_stocks_profit

    # --- Статистика ---
    elif data == 'stocks_stats' or data == 'stocks_stats_general':
        await show_stocks_stats(update, context, tab='stocks_stats_general')
    elif data == 'stocks_stats_top':
        await show_stocks_stats(update, context, tab='stocks_stats_top')

    # --- Дивіденди ---
    elif data == 'stocks_dividends':
        await show_dividends_selection(update, context)
    elif data == 'dividend_manual':
        await handle_dividend_manual(update, context)
    elif data.startswith('dividend_confirm_ticker_'):
        await handle_dividend_ticker_confirm(update, context)
    elif data.startswith('dividend_') and data != 'dividend_confirm':
        ticker = data.replace('dividend_', '')
        await handle_dividend_ticker(update, context, ticker)
    elif data == 'dividend_confirm':
        await confirm_dividend(update, context)

    # --- PnL (в розробці) ---
    elif data == 'stocks_check_pnl':
        context.user_data.pop('pnl_cache', None)
        await show_stocks_pnl(update, context, page=1, use_cache=False)
    elif data == 'pnl_refresh':
        context.user_data.pop('pnl_cache', None)
        await show_stocks_pnl(update, context, page=1, use_cache=False)
    elif data.startswith('pnl_page_'):
        page = int(data.replace('pnl_page_', ''))
        await show_stocks_pnl(update, context, page=page, use_cache=True)

    # --- Синхронізація ---
    elif data == 'stocks_sync':
        await sync_stocks_to_sheets(update, context)
    elif data == 'stocks_sync_from_sheets':
        await sync_stocks_from_sheets(update, context)


async def handle_message_stocks(update: Update, context: CallbackContext):
    """Головний роутер текстових повідомлень для розділу Акцій"""
    has_stock_step = 'stock_step' in context.user_data
    has_dividend_step = 'dividend_step' in context.user_data

    if not (has_stock_step or has_dividend_step):
        return

    try:
        if has_dividend_step:
            await handle_message_dividends(update, context)
        elif context.user_data.get('stock_step') == 'balance_amount':
            await handle_message_balance(update, context)
        else:
            await handle_message_add(update, context)

    except Exception as e:
        logger.error(f"Error in handle_message_stocks: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")