import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import requests
from bs4 import BeautifulSoup
import time

from models import Bond, ProfitRecord

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
            month_year = get_month_year(sale['sell_date'])
            
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
    
    # Сортуємо по даті для правильного FIFO
    # Вторинне сортування: купівля (0) перед продажем (1) на одну дату
    sorted_bonds = sorted(bonds, key=lambda x: (
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
            # Продаємо з черги FIFO
            remaining_quantity = bond.quantity
            sale_profit = 0
            sale_details = []
            
            while remaining_quantity > 0 and bond_stats[bond_num]['buy_queue']:
                buy = bond_stats[bond_num]['buy_queue'][0]
                
                # Скільки можемо продати з цієї купівлі
                qty_to_sell = min(remaining_quantity, buy['quantity'])
                
                # Розраховуємо прибуток для цієї партії
                profit_per_unit = bond.price_per_unit - buy['price']
                partition_profit = profit_per_unit * qty_to_sell
                sale_profit += partition_profit
                
                sale_details.append({
                    'buy_date': buy['date'],
                    'buy_price': buy['price'],
                    'quantity': qty_to_sell,
                    'partition_profit': partition_profit
                })
                
                # Оновлюємо кількість в черзі
                buy['quantity'] -= qty_to_sell
                remaining_quantity -= qty_to_sell
                
                # Якщо купівля повністю продана - видаляємо з черги
                if buy['quantity'] == 0:
                    bond_stats[bond_num]['buy_queue'].popleft()
            
            bond_stats[bond_num]['sales'].append({
                'sell_date': bond.date,
                'quantity': bond.quantity,
                'sell_price': bond.price_per_unit,
                'profit': sale_profit,
                'details': sale_details
            })
            
            bond_stats[bond_num]['profit'] += sale_profit
    
    # Розраховуємо загальний прибуток
    total_profit = sum(stats['profit'] for stats in bond_stats.values())
    
    return dict(bond_stats), total_profit


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
    elif query.data == 'bond_buy':
        context.user_data['bond_operation_type'] = 'купівля'
        context.user_data['bond_step'] = 'bond_number'
        await query.edit_message_text("🔢 Введіть номер ОВДП (наприклад: МХ3012-202):", parse_mode='Markdown')
    elif query.data == 'bond_sell':
        context.user_data['bond_operation_type'] = 'продаж'
        context.user_data['bond_step'] = 'bond_number'
        await query.edit_message_text("🔢 Введіть номер ОВДП для продажу:", parse_mode='Markdown')
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
    tomorrow = today + timedelta(days=1)
    three_days = today + timedelta(days=3)
    week = today + timedelta(days=7)
    
    keyboard = [
        [InlineKeyboardButton(f"📅 Сьогодні ({today.strftime('%d.%m.%Y')})", callback_data=f'date_{today.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton(f"📅 Завтра ({tomorrow.strftime('%d.%m.%Y')})", callback_data=f'date_{tomorrow.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton(f"📅 За 3 дні ({three_days.strftime('%d.%m.%Y')})", callback_data=f'date_{three_days.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton(f"📅 Через тиждень ({week.strftime('%d.%m.%Y')})", callback_data=f'date_{week.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton("📅 Вручну", callback_data='date_manual')],
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


async def handle_message_ovdp(update: Update, context: CallbackContext):
    """Обробка текстових повідомлень для ОВДП"""
    if 'bond_step' not in context.user_data and 'profit_step' not in context.user_data:
        return
    
    user_message = update.message.text
    step = context.user_data.get('bond_step') or context.user_data.get('profit_step')
    
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


async def save_bond(update: Update, context: CallbackContext):
    """Зберігає облігацію в базу даних"""
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await update.callback_query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bond = Bond(
            date=context.user_data['bond_date'],
            operation_type=context.user_data['bond_operation_type'],
            bond_number=context.user_data['bond_number'],
            maturity_date=context.user_data['maturity_date'],
            price_per_unit=context.user_data['price_per_unit'],
            quantity=context.user_data['quantity'],
            total_amount=context.user_data['total_amount'],
            platform=context.user_data['platform']
        )
        session.add(bond)
        session.commit()
        
        profit_record = ProfitRecord(
            operation_date=context.user_data['bond_date'],
            operation_type=context.user_data['bond_operation_type'],
            amount=context.user_data['total_amount']
        )
        session.add(profit_record)
        session.commit()
        session.close()
        
        await update.callback_query.edit_message_text(
            f"✅ Запис додано!\n\n"
            f"📈 {context.user_data['bond_operation_type'].capitalize()}\n"
            f"🔢 {context.user_data['bond_number']}\n"
            f"💰 {context.user_data['total_amount']:.2f} грн"
        )
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error saving bond: {e}")
        await update.callback_query.edit_message_text(f"❌ Помилка при збереженні: {str(e)}")


async def show_bonds_list(update: Update, context: CallbackContext):
    """Показати список всіх записів ОВДП"""
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
        
        text = "📋 *Мої записи ОВДП*\n\n"
        for bond in bonds:
            text += f"📅 {bond.date} | "
            text += f"{'🟢' if bond.operation_type == 'купівля' else '🔴'} {bond.operation_type}\n"
            text += f"   🔢 {bond.bond_number} | 💰 {bond.total_amount:.2f} грн | {bond.platform}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_bonds_portfolio(update: Update, context: CallbackContext, platform=None):
    """Показати портфель облігацій"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        all_bonds = session.query(Bond).all()
        session.close()
        
        portfolio = {}
        for bond in all_bonds:
            if bond.bond_number not in portfolio:
                portfolio[bond.bond_number] = {
                    'maturity_date': bond.maturity_date,
                    'total_quantity': 0,
                    'total_amount': 0,
                    'platform': bond.platform
                }
            
            if bond.operation_type == 'купівля':
                portfolio[bond.bond_number]['total_quantity'] += bond.quantity
                portfolio[bond.bond_number]['total_amount'] += bond.total_amount
            else:
                portfolio[bond.bond_number]['total_quantity'] -= bond.quantity
                portfolio[bond.bond_number]['total_amount'] -= bond.total_amount
        
        portfolio = {k: v for k, v in portfolio.items() if v['total_quantity'] > 0}
        
        if platform:
            platform_name = platform.upper()
            portfolio = {k: v for k, v in portfolio.items() if v['platform'].upper() == platform_name}
        
        if not portfolio:
            keyboard = [
                [InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                 InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')],
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
            ]
            platform_name = platform.upper() if platform else ''
            await query.edit_message_text(f"📭 Немає куплених ОВДП для платформи {platform_name}", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        title = f"💼 *Портфель ОВДП*"
        if platform:
            title += f" - {platform.upper()}"
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
        
        if platform:
            keyboard = [
                [InlineKeyboardButton("💹 Взнати PnL", callback_data='pnl_portfolio')],
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
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
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
        bonds = session.query(Bond).all()
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 Немає даних для статистики")
            return
        
        total_buy = 0
        total_sell = 0
        total_quantity = 0
        portfolio_by_bond = {}
        
        for bond in bonds:
            amount = bond.total_amount
            
            # Додаємо облігацію в портфель
            if bond.bond_number not in portfolio_by_bond:
                portfolio_by_bond[bond.bond_number] = {
                    'maturity_date': bond.maturity_date,
                    'quantity': 0,
                    'total_amount': 0
                }
            
            if bond.operation_type == 'купівля':
                total_buy += amount
                total_quantity += bond.quantity
                portfolio_by_bond[bond.bond_number]['quantity'] += bond.quantity
                portfolio_by_bond[bond.bond_number]['total_amount'] += amount
            else:
                total_sell += amount
                # ДЛЯ ПРОДАЖІВ - ВИЧИТАЄМО З ПОРТФЕЛЯ!
                total_quantity -= bond.quantity
                portfolio_by_bond[bond.bond_number]['quantity'] -= bond.quantity
                portfolio_by_bond[bond.bond_number]['total_amount'] -= amount
        
        current_portfolio = total_buy - total_sell
        
        # Розраховуємо прибуток по ціні
        bond_stats, realized_profit = calculate_profit_by_price(bonds)
        
        text = "📊 *Статистика ОВДП*\n\n"
        text += "💰 *Вартість портфеля:*\n"
        text += f"   {current_portfolio:.0f} грн\n"
        text += f"   Кількість ОВДП: {total_quantity} шт\n\n"
        
        # Розраховуємо активи по платформах (беремо з портфеля)
        platform_current = {'ICU': 0, 'SENSBANK': 0}
        
        # Для кожної облігації в портфелі знаходимо її платформу
        for bond_num, data in portfolio_by_bond.items():
            # Беремо платформу з останньої операції (купівля або продаж) для цієї облігації
            bond_platform = None
            for bond in reversed(bonds):  # Йдемо з кінця щоб взяти останню
                if bond.bond_number == bond_num:
                    bond_platform = bond.platform.upper()
                    break
            
            # Додаємо суму облігацій в портфелі до відповідної платформи
            if bond_platform and bond_platform in platform_current:
                platform_current[bond_platform] += data['total_amount']
        
        text += "🏦 *Активи по платформах:*\n"
        text += f"   ICU: {platform_current['ICU']:.0f} грн\n"
        text += f"   SENSBANK: {platform_current['SENSBANK']:.0f} грн\n\n"
        text += "📈 *Реалізований прибуток:*\n"
        text += f"   {realized_profit:.0f} грн\n\n"
        text += "📊 *Динаміка прибутку по місяцях:*\n"
        
        # Розраховуємо прибуток по місяцях
        monthly_profits = calculate_monthly_profit(bonds)
        
        if monthly_profits:
            # Сортуємо по даті, не по текстовому ключу
            from datetime import datetime
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
        
        for bond_num, data in portfolio_by_bond.items():
            try:
                maturity = datetime.strptime(data['maturity_date'], '%d.%m.%Y')
                if maturity > today:
                    payments.append({
                        'date': maturity,
                        'bond_number': bond_num,
                        'quantity': data['quantity'],
                        'amount': data['total_amount']
                    })
            except:
                pass
        
        payments.sort(key=lambda x: x['date'])
        
        if payments:
            for p in payments[:5]:
                text += f"   {p['date'].strftime('%d.%m.%Y')} - {p['quantity']} шт ({p['amount']:.0f} грн)\n"
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
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 Немає даних про ОВДП")
            return
        
        # Розраховуємо прибуток по ціні
        bond_stats, total_profit = calculate_profit_by_price(bonds)
        
        # Отримуємо списаний прибуток
        session = Session()
        profit_records = session.query(ProfitRecord).filter(ProfitRecord.unrealized_profit > 0).all()
        session.close()
        
        total_written_off = 0
        for record in profit_records:
            total_written_off += record.unrealized_profit
        
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
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 Немає даних про ОВДП")
            return
        
        # Розраховуємо прибуток по ціні
        bond_stats, total_profit = calculate_profit_by_price(bonds)
        
        session = Session()
        profit_records = session.query(ProfitRecord).filter(ProfitRecord.unrealized_profit > 0).all()
        session.close()
        
        total_written_off = 0
        for record in profit_records:
            total_written_off += record.unrealized_profit
        
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
    """Синхронізація ОВДП з Excel → БД"""
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
        db_bonds = session.query(Bond).all()
        
        # Створюємо словники для порівняння
        excel_keys = set()
        excel_data_by_key = {}
        
        for bond_data in excel_bonds_data:
            key = create_bond_key(bond_data)
            excel_keys.add(key)
            excel_data_by_key[key] = bond_data
        
        db_keys = {}
        for db_bond in db_bonds:
            bond_data = {
                'date': db_bond.date,
                'bond_number': db_bond.bond_number,
                'operation_type': db_bond.operation_type,
                'price_per_unit': db_bond.price_per_unit,
                'quantity': db_bond.quantity,
                'maturity_date': db_bond.maturity_date,
                'total_amount': db_bond.total_amount,
                'platform': db_bond.platform
            }
            key = create_bond_key(bond_data)
            db_keys[key] = db_bond
        
        # Підраховуємо зміни
        added = 0
        updated = 0
        deleted = 0
        errors = []
        
        # 1. Додаємо нові та оновлюємо існуючі
        for key, excel_bond in excel_data_by_key.items():
            if key in db_keys:
                # Оновлюємо існуючий запис
                db_bond = db_keys[key]
                try:
                    if (db_bond.maturity_date != excel_bond.get('maturity_date', '') or
                        db_bond.total_amount != float(excel_bond.get('total_amount', 0)) or
                        db_bond.platform != excel_bond.get('platform', '')):
                        
                        db_bond.maturity_date = excel_bond.get('maturity_date', '')
                        db_bond.total_amount = float(excel_bond.get('total_amount', 0))
                        db_bond.platform = excel_bond.get('platform', '')
                        updated += 1
                except Exception as e:
                    errors.append(f"Помилка при оновленні запису {excel_bond.get('bond_number')}: {str(e)}")
            else:
                # Додаємо новий запис
                try:
                    new_bond = Bond(
                        date=excel_bond.get('date', ''),
                        operation_type=excel_bond.get('operation_type', ''),
                        bond_number=excel_bond.get('bond_number', ''),
                        maturity_date=excel_bond.get('maturity_date', ''),
                        price_per_unit=float(excel_bond.get('price_per_unit', 0)),
                        quantity=int(excel_bond.get('quantity', 0)),
                        total_amount=float(excel_bond.get('total_amount', 0)),
                        platform=excel_bond.get('platform', '')
                    )
                    session.add(new_bond)
                    added += 1
                except Exception as e:
                    errors.append(f"Помилка при додаванні запису {excel_bond.get('bond_number')}: {str(e)}")
        
        # 2. Видаляємо записи, яких немає в Excel
        for key, db_bond in db_keys.items():
            if key not in excel_keys:
                try:
                    session.delete(db_bond)
                    deleted += 1
                except Exception as e:
                    errors.append(f"Помилка при видаленні запису {db_bond.bond_number}: {str(e)}")
        
        # Зберігаємо зміни
        session.commit()
        session.close()
        
        # Формуємо відповідь
        text = "🔄 *Синхронізація Excel → БД завершена*\n\n"
        text += f"✅ Додано: {added}\n"
        text += f"🔄 Оновлено: {updated}\n"
        text += f"❌ Видалено: {deleted}\n\n"
        
        if errors:
            text += f"⚠️ Помилок: {len(errors)}\n"
            for error in errors[:5]:  # Показуємо перші 5 помилок
                text += f"   • {error}\n"
            if len(errors) > 5:
                text += f"   • ... та ще {len(errors) - 5} помилок\n"
        else:
            text += "✨ Без помилок!"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error syncing from sheets: {e}")
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