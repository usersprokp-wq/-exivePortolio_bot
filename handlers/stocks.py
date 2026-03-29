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
    elif query.data == 'stocks_sync':
        await sync_stocks_to_sheets(update, context)
    elif query.data == 'stocks_sync_from_sheets':
        await sync_stocks_from_sheets(update, context)
    elif query.data.startswith('stocks_date_'):
        await handle_stock_date_selection(update, context)
    elif query.data.startswith('stocks_cal_'):
        await handle_calendar_navigation(update, context)
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
        [InlineKeyboardButton("🔄 Синхронізація", callback_data='stocks_sync')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def start_stock_add(update: Update, context: CallbackContext):
    """Розпочати додавання акції"""
    query = update.callback_query
    context.user_data['adding_stock'] = True
    context.user_data['stock_step'] = 'date'
    
    today = datetime.now()
    
    keyboard = [
        [InlineKeyboardButton(f"📅 Сьогодні ({today.strftime('%d.%m.%Y')})", callback_data=f'stocks_date_{today.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton("📅 Вибрати дату", callback_data='stocks_date_calendar')],
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
    
    if date_value == 'calendar':
        await show_calendar(update, context)
    elif date_value != 'manual':
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


async def show_calendar(update: Update, context: CallbackContext):
    """Показати календар для вибору дати"""
    query = update.callback_query
    
    if 'calendar_month' not in context.user_data:
        context.user_data['calendar_month'] = datetime.now()
    
    current_date = context.user_data['calendar_month']
    year = current_date.year
    month = current_date.month
    
    first_day = datetime(year, month, 1)
    last_day = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year + 1, 1, 1) - timedelta(days=1)
    start_weekday = first_day.weekday()
    
    keyboard = []
    
    month_name = first_day.strftime('%B %Y')
    nav_keyboard = [
        InlineKeyboardButton("◀️", callback_data=f'stocks_cal_prev_{year}_{month}'),
        InlineKeyboardButton(month_name, callback_data='stocks_cal_month'),
        InlineKeyboardButton("▶️", callback_data=f'stocks_cal_next_{year}_{month}')
    ]
    keyboard.append(nav_keyboard)
    
    days_of_week = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']
    keyboard.append([InlineKeyboardButton(day, callback_data='stocks_cal_dow') for day in days_of_week])
    
    day_buttons = []
    for _ in range(start_weekday):
        day_buttons.append(InlineKeyboardButton(" ", callback_data='stocks_cal_empty'))
    
    for day in range(1, last_day.day + 1):
        date_str = f"{day:02d}.{month:02d}.{year}"
        day_buttons.append(InlineKeyboardButton(str(day), callback_data=f'stocks_date_{date_str}'))
    
    for i in range(0, len(day_buttons), 7):
        keyboard.append(day_buttons[i:i+7])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')])
    
    await query.edit_message_text(
        "📅 *Виберіть дату:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_calendar_navigation(update: Update, context: CallbackContext):
    """Обробка навігації по календару"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('stocks_cal_prev_'):
        parts = query.data.replace('stocks_cal_prev_', '').split('_')
        year, month = int(parts[0]), int(parts[1])
        month -= 1
        if month < 1:
            month = 12
            year -= 1
        context.user_data['calendar_month'] = datetime(year, month, 1)
    
    elif query.data.startswith('stocks_cal_next_'):
        parts = query.data.replace('stocks_cal_next_', '').split('_')
        year, month = int(parts[0]), int(parts[1])
        month += 1
        if month > 12:
            month = 1
            year += 1
        context.user_data['calendar_month'] = datetime(year, month, 1)
    
    await show_calendar(update, context)


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
            name=context.user_data['ticker'],
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
            f"📊 Операція: {context.user_data['stock_operation_type'].capitalize()}\n"
            f"📈 Тікер: {context.user_data['ticker']}\n"
            f"💵 Ціна за шт: {context.user_data['price_per_unit']:.2f} $\n"
            f"📦 Кількість: {context.user_data['quantity']} шт\n"
            f"💰 Сума: {context.user_data['total_amount']:.2f} $\n"
            f"💸 Комісія: {context.user_data.get('commission', 0):.2f} $\n"
            f"📊 Біржа: {context.user_data['platform']}",
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
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        stocks = session.query(Stock).all()
        session.close()
        
        if not stocks:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
            await query.edit_message_text("📭 Портфель пустий", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Розраховуємо портфель
        portfolio = {}
        for stock in stocks:
            if stock.ticker not in portfolio:
                portfolio[stock.ticker] = {
                    'total_quantity': 0,
                    'total_amount': 0,
                    'platform': stock.platform
                }
            
            if stock.operation_type == 'купівля':
                portfolio[stock.ticker]['total_quantity'] += stock.quantity
                portfolio[stock.ticker]['total_amount'] += stock.total_amount
            else:
                portfolio[stock.ticker]['total_quantity'] -= stock.quantity
                portfolio[stock.ticker]['total_amount'] -= stock.total_amount
        
        # Залишаємо тільки активні позиції
        portfolio = {k: v for k, v in portfolio.items() if v['total_quantity'] > 0}
        
        if not portfolio:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
            await query.edit_message_text("📭 Портфель пустий", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        text = "💼 *Портфель Акцій*\n\n"
        total_invested = 0
        
        for ticker, data in sorted(portfolio.items()):
            avg_price = data['total_amount'] / data['total_quantity'] if data['total_quantity'] > 0 else 0
            text += f"📈 *{ticker}*\n"
            text += f"   📦 Кількість: {data['total_quantity']} шт\n"
            text += f"   💰 Ціна: {avg_price:.2f} грн\n"
            text += f"   💵 Сума: {data['total_amount']:.2f} грн\n"
            text += f"   🏦 Платформа: {data['platform']}\n\n"
            total_invested += data['total_amount']
        
        text += f"━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 *Всього інвестовано:* {total_invested:.2f} грн"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def sync_stocks_to_sheets(update: Update, context: CallbackContext):
    """Синхронізація Акцій БД → Excel"""
    query = update.callback_query
    await query.answer()
    
    try:
        sheets_manager = context.bot_data.get('sheets_manager')
        Session = context.bot_data.get('Session')
        
        if not sheets_manager or not Session:
            await query.edit_message_text("❌ Помилка: Google Sheets або БД не доступні")
            return
        
        session = Session()
        stocks = session.query(Stock).all()
        session.close()
        
        if not stocks:
            await query.edit_message_text("📭 Немає даних для синхронізації")
            return
        
        # Готуємо дані
        stocks_data = []
        for stock in stocks:
            stocks_data.append({
                'date': stock.date,
                'platform': stock.platform,
                'operation_type': stock.operation_type,
                'ticker': stock.ticker,
                'name': stock.name,
                'price_per_unit': stock.price_per_unit,
                'quantity': stock.quantity,
                'commission': 0,
                'total_amount': stock.total_amount,
                'pnl': 0
            })
        
        # Експортуємо в Google Sheets
        sheets_manager.export_stocks_to_sheets(stocks_data)
        
        # Готуємо портфель
        portfolio = {}
        for stock in stocks:
            if stock.ticker not in portfolio:
                portfolio[stock.ticker] = {
                    'total_quantity': 0,
                    'total_amount': 0,
                    'platform': stock.platform
                }
            
            if stock.operation_type == 'купівля':
                portfolio[stock.ticker]['total_quantity'] += stock.quantity
                portfolio[stock.ticker]['total_amount'] += stock.total_amount
            else:
                portfolio[stock.ticker]['total_quantity'] -= stock.quantity
                portfolio[stock.ticker]['total_amount'] -= stock.total_amount
        
        portfolio = {k: v for k, v in portfolio.items() if v['total_quantity'] > 0}
        
        portfolio_data = []
        for ticker, data in portfolio.items():
            avg_price = data['total_amount'] / data['total_quantity'] if data['total_quantity'] > 0 else 0
            portfolio_data.append({
                'ticker': ticker,
                'total_quantity': data['total_quantity'],
                'avg_price': avg_price,
                'total_amount': data['total_amount'],
                'platform': data['platform'],
                'pnl_percent': 0
            })
        
        sheets_manager.export_stocks_portfolio(portfolio_data)
        
        await query.edit_message_text(
            f"✅ Синхронізовано!\n\n"
            f"📋 Записів: {len(stocks_data)}\n"
            f"💼 Акцій в портфелі: {len(portfolio_data)}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error syncing stocks: {e}")
        await query.edit_message_text(f"❌ Помилка синхронізації: {str(e)}")


async def sync_stocks_from_sheets(update: Update, context: CallbackContext):
    """Синхронізація Акцій Excel → БД"""
    query = update.callback_query
    await query.answer()
    
    try:
        sheets_manager = context.bot_data.get('sheets_manager')
        Session = context.bot_data.get('Session')
        
        if not sheets_manager or not Session:
            await query.edit_message_text("❌ Помилка: Google Sheets або БД не доступні")
            return
        
        # Імпортуємо дані з Google Sheets
        excel_stocks_data = sheets_manager.import_stocks_from_sheets()
        
        if not excel_stocks_data:
            await query.edit_message_text("📭 Немає даних в Excel для синхронізації")
            return
        
        session = Session()
        
        # 1. ВИДАЛЯЄМО ВСЕ з БД
        try:
            session.query(Stock).delete()
            session.commit()
            deleted = len(excel_stocks_data)
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting stocks: {e}")
            deleted = 0
        
        # 2. ДОДАЄМО рядки з Excel у ТОЧНОМУ ПОРЯДКУ
        added = 0
        errors = []
        
        for row_idx, stock_data in enumerate(excel_stocks_data):
            try:
                new_stock = Stock(
                    date=stock_data.get('date', ''),
                    operation_type=stock_data.get('operation_type', ''),
                    ticker=stock_data.get('ticker', ''),
                    name=stock_data.get('name', ''),
                    price_per_unit=float(stock_data.get('price_per_unit', 0)),
                    quantity=int(stock_data.get('quantity', 0)),
                    total_amount=float(stock_data.get('total_amount', 0)),
                    platform=stock_data.get('platform', '')
                )
                session.add(new_stock)
                added += 1
            except Exception as e:
                errors.append(f"Помилка рядка {row_idx + 1} ({stock_data.get('ticker')}): {str(e)}")
        
        # 3. ЗБЕРІГАЄМО
        try:
            session.commit()
            session.close()
        except Exception as e:
            session.rollback()
            session.close()
            logger.error(f"Error committing: {e}")
            await query.edit_message_text(f"❌ Помилка збереження: {str(e)}")
            return
        
        # Формуємо відповідь
        text = "🔄 *Синхронізація Excel → БД завершена*\n\n"
        text += f"❌ Видалено: {deleted}\n"
        text += f"✅ Додано: {added}\n\n"
        
        if errors:
            text += f"⚠️ Помилок: {len(errors)}\n"
            for error in errors[:5]:
                text += f"   • {error}\n"
            if len(errors) > 5:
                text += f"   • ... та ще {len(errors) - 5} помилок\n"
        else:
            text += "✨ Без помилок!"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in sync_stocks_from_sheets: {e}")
        await query.edit_message_text(f"❌ Помилка синхронізації: {str(e)}")


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
                context.user_data['stock_step'] = 'commission'
                await update.message.reply_text("💸 Введіть комісію за транзакцію:")
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'commission':
            try:
                commission = float(user_message)
                context.user_data['commission'] = commission
                context.user_data['stock_step'] = 'platform'
                keyboard = [
                    [InlineKeyboardButton("📊 FF", callback_data='stock_platform_ff')],
                    [InlineKeyboardButton("📊 IB", callback_data='stock_platform_ib')]
                ]
                await update.message.reply_text(
                    f"💵 Сума: {context.user_data['total_amount']:.2f} $\n"
                    f"💸 Комісія: {commission:.2f} $\n\n📊 Виберіть біржу:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
    
    except Exception as e:
        logger.error(f"Error in handle_message_stocks: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")