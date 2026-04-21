import logging
from collections import defaultdict
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Crypto, CryptoPortfolio, CryptoProfitRecord

logger = logging.getLogger(__name__)


async def show_crypto_profit(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        session = Session()
        cryptos = session.query(Crypto).all()

        if not cryptos:
            session.close()
            await query.edit_message_text("📭 Немає даних про крипту")
            return

        total_profit = sum(c.pnl or 0 for c in cryptos if c.operation_type == 'продаж')

        month_data = defaultdict(float)
        for c in cryptos:
            if c.operation_type != 'продаж':
                continue
            try:
                dt = datetime.strptime(c.date, '%d.%m.%Y')
                month_key = dt.strftime('%m.%Y')
                month_data[month_key] += c.pnl or 0
            except (ValueError, TypeError):
                continue

        sorted_months = sorted(month_data.keys(), key=lambda m: datetime.strptime(m, '%m.%Y'))

        portfolio_records = session.query(CryptoPortfolio).all()
        total_assets = sum(p.total_amount or 0 for p in portfolio_records)

        profit_records = session.query(CryptoProfitRecord).filter(CryptoProfitRecord.unrealized_profit > 0).all()
        session.close()

        total_written_off = sum(r.unrealized_profit for r in profit_records)
        unrealized_profit = max(0, total_profit - total_written_off)
        context.user_data['crypto_unrealized_profit'] = unrealized_profit

        if total_assets > 0:
            pnl_percent = (total_profit / total_assets) * 100
            pnl_emoji = "📈" if pnl_percent >= 0 else "📉"
            pnl_str = f"{pnl_emoji} PnL до активів: {pnl_percent:+.2f}%\n"
        else:
            pnl_str = ""

        text = (
            f"💰 *Управління прибутками крипти*\n\n"
            f"📈 Реалізований прибуток: {total_profit:.2f} USDT\n"
            f"{pnl_str}"
        )

        if sorted_months:
            text += f"\n📅 *Прибуток по місяцях:*\n"
            for month_key in sorted_months:
                pnl = month_data[month_key]
                sign = "+" if pnl >= 0 else ""
                text += f"{month_key}: {sign}{pnl:.2f} USDT\n"

        text += f"\n📋 Не списаний прибуток: {unrealized_profit:.2f} USDT\n"

        keyboard = [
            [InlineKeyboardButton("✍️ Списати прибуток", callback_data='crypto_write_off_profit')],
            [InlineKeyboardButton("🔙 Назад", callback_data='crypto')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in show_crypto_profit: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def write_off_crypto_profit(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    unrealized_profit = context.user_data.get('crypto_unrealized_profit', 0)
    if unrealized_profit <= 0:
        await query.edit_message_text(
            "❌ *Немає прибутку для списання*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto_profit')]]),
            parse_mode='Markdown'
        )
        return

    context.user_data['crypto_profit_step'] = 'enter_amount'
    await query.edit_message_text(
        f"✍️ *Списання прибутку крипти*\n\n"
        f"💰 Доступно для списання: {unrealized_profit:.2f} USDT\n\n"
        f"Введіть суму для списання:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto_profit')]]),
        parse_mode='Markdown'
    )


async def handle_message_profit(update: Update, context: CallbackContext):
    user_message = update.message.text
    try:
        write_off_amount = float(user_message)
        unrealized_profit = context.user_data.get('crypto_unrealized_profit', 0)

        if write_off_amount > unrealized_profit:
            await update.message.reply_text(
                f"❌ Сума перевищує не списаний прибуток ({unrealized_profit:.2f} USDT)\n\n💰 Введіть суму для списання:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto_profit')]]),
            )
            return
        if write_off_amount <= 0:
            await update.message.reply_text(
                "❌ Сума має бути більше 0\n\n💰 Введіть суму для списання:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto_profit')]]),
            )
            return

        Session = context.bot_data.get('Session')
        session = Session()
        session.add(CryptoProfitRecord(
            operation_date=datetime.now().strftime('%d.%m.%Y'),
            operation_type='списання',
            amount=write_off_amount,
            unrealized_profit=write_off_amount
        ))
        session.commit()
        session.close()

        remaining = unrealized_profit - write_off_amount
        keyboard = [
            [InlineKeyboardButton("💰 До меню прибутків", callback_data='crypto_profit')],
            [InlineKeyboardButton("₿ До Крипти", callback_data='crypto')]
        ]
        await update.message.reply_text(
            f"✅ *Прибуток списано!*\n\n📝 Списано: {write_off_amount:.2f} USDT\n📋 Залишилось: {remaining:.2f} USDT\n",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        context.user_data.pop('crypto_profit_step', None)
        context.user_data.pop('crypto_unrealized_profit', None)

    except ValueError:
        await update.message.reply_text(
            "❌ Будь ласка, введіть коректне число\n\n💰 Введіть суму для списання:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto_profit')]]),
        )