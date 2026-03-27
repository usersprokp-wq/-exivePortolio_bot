import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# Налаштування логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Тимчасовий токен - заміниш пізніше
import os
BOT_TOKEN = os.getenv('BOT_TOKEN')

async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("📊 БД → Excel", callback_data='sync_db')],
        [InlineKeyboardButton("📥 Excel → БД", callback_data='sync_sheets')],
        [InlineKeyboardButton("➕ Додати", callback_data='add')],
        [InlineKeyboardButton("📋 Список", callback_data='list')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Привіт! Оберіть дію:", reply_markup=reply_markup)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"✅ Вибрано: {query.data}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("Бот запущений...")
    app.run_polling()

if __name__ == '__main__':
    main()