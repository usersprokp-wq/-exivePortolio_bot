import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock

logger = logging.getLogger(__name__)


async def button_handler_stocks(update: Update, context: CallbackContext):
    """Обробник кнопок для Акцій"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'stocks':
        await show_stocks_menu(update, context)
    elif query.data == 'stocks_add':
        await start_stock_add(update, context)
    elif query.data == 'stocks_list':
        await show_stocks_list(update, context)
    elif query.data == 'stocks_portfolio':
        await show_stocks_portfolio(update, context)
    elif query.data == 'stocks_stats':
        await show_stocks_stats(update, context)
    elif query.data == 'stocks_profit':
        await show_stocks_profit(update, context)
    elif query.data.startswith('stocks_date_'):
        await handle_stock_date_selection(update, context)
    elif query.data == 'stock_buy':
        context.user_data['stock_operation_type'] = 'купівля'
        context.user_data['stock_step'] = 'ticker'
        await query.edit_message_text("📈 Введіть тікер акції (наприклад: GAZP):", parse_mode='Markdown')
    elif query.data == 'stock_sell':
        context.user_data['stock_operation_type'] = 'продаж'
        context.user_data['stock_step'] = 'ticker'
        await query.edit_message_text("📈 Введіть тікер акції для продажу:", parse_mode='Markdown')
    elif query.data.startswith('stock_platform_'):
        platform = query.data.replace('stock_platform_', '')
        context.user_data['platform'] = platform.upper()
        await save_stock(update, context)


async def show_stocks_menu(update: Update, context: CallbackContext):
    """Показати меню Акцій"""
    query = update.callback_query
    text = "📊 *Акції*\n\nОберіть дію:"
    keyboard = [
        [InlineKeyboardButton("➕ Додати запис", callback_data='stocks_add')],
        [InlineKeyboardButton("📋 Мої записи", callback_data='stocks_list')],
        [InlineKeyboardButton("💼 Портфель", callback_data='stocks_portfolio')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stocks_stats')],
        [InlineKeyboardButton("💰 Прибуток", callback_data='stocks_profit')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def start_stock_add(update: Update, context: CallbackContext):
    """Розпочати додавання акції"""
    query = update.callback_query
    context.user_data['adding_stock'] = True
    context.user_data['stock_step'] = 'date'
    
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    three_days = today + timedelta(days=3)
    week = today + timedelta(days=7)
    
    keyboard = [
        [InlineKeyboardButton(f"📅 Сьогодні ({today.strftime('%d.%m.%Y')})", callback_data=f'stocks_date_{today.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton(f"📅 Завтра ({tomorrow.strftime('%d.%m.%Y')})", callback_data=f'stocks_date_{tomorrow.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton(f"📅 За 3 дні ({three_days.strftime('%d.%m.%Y')})", callback_data=f'stocks_date_{three_days.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton(f"📅 Через тиждень ({week.strftime('%d.%m.%Y')})", callback_data=f'stocks_date_{week.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton("📅 Вручну", callback_data='stocks_date_manual')],
        [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
    ]
    await query.edit_message_text(
        "📊 *Додавання акції*\n\n📅 Виберіть дату операції:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_stock_date_selection(update: Update, context: CallbackContext):
    """Обробка вибору дати для акцій"""
    query = update.callback_query
    date_value = query.data.replace('stocks_date_', '')
    
    if date_value != 'manual':
        context.user_data['stock_date'] = date_value
        context.user_data['stock_step'] = 'operation_type'
        keyboard = [
            [InlineKeyboardButton("🟢 Купівля", callback_data='stock_buy')],
            [InlineKeyboardButton("🔴 Продаж", callback_data='stock_sell')]
        ]
        await query.edit_message_text(
            f"📅 Дата: {date_value}\n\n📈 Виберіть тип операції:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        context.user_data['stock_step'] = 'date_manual'
        await query.edit_message_text("📅 Введіть дату вручну (у форматі ДД.ММ.РРРР):", parse_mode='Markdown')


async def save_stock(update: Update, context: CallbackContext):
    """Зберігає акцію в базу даних"""
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await update.callback_query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        stock = Stock(
            date=context.user_data['stock_date'],
            operation_type=context.user_data['stock_operation_type'],
            ticker=context.user_data['ticker'],
            name=context.user_data['name'],
            price_per_unit=context.user_data['price_per_unit'],
            quantity=context.user_data['quantity'],
            total_amount=context.user_data['total_amount'],
            platform=context.user_data['platform']
        )
        session.add(stock)
        session.commit()
        session.close()
        
        await update.callback_query.edit_message_text(
            f"✅ *Запис додано!*\n\n"
            f"📅 Дата: {context.user_data['stock_date']}\n"
            f"📈 Операція: {context.user_data['stock_operation_type'].capitalize()}\n"
            f"📊 Тікер: {context.user_data['ticker']}\n"
            f"📝 Назва: {context.user_data['name']}\n"
            f"💵 Ціна за шт: {context.user_data['price_per_unit']:.2f} грн\n"
            f"📦 Кількість: {context.user_data['quantity']} шт\n"
            f"💰 Сума: {context.user_data['total_amount']:.2f} грн\n"
            f"🏦 Платформа: {context.user_data['platform']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад до Акцій", callback_data='stocks')]
            ]),
            parse_mode='Markdown'
        )
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error saving stock: {e}")
        await update.callback_query.edit_message_text(f"❌ Помилка при збереженні: {str(e)}")


async def show_stocks_list(update: Update, context: CallbackContext):
    """Показати список записів акцій"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        stocks = session.query(Stock).all()
        session.close()
        
        if not stocks:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
            await query.edit_message_text("📭 Немає записів", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        text = f"📋 *Мої записи Акцій*\n\n"
        for stock in stocks:
            text += f"📅 {stock.date} | "
            text += f"{'🟢' if stock.operation_type == 'купівля' else '🔴'} {stock.operation_type}\n"
            text += f"   📈 {stock.ticker} | {stock.name} | 💰 {stock.total_amount:.2f} грн | {stock.platform}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_stocks_portfolio(update: Update, context: CallbackContext):
    """Показати портфель акцій"""
    query = update.callback_query
    await query.answer()
    
    try:
        await query.edit_message_text("🚧 Портфель акцій - в розробці", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]), parse_mode='Markdown')
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_stocks_stats(update: Update, context: CallbackContext):
    """Показати статистику акцій"""
    query = update.callback_query
    await query.answer()
    
    try:
        await query.edit_message_text("🚧 Статистика акцій - в розробці", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]), parse_mode='Markdown')
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_stocks_profit(update: Update, context: CallbackContext):
    """Показати прибуток від акцій"""
    query = update.callback_query
    await query.answer()
    
    try:
        await query.edit_message_text("🚧 Прибуток акцій - в розробці", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]), parse_mode='Markdown')
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_message_stocks(update: Update, context: CallbackContext):
    """Обробка текстових повідомлень для Акцій"""
    if 'stock_step' not in context.user_data:
        return
    
    user_message = update.message.text
    step = context.user_data.get('stock_step')
    
    try:
        if step == 'date_manual':
            try:
                datetime.strptime(user_message, '%d.%m.%Y')
                context.user_data['stock_date'] = user_message
                context.user_data['stock_step'] = 'operation_type'
                keyboard = [
                    [InlineKeyboardButton("🟢 Купівля", callback_data='stock_buy')],
                    [InlineKeyboardButton("🔴 Продаж", callback_data='stock_sell')]
                ]
                await update.message.reply_text(
                    f"📅 Дата: {user_message}\n\n📈 Виберіть тип операції:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.message.reply_text("❌ Невірний формат дати. Будь ласка, введіть у форматі ДД.ММ.РРРР")
        
        elif step == 'ticker':
            context.user_data['ticker'] = user_message.upper()
            context.user_data['stock_step'] = 'stock_name'
            await update.message.reply_text("📝 Введіть назву акції:")
        
        elif step == 'stock_name':
            context.user_data['name'] = user_message
            context.user_data['stock_step'] = 'price_per_unit'
            await update.message.reply_text("💰 Введіть ціну за одну акцію:")
        
        elif step == 'price_per_unit':
            try:
                price = float(user_message)
                context.user_data['price_per_unit'] = price
                context.user_data['stock_step'] = 'quantity'
                await update.message.reply_text("📦 Введіть кількість акцій:")
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'quantity':
            try:
                quantity = int(user_message)
                context.user_data['quantity'] = quantity
                total_amount = context.user_data['price_per_unit'] * quantity
                context.user_data['total_amount'] = total_amount
                context.user_data['stock_step'] = 'platform'
                keyboard = [
                    [InlineKeyboardButton("🏦 FUIB", callback_data='stock_platform_fuib')],
                    [InlineKeyboardButton("🏦 ALFABANK", callback_data='stock_platform_alfabank')],
                    [InlineKeyboardButton("🏦 ІНШЕ", callback_data='stock_platform_other')]
                ]
                await update.message.reply_text(
                    f"💵 Сума: {total_amount:.2f} грн\n\n🏦 Виберіть платформу:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
    
    except Exception as e:
        logger.error(f"Error in handle_message_stocks: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")