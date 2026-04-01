"""
Оновлення залишків на рахунках та перерахунок відсотків портфеля
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import BondPortfolio

logger = logging.getLogger(__name__)


def recalculate_bond_percents(session):
    """Перераховує відсотки кожної облігації в портфелі"""
    try:
        portfolio = session.query(BondPortfolio).all()
        
        # Рахуємо загальну суму портфеля (без uah-залишків)
        total_value = sum(
            p.total_amount for p in portfolio 
            if not p.bond_number.endswith('uah')
        )
        
        if total_value == 0:
            return
        
        # Оновлюємо відсотки
        for record in portfolio:
            if not record.bond_number.endswith('uah'):
                record.percent = (record.total_amount / total_value * 100) if total_value > 0 else 0
        
        session.commit()
        
    except Exception as e:
        logger.error(f"Error recalculating bond percents: {e}")
        session.rollback()


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


async def handle_balance_platform_selected(update: Update, context: CallbackContext, platform: str):
    """Обробка вибору платформи для оновлення залишку"""
    query = update.callback_query
    
    context.user_data['ovdp_balance_platform'] = platform
    context.user_data['bond_step'] = 'ovdp_balance_amount'
    
    await query.edit_message_text(
        f"💵 *Оновлення залишку {platform}*\n\n"
        f"Введіть нову суму залишку:",
        parse_mode='Markdown'
    )