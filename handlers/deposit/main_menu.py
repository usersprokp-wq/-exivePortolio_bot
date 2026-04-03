from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext


def get_deposit_menu_keyboard() -> InlineKeyboardMarkup:
    """Головне меню розділу Депозит."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Додати запис",  callback_data="deposit_add"),
            InlineKeyboardButton("📋 Мої записи",    callback_data="deposit_list"),
        ],
        [
            InlineKeyboardButton("🏦 Портфель",      callback_data="deposit_portfolio"),
            InlineKeyboardButton("💰 Прибуток",      callback_data="deposit_profit"),
        ],
        [
            InlineKeyboardButton("📊 Статистика",    callback_data="deposit_stats"),
        ],
        [
            InlineKeyboardButton("🔙 Назад",         callback_data="back_to_menu"),
        ],
    ])


async def show_deposit_menu(update: Update, context: CallbackContext):
    """Відкриває головне меню депозитів."""
    context.user_data.clear()
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏦 <b>Депозити</b>\n\nОберіть дію:",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )