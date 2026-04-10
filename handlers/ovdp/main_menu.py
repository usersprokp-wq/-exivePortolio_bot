"""
Головне меню ОВДП
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)


async def show_ovdp_menu(update: Update, context: CallbackContext):
    """Показати меню ОВДП"""
    query = update.callback_query
    text = "📈 *ОВДП*\n\nОберіть дію:"
    keyboard = [
        [InlineKeyboardButton("➕ Додати запис", callback_data='ovdp_add'),
         InlineKeyboardButton("📋 Мої записи", callback_data='ovdp_list')],
        [InlineKeyboardButton("💼 Портфель", callback_data='ovdp_portfolio'),
         InlineKeyboardButton("💰 Прибуток", callback_data='ovdp_profit')],
        [InlineKeyboardButton("📊 Статистика", callback_data='ovdp_stats')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')