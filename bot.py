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

class Bond(Base):
    __tablename__ = 'bonds'
    id = Column(Integer, primary_key=True)
    date = Column(String(50))
    operation_type = Column(String(20))
    bond_number = Column(String(50))
    maturity_date = Column(String(50))
    price_per_unit = Column(Float)
    quantity = Column(Integer)
    total_amount = Column(Float)
    platform = Column(String(100))
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
        [InlineKeyboardButton("📈 ОВДП", callback_data='ovdp'), InlineKeyboardButton("📊 Акції", callback_data='stocks')],
        [InlineKeyboardButton("🏦 Депозит", callback_data='deposit'), InlineKeyboardButton("₿ Криптовалюта", callback_data='crypto')],
        [InlineKeyboardButton("🪙 Нумізматика", callback_data='numismatics'), InlineKeyboardButton("📊 Аналіз портфеля", callback_data='analysis')],
        [InlineKeyboardButton("🔄 Синхронізація", callback_data='sync')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📊 *Інвестиційний портфель*\n\nОберіть розділ для роботи:"
    
    # Перевіряємо чи це callback (редагуємо) або нове повідомлення
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    # Зберігаємо поточне повідомлення
    context.user_data['current_message_id'] = query.message.message_id
    
    if query.data == 'ovdp':
        text = "📈 *ОВДП*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати запис", callback_data='ovdp_add')],
            [InlineKeyboardButton("📋 Мої записи", callback_data='ovdp_list')],
            [InlineKeyboardButton("📊 Статистика", callback_data='ovdp_stats')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    elif query.data == 'stocks':
        text = "📊 *Акції*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати", callback_data='stocks_add')],
            [InlineKeyboardButton("📋 Список", callback_data='stocks_list')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    elif query.data == 'deposit':
        text = "🏦 *Депозит*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати", callback_data='deposit_add')],
            [InlineKeyboardButton("📋 Список", callback_data='deposit_list')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    elif query.data == 'crypto':
        text = "₿ *Криптовалюта*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати", callback_data='crypto_add')],
            [InlineKeyboardButton("📋 Список", callback_data='crypto_list')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    elif query.data == 'numismatics':
        text = "🪙 *Нумізматика*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати", callback_data='numismatics_add')],
            [InlineKeyboardButton("📋 Список", callback_data='numismatics_list')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    elif query.data == 'analysis':
        text = "📊 *Аналіз портфеля*\n\nТут буде аналітика...\n\n(в розробці)"
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    elif query.data == 'sync':
        text = "🔄 *Синхронізація*\n\nОберіть напрямок:"
        keyboard = [
            [InlineKeyboardButton("📤 БД → Excel", callback_data='sync_db_to_sheets')],
            [InlineKeyboardButton("📥 Excel → БД", callback_data='sync_sheets_to_db')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    elif query.data == 'back_to_menu':
        await start(update, context)
    elif query.data == 'ovdp_add':
        context.user_data['adding_bond'] = True
        context.user_data['bond_step'] = 'date'
        await query.edit_message_text("📈 *Додавання ОВДП*\n\nВведіть дату операції (у форматі ДД.ММ.РРРР):", parse_mode='Markdown')    
    elif query.data == 'ovdp_stats':
        await query.edit_message_text("📈 *ОВДП - Статистика*\n\nТут буде статистика...\n\n(в розробці)", parse_mode='Markdown')


async def handle_message(update: Update, context: CallbackContext):
    # Додавання ОВДП
    if context.user_data.get('adding_bond'):
        step = context.user_data.get('bond_step')
        
        if step == 'date':
            context.user_data['bond_date'] = update.message.text
            context.user_data['bond_step'] = 'operation_type'
            await update.message.reply_text("📈 Введіть тип операції (купівля/продаж):")
            
        elif step == 'operation_type':
            context.user_data['bond_operation_type'] = update.message.text
            context.user_data['bond_step'] = 'bond_number'
            await update.message.reply_text("📈 Введіть номер ОВДП:")
            
        elif step == 'bond_number':
            context.user_data['bond_number'] = update.message.text
            context.user_data['bond_step'] = 'maturity_date'
            await update.message.reply_text("📈 Введіть термін до (дату погашення ДД.ММ.РРРР):")
            
        elif step == 'maturity_date':
            context.user_data['bond_maturity_date'] = update.message.text
            context.user_data['bond_step'] = 'price_per_unit'
            await update.message.reply_text("📈 Введіть ціну за шт:")
            
        elif step == 'price_per_unit':
            try:
                context.user_data['bond_price_per_unit'] = float(update.message.text)
                context.user_data['bond_step'] = 'quantity'
                await update.message.reply_text("📈 Введіть кількість:")
            except:
                await update.message.reply_text("❌ Введіть число:")
                
        elif step == 'quantity':
            try:
                context.user_data['bond_quantity'] = int(update.message.text)
                context.user_data['bond_step'] = 'total_amount'
                await update.message.reply_text("📈 Введіть суму:")
            except:
                await update.message.reply_text("❌ Введіть ціле число:")
                
        elif step == 'total_amount':
            try:
                context.user_data['bond_total_amount'] = float(update.message.text)
                context.user_data['bond_step'] = 'platform'
                await update.message.reply_text("📈 Введіть платформу (наприклад: ПриватБанк, Тіндер):")
            except:
                await update.message.reply_text("❌ Введіть число:")
                
        elif step == 'platform':
            context.user_data['bond_platform'] = update.message.text
            
            # Зберігаємо в базу даних
            session = Session()
            bond = Bond(
                date=context.user_data['bond_date'],
                operation_type=context.user_data['bond_operation_type'],
                bond_number=context.user_data['bond_number'],
                maturity_date=context.user_data['bond_maturity_date'],
                price_per_unit=context.user_data['bond_price_per_unit'],
                quantity=context.user_data['bond_quantity'],
                total_amount=context.user_data['bond_total_amount'],
                platform=context.user_data['bond_platform']
            )
            session.add(bond)
            session.commit()
            session.close()
            
            # Очищаємо дані
            context.user_data.clear()
            
            await update.message.reply_text(
                f"✅ *ОВДП додано!*\n\n"
                f"📅 Дата: {bond.date}\n"
                f"🔄 Тип: {bond.operation_type}\n"
                f"🔢 Номер: {bond.bond_number}\n"
                f"📆 Термін до: {bond.maturity_date}\n"
                f"💰 Ціна: {bond.price_per_unit} грн\n"
                f"📦 Кількість: {bond.quantity}\n"
                f"💵 Сума: {bond.total_amount} грн\n"
                f"🏦 Платформа: {bond.platform}",
                parse_mode='Markdown'
            )
    
    # Старий код для товарів (можна видалити пізніше)
    elif context.user_data.get('adding'):
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