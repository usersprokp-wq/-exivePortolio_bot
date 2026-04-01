"""
Перегляд портфеля ОВДП
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import BondPortfolio

logger = logging.getLogger(__name__)


async def show_portfolio(update: Update, context: CallbackContext, platform: str = None):
    """Показати портфель ОВДП"""
    query = update.callback_query
    
    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        
        # Фільтруємо по платформі якщо вказано
        if platform:
            portfolio = session.query(BondPortfolio).filter(
                BondPortfolio.platform == platform.upper()
            ).all()
        else:
            portfolio = session.query(BondPortfolio).all()
        
        session.close()
        
        if not portfolio:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
            text = f"📭 *Портфель {'(' + platform.upper() + ')' if platform else ''} пустий*"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Формуємо текст
        platform_text = f" ({platform.upper()})" if platform else ""
        text = f"💼 *Портфель ОВДП{platform_text}*\n\n"
        
        total_amount = 0
        total_qty = 0
        
        for record in portfolio:
            if record.bond_number.endswith('uah'):
                # Залишки на рахунках
                text += f"💰 *{record.platform} Залишок*\n"
                text += f"   💵 {record.total_amount:.2f} грн\n\n"
                total_amount += record.total_amount
            else:
                # Облігації
                text += f"🔢 *{record.bond_number}*\n"
                text += f"   📆 Погашення: {record.maturity_date}\n"
                text += f"   📦 Кількість: {record.total_quantity} шт\n"
                text += f"   💰 Середня ціна: {record.avg_price:.2f} грн\n"
                text += f"   💵 Сума: {record.total_amount:.2f} грн\n"
                text += f"   🏦 {record.platform}\n"
                if hasattr(record, 'percent') and record.percent:
                    text += f"   📊 {record.percent:.1f}% портфеля\n"
                text += "\n"
                total_amount += record.total_amount
                total_qty += record.total_quantity
        
        text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 *Всього:*\n"
        if total_qty > 0:
            text += f"   📦 {total_qty} облігацій\n"
        text += f"   💵 {total_amount:.2f} грн"
        
        # Кнопки
        keyboard = [
            [InlineKeyboardButton("💹 Взнати PnL", callback_data='pnl_portfolio')],
            [
                InlineKeyboardButton("🏦 Всі", callback_data='ovdp_portfolio'),
                InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'),
                InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank')
            ],
            [InlineKeyboardButton("💵 Оновити залишок", callback_data='ovdp_update_balance')],
            [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in show_portfolio: {e}")
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def update_balance_platform_selection(update: Update, context: CallbackContext):
    """Вибір платформи для оновлення залишку"""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("🏦 ICU", callback_data='ovdp_balance_platform_icu')],
        [InlineKeyboardButton("🏦 SENSBANK", callback_data='ovdp_balance_platform_sensbank')],
        [InlineKeyboardButton("🔙 Назад", callback_data='ovdp_portfolio')]
    ]
    
    await query.edit_message_text(
        "💵 *Оновлення залишку*\n\nОберіть платформу:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
