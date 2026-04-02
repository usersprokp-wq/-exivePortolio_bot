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
    session = None
    
    try:
        # Отримуємо платформу з callback_data якщо вона там є
        if not platform and query.data:
            # Наприклад: 'portfolio_icu' -> 'icu'
            if query.data.startswith('portfolio_'):
                platform = query.data.replace('portfolio_', '').lower()
        
        await query.answer()  # Закриваємо loading spinner
        
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return
        
        session = Session()
        
        try:
            # Фільтруємо по платформі якщо вказано
            if platform:
                portfolio = session.query(BondPortfolio).filter(
                    BondPortfolio.platform == platform.upper()
                ).all()
            else:
                portfolio = session.query(BondPortfolio).all()
        finally:
            session.close()
            session = None
        
        if not portfolio:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]]
            text = f"📭 *Портфель {'(' + platform.upper() + ')' if platform else ''} пустий*"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        
        # Групуємо облігації по номеру
        bonds_grouped = {}
        balances = []
        total_portfolio_amount = 0
        
        for record in portfolio:
            if record.bond_number.endswith('uah'):
                # Залишки на рахунках
                balances.append(record)
                total_portfolio_amount += record.total_amount
            else:
                # Облігації
                total_portfolio_amount += record.total_amount
                if record.bond_number not in bonds_grouped:
                    bonds_grouped[record.bond_number] = {
                        'maturity_date': record.maturity_date,
                        'records': []
                    }
                bonds_grouped[record.bond_number]['records'].append(record)
        
        # Формуємо текст
        platform_text = f" ({platform.upper()})" if platform else ""
        text = f"💼 *Портфель ОВДП{platform_text}*\n\n"
        
        total_qty = 0
        total_amount = 0
        
        # Виводимо згруповані облігації
        for bond_number in sorted(bonds_grouped.keys()):
            bond_data = bonds_grouped[bond_number]
            records = bond_data['records']
            
            # Підрахунки по облігації
            bond_total_qty = sum(r.total_quantity for r in records)
            bond_total_amount = sum(r.total_amount for r in records)
            bond_avg_price = bond_total_amount / bond_total_qty if bond_total_qty > 0 else 0
            bond_percent = (bond_total_amount / total_portfolio_amount * 100) if total_portfolio_amount > 0 else 0
            
            # Платформи де є ця облігація
            platforms = sorted(set(r.platform for r in records))
            platforms_text = " | ".join(platforms)
            
            text += f"🔢 *{bond_number}* 📊 {bond_percent:.1f}%\n"
            text += f"   📆 Погашення: {bond_data['maturity_date']}\n"
            text += f"   📦 Кількість: {bond_total_qty} шт\n"
            text += f"   💰 Середня ціна: {bond_avg_price:.2f} грн\n"
            text += f"   💵 Сума: {bond_total_amount:.2f} грн\n"
            text += f"   🏦 {platforms_text}\n\n"
            
            total_qty += bond_total_qty
            total_amount += bond_total_amount
        
        # Виводимо залишки
        for balance in balances:
            text += f"💰 *{balance.platform} Залишок*\n"
            text += f"   💵 {balance.total_amount:.2f} грн\n\n"
            total_amount += balance.total_amount
        
        text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 *Всього:*\n"
        if total_qty > 0:
            text += f"   📦 {total_qty} облігацій\n"
        text += f"   💵 {total_amount:.2f} грн"
        
        # Динамічні кнопки фільтрації
        filter_buttons = []
        
        if platform:
            # Якщо є фільтр - показуємо кнопку "Всі"
            filter_buttons.append(InlineKeyboardButton("🏦 Всі", callback_data='ovdp_portfolio'))
        
        # Додаємо кнопки платформ (крім активної)
        if platform and platform.lower() != 'icu':
            filter_buttons.append(InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'))
        elif not platform:
            filter_buttons.append(InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'))
            
        if platform and platform.lower() != 'sensbank':
            filter_buttons.append(InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank'))
        elif not platform:
            filter_buttons.append(InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank'))
        
        # Формуємо клавіатуру
        keyboard = []
        
        # Додаємо кнопку PnL тільки якщо НЕМАЄ фільтрації по платформі
        if not platform:
            keyboard.append([InlineKeyboardButton("💹 Взнати PnL", callback_data='pnl_portfolio')])
        
        # Додаємо кнопки фільтрів якщо вони є
        if filter_buttons:
            keyboard.append(filter_buttons)
        
        # Додаємо завжди присутні кнопки
        keyboard.extend([
            [InlineKeyboardButton("💵 Оновити залишок", callback_data='ovdp_update_balance')],
            [InlineKeyboardButton("🔙 Назад", callback_data='ovdp')]
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in show_portfolio: {e}", exc_info=True)
        try:
            await query.edit_message_text(f"❌ Помилка: {str(e)[:100]}")
        except Exception as edit_error:
            logger.error(f"Failed to edit message: {edit_error}")
    finally:
        if session:
            try:
                session.close()
            except Exception as close_error:
                logger.error(f"Error closing session: {close_error}")


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