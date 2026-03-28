import logging
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from sqlalchemy.orm import sessionmaker

from models import Bond, ProfitRecord

logger = logging.getLogger(__name__)

# Буде встановлено з bot.py
Session = None


def set_session(session):
    """Встановити сесію БД"""
    global Session
    Session = session


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
    if 'bond_step' not in context.user_data:
        return
    
    user_message = update.message.text
    step = context.user_data['bond_step']
    
    try:
        if step == 'date_manual':
            # Перевіряємо формат дати
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
    
    except Exception as e:
        logger.error(f"Error in handle_message_ovdp: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")


async def save_bond(update: Update, context: CallbackContext):
    """Зберігає облігацію в базу даних"""
    try:
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
        
        # Також зберігаємо в таблицю прибутків
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
        
        # Очищаємо контекст
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error saving bond: {e}")
        await update.callback_query.edit_message_text(f"❌ Помилка при збереженні: {str(e)}")


async def show_bonds_list(update: Update, context: CallbackContext):
    """Показати список всіх записів ОВДП"""
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
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
            await query.edit_message_text(
                "📭 Немає записів",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        text = "📋 *Мої записи ОВДП*\n\n"
        for bond in bonds:
            text += f"📅 {bond.date} | "
            text += f"{'🟢' if bond.operation_type == 'купівля' else '🔴'} {bond.operation_type}\n"
            text += f"   🔢 {bond.bond_number} | 💰 {bond.total_amount:.2f} грн | {bond.platform}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_bonds_portfolio(update: Update, context: CallbackContext, platform=None):
    """Показати портфель облігацій"""
    query = update.callback_query
    await query.answer()
    
    try:
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        all_bonds = session.query(Bond).all()
        session.close()
        
        # Формуємо портфель (купівлі - продажі по кожній облігації)
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
        
        # Видаляємо облігації з нульовою кількістю
        portfolio = {k: v for k, v in portfolio.items() if v['total_quantity'] > 0}
        
        # Фільтруємо по платформі, якщо потрібно
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
            await query.edit_message_text(
                f"📭 Немає куплених ОВДП для платформи {platform_name}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Формуємо текст
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
        
        # Додаємо кнопки фільтрації
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
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_bonds_stats(update: Update, context: CallbackContext):
    """Показати статистику ОВДП"""
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
            await query.edit_message_text("📭 Немає даних для статистики")
            return
        
        # Розрахунки
        total_buy = 0
        total_sell = 0
        total_quantity = 0
        platform_stats = {'ICU': 0, 'SENSBANK': 0}
        monthly_profit = {}
        portfolio_by_bond = {}  # для найближчих виплат
        
        for bond in bonds:
            amount = bond.total_amount
            
            if bond.operation_type == 'купівля':
                total_buy += amount
                total_quantity += bond.quantity
                # Збираємо портфель для виплат
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
            
            # Статистика по платформах (тільки купівлі)
            platform = bond.platform.upper()
            if bond.operation_type == 'купівля':
                if platform == 'ICU':
                    platform_stats['ICU'] += amount
                elif platform == 'SENSBANK':
                    platform_stats['SENSBANK'] += amount
            
            # Динаміка прибутку по місяцях
            month = bond.date[:7] if len(bond.date) >= 7 else bond.date
            if month not in monthly_profit:
                monthly_profit[month] = {'buy': 0, 'sell': 0}
            if bond.operation_type == 'купівля':
                monthly_profit[month]['buy'] += amount
            else:
                monthly_profit[month]['sell'] += amount
        
        current_portfolio = total_buy - total_sell
        realized_profit = total_sell - total_buy
        
        # Формуємо текст
        text = "📊 *Статистика ОВДП*\n\n"
        
        text += "💰 *Вартість ОВДП в портфелі:*\n"
        text += f"   {current_portfolio:.0f} грн\n"
        text += f"   Кількість ОВДП: {total_quantity} шт\n\n"
        
        text += "🏦 *Інвестування по платформах:*\n"
        text += f"   ICU: {platform_stats['ICU']:.0f} грн\n"
        text += f"   SENSBANK: {platform_stats['SENSBANK']:.0f} грн\n\n"
        
        text += "📈 *Реалізований прибуток:*\n"
        text += f"   {realized_profit:.0f} грн\n\n"
        
        text += "📊 *Динаміка по місяцях:*\n"
        for month in sorted(monthly_profit.keys()):
            buy = monthly_profit[month]['buy']
            sell = monthly_profit[month]['sell']
            profit = sell - buy
            text += f"   {month}: Куп. {buy:.0f} грн | Прод. {sell:.0f} грн | Прибуток {profit:.0f} грн\n"
        text += "\n"
        
        # Найближчі виплати (з портфеля)
        text += "💸 *Найближчі виплати:*\n"
        
        today = datetime.now()
        
        # Збираємо дати погашення
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
        
        # Сортуємо за датою
        payments.sort(key=lambda x: x['date'])
        
        if payments:
            for p in payments[:5]:  # Показуємо 5 найближчих
                text += f"   {p['date'].strftime('%d.%m.%Y')} - {p['quantity']} шт ({p['amount']:.0f} грн)\n"
        else:
            text += "   Немає майбутніх виплат\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_profit_menu(update: Update, context: CallbackContext):
    """Меню управління прибутками"""
    query = update.callback_query
    await query.answer()
    
    try:
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        session.close()
        
        # Розраховуємо прибутки
        total_buy = 0
        total_sell = 0
        
        for bond in bonds:
            if bond.operation_type == 'купівля':
                total_buy += bond.total_amount
            else:
                total_sell += bond.total_amount
        
        realized_profit = total_sell - total_buy
        
        # Отримуємо списаний прибуток
        session = Session()
        profit_records = session.query(ProfitRecord).all()
        session.close()
        
        total_written_off = 0
        for record in profit_records:
            total_written_off += record.unrealized_profit
        
        unrealized_profit = realized_profit - total_written_off
        
        text = f"💰 *Управління прибутками*\n\n"
        text += f"📈 Реалізований прибуток: {realized_profit:.0f} грн\n"
        text += f"📋 Нереалізований прибуток: {unrealized_profit:.0f} грн\n"
        text += f"✅ Списаний прибуток: {total_written_off:.0f} грн\n\n"
        
        keyboard = [
            [InlineKeyboardButton("✍️ Списати прибуток", callback_data='write_off_profit')],
            [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")