"""
Перегляд списку всіх операцій з ОВДП
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import Bond

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 10


async def show_bonds_list(update: Update, context: CallbackContext, page: int = 1):
    """Показати список всіх операцій з ОВДП з пагінацією"""
    query = update.callback_query
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        all_bonds = session.query(Bond).order_by(Bond.id.desc()).all()
        session.close()
        
        if not all_bonds:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
            await query.edit_message_text(
                "📭 *Немає записів*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        # Пагінація
        total_items = len(all_bonds)
        total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        bonds_page = all_bonds[start_idx:end_idx]
        
        # Формуємо текст
        text = f"📋 *Мої записи* (сторінка {page}/{total_pages})\n\n"
        
        for bond in bonds_page:
            op_icon = "🟢" if bond.operation_type == 'купівля' else "🔴"
            text += f"{op_icon} *{bond.operation_type.capitalize()}*\n"
            text += f"   📅 {bond.date}\n"
            text += f"   🔢 {bond.bond_number}\n"
            text += f"   📦 {bond.quantity} шт × {bond.price_per_unit:.2f} грн\n"
            text += f"   💵 {bond.total_amount:.2f} грн\n"
            text += f"   🏦 {bond.platform}\n\n"
        
        # Кнопки пагінації
        keyboard = []
        if total_pages > 1:
            page_buttons = []
            for p in range(1, total_pages + 1):
                if p == page:
                    page_buttons.append(InlineKeyboardButton(f"[{p}]", callback_data=f'bonds_list_page_{p}'))
                else:
                    page_buttons.append(InlineKeyboardButton(str(p), callback_data=f'bonds_list_page_{p}'))
            
            keyboard.append(page_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='ovdp')])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in show_bonds_list: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")
