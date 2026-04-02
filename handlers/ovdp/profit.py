"""
Показ та списання прибутків
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import Bond, ProfitRecord

logger = logging.getLogger(__name__)


def get_monthly_profit_from_pnl(bonds):
    """Прибуток по місяцях з поля pnl"""
    monthly = {}
    for bond in bonds:
        if bond.operation_type == 'продаж' and bond.pnl:
            try:
                from handlers.ovdp.utils.helpers import parse_date, get_month_year
                month_year = get_month_year(bond.date)
                monthly[month_year] = monthly.get(month_year, 0) + bond.pnl
            except Exception:
                pass
    return monthly


async def show_profit(update: Update, context: CallbackContext):
    """Показати прибутки з ОВДП"""
    query = update.callback_query

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        bonds = session.query(Bond).all()

        if not bonds:
            session.close()
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
            await query.edit_message_text(
                "📭 *Немає даних про ОВДП*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        # Загальний прибуток = сума pnl по всіх продажах
        total_profit = sum(
            (bond.pnl or 0)
            for bond in bonds
            if bond.operation_type == 'продаж'
        )

        # Прибуток по місяцях
        monthly_profit = get_monthly_profit_from_pnl(bonds)

        # Отримуємо списання
        profit_records = session.query(ProfitRecord).all()
        session.close()

        total_write_offs = sum(
            r.unrealized_profit for r in profit_records
            if r.operation_type == 'списання'
        )
        unrealized_profit = total_profit - total_write_offs

        # Формуємо текст
        text = "💰 *Прибуток з ОВДП*\n\n"
        text += f"📊 *Загальний прибуток:* {total_profit:.2f} грн\n"
        text += f"✍️ *Списано:* {total_write_offs:.2f} грн\n"
        text += f"📋 *Залишок:* {unrealized_profit:.2f} грн\n\n"

        if monthly_profit:
            text += "📅 *По місяцях:*\n"
            for month in sorted(monthly_profit.keys(), reverse=True):
                text += f"   {month}: {monthly_profit[month]:+.2f} грн\n"

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
        logger.error(f"Error in show_profit: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def write_off_profit(update: Update, context: CallbackContext):
    """Списання прибутку"""
    query = update.callback_query

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        bonds = session.query(Bond).all()

        if not bonds:
            session.close()
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_profit')]]
            await query.edit_message_text(
                "📭 *Немає даних*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        total_profit = sum(
            (bond.pnl or 0)
            for bond in bonds
            if bond.operation_type == 'продаж'
        )

        profit_records = session.query(ProfitRecord).all()
        session.close()

        total_write_offs = sum(
            r.unrealized_profit for r in profit_records
            if r.operation_type == 'списання'
        )
        unrealized_profit = total_profit - total_write_offs

        if unrealized_profit <= 0:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_profit')]]
            await query.edit_message_text(
                "❌ *Немає прибутку для списання*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        context.user_data['unrealized_profit'] = unrealized_profit
        context.user_data['profit_step'] = 'enter_amount'

        keyboard = [
            [InlineKeyboardButton("✍️ Списати", callback_data='confirm_write_off')],
            [InlineKeyboardButton("🔙 Назад", callback_data='ovdp_profit')]
        ]

        await query.edit_message_text(
            f"✍️ *Списання прибутку*\n\n"
            f"💰 Доступно для списання: {unrealized_profit:.2f} грн\n\n"
            f"Введіть суму для списання:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in write_off_profit: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")