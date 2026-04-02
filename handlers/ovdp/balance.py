"""
Перегляд портфеля ОВДП
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import BondPortfolio

logger = logging.getLogger(__name__)


def recalculate_bond_percents(session):
    """Перерахувати відсотки для всіх облігацій в портфелі"""
    try:
        all_records = session.query(BondPortfolio).all()
        
        # Загальна сума (тільки облігації, без залишків)
        total_amount = sum(
            r.total_amount for r in all_records
            if not r.bond_number.endswith('uah')
        )
        
        for record in all_records:
            if record.bond_number.endswith('uah'):
                record.percent = 0
            else:
                record.percent = (record.total_amount / total_amount * 100) if total_amount > 0 else 0
        
        session.commit()
    except Exception as e:
        logger.error(f"Error in recalculate_bond_percents: {e}")


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

        # Групуємо облігації по номеру
        bonds_grouped = {}
        balances = []
        total_portfolio_amount = 0

        for record in portfolio:
            if record.bond_number.endswith('uah'):
                balances.append(record)
                total_portfolio_amount += record.total_amount
            else:
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

        for bond_number in sorted(bonds_grouped.keys()):
            bond_data = bonds_grouped[bond_number]
            records = bond_data['records']

            bond_total_qty = sum(r.total_quantity for r in records)
            bond_total_amount = sum(r.total_amount for r in records)
            bond_avg_price = bond_total_amount / bond_total_qty if bond_total_qty > 0 else 0
            bond_percent = (bond_total_amount / total_portfolio_amount * 100) if total_portfolio_amount > 0 else 0

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
        platform_lower = platform.lower() if platform else None

        if platform_lower:
            filter_buttons.append(InlineKeyboardButton("🏦 Всі", callback_data='ovdp_portfolio'))

        if platform_lower != 'icu':
            filter_buttons.append(InlineKeyboardButton("🏦 ICU", callback_data='portfolio_icu'))
        if platform_lower != 'sensbank':
            filter_buttons.append(InlineKeyboardButton("🏦 SENSBANK", callback_data='portfolio_sensbank'))

        keyboard = [
            [InlineKeyboardButton("💹 Взнати PnL", callback_data='pnl_portfolio')],
        ]

        if filter_buttons:
            keyboard.append(filter_buttons)

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