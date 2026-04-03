import logging
from collections import defaultdict
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock, StockProfitRecord

logger = logging.getLogger(__name__)


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

        # --- Загальні суми ---
        total_profit = sum(s.pnl or 0 for s in stocks if s.operation_type == 'продаж')
        total_dividends = sum(s.total_amount or 0 for s in stocks if s.operation_type == 'дивіденди')
        total_combined = total_profit + total_dividends

        # --- Розбивка по місяцях ---
        # month_data: { 'MM.YYYY': {'profit': X, 'dividends': Y} }
        month_data = defaultdict(lambda: {'profit': 0.0, 'dividends': 0.0})

        for s in stocks:
            if s.operation_type not in ('продаж', 'дивіденди'):
                continue
            try:
                # Формат дати: 03.04.2026 -> MM.YYYY
                dt = datetime.strptime(s.date, '%d.%m.%Y')
                month_key = dt.strftime('%m.%Y')
            except (ValueError, TypeError):
                continue

            if s.operation_type == 'продаж':
                month_data[month_key]['profit'] += s.pnl or 0
            elif s.operation_type == 'дивіденди':
                month_data[month_key]['dividends'] += s.total_amount or 0

        # Сортування від старого до нового
        sorted_months = sorted(
            month_data.keys(),
            key=lambda m: datetime.strptime(m, '%m.%Y')
        )

        # --- Не списаний прибуток ---
        profit_records = session.query(StockProfitRecord).filter(StockProfitRecord.unrealized_profit > 0).all()
        session.close()

        total_written_off = sum(r.unrealized_profit for r in profit_records)
        unrealized_profit = max(0, total_combined - total_written_off)

        context.user_data['unrealized_profit'] = unrealized_profit

        # --- Формування тексту ---
        text = (
            f"💰 *Управління прибутками акцій*\n\n"
            f"📈 Реалізований прибуток: {total_profit:.2f} $\n"
            f"💵 Дивіденди: {total_dividends:.2f} $\n"
            f"💹 Загальний прибуток: {total_combined:.2f} $\n"
        )

        if sorted_months:
            text += f"\n📅 *Прибуток по місяцях:*\n"
            for month_key in sorted_months:
                data = month_data[month_key]
                parts = []
                if data['profit'] != 0:
                    parts.append(f"📈 {data['profit']:.2f} $")
                if data['dividends'] != 0:
                    parts.append(f"💵 {data['dividends']:.2f} $")
                if parts:
                    text += f"{month_key} — {' | '.join(parts)}\n"

        text += f"\n📋 Не списаний прибуток: {unrealized_profit:.2f} $\n"

        keyboard = [
            [InlineKeyboardButton("✍️ Списати прибуток", callback_data='stocks_write_off_profit')],
            [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in show_stocks_profit: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_message_profit(update: Update, context: CallbackContext):
    """Обробка суми для списання прибутку"""
    user_message = update.message.text
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
        session.add(StockProfitRecord(
            operation_date=datetime.now().strftime('%d.%m.%Y'),
            operation_type='списання',
            amount=write_off_amount,
            realized_profit=0,
            unrealized_profit=write_off_amount
        ))
        session.commit()
        session.close()

        remaining = unrealized_profit - write_off_amount
        text = f"✅ *Прибуток списано!*\n\n📝 Списано: {write_off_amount:.2f} $\n📋 Залишилось: {remaining:.2f} $\n"
        keyboard = [
            [InlineKeyboardButton("💰 До меню прибутків", callback_data='stocks_profit')],
            [InlineKeyboardButton("📊 До Акцій", callback_data='stocks')]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        context.user_data.pop('profit_step', None)
        context.user_data.pop('unrealized_profit', None)

    except ValueError:
        await update.message.reply_text("❌ Будь ласка, введіть коректне число\n\n💰 Введіть суму для списання:")