import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from .add import (
    start_crypto_add, handle_crypto_date_selection, handle_calendar_navigation,
    show_sell_crypto_selection, handle_sell_crypto_selected, save_crypto,
    handle_message_add, show_date_step
)
from .records import show_crypto_list
from .portfolio import show_crypto_portfolio, show_crypto_pnl
from .profit import show_crypto_profit, write_off_crypto_profit, handle_message_profit
from .stats import show_crypto_stats
from .entry_points import show_crypto_entry_points

logger = logging.getLogger(__name__)


async def show_crypto_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("➕ Додати запис", callback_data='crypto_add'),
         InlineKeyboardButton("📋 Мої записи", callback_data='crypto_list')],
        [InlineKeyboardButton("💼 Портфель", callback_data='crypto_portfolio'),
         InlineKeyboardButton("💰 Прибуток", callback_data='crypto_profit')],
        [InlineKeyboardButton("📊 Статистика", callback_data='crypto_stats'),
         InlineKeyboardButton("🎯 Точки входу", callback_data='crypto_entry_points')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
    ]
    await query.edit_message_text(
        "₿ *Криптовалюта*\n\nОберіть дію:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def button_handler_crypto(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'crypto':
        await show_crypto_menu(update, context)

    elif data == 'crypto_add':
        await start_crypto_add(update, context)
    elif data.startswith('crypto_date_'):
        await handle_crypto_date_selection(update, context)
    elif data.startswith('crypto_cal_'):
        await handle_calendar_navigation(update, context)
    elif data == 'crypto_buy':
        context.user_data['crypto_operation_type'] = 'купівля'
        context.user_data['crypto_step'] = 'operation_type'
        await show_date_step(update, context)
    elif data == 'crypto_sell':
        context.user_data['crypto_operation_type'] = 'продаж'
        context.user_data['crypto_step'] = 'operation_type'
        await show_date_step(update, context)
    elif data == 'crypto_date_step':
        await show_date_step(update, context)
    elif data.startswith('sell_crypto_'):
        ticker = data.replace('sell_crypto_', '')
        await handle_sell_crypto_selected(update, context, ticker)
    elif data.startswith('crypto_platform_'):
        platform = data.replace('crypto_platform_', '').upper()
        context.user_data['platform'] = platform
        await save_crypto(update, context)

    elif data == 'crypto_list':
        await show_crypto_list(update, context)
    elif data.startswith('crypto_list_page_'):
        page = int(data.replace('crypto_list_page_', ''))
        await show_crypto_list(update, context, page=page)

    elif data == 'crypto_portfolio':
        await show_crypto_portfolio(update, context)
    elif data.startswith('crypto_portfolio_page_'):
        page = int(data.replace('crypto_portfolio_page_', ''))
        await show_crypto_portfolio(update, context, page=page)
    elif data == 'crypto_check_pnl':
        context.user_data.pop('crypto_pnl_cache', None)
        await show_crypto_pnl(update, context, page=1, use_cache=False)
    elif data == 'crypto_pnl_refresh':
        context.user_data.pop('crypto_pnl_cache', None)
        await show_crypto_pnl(update, context, page=1, use_cache=False)
    elif data.startswith('crypto_pnl_page_'):
        page = int(data.replace('crypto_pnl_page_', ''))
        await show_crypto_pnl(update, context, page=page, use_cache=True)

    elif data == 'crypto_profit':
        await show_crypto_profit(update, context)

    elif data == 'crypto_stats' or data == 'crypto_stats_general':
        await show_crypto_stats(update, context, tab='crypto_stats_general')
    elif data == 'crypto_stats_top':
        await show_crypto_stats(update, context, tab='crypto_stats_top')

    elif data == 'crypto_entry_points':
        context.user_data.pop('crypto_entry_cache', None)
        await show_crypto_entry_points(update, context, page=1, use_cache=False)
    elif data == 'crypto_entry_refresh':
        context.user_data.pop('crypto_entry_cache', None)
        await show_crypto_entry_points(update, context, page=1, use_cache=False)
    elif data.startswith('crypto_entry_page_'):
        page = int(data.replace('crypto_entry_page_', ''))
        await show_crypto_entry_points(update, context, page=page, use_cache=True)


async def handle_message_crypto(update: Update, context: CallbackContext):
    has_crypto_step = 'crypto_step' in context.user_data
    has_profit_step = context.user_data.get('crypto_profit_step') == 'enter_amount'

    if not (has_crypto_step or has_profit_step):
        return

    try:
        if has_profit_step:
            await handle_message_profit(update, context)
        else:
            await handle_message_add(update, context)
    except Exception as e:
        logger.error(f"Error in handle_message_crypto: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")