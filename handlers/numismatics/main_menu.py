from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext


def get_numismatics_menu_keyboard() -> InlineKeyboardMarkup:
    """Головне меню розділу Нумізматика."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Додати запис",  callback_data="num_add"),
            InlineKeyboardButton("📋 Мої записи",    callback_data="num_list"),
        ],
        [
            InlineKeyboardButton("🏛 Портфель",      callback_data="num_portfolio"),
            InlineKeyboardButton("💰 Прибуток",      callback_data="num_profit"),
        ],
        [
            InlineKeyboardButton("📊 Статистика",    callback_data="num_stats"),
        ],
        [
            InlineKeyboardButton("🔙 Назад",         callback_data="back_to_menu"),
        ],
    ])


async def show_numismatics_menu(update: Update, context: CallbackContext):
    """Відкриває головне меню нумізматики."""
    context.user_data.clear()
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🏛 <b>Нумізматика</b>\n\nОберіть дію:",
        reply_markup=get_numismatics_menu_keyboard(),
        parse_mode="HTML",
    )