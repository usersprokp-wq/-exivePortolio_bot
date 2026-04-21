import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Crypto
from .utils import parse_date

logger = logging.getLogger(__name__)

RECORDS_PER_PAGE = 10


async def show_crypto_list(update: Update, context: CallbackContext, page=1):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        session = Session()
        cryptos = session.query(Crypto).all()
        session.close()

        if not cryptos:
            await query.edit_message_text("📭 Немає записів", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='crypto')]]))
            return

        cryptos.sort(key=lambda x: (parse_date(x.date), x.id), reverse=True)

        total_pages = (len(cryptos) + RECORDS_PER_PAGE - 1) // RECORDS_PER_PAGE
        page = max(1, min(page, total_pages))
        page_cryptos = cryptos[(page - 1) * RECORDS_PER_PAGE: page * RECORDS_PER_PAGE]

        text = f"📋 *Мої записи Крипти* (сторінка {page}/{total_pages})\n\n"
        for c in page_cryptos:
            op_emoji = '🟢' if c.operation_type == 'купівля' else '🔴'
            text += f"📅 {c.date} | {op_emoji} {c.operation_type} | {c.platform}\n"
            text += f"   ₿ {c.ticker} | {c.quantity:.8f} | {c.total_amount:.2f} USDT\n"
            if c.operation_type == 'продаж':
                pnl = c.pnl or 0
                pnl_emoji = '📈' if pnl >= 0 else '📉'
                sign = '+' if pnl >= 0 else ''
                text += f"   {pnl_emoji} PnL: {sign}{pnl:.2f} USDT\n"
            text += "\n"

        keyboard = []
        if total_pages > 1:
            keyboard.append([
                InlineKeyboardButton(f"[{p}]" if p == page else str(p), callback_data=f'crypto_list_page_{p}')
                for p in range(1, total_pages + 1)
            ])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='crypto')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")