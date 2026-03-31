import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock, StockPortfolio, StockProfitRecord

logger = logging.getLogger(__name__)


async def recalculate_portfolio(Session):
    """Пересчитати портфель з записів stocks та заповнити stock_portfolio (FIFO)"""
    try:
        session = Session()
        
        # Видаляємо старі дані
        session.query(StockPortfolio).delete()
        session.commit()
        
        # Отримуємо всі записи з stocks
        stocks = session.query(Stock).all()
        
        if not stocks:
            session.close()
            return
        
        # Сортуємо по даті (старі спочатку) для FIFO
        def parse_date(date_str):
            try:
                return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
            except:
                return datetime.min
        
        stocks = sorted(stocks, key=lambda x: (parse_date(x.date), 0 if x.operation_type == 'купівля' else 1))
        
        # FIFO черга для кожного тікера
        from collections import deque
        buy_queues = {}  # ticker -> deque of {'price': ..., 'quantity': ..., 'platform': ...}
        
        for stock in stocks:
            ticker = stock.ticker
            if ticker not in buy_queues:
                buy_queues[ticker] = {'queue': deque(), 'platform': stock.platform}
            
            if stock.operation_type == 'купівля':
                price_per_unit = stock.total_amount / stock.quantity if stock.quantity > 0 else 0
                buy_queues[ticker]['queue'].append({
                    'price': price_per_unit,
                    'quantity': stock.quantity
                })
                buy_queues[ticker]['platform'] = stock.platform
            
            else:  # продаж — списуємо по FIFO
                remaining = stock.quantity
                while remaining > 0 and buy_queues[ticker]['queue']:
                    buy = buy_queues[ticker]['queue'][0]
                    qty_to_sell = min(remaining, buy['quantity'])
                    buy['quantity'] -= qty_to_sell
                    remaining -= qty_to_sell
                    if buy['quantity'] == 0:
                        buy_queues[ticker]['queue'].popleft()
        
        # Формуємо портфель з залишків в чергах
        for ticker, data in buy_queues.items():
            total_quantity = sum(b['quantity'] for b in data['queue'])
            total_amount = sum(b['price'] * b['quantity'] for b in data['queue'])
            
            if total_quantity > 0:
                avg_price = total_amount / total_quantity
                portfolio_record = StockPortfolio(
                    ticker=ticker,
                    total_quantity=total_quantity,
                    total_amount=total_amount,
                    avg_price=avg_price,
                    platform=data['platform'],
                    last_update=datetime.now().isoformat()
                )
                session.add(portfolio_record)
        
        session.commit()
        
        # Перераховуємо процентовку
        recalculate_percents(session)
        
        session.close()
        logger.info(f"Портфель пересчитаний (FIFO)")
        
    except Exception as e:
        logger.error(f"Error recalculating portfolio: {e}")


def recalculate_percents(session):
    """Перераховує % кожної акції від загальної суми портфеля"""
    try:
        all_records = session.query(StockPortfolio).all()
        total_sum = sum(r.total_amount for r in all_records) if all_records else 0
        
        for record in all_records:
            record.percent = (record.total_amount / total_sum * 100) if total_sum > 0 else 0
        
        session.commit()
    except Exception as e:
        logger.error(f"Error recalculating percents: {e}")


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
    elif query.data.startswith('stocks_list_page_'):
        page = int(query.data.replace('stocks_list_page_', ''))
        await show_stocks_list(update, context, page=page)
    elif query.data == 'stocks_portfolio':
        await show_stocks_portfolio(update, context)
    elif query.data == 'stocks_stats':
        await show_stocks_stats(update, context)
    elif query.data == 'stocks_dividends':
        await query.edit_message_text("🚧 Дивіденди - в розробці", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]), parse_mode='Markdown')
    elif query.data == 'stocks_check_pnl':
        await query.edit_message_text("🚧 Взнати PnL - в розробці", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]), parse_mode='Markdown')
    elif query.data == 'stocks_profit':
        await show_stocks_profit(update, context)
    elif query.data == 'stocks_write_off_profit':
        await write_off_stocks_profit_menu(update, context)
    elif query.data == 'stocks_confirm_write_off':
        context.user_data['profit_step'] = 'enter_amount'
        await query.edit_message_text("💰 Введіть суму для списання:", parse_mode='Markdown')
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
        await show_sell_stock_selection(update, context)
    elif query.data.startswith('sell_stock_'):
        ticker = query.data.replace('sell_stock_', '')
        await handle_sell_stock_selected(update, context, ticker)
    elif query.data.startswith('stock_platform_'):
        platform = query.data.replace('stock_platform_', '')
        context.user_data['platform'] = platform.upper()
        await save_stock(update, context)
    elif query.data == 'portfolio_ff':
        await show_stocks_portfolio(update, context, platform='FF')
    elif query.data == 'portfolio_ib':
        await show_stocks_portfolio(update, context, platform='IB')
    elif query.data == 'portfolio_all':
        await show_stocks_portfolio(update, context, platform=None)
    elif query.data == 'update_balance':
        text = "💵 *Оновити залишок*\n\nОберіть біржу:"
        keyboard = [
            [InlineKeyboardButton("📊 FF", callback_data='balance_platform_ff')],
            [InlineKeyboardButton("📊 IB", callback_data='balance_platform_ib')],
            [InlineKeyboardButton("🔙 Назад", callback_data='stocks_portfolio')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    elif query.data.startswith('balance_platform_'):
        platform = query.data.replace('balance_platform_', '').upper()
        context.user_data['balance_platform'] = platform
        context.user_data['stock_step'] = 'balance_amount'
        ticker = f"{platform}usd"
        
        # Показуємо поточний залишок
        Session = context.bot_data.get('Session')
        if Session:
            session = Session()
            current = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()
            session.close()
            current_amount = current.total_amount if current else 0
        else:
            current_amount = 0
        
        await query.edit_message_text(
            f"💵 *Залишок {platform}*\n\n"
            f"Поточний залишок: {current_amount:.2f} $\n\n"
            f"Введіть нову суму залишку:",
            parse_mode='Markdown'
        )


async def show_stocks_menu(update: Update, context: CallbackContext):
    """Показати меню Акцій"""
    query = update.callback_query
    text = "📊 *Акції*\n\nОберіть дію:"
    keyboard = [
        [InlineKeyboardButton("➕ Додати запис", callback_data='stocks_add')],
        [InlineKeyboardButton("📋 Мої записи", callback_data='stocks_list')],
        [InlineKeyboardButton("💼 Портфель", callback_data='stocks_portfolio')],
        [InlineKeyboardButton("💰 Прибуток", callback_data='stocks_profit')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stocks_stats')],
        [InlineKeyboardButton("💵 Дивіденди", callback_data='stocks_dividends')],
        [InlineKeyboardButton("📈 Взнати PnL", callback_data='stocks_check_pnl')],
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
    """Зберігає акцію в базу даних та оновлює портфель"""
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await update.callback_query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        
        operation_type = context.user_data['stock_operation_type']
        commission = context.user_data.get('commission', 0)
        pnl = context.user_data.get('pnl', 0) if operation_type == 'продаж' else 0
        ticker = context.user_data['ticker']
        quantity = context.user_data['quantity']
        total_amount = context.user_data['total_amount']
        platform = context.user_data['platform']
        
        stock = Stock(
            date=context.user_data['stock_date'],
            operation_type=operation_type,
            ticker=ticker,
            name=ticker,
            price_per_unit=context.user_data['price_per_unit'],
            quantity=quantity,
            total_amount=total_amount,
            platform=platform,
            pnl=pnl
        )
        session.add(stock)
        session.commit()
        
        # Точкове оновлення портфеля — тільки цей тікер
        portfolio = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()
        
        if operation_type == 'купівля':
            if not portfolio:
                portfolio = StockPortfolio(
                    ticker=ticker,
                    total_quantity=quantity,
                    total_amount=total_amount,
                    avg_price=total_amount / quantity if quantity > 0 else 0,
                    platform=platform,
                    last_update=datetime.now().isoformat()
                )
                session.add(portfolio)
            else:
                portfolio.total_quantity += quantity
                portfolio.total_amount += total_amount
                portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity if portfolio.total_quantity > 0 else 0
                portfolio.last_update = datetime.now().isoformat()
        
        elif operation_type == 'продаж':
            if portfolio:
                portfolio.total_quantity -= quantity
                # Віднімаємо по середній ціні купівлі, а не по ціні продажу
                portfolio.total_amount -= (context.user_data['sell_avg_price'] * quantity)
                
                if portfolio.total_quantity <= 0:
                    session.delete(portfolio)
                else:
                    portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity if portfolio.total_quantity > 0 else 0
                    portfolio.last_update = datetime.now().isoformat()
        
        session.commit()
        
        # Перераховуємо процентовку всіх акцій
        recalculate_percents(session)
        
        session.close()
        text = (
            f"✅ *Запис додано!*\n\n"
            f"📅 Дата: {context.user_data['stock_date']}\n"
            f"📊 Операція: {operation_type.capitalize()}\n"
            f"📈 Тікер: {ticker}\n"
            f"💵 Ціна за шт: {context.user_data['price_per_unit']:.3f} $\n"
            f"📦 Кількість: {quantity} шт\n"
            f"💰 Загальна сума: {total_amount:.2f} $\n"
            f"💸 Комісія: {commission:.2f} $\n"
            f"📊 Біржа: {platform}"
        )
        
        if operation_type == 'продаж':
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            text += f"\n\n{pnl_emoji} *PnL: {pnl:+.2f} $*"
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад до Акцій", callback_data='stocks')]
            ]),
            parse_mode='Markdown'
        )
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error saving stock: {e}")
        await update.callback_query.edit_message_text(f"❌ Помилка при збереженні: {str(e)}")


async def show_stocks_list(update: Update, context: CallbackContext, page=1):
    """Показати список записів акцій з пагінацією"""
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
        
        # Сортуємо по даті: нові спочатку
        def parse_date(date_str):
            try:
                return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
            except:
                return datetime.min
        
        stocks.sort(key=lambda x: (parse_date(x.date), x.id), reverse=True)
        
        # Пагінація — по 10 записів на сторінку
        records_per_page = 10
        total_pages = (len(stocks) + records_per_page - 1) // records_per_page
        
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        start_idx = (page - 1) * records_per_page
        end_idx = start_idx + records_per_page
        page_stocks = stocks[start_idx:end_idx]
        
        text = f"📋 *Мої записи Акцій* (сторінка {page}/{total_pages})\n\n"
        for stock in page_stocks:
            text += f"📅 {stock.date} | {'🟢' if stock.operation_type == 'купівля' else '🔴'} {stock.operation_type} | {stock.platform}\n"
            text += f"   📈 {stock.ticker} | {stock.quantity} шт | {stock.total_amount:.2f} $\n\n"
        
        keyboard = []
        
        if total_pages > 1:
            page_buttons = []
            for p in range(1, total_pages + 1):
                if p == page:
                    page_buttons.append(InlineKeyboardButton(f"[{p}]", callback_data=f'stocks_list_page_{p}'))
                else:
                    page_buttons.append(InlineKeyboardButton(str(p), callback_data=f'stocks_list_page_{p}'))
            keyboard.append(page_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_stocks_portfolio(update: Update, context: CallbackContext, platform=None):
    """Показати портфель акцій з таблиці stock_portfolio"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        # Беремо дані прямо з таблиці stock_portfolio
        portfolio_records = session.query(StockPortfolio).order_by(StockPortfolio.last_update.desc()).all()
        session.close()
        
        if not portfolio_records:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
            await query.edit_message_text("📭 Портфель пустий", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Фільтруємо по біржі якщо вибрана
        if platform:
            platform = platform.upper()
            portfolio_records = [p for p in portfolio_records if p.platform == platform]
            if not portfolio_records:
                keyboard = [
                    [InlineKeyboardButton("📊 FF", callback_data='portfolio_ff'), InlineKeyboardButton("📊 IB", callback_data='portfolio_ib')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
                ]
                try:
                    await query.edit_message_text(f"📭 Немає акцій на біржі {platform}", reply_markup=InlineKeyboardMarkup(keyboard))
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
                return
        
        text = "💼 *Портфель Акцій*\n\n"
        total_invested = 0
        
        # Відокремлюємо акції від залишків
        stock_records = [r for r in portfolio_records if not r.ticker.endswith('usd')]
        balance_records = [r for r in portfolio_records if r.ticker.endswith('usd')]
        
        stock_records.sort(key=lambda r: r.total_amount, reverse=True)
        for record in stock_records:
            pct = record.percent or 0
            text += f"📈 *{record.ticker}* ({pct:.1f}%)\n"
            text += f"   📦 Кількість: {record.total_quantity} шт\n"
            text += f"   💰 Ціна: {record.avg_price:.2f} $\n"
            text += f"   💵 Сума: {record.total_amount:.2f} $\n\n"
            total_invested += record.total_amount
        
        if balance_records:
            text += f"💵 *Залишки на рахунках:*\n"
            for br in balance_records:
                pct = br.percent or 0
                text += f"   {br.ticker}: {br.total_amount:.2f} $ ({pct:.1f}%)\n"
                total_invested += br.total_amount
            text += "\n"
        
        text += f"━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 *Всього інвестовано:* {total_invested:.2f} $"
        
        # Генеруємо кнопки в залежності від фільтру
        if platform:
            # Якщо вибрана біржа - показуємо "Всі акції" та іншу біржу
            other_platform = 'IB' if platform == 'FF' else 'FF'
            keyboard = [
                [InlineKeyboardButton("📊 Всі акції", callback_data='portfolio_all'), InlineKeyboardButton(f"📊 {other_platform}", callback_data=f'portfolio_{other_platform.lower()}')],
                [InlineKeyboardButton("💵 Оновити залишок", callback_data='update_balance')],
                [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
            ]
        else:
            # Якщо показуємо всі - показуємо обидві біржі
            keyboard = [
                [InlineKeyboardButton("📊 FF", callback_data='portfolio_ff'), InlineKeyboardButton("📊 IB", callback_data='portfolio_ib')],
                [InlineKeyboardButton("💵 Оновити залишок", callback_data='update_balance')],
                [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
            ]
        
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception as e:
            error_msg = str(e).lower()
            if "not modified" in error_msg or "400" in error_msg:
                await query.answer(f"📊 Портфель: {len(portfolio_records)} акцій" + (f" на {platform}" if platform else ""), show_alert=False)
            else:
                logger.error(f"Edit error: {e}")
                await query.answer("❌ Помилка оновлення", show_alert=True)
        
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
        
        if not stocks:
            session.close()
            await query.edit_message_text("📭 Немає даних для синхронізації")
            return
        
        # Сортуємо по даті: старі зверху, нові знизу
        def parse_date(date_str):
            try:
                return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
            except:
                return datetime.min
        
        stocks = sorted(stocks, key=lambda x: parse_date(x.date), reverse=False)
        
        # Готуємо дані записів
        stocks_data = []
        for stock in stocks:
            stocks_data.append({
                'date': stock.date,
                'platform': stock.platform,
                'operation_type': stock.operation_type,
                'ticker': stock.ticker,
                'name': stock.ticker,
                'price_per_unit': stock.price_per_unit,
                'quantity': stock.quantity,
                'total_amount': stock.total_amount,
                'pnl': stock.pnl or 0
            })
        
        # Експортуємо записи в Google Sheets
        sheets_manager.export_stocks_to_sheets(stocks_data)
        
        # Беремо портфель з stock_portfolio
        portfolio_records = session.query(StockPortfolio).all()
        session.close()
        
        portfolio_data = []
        for record in portfolio_records:
            portfolio_data.append({
                'ticker': record.ticker,
                'total_quantity': record.total_quantity,
                'avg_price': record.avg_price,
                'total_amount': record.total_amount,
                'platform': record.platform,
                'percent': record.percent or 0
            })
        
        sheets_manager.export_stocks_portfolio(portfolio_data)
        
        text = (
            f"✅ Синхронізовано!\n\n"
            f"📋 Записів: {len(stocks_data)}\n"
            f"💼 Акцій в портфелі: {len(portfolio_data)}"
        )
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync_stocks')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
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
        
        # 2. Сортуємо по даті (нові спочатку)
        def parse_date_for_sort(stock_data):
            try:
                return datetime.strptime(str(stock_data.get('date', '')).strip(), '%d.%m.%Y')
            except:
                return datetime.min
        
        excel_stocks_data.sort(key=parse_date_for_sort, reverse=True)
        
        # 3. ДОДАЄМО рядки в БД з row_order
        added = 0
        errors = []
        
        for row_idx, stock_data in enumerate(excel_stocks_data):
            try:
                new_stock = Stock(
                    row_order=row_idx + 1,
                    date=stock_data.get('date', ''),
                    operation_type=stock_data.get('operation_type', ''),
                    ticker=stock_data.get('ticker', ''),
                    name=stock_data.get('name', ''),
                    price_per_unit=float(stock_data.get('price_per_unit', 0)),
                    quantity=int(stock_data.get('quantity', 0)),
                    total_amount=float(stock_data.get('total_amount', 0)),
                    platform=stock_data.get('platform', ''),
                    pnl=float(stock_data.get('pnl', 0))
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
            text += "✨ Без помилок!\n\n"
        
        # Пересчитуємо портфель
        text += "⏳ Пересчитую портфель..."
        await query.edit_message_text(text, parse_mode='Markdown')
        
        session = Session()
        
        # 1. Рахуємо залишки по записах (тікер + платформа → кількість)
        all_stocks = session.query(Stock).all()
        from collections import defaultdict
        calculated_remains = defaultdict(lambda: {'quantity': 0})
        
        for stock in all_stocks:
            key = (stock.ticker, stock.platform.upper() if stock.platform else '')
            if stock.operation_type == 'купівля':
                calculated_remains[key]['quantity'] += stock.quantity
            else:
                calculated_remains[key]['quantity'] -= stock.quantity
        
        # Тільки активні позиції
        calculated_remains = {k: v for k, v in calculated_remains.items() if v['quantity'] > 0}
        
        # 2. Імпортуємо портфель з Excel
        excel_portfolio = sheets_manager.import_stocks_portfolio_from_sheets()
        
        # Формуємо словник Excel-портфеля по ключу (тікер, платформа)
        excel_dict = {}
        for item in excel_portfolio:
            key = (item['ticker'], item.get('platform', '').upper())
            excel_dict[key] = item
        
        # 3. Очищаємо таблицю портфеля
        session.query(StockPortfolio).delete()
        session.commit()
        
        matched = 0
        recalculated = 0
        
        # 4. Порівнюємо і заповнюємо портфель
        for (ticker, platform), calc_data in calculated_remains.items():
            key = (ticker, platform)
            excel_item = excel_dict.get(key)
            
            if excel_item and excel_item['total_quantity'] == calc_data['quantity']:
                # Збігається → беремо з Excel
                record = StockPortfolio(
                    ticker=ticker,
                    total_quantity=excel_item['total_quantity'],
                    total_amount=excel_item['total_amount'],
                    avg_price=excel_item['avg_price'],
                    platform=platform,
                    percent=0,
                    last_update=datetime.now().isoformat()
                )
                matched += 1
            else:
                # Не збігається → точковий перерахунок по середньозваженій
                total_qty = 0
                total_amt = 0
                
                stock_records = [s for s in all_stocks 
                                if s.ticker == ticker 
                                and (s.platform.upper() if s.platform else '') == platform]
                
                def parse_date(date_str):
                    try:
                        return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
                    except:
                        return datetime.min
                
                stock_records.sort(key=lambda x: (parse_date(x.date), 0 if x.operation_type == 'купівля' else 1))
                
                for s in stock_records:
                    if s.operation_type == 'купівля':
                        total_qty += s.quantity
                        total_amt += s.total_amount
                    else:
                        if total_qty > 0:
                            avg = total_amt / total_qty
                            total_amt -= avg * s.quantity
                            total_qty -= s.quantity
                
                avg_price = total_amt / total_qty if total_qty > 0 else 0
                
                record = StockPortfolio(
                    ticker=ticker,
                    total_quantity=total_qty,
                    total_amount=total_amt,
                    avg_price=avg_price,
                    platform=platform,
                    percent=0,
                    last_update=datetime.now().isoformat()
                )
                recalculated += 1
            
            session.add(record)
        
        # 5. Додаємо залишки (FFusd, IBusd) з Excel
        for item in excel_portfolio:
            if item['ticker'].endswith('usd'):
                record = StockPortfolio(
                    ticker=item['ticker'],
                    total_quantity=item.get('total_quantity', 1),
                    total_amount=item.get('total_amount', 0),
                    avg_price=item.get('avg_price', 0),
                    platform=item.get('platform', ''),
                    percent=0,
                    last_update=datetime.now().isoformat()
                )
                session.add(record)
        
        # Якщо залишків не було в Excel — додаємо з 0
        for default_bal in [('FFusd', 'FF'), ('IBusd', 'IB')]:
            ticker_bal, plat = default_bal
            exists = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker_bal).first()
            if not exists:
                record = StockPortfolio(
                    ticker=ticker_bal,
                    total_quantity=1,
                    total_amount=0,
                    avg_price=0,
                    platform=plat,
                    percent=0,
                    last_update=datetime.now().isoformat()
                )
                session.add(record)
        
        session.commit()
        recalculate_percents(session)
        session.close()
        
        text += f"\n✅ Портфель оновлено!"
        text += f"\n📋 З Excel: {matched} | Перераховано: {recalculated}"
        
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
    """Меню управління прибутками акцій"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        stocks = session.query(Stock).all()
        
        if not stocks:
            session.close()
            await query.edit_message_text("📭 Немає даних про акції")
            return
        
        # Реалізований прибуток — сума pnl з операцій продажу
        total_profit = sum(s.pnl or 0 for s in stocks if s.operation_type == 'продаж')
        
        # Отримуємо списаний прибуток
        profit_records = session.query(StockProfitRecord).filter(StockProfitRecord.unrealized_profit > 0).all()
        session.close()
        
        total_written_off = sum(r.unrealized_profit for r in profit_records)
        
        unrealized_profit = total_profit - total_written_off
        if unrealized_profit < 0:
            unrealized_profit = 0
        
        text = f"💰 *Управління прибутками акцій*\n\n"
        text += f"📈 Реалізований прибуток: {total_profit:.2f} $\n"
        text += f"📋 Не списаний прибуток: {unrealized_profit:.2f} $\n\n"
        
        keyboard = [
            [InlineKeyboardButton("✍️ Списати прибуток", callback_data='stocks_write_off_profit')],
            [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def write_off_stocks_profit_menu(update: Update, context: CallbackContext):
    """Меню списання прибутку акцій"""
    query = update.callback_query
    await query.answer()
    
    logger.info("write_off_stocks_profit_menu called")
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        stocks = session.query(Stock).all()
        
        if not stocks:
            session.close()
            await query.edit_message_text("📭 Немає даних про акції")
            return
        
        # Реалізований прибуток — сума pnl з операцій продажу
        total_profit = sum(s.pnl or 0 for s in stocks if s.operation_type == 'продаж')
        
        profit_records = session.query(StockProfitRecord).filter(StockProfitRecord.unrealized_profit > 0).all()
        session.close()
        
        total_written_off = sum(r.unrealized_profit for r in profit_records)
        
        unrealized_profit = total_profit - total_written_off
        if unrealized_profit < 0:
            unrealized_profit = 0
        
        context.user_data['unrealized_profit'] = unrealized_profit
        
        text = f"💰 *Списання прибутку акцій*\n\n"
        text += f"📋 Не списаний прибуток: *{unrealized_profit:.2f} $*\n\n"
        
        if unrealized_profit > 0:
            keyboard = [
                [InlineKeyboardButton("✍️ Списати", callback_data='stocks_confirm_write_off')],
                [InlineKeyboardButton("🔙 Назад", callback_data='stocks_profit')]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data='stocks_profit')]
            ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in write_off_stocks_profit_menu: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_sell_stock_selection(update: Update, context: CallbackContext):
    """Показати список акцій з портфеля для продажу"""
    query = update.callback_query
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        portfolio_records = session.query(StockPortfolio).all()
        session.close()
        
        # Фільтруємо — прибираємо залишки (FFusd, IBusd)
        portfolio_records = [r for r in portfolio_records if not r.ticker.endswith('usd')]
        
        if not portfolio_records:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')]]
            await query.edit_message_text("📭 Портфель пустий — немає що продавати", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        text = "🔴 *Продаж акції*\n\nОберіть акцію для продажу:"
        keyboard = []
        for record in portfolio_records:
            label = f"{record.ticker} | {record.total_quantity} шт | {record.avg_price:.2f} $ | {record.platform}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'sell_stock_{record.ticker}')])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in show_sell_stock_selection: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_sell_stock_selected(update: Update, context: CallbackContext, ticker: str):
    """Обробка вибору акції для продажу"""
    query = update.callback_query
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        portfolio_record = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()
        session.close()
        
        if not portfolio_record:
            await query.edit_message_text("❌ Акцію не знайдено в портфелі")
            return
        
        # Зберігаємо дані з портфеля
        context.user_data['ticker'] = ticker
        context.user_data['sell_avg_price'] = portfolio_record.avg_price
        context.user_data['sell_max_quantity'] = portfolio_record.total_quantity
        context.user_data['sell_platform'] = portfolio_record.platform
        context.user_data['stock_step'] = 'sell_price'
        
        await query.edit_message_text(
            f"🔴 *Продаж акції*\n\n"
            f"📈 Тікер: {ticker}\n"
            f"📦 В портфелі: {portfolio_record.total_quantity} шт\n"
            f"💰 Середня ціна купівлі: {portfolio_record.avg_price:.2f} $\n"
            f"📊 Біржа: {portfolio_record.platform}\n\n"
            f"💵 Введіть ціну продажу за одну акцію:",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_sell_stock_selected: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_message_stocks(update: Update, context: CallbackContext):
    """Обробка текстових повідомлень для Акцій"""
    if 'stock_step' not in context.user_data and 'profit_step' not in context.user_data:
        return
    
    user_message = update.message.text
    step = context.user_data.get('stock_step')
    profit_step = context.user_data.get('profit_step')
    
    try:
        if profit_step == 'enter_amount':
            try:
                write_off_amount = float(user_message)
                unrealized_profit = context.user_data.get('unrealized_profit', 0)
                
                if write_off_amount > unrealized_profit:
                    await update.message.reply_text(
                        f"❌ Сума перевищує не списаний прибуток ({unrealized_profit:.2f} $)\n\n"
                        f"💰 Введіть суму для списання:"
                    )
                    return
                
                if write_off_amount <= 0:
                    await update.message.reply_text("❌ Сума має бути більше 0\n\n💰 Введіть суму для списання:")
                    return
                
                Session = context.bot_data.get('Session')
                if not Session:
                    await update.message.reply_text("❌ Помилка підключення до бази даних")
                    return
                
                session = Session()
                
                profit_record = StockProfitRecord(
                    operation_date=datetime.now().strftime('%d.%m.%Y'),
                    operation_type='списання',
                    amount=write_off_amount,
                    realized_profit=0,
                    unrealized_profit=write_off_amount
                )
                session.add(profit_record)
                session.commit()
                session.close()
                
                remaining_profit = unrealized_profit - write_off_amount
                text = f"✅ *Прибуток списано!*\n\n"
                text += f"📝 Списано: {write_off_amount:.2f} $\n"
                text += f"📋 Залишилось: {remaining_profit:.2f} $\n"
                
                keyboard = [
                    [InlineKeyboardButton("💰 До меню прибутків", callback_data='stocks_profit')],
                    [InlineKeyboardButton("📊 До Акцій", callback_data='stocks')]
                ]
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                
                # Очищуємо дані про прибуток
                context.user_data.pop('profit_step', None)
                context.user_data.pop('unrealized_profit', None)
                
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число\n\n💰 Введіть суму для списання:")
        
        elif step == 'date_manual':
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
                await update.message.reply_text("❌ Будь ласка, введіть коректне число (або 0 для вводу суми)")
        
        elif step == 'quantity':
            try:
                quantity = int(user_message)
                context.user_data['quantity'] = quantity
                context.user_data['stock_step'] = 'commission'
                await update.message.reply_text("💸 Введіть комісію за транзакцію:")
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'commission':
            try:
                commission = float(user_message)
                context.user_data['commission'] = commission
                
                price = context.user_data.get('price_per_unit', 0)
                quantity = context.user_data.get('quantity', 0)
                
                # Якщо ціна була введена (> 0)
                if price > 0:
                    total_amount = (price * quantity) + commission
                    avg_price = total_amount / quantity if quantity > 0 else 0
                    context.user_data['total_amount'] = total_amount
                    context.user_data['price_per_unit'] = avg_price  # Оновлюємо на реальну собівартість
                    context.user_data['stock_step'] = 'platform'
                    keyboard = [
                        [InlineKeyboardButton("📊 FF", callback_data='stock_platform_ff')],
                        [InlineKeyboardButton("📊 IB", callback_data='stock_platform_ib')]
                    ]
                    await update.message.reply_text(
                        f"💵 Сума: {total_amount:.2f} $\n"
                        f"💸 Комісія: {commission:.2f} $\n"
                        f"📊 Реальна ціна за шт: {avg_price:.3f} $\n\n📊 Виберіть біржу:",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                # Якщо ціна = 0 (вводимо суму)
                else:
                    context.user_data['stock_step'] = 'total_amount'
                    await update.message.reply_text("💰 Введіть загальну суму (без комісії):")
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'total_amount':
            try:
                total_without_commission = float(user_message)
                commission = context.user_data.get('commission', 0)
                quantity = context.user_data.get('quantity', 0)
                
                total_with_commission = total_without_commission + commission
                avg_price = total_with_commission / quantity if quantity > 0 else 0
                
                context.user_data['total_amount'] = total_with_commission
                context.user_data['price_per_unit'] = avg_price  # Реальна собівартість
                context.user_data['stock_step'] = 'platform'
                
                keyboard = [
                    [InlineKeyboardButton("📊 FF", callback_data='stock_platform_ff')],
                    [InlineKeyboardButton("📊 IB", callback_data='stock_platform_ib')]
                ]
                await update.message.reply_text(
                    f"💰 Сума без комісії: {total_without_commission:.2f} $\n"
                    f"💸 Комісія: {commission:.2f} $\n"
                    f"💵 Загальна сума: {total_with_commission:.2f} $\n"
                    f"📊 Реальна ціна за шт: {avg_price:.3f} $\n\n📊 Виберіть біржу:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'sell_price':
            try:
                price = float(user_message)
                context.user_data['price_per_unit'] = price
                context.user_data['stock_step'] = 'sell_quantity'
                max_qty = context.user_data['sell_max_quantity']
                await update.message.reply_text(
                    f"💵 Ціна продажу: {price:.2f} $\n\n"
                    f"📦 Введіть кількість (максимум {max_qty} шт):"
                )
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'sell_quantity':
            try:
                quantity = int(user_message)
                max_qty = context.user_data['sell_max_quantity']
                
                if quantity <= 0:
                    await update.message.reply_text("❌ Кількість має бути більше 0")
                    return
                
                if quantity > max_qty:
                    await update.message.reply_text(
                        f"❌ В портфелі тільки {max_qty} шт.\n\n"
                        f"📦 Введіть кількість (максимум {max_qty} шт):"
                    )
                    return
                
                context.user_data['quantity'] = quantity
                context.user_data['stock_step'] = 'sell_commission'
                await update.message.reply_text("💸 Введіть комісію за транзакцію:")
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'sell_commission':
            try:
                commission = float(user_message)
                context.user_data['commission'] = commission
                
                price = context.user_data['price_per_unit']
                quantity = context.user_data['quantity']
                total_amount = (price * quantity) - commission
                context.user_data['total_amount'] = total_amount
                
                # Рахуємо PnL
                avg_price = context.user_data['sell_avg_price']
                pnl = (price - avg_price) * quantity - commission
                context.user_data['pnl'] = pnl
                
                # Біржа автоматично з портфеля (продаємо там де купили)
                platform = context.user_data['sell_platform']
                context.user_data['platform'] = platform
                
                pnl_emoji = "📈" if pnl >= 0 else "📉"
                ticker = context.user_data['ticker']
                
                # Зберігаємо одразу без вибору біржі
                Session = context.bot_data.get('Session')
                if not Session:
                    await update.message.reply_text("❌ Помилка підключення до бази даних")
                    return
                
                session = Session()
                
                stock = Stock(
                    date=context.user_data['stock_date'],
                    operation_type='продаж',
                    ticker=ticker,
                    name=ticker,
                    price_per_unit=price,
                    quantity=quantity,
                    total_amount=total_amount,
                    platform=platform,
                    pnl=pnl
                )
                session.add(stock)
                session.commit()
                
                # Оновлюємо портфель
                portfolio = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()
                if portfolio:
                    portfolio.total_quantity -= quantity
                    portfolio.total_amount -= (avg_price * quantity)
                    
                    if portfolio.total_quantity <= 0:
                        session.delete(portfolio)
                    else:
                        portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity if portfolio.total_quantity > 0 else 0
                        portfolio.last_update = datetime.now().isoformat()
                
                session.commit()
                recalculate_percents(session)
                session.close()
                
                text = (
                    f"✅ *Запис додано!*\n\n"
                    f"📅 Дата: {context.user_data['stock_date']}\n"
                    f"📊 Операція: Продаж\n"
                    f"📈 Тікер: {ticker}\n"
                    f"💵 Ціна за шт: {price:.3f} $\n"
                    f"📦 Кількість: {quantity} шт\n"
                    f"💰 Загальна сума: {total_amount:.2f} $\n"
                    f"💸 Комісія: {commission:.2f} $\n"
                    f"📊 Біржа: {platform}\n\n"
                    f"{pnl_emoji} *PnL: {pnl:+.2f} $*"
                )
                
                await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Назад до Акцій", callback_data='stocks')]
                    ]),
                    parse_mode='Markdown'
                )
                context.user_data.clear()
                
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'balance_amount':
            try:
                amount = float(user_message)
                if amount < 0:
                    await update.message.reply_text("❌ Сума має бути 0 або більше")
                    return
                
                Session = context.bot_data.get('Session')
                if not Session:
                    await update.message.reply_text("❌ Помилка підключення до бази даних")
                    return
                
                platform = context.user_data['balance_platform']
                ticker = f"{platform}usd"
                
                session = Session()
                record = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()
                
                if record:
                    record.total_amount = amount
                    record.avg_price = amount
                    record.last_update = datetime.now().isoformat()
                else:
                    record = StockPortfolio(
                        ticker=ticker,
                        total_quantity=1,
                        total_amount=amount,
                        avg_price=amount,
                        platform=platform,
                        percent=0,
                        last_update=datetime.now().isoformat()
                    )
                    session.add(record)
                
                session.commit()
                
                # Перераховуємо процентовку
                recalculate_percents(session)
                
                session.close()
                
                keyboard = [
                    [InlineKeyboardButton("💼 До портфеля", callback_data='stocks_portfolio')],
                    [InlineKeyboardButton("🔙 До Акцій", callback_data='stocks')]
                ]
                await update.message.reply_text(
                    f"✅ *Залишок оновлено!*\n\n"
                    f"📊 Біржа: {platform}\n"
                    f"💵 Залишок: {amount:.2f} $",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                
                context.user_data.pop('stock_step', None)
                context.user_data.pop('balance_platform', None)
                
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
    
    except Exception as e:
        logger.error(f"Error in handle_message_stocks: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")