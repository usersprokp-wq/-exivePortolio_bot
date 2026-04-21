import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Crypto, CryptoPortfolio
from .utils import parse_date, recalculate_percents

logger = logging.getLogger(__name__)

UA_MONTHS = {
    1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
    5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
    9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
}


def _back_kb(callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=callback)]])


def _operation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Купівля", callback_data='crypto_buy')],
        [InlineKeyboardButton("🔴 Продаж", callback_data='crypto_sell')],
        [InlineKeyboardButton("🔙 Назад", callback_data='crypto')],
    ])


async def show_date_step(update: Update, context: CallbackContext):
    query = update.callback_query
    today = datetime.now()
    keyboard = [
        [InlineKeyboardButton(f"📅 Сьогодні ({today.strftime('%d.%m.%Y')})", callback_data=f'crypto_date_{today.strftime("%d.%m.%Y")}')],
        [InlineKeyboardButton("📅 Вибрати дату", callback_data='crypto_date_calendar')],
        [InlineKeyboardButton("🔙 Назад", callback_data='crypto_add')]
    ]
    op = context.user_data.get('crypto_operation_type', '')
    op_label = {'купівля': '🟢 Купівля', 'продаж': '🔴 Продаж'}.get(op, '')
    await query.edit_message_text(
        f"₿ *Додавання крипти*\n{op_label}\n\n📅 Виберіть дату операції:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def start_crypto_add(update: Update, context: CallbackContext):
    query = update.callback_query
    context.user_data['crypto_step'] = 'operation_type'
    await query.edit_message_text(
        "₿ *Додавання крипти*\n\n📈 Виберіть тип операції:",
        reply_markup=_operation_keyboard(),
        parse_mode='Markdown'
    )


async def handle_crypto_date_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    date_value = query.data.replace('crypto_date_', '')
    operation_type = context.user_data.get('crypto_operation_type', '')
    op_label = {'купівля': '🟢 Купівля', 'продаж': '🔴 Продаж'}.get(operation_type, '')

    if date_value == 'calendar':
        await show_calendar(update, context)
    else:
        context.user_data['crypto_date'] = date_value
        if operation_type == 'продаж':
            context.user_data['crypto_step'] = 'sell_ticker'
            await show_sell_crypto_selection(update, context)
        else:
            context.user_data['crypto_step'] = 'ticker'
            await query.edit_message_text(
                f"📅 Дата: {date_value}\n{op_label}\n\n₿ Введіть тікер монети (наприклад BTC, ETH):",
                reply_markup=_back_kb('crypto_date_step'),
                parse_mode='Markdown'
            )


async def show_calendar(update: Update, context: CallbackContext):
    query = update.callback_query
    if 'crypto_calendar_month' not in context.user_data:
        context.user_data['crypto_calendar_month'] = datetime.now()

    current_date = context.user_data['crypto_calendar_month']
    year, month = current_date.year, current_date.month
    first_day = datetime(year, month, 1)
    last_day = (
        datetime(year, month + 1, 1) - timedelta(days=1)
        if month < 12
        else datetime(year + 1, 1, 1) - timedelta(days=1)
    )
    start_weekday = first_day.weekday()
    month_label = f"{UA_MONTHS[month]} {year}"
    nav_row = [
        InlineKeyboardButton("◀️", callback_data=f'crypto_cal_prev_{year}_{month}'),
        InlineKeyboardButton(month_label, callback_data='crypto_cal_month'),
        InlineKeyboardButton("▶️", callback_data=f'crypto_cal_next_{year}_{month}')
    ]
    dow_row = [InlineKeyboardButton(d, callback_data='crypto_cal_dow') for d in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']]
    day_buttons = [InlineKeyboardButton(" ", callback_data='crypto_cal_empty')] * start_weekday
    for day in range(1, last_day.day + 1):
        date_str = f"{day:02d}.{month:02d}.{year}"
        day_buttons.append(InlineKeyboardButton(str(day), callback_data=f'crypto_date_{date_str}'))

    keyboard = [nav_row, dow_row] + [day_buttons[i:i+7] for i in range(0, len(day_buttons), 7)]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='crypto_add')])
    await query.edit_message_text("📅 *Виберіть дату:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def handle_calendar_navigation(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data.startswith('crypto_cal_prev_'):
        year, month = map(int, query.data.replace('crypto_cal_prev_', '').split('_'))
        month -= 1
        if month < 1:
            month, year = 12, year - 1
    elif query.data.startswith('crypto_cal_next_'):
        year, month = map(int, query.data.replace('crypto_cal_next_', '').split('_'))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    context.user_data['crypto_calendar_month'] = datetime(year, month, 1)
    await show_calendar(update, context)


async def show_sell_crypto_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        session = Session()
        portfolio_records = session.query(CryptoPortfolio).all()
        session.close()

        if not portfolio_records:
            await query.edit_message_text("📭 Портфель пустий — немає що продавати", reply_markup=_back_kb('crypto_add'))
            return

        keyboard = [
            [InlineKeyboardButton(
                f"{r.ticker} | {r.total_quantity:.8f} | {r.avg_price:.4f} USDT",
                callback_data=f'sell_crypto_{r.ticker}'
            )]
            for r in portfolio_records
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='crypto_add')])
        await query.edit_message_text(
            "🔴 *Продаж крипти*\n\nОберіть монету для продажу:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_sell_crypto_selected(update: Update, context: CallbackContext, ticker: str):
    query = update.callback_query
    try:
        Session = context.bot_data.get('Session')
        session = Session()
        portfolio_record = session.query(CryptoPortfolio).filter(CryptoPortfolio.ticker == ticker).first()
        session.close()

        if not portfolio_record:
            await query.edit_message_text("❌ Монету не знайдено в портфелі")
            return

        context.user_data.update({
            'ticker': ticker,
            'sell_avg_price': portfolio_record.avg_price,
            'sell_max_quantity': portfolio_record.total_quantity,
            'sell_platform': portfolio_record.platform,
            'crypto_step': 'sell_price'
        })
        await query.edit_message_text(
            f"🔴 *Продаж крипти*\n\n"
            f"₿ Монета: {ticker}\n"
            f"📦 В портфелі: {portfolio_record.total_quantity:.8f}\n"
            f"💰 Середня ціна купівлі: {portfolio_record.avg_price:.4f} USDT\n\n"
            f"💵 Введіть ціну продажу за одну монету (USDT):",
            reply_markup=_back_kb('crypto_sell'),
            parse_mode='Markdown'
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def save_crypto(update: Update, context: CallbackContext):
    try:
        Session = context.bot_data.get('Session')
        session = Session()
        operation_type = context.user_data['crypto_operation_type']
        commission = context.user_data.get('commission', 0)
        pnl = context.user_data.get('pnl', 0) if operation_type == 'продаж' else 0
        ticker = context.user_data['ticker']
        quantity = context.user_data['quantity']
        total_amount = context.user_data['total_amount']
        platform = context.user_data['platform']

        crypto = Crypto(
            date=context.user_data['crypto_date'],
            operation_type=operation_type,
            ticker=ticker,
            name=ticker,
            price_per_unit=context.user_data['price_per_unit'],
            quantity=quantity,
            total_amount=total_amount,
            platform=platform,
            pnl=pnl
        )
        session.add(crypto)
        session.commit()

        portfolio = session.query(CryptoPortfolio).filter(CryptoPortfolio.ticker == ticker).first()

        if operation_type == 'купівля':
            if not portfolio:
                session.add(CryptoPortfolio(
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
                portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity
                portfolio.last_update = datetime.now().isoformat()
        elif operation_type == 'продаж' and portfolio:
            portfolio.total_quantity -= quantity
            portfolio.total_amount -= (context.user_data['sell_avg_price'] * quantity)
            if portfolio.total_quantity <= 0:
                session.delete(portfolio)
            else:
                portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity
                portfolio.last_update = datetime.now().isoformat()

        session.commit()
        recalculate_percents(session)
        session.close()

        text = (
            f"✅ *Запис додано!*\n\n"
            f"📅 Дата: {context.user_data['crypto_date']}\n"
            f"📊 Операція: {operation_type.capitalize()}\n"
            f"₿ Монета: {ticker}\n"
            f"💵 Ціна за шт: {context.user_data['price_per_unit']:.4f} USDT\n"
            f"📦 Кількість: {quantity:.8f}\n"
            f"💰 Загальна сума: {total_amount:.2f} USDT\n"
            f"💸 Комісія: {commission:.2f} USDT\n"
            f"📊 Біржа: {platform}"
        )
        if operation_type == 'продаж':
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            text += f"\n\n{pnl_emoji} *PnL: {pnl:+.2f} USDT*"

        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад до Крипти", callback_data='crypto')]]),
            parse_mode='Markdown'
        )
        context.user_data.clear()

    except Exception as e:
        logger.error(f"Error saving crypto: {e}")
        await update.callback_query.edit_message_text(f"❌ Помилка при збереженні: {str(e)}")


async def handle_message_add(update: Update, context: CallbackContext):
    user_message = update.message.text
    step = context.user_data.get('crypto_step')

    if step == 'ticker':
        context.user_data['ticker'] = user_message.upper()
        context.user_data['crypto_step'] = 'price_per_unit'
        await update.message.reply_text("💰 Введіть ціну за одну монету (USDT):", reply_markup=_back_kb('crypto_add'))

    elif step == 'price_per_unit':
        try:
            context.user_data['price_per_unit'] = float(user_message)
            context.user_data['crypto_step'] = 'quantity'
            await update.message.reply_text("📦 Введіть кількість монет (підтримуються дробові числа, наприклад 0.00350000):", reply_markup=_back_kb('crypto_add'))
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть коректне число", reply_markup=_back_kb('crypto_add'))

    elif step == 'quantity':
        try:
            quantity = float(user_message)
            if quantity <= 0:
                await update.message.reply_text("❌ Кількість має бути більше 0", reply_markup=_back_kb('crypto_add'))
                return
            context.user_data['quantity'] = quantity
            context.user_data['crypto_step'] = 'commission'
            await update.message.reply_text("💸 Введіть комісію за транзакцію (USDT):", reply_markup=_back_kb('crypto_add'))
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть коректне число", reply_markup=_back_kb('crypto_add'))

    elif step == 'commission':
        try:
            commission = float(user_message)
            context.user_data['commission'] = commission
            price = context.user_data.get('price_per_unit', 0)
            quantity = context.user_data.get('quantity', 0)
            total_amount = (price * quantity) + commission
            avg_price = total_amount / quantity if quantity > 0 else 0
            context.user_data['total_amount'] = total_amount
            context.user_data['price_per_unit'] = avg_price
            context.user_data['crypto_step'] = 'platform'
            platform_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔶 Binance", callback_data='crypto_platform_binance')],
                [InlineKeyboardButton("🔷 Bybit", callback_data='crypto_platform_bybit')],
                [InlineKeyboardButton("🟡 OKX", callback_data='crypto_platform_okx')],
                [InlineKeyboardButton("⚪ Інша", callback_data='crypto_platform_other')],
                [InlineKeyboardButton("🔙 Назад", callback_data='crypto_add')],
            ])
            await update.message.reply_text(
                f"💵 Сума: {total_amount:.2f} USDT\n"
                f"💸 Комісія: {commission:.2f} USDT\n"
                f"📊 Реальна ціна за шт: {avg_price:.4f} USDT\n\n📊 Виберіть біржу:",
                reply_markup=platform_keyboard
            )
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть коректне число", reply_markup=_back_kb('crypto_add'))

    elif step == 'sell_price':
        try:
            price = float(user_message)
            context.user_data['price_per_unit'] = price
            context.user_data['crypto_step'] = 'sell_quantity'
            max_qty = context.user_data['sell_max_quantity']
            await update.message.reply_text(
                f"💵 Ціна продажу: {price:.4f} USDT\n\n"
                f"📦 Введіть кількість (максимум {max_qty:.8f}):",
                reply_markup=_back_kb('crypto_sell')
            )
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть коректне число", reply_markup=_back_kb('crypto_sell'))

    elif step == 'sell_quantity':
        try:
            quantity = float(user_message)
            max_qty = context.user_data['sell_max_quantity']
            if quantity <= 0:
                await update.message.reply_text("❌ Кількість має бути більше 0", reply_markup=_back_kb('crypto_sell'))
                return
            if quantity > max_qty:
                await update.message.reply_text(
                    f"❌ В портфелі тільки {max_qty:.8f}\n\n📦 Введіть кількість:",
                    reply_markup=_back_kb('crypto_sell')
                )
                return
            context.user_data['quantity'] = quantity
            context.user_data['crypto_step'] = 'sell_commission'
            await update.message.reply_text("💸 Введіть комісію за транзакцію (USDT):", reply_markup=_back_kb('crypto_sell'))
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть коректне число", reply_markup=_back_kb('crypto_sell'))

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
            context.user_data.update({'total_amount': total_amount, 'pnl': pnl, 'platform': platform})

            Session = context.bot_data.get('Session')
            session = Session()
            ticker = context.user_data['ticker']

            crypto = Crypto(
                date=context.user_data['crypto_date'],
                operation_type='продаж',
                ticker=ticker,
                name=ticker,
                price_per_unit=price,
                quantity=quantity,
                total_amount=total_amount,
                platform=platform,
                pnl=pnl
            )
            session.add(crypto)
            session.commit()

            portfolio = session.query(CryptoPortfolio).filter(CryptoPortfolio.ticker == ticker).first()
            if portfolio:
                portfolio.total_quantity -= quantity
                portfolio.total_amount -= (avg_price * quantity)
                if portfolio.total_quantity <= 0:
                    session.delete(portfolio)
                else:
                    portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity
                    portfolio.last_update = datetime.now().isoformat()

            session.commit()
            recalculate_percents(session)
            session.close()

            pnl_emoji = "📈" if pnl >= 0 else "📉"
            text = (
                f"✅ *Запис додано!*\n\n"
                f"📅 Дата: {context.user_data['crypto_date']}\n"
                f"📊 Операція: Продаж\n"
                f"₿ Монета: {ticker}\n"
                f"💵 Ціна за шт: {price:.4f} USDT\n"
                f"📦 Кількість: {quantity:.8f}\n"
                f"💰 Загальна сума: {total_amount:.2f} USDT\n"
                f"💸 Комісія: {commission:.2f} USDT\n"
                f"📊 Біржа: {platform}\n\n"
                f"{pnl_emoji} *PnL: {pnl:+.2f} USDT*"
            )
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад до Крипти", callback_data='crypto')]]),
                parse_mode='Markdown'
            )
            context.user_data.clear()
        except ValueError:
            await update.message.reply_text("❌ Будь ласка, введіть коректне число", reply_markup=_back_kb('crypto_sell'))