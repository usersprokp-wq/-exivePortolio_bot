from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CallbackContext
from handlers.deposit.main_menu import get_deposit_menu_keyboard


async def show_deposit_stats(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📊 <b>Статистика депозитів</b>\n\n⏳ Розділ у розробці...",
        reply_markup=get_deposit_menu_keyboard(),
        parse_mode="HTML",
    )