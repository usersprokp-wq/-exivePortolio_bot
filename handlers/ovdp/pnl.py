"""
Показ PnL портфеля з актуальними цінами
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import Bond
from utils import fetch_bond_price_icu, calculate_current_portfolio

logger = logging.getLogger(__name__)


async def show_pnl_portfolio(update: Update, context: CallbackContext):
    """Показати PnL портфеля"""
    query = update.callback_query
    await query.answer()
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 Немає даних про ОВДП")
            return
        
        # Розраховуємо портфель
        portfolio = calculate_current_portfolio(bonds)
        
        if not portfolio:
            await query.edit_message_text("📭 Портфель пустий")
            return
        
        text = "📊 *PnL Портфеля (Live)*\n\n"
        total_buy_value = 0
        total_current_value = 0
        
        for bond_num, data in sorted(portfolio.items()):
            quantity = data['quantity']
            avg_price = data['avg_price']
            buy_value = data['buy_amount']
            
            # Парсимо ціну з uainvest
            current_price = fetch_bond_price_icu(bond_num)
            
            if current_price is None:
                current_price = avg_price
                price_status = " (не вдалось завантажити)"
            else:
                price_status = " (live)"
            
            current_value = current_price * quantity
            pnl = current_value - buy_value
            pnl_percent = (pnl / buy_value * 100) if buy_value > 0 else 0
            
            text += f"🔢 *Bond \"{bond_num}\"*\n"
            text += f"   📦 Кількість: {quantity} шт\n"
            text += f"   💰 Ціна покупки: {avg_price:.2f} грн/шт\n"
            text += f"   📈 ICU ціна: {current_price:.2f} грн/шт{price_status}\n"
            text += f"   💵 Поточна вартість: {current_value:.0f} грн\n"
            text += f"   💵 PnL: {pnl:+.0f} грн ({pnl_percent:+.1f}%)\n\n"
            
            total_buy_value += buy_value
            total_current_value += current_value
        
        # Загальні показники
        total_pnl = total_current_value - total_buy_value
        total_pnl_percent = (total_pnl / total_buy_value * 100) if total_buy_value > 0 else 0
        
        text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 *Портфель всього:*\n"
        text += f"   📦 Кількість: {sum(d['quantity'] for d in portfolio.values())} шт\n"
        text += f"   💵 Твоя вартість: {total_buy_value:.0f} грн\n"
        text += f"   📈 Поточна вартість: {total_current_value:.0f} грн\n"
        text += f"   ✅ PnL: {total_pnl:+.0f} грн ({total_pnl_percent:+.1f}%)"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp_portfolio')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in show_pnl_portfolio: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")
