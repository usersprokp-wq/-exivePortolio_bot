"""
Перегляд списку всіх операцій з ОВДП
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import Bond, BondPortfolio, ProfitRecord
from datetime import datetime

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 5


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

        keyboard = []

        for bond in bonds_page:
            op_icon = "🟢" if bond.operation_type == 'купівля' else "🔴"
            text += f"📅 {bond.date} | 🏦 {bond.platform}\n"
            text += f"🔢 {bond.bond_number} | {op_icon} {bond.operation_type.capitalize()}\n"
            text += f"📦 {bond.quantity} шт × {bond.price_per_unit:.2f} грн\n"
            text += f"💵 {bond.total_amount:.2f} грн\n\n"

            # Кнопка видалення під кожним записом
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 Видалити {bond.bond_number} {bond.operation_type} {bond.date}",
                    callback_data=f'bond_delete_{bond.id}'
                )
            ])

        # Кнопки пагінації
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


async def handle_bond_delete(update: Update, context: CallbackContext):
    """Обробка видалення запису ОВДП з відкатом портфелю і прибутків"""
    query = update.callback_query
    await query.answer()

    try:
        bond_id = int(query.data.replace('bond_delete_', ''))

        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()

        # Знаходимо запис
        bond = session.query(Bond).filter(Bond.id == bond_id).first()
        if not bond:
            await query.edit_message_text("❌ Запис не знайдено")
            session.close()
            return

        bond_number = bond.bond_number
        platform = bond.platform
        quantity = bond.quantity
        total_amount = bond.total_amount
        operation_type = bond.operation_type
        pnl = bond.pnl or 0

        # Знаходимо запис портфелю
        portfolio = session.query(BondPortfolio).filter(
            BondPortfolio.bond_number == bond_number,
            BondPortfolio.platform == platform
        ).first()

        if operation_type == 'купівля':
            # Відкочуємо купівлю: віднімаємо кількість і суму
            if portfolio:
                portfolio.total_quantity -= quantity
                portfolio.total_amount -= total_amount

                if portfolio.total_quantity <= 0:
                    session.delete(portfolio)
                else:
                    portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity
                    portfolio.last_update = datetime.now().isoformat()

        elif operation_type == 'продаж':
            # Відкочуємо продаж: повертаємо собівартість в портфель
            # собівартість = total_amount - pnl
            cost_of_sold = total_amount - pnl

            if portfolio:
                portfolio.total_quantity += quantity
                portfolio.total_amount += cost_of_sold
                portfolio.avg_price = portfolio.total_amount / portfolio.total_quantity
                portfolio.last_update = datetime.now().isoformat()
            else:
                # Якщо запис портфелю був видалений раніше — відновлюємо
                portfolio = BondPortfolio(
                    bond_number=bond_number,
                    maturity_date=bond.maturity_date,
                    total_quantity=quantity,
                    total_amount=cost_of_sold,
                    avg_price=cost_of_sold / quantity if quantity > 0 else 0,
                    platform=platform,
                    last_update=datetime.now().isoformat()
                )
                session.add(portfolio)

            # Видаляємо відповідний запис з profit_records
            profit_record = session.query(ProfitRecord).filter(
                ProfitRecord.operation_date == bond.date,
                ProfitRecord.operation_type == 'продаж',
                ProfitRecord.amount == total_amount
            ).order_by(ProfitRecord.id.desc()).first()

            if profit_record:
                session.delete(profit_record)

        # Видаляємо сам запис
        session.delete(bond)
        session.commit()

        # Перераховуємо відсотки
        from .balance import recalculate_bond_percents
        recalculate_bond_percents(session)

        session.close()

        op_icon = "🟢" if operation_type == 'купівля' else "🔴"
        await query.edit_message_text(
            f"✅ *Запис видалено*\n\n"
            f"🔢 {bond_number} | {op_icon} {operation_type.capitalize()}\n"
            f"📦 {quantity} шт × {total_amount / quantity:.2f} грн\n"
            f"💵 {total_amount:.2f} грн\n\n"
            f"Портфель оновлено.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Мої записи", callback_data='ovdp_list')],
                [InlineKeyboardButton("🔙 Назад до ОВДП", callback_data='ovdp')]
            ]),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in handle_bond_delete: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Помилка при видаленні: {str(e)}")