"""
Статистика по ОВДП
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import Bond, BondPortfolio, ProfitRecord

logger = logging.getLogger(__name__)


async def show_statistics(update: Update, context: CallbackContext):
    """Показати статистику по ОВДП"""
    query = update.callback_query

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        bonds = session.query(Bond).all()
        portfolio_records = session.query(BondPortfolio).all()
        profit_records = session.query(ProfitRecord).all()
        session.close()

        if not bonds:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
            await query.edit_message_text(
                "📭 *Немає даних*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        # ── Портфель ──────────────────────────────────────
        bond_records = [r for r in portfolio_records if not r.bond_number.endswith('uah')]
        balance_records = [r for r in portfolio_records if r.bond_number.endswith('uah')]

        total_bonds_qty = sum(r.total_quantity for r in bond_records)
        total_bonds_amount = sum(r.total_amount for r in bond_records)
        total_balances = sum(r.total_amount for r in balance_records)
        total_assets = total_bonds_amount + total_balances

        # ── Прибуток ──────────────────────────────────────
        total_profit = sum(
            (b.pnl or 0) for b in bonds if b.operation_type == 'продаж'
        )
        total_write_offs = sum(
            r.unrealized_profit for r in profit_records if r.operation_type == 'списання'
        )
        profit_remainder = total_profit - total_write_offs

        # ── Прибуток по місяцях ───────────────────────────
        monthly = {}
        for b in bonds:
            if b.operation_type == 'продаж' and b.pnl:
                try:
                    from handlers.ovdp.utils.helpers import get_month_year
                    key = get_month_year(b.date)
                    monthly[key] = monthly.get(key, 0) + b.pnl
                except Exception:
                    pass

        # ── Формуємо текст ────────────────────────────────
        text = "📊 *Статистика ОВДП*\n\n"

        # Портфель
        text += f"💼 *Портфель:*\n"
        text += f"   Облігацій: {total_bonds_qty} шт · {total_bonds_amount:.0f} грн\n"
        if total_balances > 0:
            text += f"   Залишки: {total_balances:.2f} грн\n"
        text += f"   Всього активів: {total_assets:.0f} грн\n\n"

        # Прибуток
        text += f"💰 *Прибуток:*\n"
        text += f"   Загальний PnL: {total_profit:+.2f} грн\n"
        text += f"   Списано: {total_write_offs:.2f} грн\n"
        text += f"   Залишок: {profit_remainder:+.2f} грн\n\n"

        # По місяцях
        if monthly:
            text += f"📅 *По місяцях:*\n"
            def month_sort_key(m):
                try:
                    parts = m.split('.')
                    return (int(parts[1]), int(parts[0]))
                except Exception:
                    return (0, 0)
            for month in sorted(monthly.keys(), key=month_sort_key, reverse=False):
                text += f"   {month}: {monthly[month]:+.2f} грн\n"
            text += "\n"

        keyboard = [[InlineKeyboardButton("🔙 Назад до ОВДП", callback_data='ovdp')]]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in show_statistics: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")