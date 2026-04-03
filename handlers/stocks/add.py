import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock, StockPortfolio
from ..ovdp.utils import parse_date, recalculate_percents

logger = logging.getLogger(__name__)


def _back_kb(callback: str) -> InlineKeyboardMarkup:
    """Клавіатура з однією кнопкою Назад"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=callback)]])


def _operation_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура вибору типу операції"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Купівля", callback_data='stock_buy')],
        [InlineKeyboardButton("🔴 Продаж", callback_data='stock_sell')],
        [InlineKeyboardButton("💵 Дивіденди", callback_data='stock_dividend')],
        [InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')],
    ])


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
        await query.edit_message_text(
            f"📅 Дата: {date_value}\n\n📈 Виберіть тип операції:",
            reply_markup=_operation_keyboard(),
            parse_mode='Markdown'
        )
    else:
        context.user_data['stock_step'] = 'date_manual'
        await query.edit_message_text(
            "📅 Введіть дату вручну (у форматі ДД.ММ.РРРР):",
            reply_markup=_back_kb('stocks_add'),
            parse_mode='Markdown'
        )


async def show_calendar(update: Update, context: CallbackContext):
    """Показати календар для вибору дати"""
    query = update.callback_query

    if 'calendar_month' not in context.user_data:
        context.user_data['calendar_month'] = datetime.now()

    current_date = context.user_data['calendar_month']
    year, month = current_date.year, current_date.month

    first_day = datetime(year, month, 1)
    last_day = (
        datetime(year, month + 1, 1) - timedelta(days=1)
        if month < 12
        else datetime(year + 1, 1, 1) - timedelta(days=1)
    )
    start_weekday = first_day.weekday()

    nav_row = [
        InlineKeyboardButton("◀️", callback_data=f'stocks_cal_prev_{year}_{month}'),
        InlineKeyboardButton(first_day.strftime('%B %Y'), callback_data='stocks_cal_month'),
        InlineKeyboardButton("▶️", callback_data=f'stocks_cal_next_{year}_{month}')
    ]
    dow_row = [InlineKeyboardButton(d, callback_data='stocks_cal_dow') for d in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']]

    day_buttons = [InlineKeyboardButton(" ", callback_data='stocks_cal_empty')] * start_weekday
    for day in range(1, last_day.day + 1):
        date_str = f"{day:02d}.{month:02d}.{year}"
        day_buttons.append(InlineKeyboardButton(str(day), callback_data=f'stocks_date_{date_str}'))

    keyboard = [nav_row, dow_row] + [day_buttons[i:i+7] for i in range(0, len(day_buttons), 7)]
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
        year, month = map(int, query.data.replace('stocks_cal_prev_', '').split('_'))
        month -= 1
        if month < 1:
            month, year = 12, year - 1
    elif query.data.startswith('stocks_cal_next_'):
        year, month = map(int, query.data.replace('stocks_cal_next_', '').split('_'))
        month += 1
        if month > 12:
            month, year = 1, year + 1

    context.user_data['calendar_month'] = datetime(year, month, 1)
    await show_calendar(update, context)


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

        portfolio_records = [r for r in portfolio_records if not r.ticker.endswith('usd')]

        if not portfolio_records:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')]]
            await query.edit_message_text("📭 Портфель пустий — немає що продавати", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        keyboard = [
            [InlineKeyboardButton(
                f"{r.ticker} | {r.total_quantity} шт | {r.avg_price:.2f} $ | {r.platform}",
                callback_data=f'sell_stock_{r.ticker}'
            )]
            for r in portfolio_records
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')])
        await query.edit_message_text(
            "🔴 *Продаж акції*\n\nОберіть акцію для продажу:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

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

        context.user_data.update({
            'ticker': ticker,
            'sell_avg_price': portfolio_record.avg_price,
            'sell_max_quantity': portfolio_record.total_quantity,
            'sell_platform': portfolio_record.platform,
            'stock_step': 'sell_price'
        })

        await query.edit_message_text(
            f"🔴 *Продаж акції*\n\n"
            f"📈 Тікер: {ticker}\n"
            f"📦 В портфелі: {portfolio_record.total_quantity} шт\n"
            f"💰 Середня ціна купівлі: {portfolio_record.avg_price:.2f} $\n"
            f"📊 Біржа: {portfolio_record.platform}\n\n"
            f"💵 Введіть ціну продажу за одну акцію:",
            reply_markup=_back_kb('stock_sell'),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in handle_sell_stock_selected: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def show_dividend_selection_from_add(update: Update, context: CallbackContext):
    """Показати список акцій для дивідендів (з потоку додавання)"""
    query = update.callback_query

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        portfolio_records = session.query(StockPortfolio).all()
        session.close()

        portfolio_records = [r for r in portfolio_records if not r.ticker.endswith('usd')]

        keyboard = [
            [InlineKeyboardButton(f"{r.ticker} | {r.total_quantity} шт", callback_data=f'dividend_{r.ticker}')]
            for r in portfolio_records
        ]
        keyboard.append([InlineKeyboardButton("📝 Ввести вручну", callback_data='dividend_manual')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')])

        await query.edit_message_text(
            "💵 *Дивіденди*\n\nОберіть акцію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in show_dividend_selection_from_add: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


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

        portfolio = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()

        if operation_type == 'купівля':
            if not portfolio:
                session.add(StockPortfolio(
                    ticker=ticker,
                    total_quantity=quantity,
                    total_amount=total_amount,
                    avg_price=total_amount / quantity if quantity > 0 else 0,
                    platform=platform,
                    last_update=datetime.now().isoformat()
                ))
            else:
                portfolio.total_quantity += quantity
                portfolio.total_amount += total_amount
                portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity if portfolio.total_quantity > 0 else 0
                portfolio.last_update = datetime.now().isoformat()

        elif operation_type == 'продаж' and portfolio:
            portfolio.total_quantity -= quantity
            portfolio.total_amount -= (context.user_data['sell_avg_price'] * quantity)
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад до Акцій", callback_data='stocks')]]),
            parse_mode='Markdown'
        )
        context.user_data.clear()

    except Exception as e:
        logger.error(f"Error saving stock: {e}")
        await update.callback_query.edit_message_text(f"❌ Помилка при збереженні: {str(e)}")


async def handle_message_add(update: Update, context: CallbackContext):
    """Обробка текстових повідомлень при додаванні акції"""
    user_message = update.message.text
    step = context.user_data.get('stock_step')

    if step == 'date_manual':
        try:
            datetime.strptime(user_message, '%d.%m.%Y')
            context.user_data['stock_date'] = user_message
            context.user_data['stock_step'] = 'operation_type'
            await update.message.reply_text(
                f"📅 Дата: {user_message}\n\n📈 Виберіть тип операції:",
                reply_markup=_operation_keyboard(),
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Невірний формат дати. Введіть у форматі ДД.ММ.РРРР",
                reply_markup=_back_kb('stocks_add')
            )

    elif step == 'ticker':
        context.user_data['ticker'] = user_message.upper()
        context.user_data['stock_step'] = 'price_per_unit'
        await update.message.reply_text(
            "💰 Введіть ціну за одну акцію:",
            reply_markup=_back_kb('stocks_add')
        )

    elif step == 'price_per_unit':
        try:
            context.user_data['price_per_unit'] = float(user_message)
            context.user_data['stock_step'] = 'quantity'
            await update.message.reply_text(
                "📦 Введіть кількість акцій:",
                reply_markup=_back_kb('stocks_add')
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Будь ласка, введіть коректне число",
                reply_markup=_back_kb('stocks_add')
            )

    elif step == 'quantity':
        try:
            context.user_data['quantity'] = int(user_message)
            context.user_data['stock_step'] = 'commission'
            await update.message.reply_text(
                "💸 Введіть комісію за транзакцію:",
                reply_markup=_back_kb('stocks_add')
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Будь ласка, введіть коректне число",
                reply_markup=_back_kb('stocks_add')
            )

    elif step == 'commission':
        try:
            commission = float(user_message)
            context.user_data['commission'] = commission
            price = context.user_data.get('price_per_unit', 0)
            quantity = context.user_data.get('quantity', 0)
            platform_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 FF", callback_data='stock_platform_ff')],
                [InlineKeyboardButton("📊 IB", callback_data='stock_platform_ib')],
                [InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')],
            ])
            if price > 0:
                total_amount = (price * quantity) + commission
                avg_price = total_amount / quantity if quantity > 0 else 0
                context.user_data['total_amount'] = total_amount
                context.user_data['price_per_unit'] = avg_price
                context.user_data['stock_step'] = 'platform'
                await update.message.reply_text(
                    f"💵 Сума: {total_amount:.2f} $\n"
                    f"💸 Комісія: {commission:.2f} $\n"
                    f"📊 Реальна ціна за шт: {avg_price:.3f} $\n\n📊 Виберіть біржу:",
                    reply_markup=platform_keyboard
                )
            else:
                context.user_data['stock_step'] = 'total_amount'
                await update.message.reply_text(
                    "💰 Введіть загальну суму (без комісії):",
                    reply_markup=_back_kb('stocks_add')
                )
        except ValueError:
            await update.message.reply_text(
                "❌ Будь ласка, введіть коректне число",
                reply_markup=_back_kb('stocks_add')
            )

    elif step == 'total_amount':
        try:
            total_without_commission = float(user_message)
            commission = context.user_data.get('commission', 0)
            quantity = context.user_data.get('quantity', 0)
            total_with_commission = total_without_commission + commission
            avg_price = total_with_commission / quantity if quantity > 0 else 0
            context.user_data['total_amount'] = total_with_commission
            context.user_data['price_per_unit'] = avg_price
            context.user_data['stock_step'] = 'platform'
            platform_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 FF", callback_data='stock_platform_ff')],
                [InlineKeyboardButton("📊 IB", callback_data='stock_platform_ib')],
                [InlineKeyboardButton("🔙 Назад", callback_data='stocks_add')],
            ])
            await update.message.reply_text(
                f"💰 Сума без комісії: {total_without_commission:.2f} $\n"
                f"💸 Комісія: {commission:.2f} $\n"
                f"💵 Загальна сума: {total_with_commission:.2f} $\n"
                f"📊 Реальна ціна за шт: {avg_price:.3f} $\n\n📊 Виберіть біржу:",
                reply_markup=platform_keyboard
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Будь ласка, введіть коректне число",
                reply_markup=_back_kb('stocks_add')
            )

    elif step == 'sell_price':
        try:
            price = float(user_message)
            context.user_data['price_per_unit'] = price
            context.user_data['stock_step'] = 'sell_quantity'
            max_qty = context.user_data['sell_max_quantity']
            await update.message.reply_text(
                f"💵 Ціна продажу: {price:.2f} $\n\n"
                f"📦 Введіть кількість (максимум {max_qty} шт):",
                reply_markup=_back_kb('stock_sell')
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Будь ласка, введіть коректне число",
                reply_markup=_back_kb('stock_sell')
            )

    elif step == 'sell_quantity':
        try:
            quantity = int(user_message)
            max_qty = context.user_data['sell_max_quantity']
            if quantity <= 0:
                await update.message.reply_text(
                    "❌ Кількість має бути більше 0",
                    reply_markup=_back_kb('stock_sell')
                )
                return
            if quantity > max_qty:
                await update.message.reply_text(
                    f"❌ В портфелі тільки {max_qty} шт.\n\n📦 Введіть кількість (максимум {max_qty} шт):",
                    reply_markup=_back_kb('stock_sell')
                )
                return
            context.user_data['quantity'] = quantity
            context.user_data['stock_step'] = 'sell_commission'
            await update.message.reply_text(
                "💸 Введіть комісію за транзакцію:",
                reply_markup=_back_kb('stock_sell')
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Будь ласка, введіть коректне число",
                reply_markup=_back_kb('stock_sell')
            )

    elif step == 'sell_commission':
        try:
            commission = float(user_message)
            context.user_data['commission'] = commission
            price = context.user_data['price_per_unit']
            quantity = context.user_data['quantity']
            avg_price = context.user_data['sell_avg_price']
            platform = context.user_data['sell_platform']

            total_amount = (price * quantity) - commission
            pnl = (price - avg_price) * quantity - commission
            context.user_data.update({
                'total_amount': total_amount,
                'pnl': pnl,
                'platform': platform
            })

            Session = context.bot_data.get('Session')
            if not Session:
                await update.message.reply_text("❌ Помилка підключення до бази даних")
                return

            session = Session()
            ticker = context.user_data['ticker']

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

            pnl_emoji = "📈" if pnl >= 0 else "📉"
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
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад до Акцій", callback_data='stocks')]]),
                parse_mode='Markdown'
            )
            context.user_data.clear()

        except ValueError:
            await update.message.reply_text(
                "❌ Будь ласка, введіть коректне число",
                reply_markup=_back_kb('stock_sell')
            )