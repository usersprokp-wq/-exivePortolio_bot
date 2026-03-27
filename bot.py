import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Налаштування бази даних
Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    price = Column(Float)
    quantity = Column(Integer)
    created_at = Column(String(50), default=datetime.now().isoformat())

if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    logger.info("База даних підключена")
else:
    logger.error("DATABASE_URL не знайдено")
    Session = None

async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("➕ Додати товар", callback_data='add')],
        [InlineKeyboardButton("📋 Список товарів", callback_data='list')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Привіт! Оберіть дію:", reply_markup=reply_markup)

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'add':
        context.user_data['adding'] = True
        await query.edit_message_text("Введіть назву товару:")
    elif query.data == 'list':
        await show_products(query)

async def show_products(query):
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return
    
    session = Session()
    products = session.query(Product).all()
    session.close()
    
    if not products:
        await query.edit_message_text("📭 Список товарів порожній")
        return
    
    text = "📋 Список товарів:\n\n"
    for i, p in enumerate(products, 1):
        text += f"{i}. {p.name} - {p.price} грн (в наявності: {p.quantity})\n"
    
    await query.edit_message_text(text)

async def handle_message(update: Update, context: CallbackContext):
    if context.user_data.get('adding'):
        context.user_data['name'] = update.message.text
        context.user_data['awaiting_price'] = True
        await update.message.reply_text("💰 Введіть ціну:")
    elif context.user_data.get('awaiting_price'):
        try:
            price = float(update.message.text)
            context.user_data['price'] = price
            context.user_data['awaiting_quantity'] = True
            await update.message.reply_text("📦 Введіть кількість:")
        except:
            await update.message.reply_text("❌ Введіть число:")
    elif context.user_data.get('awaiting_quantity'):
        try:
            quantity = int(update.message.text)
            
            # Зберігаємо в базу даних
            session = Session()
            product = Product(
                name=context.user_data['name'],
                price=context.user_data['price'],
                quantity=quantity
            )
            session.add(product)
            session.commit()
            session.close()
            
            context.user_data.clear()
            await update.message.reply_text(f"✅ Товар додано!\nНазва: {product.name}\nЦіна: {product.price} грн\nКількість: {product.quantity}")
        except:
            await update.message.reply_text("❌ Введіть ціле число:")
    else:
        await update.message.reply_text("Використайте /start")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущений...")
    app.run_polling()

if __name__ == '__main__':
    main()