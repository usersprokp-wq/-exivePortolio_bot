import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock, StockPortfolio

logger = logging.getLogger(__name__)

DIVIDEND_KEYS = ('dividend_step', 'dividend_ticker', 'dividend_amount', 'dividend_tax', 'dividend_net')


def _clear_dividend_data(context: CallbackContext):
    for key in DIVIDEND_KEYS:
        context.user_data.pop(key, None)


async def show_dividends_selection(update: Update, context: CallbackContext):
    """Показати список акцій для внесення дивідендів (з портфеля — legacy)"""
    query = update.callback_query
    _clear_dividend_data(context)

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
        logger.error(f"Error in show_dividends_selection: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_dividend_ticker(update: Update, context: CallbackContext, ticker: str):
    """Обробка вибору акції для дивідендів"""
    query = update.callback_query
    if ticker == 'manual':
        context.user_data['dividend_step'] = 'ticker'
        await query.edit_message_text("📝 Введіть тікер акції:", parse_mode='Markdown')
    else:
        context.user_data['dividend_ticker'] = ticker
        context.user_data['dividend_step'] = 'amount'
        await query.edit_message_text(f"💵 Акція: {ticker}\n\n💰 Введіть суму дивіденду ($):", parse_mode='Markdown')


async def confirm_dividend(update: Update, context: CallbackContext):
    """Підтвердження та збереження дивідендів"""
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        ticker = context.user_data.get('dividend_ticker')
        amount = context.user_data.get('dividend_amount')
        tax = context.user_data.get('dividend_tax')
        net_amount = context.user_data.get('dividend_net')

        if not all([ticker, amount is not None, tax is not None, net_amount is not None]):
            await query.edit_message_text("❌ Помилка: дані дивідендів відсутні")
            return

        session = Session()
        session.add(Stock(
            date=datetime.now().strftime('%d.%m.%Y'),
            operation_type='дивіденди',
            ticker=ticker,
            name=ticker,
            price_per_unit=0,
            quantity=0,
            total_amount=amount,
            platform='',
            pnl=net_amount
        ))
        session.commit()
        session.close()

        text = (
            f"✅ *Дивіденди додано!*\n\n"
            f"📈 Акція: {ticker}\n"
            f"💰 Сума: {amount:.2f} $\n"
            f"🏦 Податок: {tax:.2f} $\n"
            f"📊 PnL: {net_amount:.2f} $\n"
        )
        keyboard = [
            [InlineKeyboardButton("➕ Додати ще", callback_data='stocks_add')],
            [InlineKeyboardButton("📊 До Акцій", callback_data='stocks')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        _clear_dividend_data(context)

    except Exception as e:
        logger.error(f"Error in confirm_dividend: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_message_dividends(update: Update, context: CallbackContext):
    """Обробка текстових повідомлень для дивідендів"""
    if 'dividend_step' not in context.user_data:
        return

    user_message = update.message.text
    step = context.user_data.get('dividend_step')

    try:
        if step == 'ticker':
            context.user_data['dividend_ticker'] = user_message.upper()
            context.user_data['dividend_step'] = 'amount'
            await update.message.reply_text("💰 Введіть суму дивіденду ($):")

        elif step == 'amount':
            try:
                amount = float(user_message)
                if amount <= 0:
                    await update.message.reply_text("❌ Сума має бути більше 0\n\n💰 Введіть суму дивіденду ($):")
                    return
                context.user_data['dividend_amount'] = amount
                context.user_data['dividend_step'] = 'tax'
                await update.message.reply_text("🏦 Введіть податок/комісію ($):")
            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число\n\n💰 Введіть суму дивіденду ($):")

        elif step == 'tax':
            try:
                tax = float(user_message)
                if tax < 0:
                    await update.message.reply_text("❌ Податок не може бути негативним\n\n🏦 Введіть податок/комісію ($):")
                    return

                amount = context.user_data['dividend_amount']
                ticker = context.user_data['dividend_ticker']
                net_amount = amount - tax

                context.user_data['dividend_tax'] = tax
                context.user_data['dividend_net'] = net_amount

                text = (
                    f"💵 *Підтвердження Дивідендів*\n\n"
                    f"📈 Акція: {ticker}\n"
                    f"💰 Сума: {amount:.2f} $\n"
                    f"🏦 Податок: {tax:.2f} $\n"
                    f"📊 PnL: {net_amount:.2f} $\n"
                )
                keyboard = [
                    [InlineKeyboardButton("✅ Підтвердити", callback_data='dividend_confirm')],
                    [InlineKeyboardButton("❌ Скасувати", callback_data='stocks_add')]
                ]
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

            except ValueError:
                await update.message.reply_text("❌ Будь ласка, введіть коректне число\n\n🏦 Введіть податок/комісію ($):")

    except Exception as e:
        logger.error(f"Error in handle_message_dividends: {e}")
        await update.message.reply_text(f"❌ Помилка: {str(e)}")