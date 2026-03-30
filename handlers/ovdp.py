import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import requests
from bs4 import BeautifulSoup
import time

from models import Bond, ProfitRecord, BondPortfolio

logger = logging.getLogger(__name__)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available")


def fetch_bond_price_icu(bond_number):
    """
    Парсить ціну облігації з uainvest.com.ua для ICU
    Повертає ціну або None
    """
    try:
        url = "https://uainvest.com.ua/ukrbonds"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table')
        if not table:
            return None
        
        rows = table.find_all('tr')
        if not rows:
            return None
        
        # Знаходимо індекси колонок
        headers_row = rows[0].find_all('th')
        isin_col = broker_col = price_col = None
        
        for i, th in enumerate(headers_row):
            text = th.text.strip()
            if text == 'ISIN':
                isin_col = i
            if text == 'Брокер':
                broker_col = i
            if text == 'Ціна':
                price_col = i
        
        if None in (isin_col, broker_col, price_col):
            return None
        
        isin = f"UA{bond_number}"
        
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) > max(isin_col, broker_col, price_col):
                current_isin = cells[isin_col].text.strip()
                if current_isin.startswith(isin):
                    broker = cells[broker_col].text.strip().lower()
                    price = cells[price_col].text.strip()
                    if broker == 'icu' and price != '-':
                        return float(price.replace(',', '.'))
        
        return None
        
    except Exception as e:
        print(f"Error: {e}")
        return None


def calculate_monthly_profit(bonds):
    """
    Розраховує прибуток по місяцях на основі FIFO результатів з calculate_profit_by_price.
    """
    from datetime import datetime
    
    def parse_date(date_str):
        """Парсує дату з формату ДД.ММ.РРРР або ДД.ММ.РРРРр."""
        try:
            cleaned = str(date_str).strip().replace('р.', '').replace('р', '').strip()
            return datetime.strptime(cleaned, '%d.%m.%Y')
        except:
            return datetime.max
    
    def get_month_year(date_str):
        """Витягує місяць.рік з дати"""
        parsed = parse_date(date_str)
        if parsed == datetime.max:
            return "невідома дата"
        return f"{parsed.month:02d}.{parsed.year}"
    
    # Отримуємо FIFO результати
    bond_stats, _ = calculate_profit_by_price(bonds)
    
    monthly_profit = {}
    
    # Проходимо по кожній облігації та її продажам
    for bond_num, stats in bond_stats.items():
        for sale in stats['sales']:
            month_year = get_month_year(sale['date'])
            
            if month_year not in monthly_profit:
                monthly_profit[month_year] = 0
            
            # Додаємо прибуток цієї продажі до місяця
            monthly_profit[month_year] += sale['profit']
    
    return monthly_profit


def calculate_profit_by_price(bonds):
    """
    Розраховує прибуток по методу FIFO (First In First Out).
    
    Логіка:
    1. Для кожної облігації ведемо чергу купівель з ціною
    2. При продажі - спочатку продаємо найстарішу купівлю
    3. Якщо однієї купівлі недостатньо - беремо з наступної
    4. Прибуток = (price_sell - price_buy) * quantity_sell
    """
    from collections import defaultdict, deque
    from datetime import datetime
    
    bond_stats = defaultdict(lambda: {
        'buy_queue': deque(),
        'sales': [],
        'profit': 0
    })
    
    def parse_date(date_str):
        """Парсує дату з формату ДД.ММ.РРРР або ДД.ММ.РРРРр."""
        try:
            # Видаляємо "р." якщо є
            cleaned = str(date_str).strip().replace('р.', '').replace('р', '').strip()
            return datetime.strptime(cleaned, '%d.%m.%Y')
        except:
            return datetime.max
    
    # Сортуємо по row_order (порядку з Excel) для правильного FIFO
    # Якщо row_order не встановлений - сортуємо по даті
    sorted_bonds = sorted(bonds, key=lambda x: (
        x.row_order if x.row_order and x.row_order > 0 else float('inf'),
        parse_date(x.date),
        0 if x.operation_type == 'купівля' else 1
    ))
    
    for bond in sorted_bonds:
        bond_num = bond.bond_number
        
        if bond.operation_type == 'купівля':
            # Додаємо купівлю в чергу
            bond_stats[bond_num]['buy_queue'].append({
                'price': bond.price_per_unit,
                'quantity': bond.quantity,
                'date': bond.date
            })
        
        elif bond.operation_type == 'продаж':
            # Продаємо по FIFO - списуємо перші за часом купівлі
            remaining_to_sell = bond.quantity
            cost_of_goods_sold = 0  # Собівартість (сума списаних купівель)
            sale_details = []
            
            # Списуємо купівлі з черги
            while remaining_to_sell > 0 and bond_stats[bond_num]['buy_queue']:
                buy = bond_stats[bond_num]['buy_queue'][0]
                
                # Скільки можемо продати з цієї купівлі
                qty_from_this_buy = min(remaining_to_sell, buy['quantity'])
                
                # Собівартість цієї партії = ціна купівлі × кількість
                partition_cost = qty_from_this_buy * buy['price']
                cost_of_goods_sold += partition_cost
                
                sale_details.append({
                    'buy_date': buy['date'],
                    'buy_price': buy['price'],
                    'qty': qty_from_this_buy,
                    'cost': partition_cost
                })
                
                # Оновлюємо залишок в черзі
                buy['quantity'] -= qty_from_this_buy
                remaining_to_sell -= qty_from_this_buy
                
                # Видаляємо купівлю якщо вона повністю продана
                if buy['quantity'] == 0:
                    bond_stats[bond_num]['buy_queue'].popleft()
            
            # Розраховуємо прибуток для цього продажу
            # Прибуток = Сума продажу − Собівартість
            sale_revenue = bond.quantity * bond.price_per_unit
            profit = sale_revenue - cost_of_goods_sold
            
            bond_stats[bond_num]['sales'].append({
                'date': bond.date,
                'qty': bond.quantity,
                'price': bond.price_per_unit,
                'revenue': sale_revenue,
                'cost': cost_of_goods_sold,
                'profit': profit,
                'details': sale_details,
                'row_order': bond.row_order
            })
            
            bond_stats[bond_num]['profit'] += profit
    
    # Розраховуємо загальний прибуток
    total_profit = sum(stats['profit'] for stats in bond_stats.values())
    
    logger.info(f"FIFO Profit calculation: total_profit={total_profit:.2f}, bonds_count={len(bond_stats)}")
    for bond_num, stats in bond_stats.items():
        if stats['profit'] != 0:
            logger.info(f"  {bond_num}: profit={stats['profit']:.2f}, sales_count={len(stats['sales'])}")
    
    return dict(bond_stats), total_profit


async def recalculate_bond_portfolio(Session):
    """Пересчитати портфель облігацій з записів bonds та заповнити bond_portfolio"""
    try:
        session = Session()
        
        # Видаляємо старі дані
        session.query(BondPortfolio).delete()
        session.commit()
        
        # Отримуємо всі записи з bonds
        all_bonds = session.query(Bond).all()
        
        if not all_bonds:
            session.close()
            return
        
        from collections import defaultdict
        # Ключ = (bond_number, platform)
        portfolio_data = defaultdict(lambda: {
            'quantity': 0,
            'amount': 0,
            'maturity_date': '',
        })
        
        for bond in all_bonds:
            key = (bond.bond_number, bond.platform.upper() if bond.platform else '')
            portfolio_data[key]['maturity_date'] = bond.maturity_date
            
            if bond.operation_type == 'купівля':
                portfolio_data[key]['quantity'] += bond.quantity
                portfolio_data[key]['amount'] += bond.total_amount
            else:  # продаж
                portfolio_data[key]['quantity'] -= bond.quantity
                portfolio_data[key]['amount'] -= bond.total_amount
        
        # Зберігаємо в bond_portfolio
        for (bond_num, platform), data in portfolio_data.items():
            if data['quantity'] > 0:
                avg_price = data['amount'] / data['quantity'] if data['quantity'] > 0 else 0
                portfolio_record = BondPortfolio(
                    bond_number=bond_num,
                    maturity_date=data['maturity_date'],
                    total_quantity=data['quantity'],
                    total_amount=data['amount'],
                    avg_price=avg_price,
                    platform=platform,
                    last_update=datetime.now().isoformat()
                )
                session.add(portfolio_record)
        
        session.commit()
        session.close()
        logger.info(f"Портфель облігацій пересчитаний: {len(portfolio_data)} позицій")
        
    except Exception as e:
        logger.error(f"Error recalculating bond portfolio: {e}")


async def button_handler_ovdp(update: Update, context: CallbackContext):
    """Обробник кнопок для ОВДП"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'ovdp':
        await show_ovdp_menu(update, context)
    elif query.data == 'ovdp_add':
        await start_bond_add(update, context)
    elif query.data == 'ovdp_list':
        await show_bonds_list(update, context)
    elif query.data.startswith('bonds_list_page_'):
        page = int(query.data.replace('bonds_list_page_', ''))
        await show_bonds_list(update, context, page=page)
    elif query.data == 'ovdp_portfolio':
        await show_bonds_portfolio(update, context, platform=None)
    elif query.data == 'ovdp_stats':
        await show_bonds_stats(update, context)
    elif query.data == 'ovdp_profit':
        await show_profit_menu(update, context)
    elif query.data.startswith('portfolio_'):
        platform = query.data.replace('portfolio_', '')
        await show_bonds_portfolio(update, context, platform=platform)
    elif query.data.startswith('date_'):
        await handle_date_selection(update, context)
    elif query.data.startswith('cal_'):
        await handle_bond_calendar_navigation(update, context)
    elif query.data == 'bond_buy':
        context.user_data['bond_operation_type'] = 'купівля'
        context.user_data['bond_step'] = 'bond_number'
        await query.edit_message_text("🔢 Введіть номер ОВДП (наприклад: МХ3012-202):", parse_mode='Markdown')
    elif query.data == 'bond_sell':
        context.user_data['bond_operation_type'] = 'продаж'
        await show_sell_bond_selection(update, context)
    elif query.data.startswith('sell_bond_'):
        bond_number = query.data.replace('sell_bond_', '')
        await handle_sell_bond_selected(update, context, bond_number)
    elif query.data.startswith('platform_'):
        platform = query.data.replace('platform_', '')
        context.user_data['platform'] = platform.upper()
        await save_bond(update, context)
    elif query.data == 'write_off_profit':
        await write_off_profit_menu(update, context)
    elif query.data == 'confirm_write_off':
        context.user_data['profit_step'] = 'enter_amount'
        await query.edit_message_text("💰 Введіть суму для списання:", parse_mode='Markdown')
    elif query.data == 'pnl_portfolio':
        await show_pnl_portfolio(update, context)
    elif query.data == 'sync_sheets_to_db':
        await sync_bonds_from_sheets(update, context)


async def show_ovdp_menu(update: Update, context: CallbackContext):
    """Показати меню ОВДП"""
    query = update.callback_query
    text = "📈 *ОВДП*\n\nОберіть дію:"
    keyboard = [
        [InlineKeyboardButton("➕ Додати запис", callback_data='ovdp_add')],
        [InlineKeyboardButton("📋 Мої записи", callback_data='ovdp_list')],
        [InlineKeyboardButton("💼 Портфель", callback_data='ovdp_portfolio')],
        [InlineKeyboardButton("💰 Прибуток", callback_data='ovdp_profit')],
        [InlineKeyboardButton("📊 Статистика", callback_data='ovdp_stats')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def start_bond_add(update: Update, context: CallbackContext):
    """Розпочати додавання ОВДП"""
    query = update.callback_query
    context.user_data['adding_bond'] = True
    context.user_data['bond_step'] = 'date'
    
    today = datetime.now()
    
    keyboard = [
        [InlineKeyboardButton(f"📅 Сьогодні ({today.strftime('%d.%m.%Y')})", callback_data=f'date_{today.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton("📅 Вибрати дату", callback_data='date_calendar')],
        [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
    ]
    await query.edit_message_text(
        "📈 *Додавання запису ОВДП*\n\n📅 Виберіть дату операції:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_date_selection(update: Update, context: CallbackContext):
    """Обробка вибору дати"""
    query = update.callback_query
    date_value = query.data.replace('date_', '')
    
    if date_value == 'calendar':
        await show_bond_calendar(update, context)
    elif date_value != 'manual':
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


async def show_bond_calendar(update: Update, context: CallbackContext):
    """Показати календар для вибору дати ОВДП"""
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
        InlineKeyboardButton("◀️", callback_data=f'cal_prev_{year}_{month}'),
        InlineKeyboardButton(month_name, callback_data='cal_month'),
        InlineKeyboardButton("▶️", callback_data=f'cal_next_{year}_{month}')
    ]
    keyboard.append(nav_keyboard)
    
    days_of_week = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']
    keyboard.append([InlineKeyboardButton(day, callback_data='cal_dow') for day in days_of_week])
    
    day_buttons = []
    for _ in range(start_weekday):
        day_buttons.append(InlineKeyboardButton(" ", callback_data='cal_empty'))
    
    for day in range(1, last_day.day + 1):
        date_str = f"{day:02d}.{month:02d}.{year}"
        day_buttons.append(InlineKeyboardButton(str(day), callback_data=f'date_{date_str}'))
    
    for i in range(0, len(day_buttons), 7):
        keyboard.append(day_buttons[i:i+7])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')])
    
    await query.edit_message_text(
        "📅 *Виберіть дату:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_bond_calendar_navigation(update: Update, context: CallbackContext):
    """Обробка навігації по календару для ОВДП"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('cal_prev_'):
        parts = query.data.replace('cal_prev_', '').split('_')
        year, month = int(parts[0]), int(parts[1])
        month -= 1
        if month < 1:
            month = 12
            year -= 1
        context.user_data['calendar_month'] = datetime(year, month, 1)
    
    elif query.data.startswith('cal_next_'):
        parts = query.data.replace('cal_next_', '').split('_')
        year, month = int(parts[0]), int(parts[1])
        month += 1
        if month > 12:
            month = 1
            year += 1
        context.user_data['calendar_month'] = datetime(year, month, 1)
    
    await show_bond_calendar(update, context)


async def show_sell_bond_selection(update: Update, context: CallbackContext):
    """Показати список ОВДП з портфеля для продажу"""
    query = update.callback_query
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        portfolio_records = session.query(BondPortfolio).all()
        session.close()
        
        if not portfolio_records:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]]
            await query.edit_message_text("📭 Портфель пустий — немає що продавати", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        text = "🔴 *Продаж ОВДП*\n\nОберіть облігацію для продажу:"
        keyboard = []
        for record in portfolio_records:
            label = f"{record.bond_number} | {record.platform} | {record.total_quantity} шт | {record.avg_price:.2f} грн"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'sell_bond_{record.id}')])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in show_sell_bond_selection: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_sell_bond_selected(update: Update, context: CallbackContext, bond_number: str):
    """Обробка вибору облігації для продажу"""
    query = update.callback_query
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        # bond_number тут насправді id запису з bond_portfolio
        record_id = int(bond_number)
        session = Session()
        portfolio_record = session.query(BondPortfolio).filter(BondPortfolio.id == record_id).first()
        session.close()
        
        if not portfolio_record:
            await query.edit_message_text("❌ Облігацію не знайдено в портфелі")
            return
        
        # Зберігаємо дані з портфеля
        context.user_data['bond_number'] = portfolio_record.bond_number
        context.user_data['maturity_date'] = portfolio_record.maturity_date
        context.user_data['sell_avg_price'] = portfolio_record.avg_price
        context.user_data['sell_max_quantity'] = portfolio_record.total_quantity
        context.user_data['sell_platform'] = portfolio_record.platform
        context.user_data['bond_step'] = 'sell_price'
        
        await query.edit_message_text(
            f"🔴 *Продаж ОВДП*\n\n"
            f"🔢 Номер: {portfolio_record.bond_number}\n"
            f"🏦 Платформа: {portfolio_record.platform}\n"
            f"📆 Термін погашення: {portfolio_record.maturity_date}\n"
            f"📦 В портфелі: {portfolio_record.total_quantity} шт\n"
            f"💰 Середня ціна купівлі: {portfolio_record.avg_price:.2f} грн\n\n"
            f"💵 Введіть ціну продажу за одну облігацію:",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in handle_sell_bond_selected: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_message_ovdp(update: Update, context: CallbackContext):
    """Обробка текстових повідомлень для ОВДП"""
    if 'bond_step' not in context.user_data and 'profit_step' not in context.user_data:
        return
    
    user_message = update.message.text
    
    # profit_step має пріоритет, бо bond_step може залишитися від попереднього flow
    if 'profit_step' in context.user_data:
        step = context.user_data.get('profit_step')
    else:
        step = context.user_data.get('bond_step')
    
    try:
        if step == 'date_manual':
            try:
                datetime.strptime(user_message, '%d.%m.%Y')
                context.user_data['bond_date'] = user_message
                context.user_data['bond_step'] = 'operation_type'
                keyboard = [
                    [InlineKeyboardButton("🟢 Купівля", callback_data='bond_buy')],
                    [InlineKeyboardButton("🔴 Продаж", callback_data='bond_sell')]
                ]
                await update.message.reply_text(
                    f"📅 Дата: {user_message}\n\n📈 Виберіть тип операції:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.message.reply_text("❌ Невірний формат дати. Будь ласка, введіть у форматі ДД.ММ.РРРР")
        
        elif step == 'bond_number':
            # Тільки для купівлі — продаж іде через кнопки
            context.user_data['bond_number'] = user_message
            context.user_data['bond_step'] = 'maturity_date'
            await update.message.reply_text("📆 Введіть термін погашення (ДД.ММ.РРРР):")
        
        elif step == 'maturity_date':
            try:
                datetime.strptime(user_message, '%d.%m.%Y')
                context.user_data['maturity_date'] = user_message
                context.user_data['bond_step'] = 'price_per_unit'
                await update.message.reply_text("💰 Введіть ціну за одну облігацію:")
            except ValueError:
                await update.message.reply_text("❌ Невірний формат дати. Будь ласка, введіть у форматі ДД.ММ.РРРР")
        
        elif step == 'price_per_unit':
            try:
                price = float(user_message)
                context.user_data['price_per_unit'] = price
                context.user_data['bond_step'] = 'quantity'
                await update.message.reply_text("📦 Введіть кількість облігацій:")
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'quantity':
            try:
                quantity = int(user_message)
                context.user_data['quantity'] = quantity
                total_amount = context.user_data['price_per_unit'] * quantity
                context.user_data['total_amount'] = total_amount
                context.user_data['bond_step'] = 'platform'
                keyboard = [
                    [InlineKeyboardButton("🏦 ICU", callback_data='platform_icu')],
                    [InlineKeyboardButton("🏦 SENSBANK", callback_data='platform_sensbank')]
                ]
                await update.message.reply_text(
                    f"💵 Сума: {total_amount:.2f} грн\n\n🏦 Виберіть платформу:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'sell_price':
            try:
                price = float(user_message)
                context.user_data['price_per_unit'] = price
                context.user_data['bond_step'] = 'sell_quantity'
                max_qty = context.user_data['sell_max_quantity']
                await update.message.reply_text(
                    f"💵 Ціна продажу: {price:.2f} грн\n\n"
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
                total_amount = context.user_data['price_per_unit'] * quantity
                context.user_data['total_amount'] = total_amount
                
                # Рахуємо PnL
                avg_price = context.user_data['sell_avg_price']
                pnl = (context.user_data['price_per_unit'] - avg_price) * quantity
                context.user_data['pnl'] = pnl
                
                # Платформа фіксується з портфеля
                context.user_data['platform'] = context.user_data['sell_platform']
                
                # Зберігаємо продаж
                await save_bond_sell(update, context)
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
        
        elif step == 'enter_amount':
            try:
                write_off_amount = float(user_message)
                unrealized_profit = context.user_data.get('unrealized_profit', 0)
                
                if write_off_amount > unrealized_profit:
                    await update.message.reply_text(
                        f"❌ Сума перевищує нереалізований прибуток ({unrealized_profit:.0f} грн)\n\n"
                        f"Введіть коректну суму:"
                    )
                    return
                
                if write_off_amount <= 0:
                    await update.message.reply_text("❌ Сума має бути більше 0")
                    return
                
                Session = context.bot_data.get('Session')
                if not Session:
                    await update.message.reply_text("❌ Помилка підключення до бази даних")
                    return
                
                session = Session()
                profit_record = ProfitRecord(
                    operation_date=datetime.now().strftime('%d.%m.%Y'),
                    operation_type='списання',
                    amount=0,
                    realized_profit=0,
                    unrealized_profit=write_off_amount
                )
                session.add(profit_record)
                session.commit()
                session.close()
                
                remaining_profit = unrealized_profit - write_off_amount
                text = f"✅ *Оновлено!*\n\n"
                text += f"📝 Списано: {write_off_amount:.0f} грн\n"
                text += f"📋 Залишок: {remaining_profit:.0f} грн"
                
                keyboard = [
                    [InlineKeyboardButton("💰 До меню прибутків", callback_data='ovdp_profit')],
                    [InlineKeyboardButton("🔙 До ОВДП", callback_data='ovdp')]
                ]
                
                await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                
                context.user_data.pop('profit_step', None)
                context.user_data.pop('unrealized_profit', None)
                
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число")
    
    except Exception as e:
        logger.error(f"Error in handle_message_ovdp: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")


async def save_bond_sell(update: Update, context: CallbackContext):
    """Зберігає продаж облігації (викликається з handle_message_ovdp)"""
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await update.message.reply_text("❌ Помилка підключення до бази даних")
            return
        
        pnl = context.user_data.get('pnl', 0)
        bond_number = context.user_data['bond_number']
        quantity = context.user_data['quantity']
        total_amount = context.user_data['total_amount']
        platform = context.user_data['platform']
        maturity_date = context.user_data['maturity_date']
        
        session = Session()
        bond = Bond(
            date=context.user_data['bond_date'],
            operation_type='продаж',
            bond_number=bond_number,
            maturity_date=maturity_date,
            price_per_unit=context.user_data['price_per_unit'],
            quantity=quantity,
            total_amount=total_amount,
            platform=platform,
            pnl=pnl
        )
        session.add(bond)
        session.commit()
        
        profit_record = ProfitRecord(
            operation_date=context.user_data['bond_date'],
            operation_type='продаж',
            amount=total_amount
        )
        session.add(profit_record)
        session.commit()
        
        # Точкове оновлення портфеля — по bond_number + platform
        portfolio = session.query(BondPortfolio).filter(
            BondPortfolio.bond_number == bond_number,
            BondPortfolio.platform == platform
        ).first()
        
        if portfolio:
            portfolio.total_quantity -= quantity
            portfolio.total_amount -= (context.user_data['sell_avg_price'] * quantity)
            
            if portfolio.total_quantity <= 0:
                session.delete(portfolio)
            else:
                portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity if portfolio.total_quantity > 0 else 0
                portfolio.last_update = datetime.now().isoformat()
        
        session.commit()
        session.close()
        
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        text = (
            f"✅ *Запис додано!*\n\n"
            f"📅 Дата: {context.user_data['bond_date']}\n"
            f"📈 Операція: Продаж\n"
            f"🔢 Номер: {bond_number}\n"
            f"📆 Термін погашення: {maturity_date}\n"
            f"💵 Ціна за шт: {context.user_data['price_per_unit']:.2f} грн\n"
            f"📦 Кількість: {quantity} шт\n"
            f"💰 Сума: {total_amount:.2f} грн\n"
            f"🏦 Платформа: {platform}\n\n"
            f"{pnl_emoji} *PnL: {pnl:+.2f} грн*"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад до ОВДП", callback_data='ovdp')]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error saving bond sell: {e}")
        await update.message.reply_text(f"❌ Помилка при збереженні: {str(e)}")


async def save_bond(update: Update, context: CallbackContext):
    """Зберігає облігацію в базу даних та оновлює портфель"""
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await update.callback_query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        operation_type = context.user_data['bond_operation_type']
        pnl = context.user_data.get('pnl', 0) if operation_type == 'продаж' else 0
        bond_number = context.user_data['bond_number']
        quantity = context.user_data['quantity']
        total_amount = context.user_data['total_amount']
        platform = context.user_data['platform']
        maturity_date = context.user_data['maturity_date']
        
        session = Session()
        bond = Bond(
            date=context.user_data['bond_date'],
            operation_type=operation_type,
            bond_number=bond_number,
            maturity_date=maturity_date,
            price_per_unit=context.user_data['price_per_unit'],
            quantity=quantity,
            total_amount=total_amount,
            platform=platform,
            pnl=pnl
        )
        session.add(bond)
        session.commit()
        
        profit_record = ProfitRecord(
            operation_date=context.user_data['bond_date'],
            operation_type=operation_type,
            amount=total_amount
        )
        session.add(profit_record)
        session.commit()
        
        # Точкове оновлення портфеля — по bond_number + platform
        portfolio = session.query(BondPortfolio).filter(
            BondPortfolio.bond_number == bond_number,
            BondPortfolio.platform == platform
        ).first()
        
        if operation_type == 'купівля':
            if not portfolio:
                portfolio = BondPortfolio(
                    bond_number=bond_number,
                    maturity_date=maturity_date,
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
                # Віднімаємо по середній ціні купівлі
                portfolio.total_amount -= (context.user_data['sell_avg_price'] * quantity)
                
                if portfolio.total_quantity <= 0:
                    session.delete(portfolio)
                else:
                    portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity if portfolio.total_quantity > 0 else 0
                    portfolio.last_update = datetime.now().isoformat()
        
        session.commit()
        session.close()
        
        # Формуємо повідомлення
        text = (
            f"✅ *Запис додано!*\n\n"
            f"📅 Дата: {context.user_data['bond_date']}\n"
            f"📈 Операція: {operation_type.capitalize()}\n"
            f"🔢 Номер: {bond_number}\n"
            f"📆 Термін погашення: {maturity_date}\n"
            f"💵 Ціна за шт: {context.user_data['price_per_unit']:.2f} грн\n"
            f"📦 Кількість: {quantity} шт\n"
            f"💰 Сума: {total_amount:.2f} грн\n"
            f"🏦 Платформа: {platform}"
        )
        
        if operation_type == 'продаж':
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            text += f"\n\n{pnl_emoji} *PnL: {pnl:+.2f} грн*"
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад до ОВДП", callback_data='ovdp')]
            ]),
            parse_mode='Markdown'
        )
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error saving bond: {e}")
        await update.callback_query.edit_message_text(f"❌ Помилка при збереженні: {str(e)}")


async def show_bonds_list(update: Update, context: CallbackContext, page=1):
    """Показати список записів ОВДП з пагінацією (по 10 на сторінку)"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        session.close()
        
        if not bonds:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
            await query.edit_message_text("📭 Немає записів", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Сортуємо по даті: нові спочатку
        def parse_date(date_str):
            try:
                return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
            except:
                return datetime.min
        
        bonds.sort(key=lambda x: (parse_date(x.date), x.id), reverse=True)
        
        # Пагінація - по 10 записів на сторінку
        records_per_page = 10
        total_pages = (len(bonds) + records_per_page - 1) // records_per_page
        
        # Перевіряємо границі сторінки
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        # Беремо записи для поточної сторінки
        start_idx = (page - 1) * records_per_page
        end_idx = start_idx + records_per_page
        page_bonds = bonds[start_idx:end_idx]
        
        text = f"📋 *Мої записи ОВДП* (сторінка {page}/{total_pages})\n\n"
        for bond in page_bonds:
            text += f"📅 {bond.date} | {'🟢' if bond.operation_type == 'купівля' else '🔴'} {bond.operation_type} | {bond.platform}\n"
            text += f"   🔢 {bond.bond_number} | {bond.quantity} шт | {bond.total_amount:.2f} грн\n\n"
        
        # Будуємо кнопки пагінації
        keyboard = []
        
        # Кнопки номерів сторінок
        if total_pages > 1:
            page_buttons = []
            for p in range(1, total_pages + 1):
                if p == page:
                    page_buttons.append(InlineKeyboardButton(f"[{p}]", callback_data=f'bonds_list_page_{p}'))
                else:
                    page_buttons.append(InlineKeyboardButton(str(p), callback_data=f'bonds_list_page_{p}'))
            keyboard.append(page_buttons)
        
        # Кнопка назад
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='ovdp')])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_bonds_portfolio(update: Update, context: CallbackContext, platform=None):
    """Показати портфель облігацій з таблиці bond_portfolio"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        # Беремо дані прямо з таблиці bond_portfolio
        portfolio_records = session.query(BondPortfolio).order_by(BondPortfolio.last_update.desc()).all()
        session.close()
        
        if not portfolio_records:
            keyboard = [
                [InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                 InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')],
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
            ]
            await query.edit_message_text("📭 Портфель пустий", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Фільтруємо по платформі якщо вибрана
        if platform:
            platform = platform.upper()
            portfolio_records = [p for p in portfolio_records if p.platform.upper() == platform]
            if not portfolio_records:
                keyboard = [
                    [InlineKeyboardButton("💹 Взнати PnL", callback_data='pnl_portfolio')],
                    [InlineKeyboardButton("🏦 Всі", callback_data='ovdp_portfolio'),
                     InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                     InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
                ]
                await query.edit_message_text(f"📭 Немає облігацій для платформи {platform}", reply_markup=InlineKeyboardMarkup(keyboard))
                return
        
        title = f"💼 *Портфель ОВДП*"
        if platform:
            title += f" - {platform}"
        text = f"{title}\n\n"
        total_invested = 0
        total_quantity = 0
        
        if platform:
            # Фільтр по платформі — показуємо як є
            for record in portfolio_records:
                text += f"🔢 *{record.bond_number}*\n"
                text += f"   📆 Термін: {record.maturity_date}\n"
                text += f"   📦 Кількість: {record.total_quantity} шт\n"
                text += f"   💰 Середня ціна: {record.avg_price:.2f} грн\n"
                text += f"   💵 Сума: {record.total_amount:.2f} грн\n\n"
                total_invested += record.total_amount
                total_quantity += record.total_quantity
        else:
            # Загальний портфель — групуємо по bond_number
            from collections import defaultdict
            grouped = defaultdict(lambda: {'quantity': 0, 'amount': 0, 'maturity_date': ''})
            
            for record in portfolio_records:
                grouped[record.bond_number]['quantity'] += record.total_quantity
                grouped[record.bond_number]['amount'] += record.total_amount
                grouped[record.bond_number]['maturity_date'] = record.maturity_date
            
            for bond_num, data in sorted(grouped.items()):
                avg_price = data['amount'] / data['quantity'] if data['quantity'] > 0 else 0
                text += f"🔢 *{bond_num}*\n"
                text += f"   📆 Термін: {data['maturity_date']}\n"
                text += f"   📦 Кількість: {data['quantity']} шт\n"
                text += f"   💰 Середня ціна: {avg_price:.2f} грн\n"
                text += f"   💵 Сума: {data['amount']:.2f} грн\n\n"
                total_invested += data['amount']
                total_quantity += data['quantity']
        
        text += f"━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 *Всього інвестовано:* {total_invested:.2f} грн\n"
        text += f"📊 *Всього облігацій:* {total_quantity} шт"
        
        if platform:
            keyboard = [
                [InlineKeyboardButton("🏦 Всі", callback_data='ovdp_portfolio'),
                 InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                 InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')],
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("💹 Взнати PnL", callback_data='pnl_portfolio')],
                [InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                 InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')],
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
            ]
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception as e:
            error_msg = str(e).lower()
            if "not modified" in error_msg:
                await query.answer("📊 Портфель не змінився", show_alert=False)
            else:
                logger.error(f"Edit error: {e}")
                await query.answer("❌ Помилка оновлення", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error showing bonds portfolio: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_bonds_stats(update: Update, context: CallbackContext):
    """Показати статистику ОВДП"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        
        # Беремо дані портфеля з bond_portfolio
        portfolio_records = session.query(BondPortfolio).all()
        
        # Беремо всі записи для розрахунку прибутку
        bonds = session.query(Bond).all()
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 Немає даних для статистики")
            return
        
        # Вартість портфеля, кількість, активи по платформах — з bond_portfolio
        current_portfolio = 0
        total_quantity = 0
        platform_current = {'ICU': 0, 'SENSBANK': 0}
        
        for record in portfolio_records:
            current_portfolio += record.total_amount
            total_quantity += record.total_quantity
            platform_key = record.platform.upper() if record.platform else ''
            if platform_key in platform_current:
                platform_current[platform_key] += record.total_amount
        
        # Реалізований прибуток — сума pnl з усіх продажів
        realized_profit = sum(b.pnl or 0 for b in bonds if b.operation_type == 'продаж')
        
        text = "📊 *Статистика ОВДП*\n\n"
        text += f"💰 *Вартість портфеля:* {current_portfolio:.0f} грн\n"
        text += f"🔢 *Кількість ОВДП:* {total_quantity} шт\n\n"
        
        text += "🏦 *Активи по платформах:*\n"
        text += f"   ICU: {platform_current['ICU']:.0f} грн\n"
        text += f"   SENSBANK: {platform_current['SENSBANK']:.0f} грн\n\n"
        text += "📈 *Реалізований прибуток:*\n"
        text += f"   {realized_profit:.0f} грн\n\n"
        text += "📊 *Динаміка прибутку по місяцях:*\n"
        
        # Динаміка по місяцях — з pnl по даті продажу
        monthly_profits = {}
        for bond in bonds:
            if bond.operation_type == 'продаж' and (bond.pnl or 0) != 0:
                try:
                    parsed = datetime.strptime(str(bond.date).strip(), '%d.%m.%Y')
                    month_key = f"{parsed.month:02d}.{parsed.year}"
                except:
                    month_key = "невідома дата"
                
                if month_key not in monthly_profits:
                    monthly_profits[month_key] = 0
                monthly_profits[month_key] += bond.pnl or 0
        
        if monthly_profits:
            def parse_month_year(month_str):
                try:
                    return datetime.strptime(month_str, '%m.%Y')
                except:
                    return datetime.max
            
            for month in sorted(monthly_profits.keys(), key=parse_month_year):
                profit = monthly_profits[month]
                text += f"   {month} - {profit:.0f} грн\n"
        else:
            text += "   Нема продажів\n"
        text += "\n"
        
        text += "💸 *Найближчі виплати:*\n"
        today = datetime.now()
        payments = []
        
        # Найближчі виплати — з bond_portfolio
        for record in portfolio_records:
            try:
                maturity = datetime.strptime(record.maturity_date, '%d.%m.%Y')
                if maturity > today:
                    payments.append({
                        'date': maturity,
                        'bond_number': record.bond_number,
                        'quantity': record.total_quantity,
                        'amount': record.total_amount
                    })
            except:
                pass
        
        payments.sort(key=lambda x: x['date'])
        
        if payments:
            for p in payments[:5]:
                text += f"   {p['date'].strftime('%d.%m.%Y')} - {p['bond_number']} - {p['quantity']} шт ({p['amount']:.0f} грн)\n"
        else:
            text += "   Немає майбутніх виплат\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_profit_menu(update: Update, context: CallbackContext):
    """Меню управління прибутками"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        
        if not bonds:
            session.close()
            await query.edit_message_text("📭 Немає даних про ОВДП")
            return
        
        # Реалізований прибуток — сума pnl з усіх продажів
        total_profit = sum(b.pnl or 0 for b in bonds if b.operation_type == 'продаж')
        
        # Отримуємо списаний прибуток
        profit_records = session.query(ProfitRecord).filter(ProfitRecord.unrealized_profit > 0).all()
        session.close()
        
        total_written_off = sum(r.unrealized_profit for r in profit_records)
        
        unrealized_profit = total_profit - total_written_off
        if unrealized_profit < 0:
            unrealized_profit = 0
        
        text = f"💰 *Управління прибутками*\n\n"
        text += f"📈 Реалізований прибуток: {total_profit:.0f} грн\n"
        text += f"📋 Не списаний прибуток: {unrealized_profit:.0f} грн\n\n"
        
        keyboard = [
            [InlineKeyboardButton("✍️ Списати прибуток", callback_data='write_off_profit')],
            [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def write_off_profit_menu(update: Update, context: CallbackContext):
    """Меню списання прибутку"""
    query = update.callback_query
    await query.answer()
    
    logger.info("write_off_profit_menu called")
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        
        if not bonds:
            session.close()
            await query.edit_message_text("📭 Немає даних про ОВДП")
            return
        
        # Реалізований прибуток — сума pnl з усіх продажів
        total_profit = sum(b.pnl or 0 for b in bonds if b.operation_type == 'продаж')
        
        profit_records = session.query(ProfitRecord).filter(ProfitRecord.unrealized_profit > 0).all()
        session.close()
        
        total_written_off = sum(r.unrealized_profit for r in profit_records)
        
        unrealized_profit = total_profit - total_written_off
        if unrealized_profit < 0:
            unrealized_profit = 0
        
        context.user_data['unrealized_profit'] = unrealized_profit
        
        text = f"💰 *Списання прибутку*\n\n"
        text += f"📋 Не списаний прибуток: *{unrealized_profit:.0f} грн*\n\n"
        
        if unrealized_profit > 0:
            keyboard = [
                [InlineKeyboardButton("✍️ Списати", callback_data='confirm_write_off')],
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp_profit')]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp_profit')]
            ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in write_off_profit_menu: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


def create_bond_key(bond_data):
    """Створює унікальний ключ для запису (дата + номер + тип + ціна + кількість)"""
    return (
        bond_data.get('date', ''),
        bond_data.get('bond_number', ''),
        bond_data.get('operation_type', ''),
        float(bond_data.get('price_per_unit', 0)),
        int(bond_data.get('quantity', 0))
    )


async def sync_bonds_from_sheets(update: Update, context: CallbackContext):
    """Синхронізація ОВДП з Excel → БД (простий експорт)"""
    query = update.callback_query
    await query.answer()
    
    try:
        sheets_manager = context.bot_data.get('sheets_manager')
        Session = context.bot_data.get('Session')
        
        if not sheets_manager or not Session:
            await query.edit_message_text("❌ Помилка: Google Sheets або БД не доступні")
            return
        
        # Імпортуємо дані з Google Sheets
        excel_bonds_data = sheets_manager.import_bonds_from_sheets()
        
        if not excel_bonds_data:
            await query.edit_message_text("📭 Немає даних в Excel для синхронізації")
            return
        
        session = Session()
        
        # 1. ВИДАЛЯЄМО ВСЕ з БД
        try:
            session.query(Bond).delete()
            session.commit()
            deleted = len(excel_bonds_data)  # Кількість рядків що були
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting bonds: {e}")
            deleted = 0
        
        # 2. ДОДАЄМО рядки з Excel у ТОЧНОМУ ПОРЯДКУ
        added = 0
        errors = []
        
        for row_idx, bond_data in enumerate(excel_bonds_data):
            try:
                new_bond = Bond(
                    row_order=row_idx + 1,  # Порядок з Excel (1, 2, 3, ...)
                    date=bond_data.get('date', ''),
                    operation_type=bond_data.get('operation_type', ''),
                    bond_number=bond_data.get('bond_number', ''),
                    maturity_date=bond_data.get('maturity_date', ''),
                    price_per_unit=float(bond_data.get('price_per_unit', 0)),
                    quantity=int(bond_data.get('quantity', 0)),
                    total_amount=float(bond_data.get('total_amount', 0)),
                    platform=bond_data.get('platform', ''),
                    pnl=float(bond_data.get('pnl', 0))
                )
                session.add(new_bond)
                added += 1
            except Exception as e:
                errors.append(f"Помилка рядка {row_idx + 1} ({bond_data.get('bond_number')}): {str(e)}")
        
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
        text += "⏳ Пересчитую портфель облігацій..."
        await query.edit_message_text(text, parse_mode='Markdown')
        
        await recalculate_bond_portfolio(Session)
        
        text += "\n✅ Портфель оновлено!"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in sync_bonds_from_sheets: {e}")
        await query.edit_message_text(f"❌ Помилка синхронізації: {str(e)}")


async def show_pnl_portfolio(update: Update, context: CallbackContext):
    """Показати PnL портфеля"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 Немає даних про ОВДП")
            return
        
        # Розраховуємо портфель
        portfolio = {}
        for bond in bonds:
            if bond.bond_number not in portfolio:
                portfolio[bond.bond_number] = {
                    'quantity': 0,
                    'buy_amount': 0,
                    'avg_price': 0
                }
            
            if bond.operation_type == 'купівля':
                portfolio[bond.bond_number]['quantity'] += bond.quantity
                portfolio[bond.bond_number]['buy_amount'] += bond.total_amount
            else:
                portfolio[bond.bond_number]['quantity'] -= bond.quantity
                portfolio[bond.bond_number]['buy_amount'] -= bond.total_amount
        
        portfolio = {k: v for k, v in portfolio.items() if v['quantity'] > 0}
        
        if not portfolio:
            await query.edit_message_text("📭 Портфель пустий")
            return
        
        # Розраховуємо середню ціну покупки
        for bond_num, data in portfolio.items():
            if data['quantity'] > 0:
                data['avg_price'] = data['buy_amount'] / data['quantity']
        
        text = "📊 *PnL Портфеля (Live)*\n\n"
        total_buy_value = 0
        total_current_value = 0
        
        for bond_num, data in sorted(portfolio.items()):
            quantity = data['quantity']
            avg_price = data['avg_price']
            buy_value = data['buy_amount']
            
            # Парсимо ціну з uainvest
            current_price = fetch_bond_price_icu(bond_num)
            
            if current_price is None:
                current_price = avg_price
                price_status = " (не вдалось завантажити)"
            else:
                price_status = " (live)"
            
            current_value = current_price * quantity
            pnl = current_value - buy_value
            pnl_percent = (pnl / buy_value * 100) if buy_value > 0 else 0
            
            text += f"🔢 *Bond \"{bond_num}\"*\n"
            text += f"   📦 Кількість: {quantity} шт\n"
            text += f"   💰 Ціна покупки: {avg_price:.2f} грн/шт\n"
            text += f"   📈 ICU ціна: {current_price:.2f} грн/шт{price_status}\n"
            text += f"   💵 Поточна вартість: {current_value:.0f} грн\n"
            text += f"   💵 PnL: {pnl:+.0f} грн ({pnl_percent:+.1f}%)\n\n"
            
            total_buy_value += buy_value
            total_current_value += current_value
        
        # Загальні показники
        total_pnl = total_current_value - total_buy_value
        total_pnl_percent = (total_pnl / total_buy_value * 100) if total_buy_value > 0 else 0
        
        text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 *Портфель всього:*\n"
        text += f"   📦 Кількість: {sum(d['quantity'] for d in portfolio.values())} шт\n"
        text += f"   💵 Твоя вартість: {total_buy_value:.0f} грн\n"
        text += f"   📈 Поточна вартість: {total_current_value:.0f} грн\n"
        text += f"   ✅ PnL: {total_pnl:+.0f} грн ({total_pnl_percent:+.1f}%)"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_portfolio')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in show_pnl_portfolio: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")