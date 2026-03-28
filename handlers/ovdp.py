import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Bond, ProfitRecord

logger = logging.getLogger(__name__)


def calculate_monthly_profit(bonds):
    """
    Розраховує прибуток по місяцях
    Повертає словник {месяц: прибуток}
    """
    monthly_profit = {}
    
    # Розраховуємо середню ціну купівлі для кожного номера
    bond_avg_prices = {}
    for bond in bonds:
        bond_num = bond.bond_number
        if bond_num not in bond_avg_prices:
            bond_avg_prices[bond_num] = {
                'buy_total': 0,
                'buy_quantity': 0
            }
        
        if bond.operation_type == 'купівля':
            bond_avg_prices[bond_num]['buy_total'] += bond.total_amount
            bond_avg_prices[bond_num]['buy_quantity'] += bond.quantity
    
    # Розраховуємо середню ціну для кожного номера
    for bond_num in bond_avg_prices:
        if bond_avg_prices[bond_num]['buy_quantity'] > 0:
            bond_avg_prices[bond_num]['avg_price'] = (
                bond_avg_prices[bond_num]['buy_total'] / 
                bond_avg_prices[bond_num]['buy_quantity']
            )
        else:
            bond_avg_prices[bond_num]['avg_price'] = 0
    
    # Обробляємо продажі по місяцях
    for bond in bonds:
        if bond.operation_type == 'продаж':
            # Витягуємо місяць з дати (формат ДД.ММ.РРРР -> ММ.РРРР)
            date_parts = bond.date.split('.')
            if len(date_parts) >= 2:
                month_year = f"{date_parts[1]}.{date_parts[2]}"
            else:
                month_year = bond.date
            
            if month_year not in monthly_profit:
                monthly_profit[month_year] = 0
            
            # Розраховуємо прибуток
            bond_num = bond.bond_number
            avg_price = bond_avg_prices[bond_num]['avg_price']
            profit_per_unit = bond.price_per_unit - avg_price
            total_profit = profit_per_unit * bond.quantity
            
            monthly_profit[month_year] += total_profit
    
    return monthly_profit


def calculate_profit_by_price(bonds):
    """
    Розраховує прибуток по кожному bond_number окремо.
    
    Логіка:
    1. Знаходимо середню ціну купівлі для кожного номера
    2. Для кожної продажі: прибуток = (price_sell - avg_price_buy) * quantity_sell
    3. Загальний прибуток = сума всіх прибутків від продажів
    """
    bond_stats = {}
    
    # Спочатку збираємо всі купівлі по bond_number
    for bond in bonds:
        bond_num = bond.bond_number
        
        if bond_num not in bond_stats:
            bond_stats[bond_num] = {
                'buy_total_amount': 0,
                'buy_total_quantity': 0,
                'avg_price_buy': 0,
                'sales': [],
                'profit': 0
            }
        
        if bond.operation_type == 'купівля':
            bond_stats[bond_num]['buy_total_amount'] += bond.total_amount
            bond_stats[bond_num]['buy_total_quantity'] += bond.quantity
    
    # Розраховуємо середню ціну купівлі для кожного номера
    for bond_num, stats in bond_stats.items():
        if stats['buy_total_quantity'] > 0:
            stats['avg_price_buy'] = stats['buy_total_amount'] / stats['buy_total_quantity']
    
    # Обробляємо продажі
    for bond in bonds:
        if bond.operation_type == 'продаж':
            bond_num = bond.bond_number
            avg_price = bond_stats[bond_num]['avg_price_buy']
            
            # Прибуток на одну облігацію
            profit_per_unit = bond.price_per_unit - avg_price
            
            # Загальний прибуток від цієї продажі
            total_profit = profit_per_unit * bond.quantity
            
            bond_stats[bond_num]['sales'].append({
                'quantity': bond.quantity,
                'price_per_unit': bond.price_per_unit,
                'profit': total_profit
            })
            
            bond_stats[bond_num]['profit'] += total_profit
    
    # Розраховуємо загальний прибуток
    total_profit = sum(stats['profit'] for stats in bond_stats.values())
    
    return bond_stats, total_profit


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


async def show_ovdp_menu(update: Update, context: CallbackContext):
    """Показати меню ОВДП"""
    query = update.callback_query
    text = "📈 *ОВДП*\n\nОберіть дію:"
    keyboard = [
        [InlineKeyboardButton("➕ Додати запис", callback_data='ovdp_add')],
        [InlineKeyboardButton("📋 Мої записи", callback_data='ovdp_list')],
        [InlineKeyboardButton("💼 Портфель", callback_data='ovdp_portfolio')],
        [InlineKeyboardButton("📊 Статистика", callback_data='ovdp_stats')],
        [InlineKeyboardButton("💰 Прибуток", callback_data='ovdp_profit')],
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
                [InlineKeyboardButton("🏦 Всі", callback_data='ovdp_portfolio'),
                 InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                 InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')],
                [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
            ]
        else:
            keyboard = [
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
        platform_stats = {'ICU': 0, 'SENSBANK': 0}
        monthly_profit = {}
        portfolio_by_bond = {}
        
        for bond in bonds:
            amount = bond.total_amount
            if bond.operation_type == 'купівля':
                total_buy += amount
                total_quantity += bond.quantity
                if bond.bond_number not in portfolio_by_bond:
                    portfolio_by_bond[bond.bond_number] = {
                        'maturity_date': bond.maturity_date,
                        'quantity': 0,
                        'total_amount': 0
                    }
                portfolio_by_bond[bond.bond_number]['quantity'] += bond.quantity
                portfolio_by_bond[bond.bond_number]['total_amount'] += amount
            else:
                total_sell += amount
            
            platform = bond.platform.upper()
            if bond.operation_type == 'купівля':
                if platform == 'ICU':
                    platform_stats['ICU'] += amount
                elif platform == 'SENSBANK':
                    platform_stats['SENSBANK'] += amount
            
            month = bond.date[:7] if len(bond.date) >= 7 else bond.date
            if month not in monthly_profit:
                monthly_profit[month] = {'buy': 0, 'sell': 0}
            if bond.operation_type == 'купівля':
                monthly_profit[month]['buy'] += amount
            else:
                monthly_profit[month]['sell'] += amount
        
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
            for month in sorted(monthly_profits.keys()):
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