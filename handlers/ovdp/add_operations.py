"""
Додавання операцій з ОВДП (купівля/продаж)
Включає календар для вибору дати
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import Bond, BondPortfolio, ProfitRecord

logger = logging.getLogger(__name__)

MONTHS_UA = {
    1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
    5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
    9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
}


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
            [InlineKeyboardButton("🔴 Продаж", callback_data='bond_sell')],
            [InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]
        ]
        await query.edit_message_text(
            f"📅 Дата: {date_value}\n\n📈 Виберіть тип операції:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        context.user_data['bond_step'] = 'date_manual'
        await query.edit_message_text(
            "📅 Введіть дату вручну (у форматі ДД.ММ.РРРР):\n\n"
            "Або натисніть кнопку нижче:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]]),
            parse_mode='Markdown'
        )


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
    
    month_name = f"{MONTHS_UA[month]} ({month:02d})"
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
        portfolio_records = [
            r for r in session.query(BondPortfolio).all()
            if not r.bond_number.endswith('uah')
        ]
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='bond_sell')]]),
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
                    [InlineKeyboardButton("🔴 Продаж", callback_data='bond_sell')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]
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

            # Шукаємо чи є вже записи з таким номером ОВДП
            Session = context.bot_data.get('Session')
            existing_maturity = None
            if Session:
                session = Session()
                existing = session.query(Bond).filter(
                    Bond.bond_number == user_message
                ).first()
                session.close()
                if existing and existing.maturity_date:
                    existing_maturity = existing.maturity_date

            if existing_maturity:
                # Пропонуємо знайдену дату погашення
                context.user_data['bond_step'] = 'maturity_date_confirm'
                keyboard = [
                    [InlineKeyboardButton(f"✅ {existing_maturity}", callback_data=f'maturity_use_{existing_maturity}')],
                    [InlineKeyboardButton("✏️ Ввести іншу", callback_data='maturity_manual')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]
                ]
                await update.message.reply_text(
                    f"🔢 Номер: {user_message}\n\n"
                    f"📆 Знайдено дату погашення з попередніх записів:\n"
                    f"*{existing_maturity}*\n\n"
                    f"Використати цю дату?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            else:
                # Нова облігація — вводимо вручну
                context.user_data['bond_step'] = 'maturity_date'
                await update.message.reply_text(
                    "📆 Введіть термін погашення (ДД.ММ.РРРР):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]]),
                )
        
        elif step == 'maturity_date':
            try:
                datetime.strptime(user_message, '%d.%m.%Y')
                context.user_data['maturity_date'] = user_message
                context.user_data['bond_step'] = 'price_per_unit'
                await update.message.reply_text(
                    "💰 Введіть ціну за одну облігацію:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]]),
                )
            except ValueError:
                await update.message.reply_text("❌ Невірний формат дати. Будь ласка, введіть у форматі ДД.ММ.РРРР")
        
        elif step == 'price_per_unit':
            try:
                price = float(user_message)
                context.user_data['price_per_unit'] = price
                context.user_data['bond_step'] = 'quantity'
                await update.message.reply_text(
                    "📦 Введіть кількість облігацій:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]]),
                )
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
                    [InlineKeyboardButton("🏦 SENSBANK", callback_data='platform_sensbank')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='ovdp_add')]
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
                    f"📦 Введіть кількість (максимум {max_qty} шт):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='bond_sell')]]),
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
        
        elif step == 'ovdp_balance_amount':
            try:
                amount = float(user_message)
                if amount < 0:
                    await update.message.reply_text("❌ Сума має бути 0 або більше")
                    return
                
                Session = context.bot_data.get('Session')
                if not Session:
                    await update.message.reply_text("❌ Помилка підключення до бази даних")
                    return
                
                platform = context.user_data['ovdp_balance_platform']
                ticker = f"{platform}uah"
                
                session = Session()
                record = session.query(BondPortfolio).filter(BondPortfolio.bond_number == ticker).first()
                
                if record:
                    record.total_amount = amount
                    record.avg_price = amount
                    record.last_update = datetime.now().isoformat()
                else:
                    record = BondPortfolio(
                        bond_number=ticker,
                        maturity_date='',
                        total_quantity=1,
                        total_amount=amount,
                        avg_price=amount,
                        platform=platform,
                        percent=0,
                        last_update=datetime.now().isoformat()
                    )
                    session.add(record)
                
                session.commit()
                from .balance import recalculate_bond_percents
                recalculate_bond_percents(session)
                session.close()
                
                keyboard = [
                    [InlineKeyboardButton("💼 До портфеля", callback_data='ovdp_portfolio')],
                    [InlineKeyboardButton("🔙 До ОВДП", callback_data='ovdp')]
                ]
                await update.message.reply_text(
                    f"✅ *Залишок оновлено!*\n\n"
                    f"🏦 Платформа: {platform}\n"
                    f"💵 Залишок: {amount:.2f} грн",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                
                context.user_data.pop('bond_step', None)
                context.user_data.pop('ovdp_balance_platform', None)
                
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
        from .balance import recalculate_bond_percents
        recalculate_bond_percents(session)
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
    """Зберігає облігацію в базу даних та оновлює портфель (для купівлі)"""
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
        from .balance import recalculate_bond_percents
        recalculate_bond_percents(session)
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