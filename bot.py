import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from dotenv import load_dotenv
from google_sheets import GoogleSheetsManager


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
    
    # Підключаємо Google Sheets
    try:
        from google_sheets import GoogleSheetsManager
        sheets_manager = GoogleSheetsManager()
        logger.info("Google Sheets підключено")
    except Exception as e:
        logger.error(f"Google Sheets помилка: {e}")
        sheets_manager = None
else:
    logger.error("DATABASE_URL не знайдено")
    Session = None
    sheets_manager = None

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
            [InlineKeyboardButton("💼 Портфель", callback_data='ovdp_portfolio')],
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
    elif query.data == 'sync_db_to_sheets':
        await sync_bonds_to_sheets(update, context)
        
    elif query.data == 'sync_sheets_to_db':
        await query.edit_message_text("🔄 Синхронізація Excel → БД\n\n(в розробці)", parse_mode='Markdown')


    elif query.data.startswith('date_'):
        date_value = query.data.replace('date_', '')
        if date_value != 'manual':
            context.user_data['bond_date'] = date_value
            context.user_data['bond_step'] = 'operation_type'
            keyboard = [
                [InlineKeyboardButton("🟢 Купівля", callback_data='bond_buy')],
                [InlineKeyboardButton("🔴 Продаж", callback_data='bond_sell')]
            ]
            await query.edit_message_text(
                f"📅 Дата: {date_value}\n\n📈 Виберіть тип операції:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            context.user_data['bond_step'] = 'date_manual'
            await query.edit_message_text("📅 Введіть дату вручну (у форматі ДД.ММ.РРРР):", parse_mode='Markdown')

    elif query.data == 'back_to_menu':
        await start(update, context)
    elif query.data == 'ovdp_add':
        context.user_data['adding_bond'] = True
        context.user_data['bond_step'] = 'date'
        
        # Імпортуємо datetime для роботи з датами
        from datetime import datetime, timedelta
        
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        three_days = today + timedelta(days=3)
        week = today + timedelta(days=7)
        
        keyboard = [
            [InlineKeyboardButton(f"📅 Сьогодні ({today.strftime('%d.%m.%Y')})", callback_data=f'date_{today.strftime("%d.%m.%Y")}')],
            [InlineKeyboardButton(f"📅 Завтра ({tomorrow.strftime('%d.%m.%Y')})", callback_data=f'date_{tomorrow.strftime("%d.%m.%Y")}')],
            [InlineKeyboardButton(f"📅 Через 3 дні ({three_days.strftime('%d.%m.%Y')})", callback_data=f'date_{three_days.strftime("%d.%m.%Y")}')],
            [InlineKeyboardButton(f"📅 Через тиждень ({week.strftime('%d.%m.%Y')})", callback_data=f'date_{week.strftime("%d.%m.%Y")}')],
            [InlineKeyboardButton("✏️ Ввести вручну", callback_data='date_manual')]
        ]
        await query.edit_message_text(
            "📅 *Виберіть дату операції:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif query.data == 'ovdp_stats':
        await query.edit_message_text("📈 *ОВДП - Статистика*\n\nТут буде статистика...\n\n(в розробці)", parse_mode='Markdown')
    
    elif query.data == 'bond_buy':
        context.user_data['bond_operation_type'] = 'купівля'
        context.user_data['bond_step'] = 'bond_number'
        await query.edit_message_text("📈 Введіть номер ОВДП:", parse_mode='Markdown')
        
    elif query.data == 'bond_sell':
        context.user_data['bond_operation_type'] = 'продаж'
        context.user_data['bond_step'] = 'bond_number'
        await query.edit_message_text("📈 Введіть номер ОВДП:", parse_mode='Markdown')
        
    elif query.data == 'bond_confirm_amount':
        quantity = context.user_data.get('bond_quantity', 0)
        price = context.user_data.get('bond_price_per_unit', 0)
        total = quantity * price
        context.user_data['bond_total_amount'] = total
        context.user_data['bond_step'] = 'platform'
        keyboard = [
            [InlineKeyboardButton("🏦 ICU", callback_data='platform_icu')],
            [InlineKeyboardButton("🏦 SENSBANK", callback_data='platform_sensbank')]
        ]
        await query.edit_message_text(
            f"📈 Сума: {total} грн\n\nВиберіть платформу:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == 'bond_edit_amount':
        context.user_data['bond_step'] = 'total_amount_manual'
        await query.edit_message_text("📈 Введіть суму вручну:", parse_mode='Markdown')

    elif query.data == 'ovdp_list':
        await show_bonds_list(update, context)

    elif query.data == 'ovdp_portfolio':
        await show_bonds_portfolio(update, context, platform=None)

    elif query.data == 'portfolio_icu':
        await show_bonds_portfolio(update, context, platform='ICU')
        
    elif query.data == 'portfolio_sensbank':
        await show_bonds_portfolio(update, context, platform='SENSBANK')

    elif query.data == 'platform_icu':
        context.user_data['bond_platform'] = 'ICU'
        # Продовжуємо збереження
        session = Session()
        bond = Bond(
            date=context.user_data['bond_date'],
            operation_type=context.user_data['bond_operation_type'],
            bond_number=context.user_data['bond_number'],
            maturity_date=context.user_data['bond_maturity_date'],
            price_per_unit=context.user_data['bond_price_per_unit'],
            quantity=context.user_data['bond_quantity'],
            total_amount=context.user_data['bond_total_amount'],
            platform='ICU'
        )
        session.add(bond)
        session.commit()
        
        bond_data = {
            'date': bond.date,
            'operation_type': bond.operation_type,
            'bond_number': bond.bond_number,
            'maturity_date': bond.maturity_date,
            'price_per_unit': bond.price_per_unit,
            'quantity': bond.quantity,
            'total_amount': bond.total_amount,
            'platform': bond.platform
        }
        session.close()
        
        context.user_data.clear()
        
        keyboard = [[InlineKeyboardButton("🔙 Назад до ОВДП", callback_data='ovdp')]]
        await query.edit_message_text(
            f"✅ *ОВДП додано!*\n\n"
            f"📅 Дата: {bond_data['date']}\n"
            f"🔄 Тип: {bond_data['operation_type']}\n"
            f"🔢 Номер: {bond_data['bond_number']}\n"
            f"📆 Термін до: {bond_data['maturity_date']}\n"
            f"💰 Ціна: {bond_data['price_per_unit']} грн\n"
            f"📦 Кількість: {bond_data['quantity']}\n"
            f"💵 Сума: {bond_data['total_amount']} грн\n"
            f"🏦 Платформа: {bond_data['platform']}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    elif query.data == 'platform_sensbank':
        context.user_data['bond_platform'] = 'SENSBANK'
        # Аналогічний код для SENSBANK
        session = Session()
        bond = Bond(
            date=context.user_data['bond_date'],
            operation_type=context.user_data['bond_operation_type'],
            bond_number=context.user_data['bond_number'],
            maturity_date=context.user_data['bond_maturity_date'],
            price_per_unit=context.user_data['bond_price_per_unit'],
            quantity=context.user_data['bond_quantity'],
            total_amount=context.user_data['bond_total_amount'],
            platform='SENSBANK'
        )
        session.add(bond)
        session.commit()
        
        bond_data = {
            'date': bond.date,
            'operation_type': bond.operation_type,
            'bond_number': bond.bond_number,
            'maturity_date': bond.maturity_date,
            'price_per_unit': bond.price_per_unit,
            'quantity': bond.quantity,
            'total_amount': bond.total_amount,
            'platform': bond.platform
        }
        session.close()
        
        context.user_data.clear()
        
        keyboard = [[InlineKeyboardButton("🔙 Назад до ОВДП", callback_data='ovdp')]]
        await query.edit_message_text(
            f"✅ *ОВДП додано!*\n\n"
            f"📅 Дата: {bond_data['date']}\n"
            f"🔄 Тип: {bond_data['operation_type']}\n"
            f"🔢 Номер: {bond_data['bond_number']}\n"
            f"📆 Термін до: {bond_data['maturity_date']}\n"
            f"💰 Ціна: {bond_data['price_per_unit']} грн\n"
            f"📦 Кількість: {bond_data['quantity']}\n"
            f"💵 Сума: {bond_data['total_amount']} грн\n"
            f"🏦 Платформа: {bond_data['platform']}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: CallbackContext):
    # Додавання ОВДП
    if context.user_data.get('adding_bond'):
        step = context.user_data.get('bond_step')
        
        if step == 'date_manual':
            context.user_data['bond_date'] = update.message.text
            context.user_data['bond_step'] = 'operation_type'
            keyboard = [
                [InlineKeyboardButton("🟢 Купівля", callback_data='bond_buy')],
                [InlineKeyboardButton("🔴 Продаж", callback_data='bond_sell')]
            ]
            await update.message.reply_text(
                f"📅 Дата: {update.message.text}\n\n📈 Виберіть тип операції:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        if step == 'date':
            context.user_data['bond_date'] = update.message.text
            context.user_data['bond_step'] = 'operation_type'
            keyboard = [
                [InlineKeyboardButton("🟢 Купівля", callback_data='bond_buy')],
                [InlineKeyboardButton("🔴 Продаж", callback_data='bond_sell')]
            ]
            await update.message.reply_text(
                "📈 Виберіть тип операції:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        elif step == 'operation_type':
            keyboard = [
                [InlineKeyboardButton("🟢 Купівля", callback_data='bond_buy')],
                [InlineKeyboardButton("🔴 Продаж", callback_data='bond_sell')]
            ]
            await update.message.reply_text(
                "📈 Виберіть тип операції:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
            
        elif step == 'bond_number':
            context.user_data['bond_number'] = update.message.text
            context.user_data['bond_step'] = 'maturity_date'
            await update.message.reply_text("📈 Введіть термін до (дату погашення ДД.ММ.РРРР):")
            
        elif step == 'maturity_date':
            date_value = update.message.text
            if '.' not in date_value:
                await update.message.reply_text("❌ Використовуйте крапку! Наприклад: 10.12.2025")
                return
            date_value = date_value.replace(',', '.')
            context.user_data['bond_maturity_date'] = date_value
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
                quantity = int(update.message.text)
                context.user_data['bond_quantity'] = quantity
                price = context.user_data.get('bond_price_per_unit', 0)
                total = quantity * price
                
                keyboard = [
                    [InlineKeyboardButton(f"✅ Прийняти {total} грн", callback_data='bond_confirm_amount')],
                    [InlineKeyboardButton("✏️ Ввести свою суму", callback_data='bond_edit_amount')]
                ]
                await update.message.reply_text(
                    f"📈 Розрахована сума: {total} грн\n\nОберіть дію:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                context.user_data['bond_step'] = 'confirm_amount'
            except:
                await update.message.reply_text("❌ Введіть ціле число:")
                
        elif step == 'total_amount_manual':
            try:
                context.user_data['bond_total_amount'] = float(update.message.text)
                context.user_data['bond_step'] = 'platform'
                keyboard = [
                    [InlineKeyboardButton("🏦 ICU", callback_data='platform_icu')],
                    [InlineKeyboardButton("🏦 SENSBANK", callback_data='platform_sensbank')]
                ]
                await update.message.reply_text(
                    "📈 Виберіть платформу:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await update.message.reply_text("❌ Введіть число:")
                
        elif step == 'platform':
            keyboard = [
                [InlineKeyboardButton("🏦 ICU", callback_data='platform_icu')],
                [InlineKeyboardButton("🏦 SENSBANK", callback_data='platform_sensbank')]
            ]
            await update.message.reply_text(
                "📈 Виберіть платформу:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
    
    # Старий код для товарів
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


async def sync_bonds_to_sheets(update: Update, context: CallbackContext):
    """Синхронізація даних ОВДП з Google Sheets"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔄 Синхронізація даних з Google Sheets...")
    
    try:
        if not Session or not sheets_manager:
            await query.edit_message_text("❌ Помилка підключення")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        
        if not bonds:
            await query.edit_message_text("⚠️ Немає даних для синхронізації")
            session.close()
            return
        
        # Експортуємо записи
        bonds_data = []
        for bond in bonds:
            bonds_data.append({
                'date': bond.date,
                'operation_type': bond.operation_type,
                'bond_number': bond.bond_number,
                'maturity_date': bond.maturity_date,
                'price_per_unit': bond.price_per_unit,
                'quantity': bond.quantity,
                'total_amount': bond.total_amount,
                'platform': bond.platform
            })
        
        sheets_manager.export_bonds_to_sheets(bonds_data)
        
        # Розраховуємо портфель (сумуємо по номерах ОВДП)
        portfolio = {}
        for bond in bonds:
            if bond.operation_type == 'купівля':
                num = bond.bond_number
                # Форматуємо дату: замінюємо кому на крапку
                maturity = bond.maturity_date.replace(',', '.')
                if num not in portfolio:
                    portfolio[num] = {
                        'bond_number': num,
                        'maturity_date': maturity,
                        'total_quantity': 0,
                        'total_amount': 0,
                        'total_price': 0
                    }
                portfolio[num]['total_quantity'] += bond.quantity
                portfolio[num]['total_amount'] += bond.total_amount
                portfolio[num]['total_price'] += bond.price_per_unit * bond.quantity

        # Розраховуємо середню ціну
        portfolio_data = []
        for num, data in portfolio.items():
            portfolio_data.append({
                'bond_number': num,
                'maturity_date': data['maturity_date'],
                'total_quantity': data['total_quantity'],
                'avg_price': round(data['total_amount'] / data['total_quantity'], 2) if data['total_quantity'] > 0 else 0,
                'total_amount': data['total_amount']
        })
        
        # Експортуємо портфель
        sheets_manager.export_bonds_portfolio(portfolio_data)
        
        session.close()
        await query.edit_message_text("✅ Синхронізація завершена успішно!")
    except Exception as e:
        logger.error(f"Sync error: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_bonds_list(update: Update, context: CallbackContext):
    """Показати список ОВДП"""
    query = update.callback_query
    await query.answer()
    
    try:
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bonds = session.query(Bond).order_by(Bond.date.desc()).limit(20).all()
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 У вас ще немає записів ОВДП")
            return
        
        text = "📋 *Останні 20 записів ОВДП:*\n\n"
        for i, bond in enumerate(bonds, 1):
            text += f"{i}. 📅 {bond.date} | {bond.operation_type}\n"
            text += f"   🔢 {bond.bond_number} | {bond.quantity} шт | {bond.total_amount} грн\n"
            text += f"   🏦 {bond.platform}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")

async def show_bonds_portfolio(update: Update, context: CallbackContext, platform=None):
    """Показати портфель ОВДП (опціонально з фільтром по платформі)"""
    query = update.callback_query
    await query.answer()
    
    try:
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 У вас ще немає записів ОВДП")
            return
        
        # Фільтруємо по платформі
        filtered_bonds = bonds
        platform_name = "Всі"
        if platform:
            filtered_bonds = [b for b in bonds if b.platform.upper() == platform.upper()]
                    # Тимчасове логування
            logger.info(f"=== Фільтр по платформі: {platform} ===")
            for b in bonds:
                logger.info(f"Bond: {b.bond_number}, platform: '{b.platform}'")
            logger.info(f"Знайдено після фільтра: {len(filtered_bonds)}")
            platform_name = platform
        
        if not filtered_bonds:
            await query.edit_message_text(f"📭 Немає записів для платформи {platform_name}")
            return
        
        # Розраховуємо портфель (тільки купівлі)
        portfolio = {}
        for bond in filtered_bonds:
            if bond.operation_type == 'купівля':
                num = bond.bond_number
                if num not in portfolio:
                    portfolio[num] = {
                        'bond_number': num,
                        'maturity_date': bond.maturity_date,
                        'total_quantity': 0,
                        'total_amount': 0
                    }
                portfolio[num]['total_quantity'] += bond.quantity
                portfolio[num]['total_amount'] += bond.total_amount
        
        if not portfolio:
            await query.edit_message_text(f"📭 Немає куплених ОВДП для платформи {platform_name}")
            return
        
        # Формуємо текст
        title = f"💼 *Портфель ОВДП*"
        if platform:
            title += f" - {platform_name}"
        text = f"{title}\n\n"
        total_invested = 0
        total_quantity = 0
        
        for num, data in portfolio.items():
            avg_price = data['total_amount'] / data['total_quantity'] if data['total_quantity'] > 0 else 0
            text += f"🔢 *{num}*\n"
            text += f"   📆 Термін: {data['maturity_date']}\n"
            text += f"   📦 Кількість: {data['total_quantity']} шт\n"
            text += f"   💰 Середня ціна: {avg_price:.2f} грн\n"
            text += f"   💵 Сума: {data['total_amount']:.2f} грн\n\n"
            total_invested += data['total_amount']
            total_quantity += data['total_quantity']
        
        text += f"━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 *Всього інвестовано:* {total_invested:.2f} грн\n"
        text += f"📊 *Всього облігацій:* {total_quantity} шт"
        
        # Додаємо кнопки фільтрації
        if platform:
            # Якщо фільтр активний - показуємо кнопку "Всі"
            keyboard = [
                [InlineKeyboardButton("🏦 Всі", callback_data='ovdp_portfolio'),
                 InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                 InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')],
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
            ]
        else:
            # Якщо фільтр не активний - показуємо тільки ICU та SENSBANK
            keyboard = [
                [InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                 InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')],
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
            ]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущений...")
    app.run_polling()

if __name__ == '__main__':
    main()
