"""
Статистика по ОВДП
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import Bond
from .utils import calculate_profit_by_price

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
        session.close()
        
        if not bonds:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
            await query.edit_message_text(
                "📭 *Немає даних*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        # Збираємо статистику
        total_buy = sum(b.total_amount for b in bonds if b.operation_type == 'купівля')
        total_sell = sum(b.total_amount for b in bonds if b.operation_type == 'продаж')
        buy_count = len([b for b in bonds if b.operation_type == 'купівля'])
        sell_count = len([b for b in bonds if b.operation_type == 'продаж'])
        
        # Розраховуємо прибуток
        _, total_profit = calculate_profit_by_price(bonds)
        
        # Статистика по платформах
        icu_bonds = [b for b in bonds if b.platform and b.platform.upper() == 'ICU']
        sensbank_bonds = [b for b in bonds if b.platform and b.platform.upper() == 'SENSBANK']
        
        text = "📊 *Статистика ОВДП*\n\n"
        text += f"🟢 *Купівлі:*\n"
        text += f"   Операцій: {buy_count}\n"
        text += f"   Сума: {total_buy:.0f} грн\n\n"
        
        text += f"🔴 *Продажі:*\n"
        text += f"   Операцій: {sell_count}\n"
        text += f"   Сума: {total_sell:.0f} грн\n\n"
        
        text += f"💰 *Прибуток:* {total_profit:+.0f} грн\n\n"
        
        if icu_bonds or sensbank_bonds:
            text += f"🏦 *По платформах:*\n"
            if icu_bonds:
                text += f"   ICU: {len(icu_bonds)} операцій\n"
            if sensbank_bonds:
                text += f"   SENSBANK: {len(sensbank_bonds)} операцій\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад до ОВДП", callback_data='ovdp')]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in show_statistics: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")