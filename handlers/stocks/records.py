import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock
from .utils import parse_date

logger = logging.getLogger(__name__)

RECORDS_PER_PAGE = 10


async def show_stocks_list(update: Update, context: CallbackContext, page=1):
    """Показати список записів акцій з пагінацією"""
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        stocks = session.query(Stock).all()
        session.close()

        if not stocks:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
            await query.edit_message_text("📭 Немає записів", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        stocks.sort(key=lambda x: (parse_date(x.date), x.id), reverse=True)

        total_pages = (len(stocks) + RECORDS_PER_PAGE - 1) // RECORDS_PER_PAGE
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * RECORDS_PER_PAGE
        page_stocks = stocks[start_idx:start_idx + RECORDS_PER_PAGE]

        text = f"📋 *Мої записи Акцій* (сторінка {page}/{total_pages})\n\n"
        for stock in page_stocks:
            op_emoji = '🟢' if stock.operation_type == 'купівля' else '🔴'
            text += f"📅 {stock.date} | {op_emoji} {stock.operation_type} | {stock.platform}\n"
            text += f"   📈 {stock.ticker} | {stock.quantity} шт | {stock.total_amount:.2f} $\n"

            if stock.operation_type == 'продаж':
                pnl = stock.pnl or 0
                pnl_emoji = '📈' if pnl >= 0 else '📉'
                pnl_sign = '+' if pnl >= 0 else ''
                text += f"   {pnl_emoji} PnL: {pnl_sign}{pnl:.2f} $\n"

            text += "\n"

        keyboard = []
        if total_pages > 1:
            keyboard.append([
                InlineKeyboardButton(f"[{p}]" if p == page else str(p), callback_data=f'stocks_list_page_{p}')
                for p in range(1, total_pages + 1)
            ])

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")