import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock, StockPortfolio

logger = logging.getLogger(__name__)


async def show_stocks_stats(update: Update, context: CallbackContext):
    """Показати статистику акцій"""
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        stocks = session.query(Stock).all()
        portfolio = session.query(StockPortfolio).all()
        session.close()

        if not stocks:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
            await query.edit_message_text("📭 Немає даних про акції", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        total_invested = sum(s.total_amount for s in stocks if s.operation_type == 'купівля')
        total_pnl = sum(s.pnl or 0 for s in stocks if s.operation_type == 'продаж')
        current_portfolio_value = sum(p.total_amount for p in portfolio if not p.ticker.endswith('usd'))
        different_stocks = len(set(s.ticker for s in stocks if s.operation_type == 'купівля'))
        pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        sell_operations = [s for s in stocks if s.operation_type == 'продаж']
        avg_pnl = (sum(s.pnl or 0 for s in sell_operations) / len(sell_operations)) if sell_operations else 0

        platforms = {}
        for s in stocks:
            if s.operation_type == 'продаж':
                platforms.setdefault(s.platform, {'invested': 0, 'pnl': 0, 'operations': 0})
                platforms[s.platform]['pnl'] += s.pnl or 0
                platforms[s.platform]['operations'] += 1
        for p in portfolio:
            if not p.ticker.endswith('usd'):
                platforms.setdefault(p.platform, {'invested': 0, 'pnl': 0, 'operations': 0})
                platforms[p.platform]['invested'] += p.total_amount

        text = (
            f"📊 *Статистика Акцій*\n\n"
            f"💼 *Загальна Статистика Портфеля:*\n"
            f"💵 Загальна сума інвестицій: {total_invested:.2f} $\n"
            f"📈 Поточна вартість портфеля: {current_portfolio_value:.2f} $\n"
            f"📊 Загальний P&L: {total_pnl:.2f} $ ({pnl_percent:+.2f}%)\n"
            f"🔢 Різних акцій: {different_stocks}\n\n"
            f"📍 *Статистика По Операціях:*\n"
            f"📈 Середній P&L на операцію: {avg_pnl:.2f} $\n"
            f"🔢 Всього операцій продажу: {len(sell_operations)}\n\n"
            f"🏛️ *По Біржах:*\n"
        )
        for platform, data in sorted(platforms.items()):
            text += f"\n*{platform}:*\n"
            text += f"  💼 В портфелі: {data['invested']:.2f} $\n"
            text += f"  📊 P&L: {data['pnl']:.2f} $\n"
            if data['operations'] > 0:
                text += f"  🔢 Операцій: {data['operations']}\n"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in show_stocks_stats: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")
