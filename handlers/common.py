import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from google_sheets import GoogleSheetsManager
from models import Bond
import os

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')


async def start(update: Update, context: CallbackContext):
    """Головне меню"""
    keyboard = [
        [InlineKeyboardButton("📈 ОВДП", callback_data='ovdp'), InlineKeyboardButton("📊 Акції", callback_data='stocks')],
        [InlineKeyboardButton("🏦 Депозит", callback_data='deposit'), InlineKeyboardButton("₿ Криптовалюта", callback_data='crypto')],
        [InlineKeyboardButton("🪙 Нумізматика", callback_data='numismatics'), InlineKeyboardButton("📊 Аналіз портфеля", callback_data='analysis')],
        [InlineKeyboardButton("🔄 Синхронізація", callback_data='sync')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📊 *Інвестиційний портфель*\n\nОберіть розділ для роботи:"
    
    # Перевіряємо чи це callback (редагуємо) або нове повідомлення
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def button_handler_main(update: Update, context: CallbackContext):
    """Головний обробник кнопок головного меню"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['current_message_id'] = query.message.message_id
    
    if query.data == 'ovdp':
        # Імпортуємо функцію з ovdp
        from handlers.ovdp import show_ovdp_menu
        await show_ovdp_menu(update, context)
    
    elif query.data == 'stocks':
        text = "📊 *Акції*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати", callback_data='stocks_add')],
            [InlineKeyboardButton("📋 Список", callback_data='stocks_list')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'deposit':
        text = "🏦 *Депозит*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати", callback_data='deposit_add')],
            [InlineKeyboardButton("📋 Список", callback_data='deposit_list')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'crypto':
        text = "₿ *Криптовалюта*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати", callback_data='crypto_add')],
            [InlineKeyboardButton("📋 Список", callback_data='crypto_list')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'numismatics':
        text = "🪙 *Нумізматика*\n\nОберіть дію:"
        keyboard = [
            [InlineKeyboardButton("➕ Додати", callback_data='numismatics_add')],
            [InlineKeyboardButton("📋 Список", callback_data='numismatics_list')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'analysis':
        text = "📊 *Аналіз портфеля*\n\nТут буде аналітика...\n\n(в розробці)"
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'sync':
        text = "🔄 *Синхронізація*\n\nОберіть напрямок:"
        keyboard = [
            [InlineKeyboardButton("📤 БД → Excel", callback_data='sync_db_to_sheets')],
            [InlineKeyboardButton("📥 Excel → БД", callback_data='sync_sheets_to_db')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'sync_db_to_sheets':
        await sync_bonds_to_sheets(update, context)
    
    elif query.data == 'sync_sheets_to_db':
        from handlers.ovdp import sync_bonds_from_sheets
        await sync_bonds_from_sheets(update, context)
    
    elif query.data == 'back_to_menu':
        await start(update, context)


async def sync_bonds_to_sheets(update: Update, context: CallbackContext):
    """Синхронізація облігацій в Google Sheets"""
    query = update.callback_query
    await query.answer()
    
    try:
        sheets_manager = context.bot_data.get('sheets_manager')
        Session = context.bot_data.get('Session')
        
        if not sheets_manager or not Session:
            await query.edit_message_text("❌ Помилка: Google Sheets або БД не доступні")
            return
        
        session = Session()
        bonds = session.query(Bond).all()
        session.close()
        
        if not bonds:
            await query.edit_message_text("📭 Немає даних для синхронізації")
            return
        
        # Готуємо дані
        bonds_data = []
        for bond in bonds:
            bonds_data.append({
                'date': bond.date,
                'operation_type': bond.operation_type,
                'bond_number': bond.bond_number,
                'maturity_date': bond.maturity_date,
                'price_per_unit': bond.price_per_unit,
                'quantity': bond.quantity,
                'total_amount': bond.total_amount,
                'platform': bond.platform
            })
        
        # Експортуємо в Google Sheets
        sheets_manager.export_bonds_to_sheets(bonds_data)
        
        # Готуємо портфель
        portfolio = {}
        for bond in bonds:
            if bond.bond_number not in portfolio:
                portfolio[bond.bond_number] = {
                    'maturity_date': bond.maturity_date,
                    'total_quantity': 0,
                    'total_amount': 0
                }
            
            if bond.operation_type == 'купівля':
                portfolio[bond.bond_number]['total_quantity'] += bond.quantity
                portfolio[bond.bond_number]['total_amount'] += bond.total_amount
            else:
                portfolio[bond.bond_number]['total_quantity'] -= bond.quantity
                portfolio[bond.bond_number]['total_amount'] -= bond.total_amount
        
        portfolio = {k: v for k, v in portfolio.items() if v['total_quantity'] > 0}
        
        portfolio_data = []
        for bond_num, data in portfolio.items():
            avg_price = data['total_amount'] / data['total_quantity'] if data['total_quantity'] > 0 else 0
            portfolio_data.append({
                'bond_number': bond_num,
                'maturity_date': data['maturity_date'],
                'total_quantity': data['total_quantity'],
                'avg_price': avg_price,
                'total_amount': data['total_amount']
            })
        
        sheets_manager.export_bonds_portfolio(portfolio_data)
        
        await query.edit_message_text(
            f"✅ Синхронізовано!\n\n"
            f"📋 Записів: {len(bonds_data)}\n"
            f"💼 Облігацій в портфелі: {len(portfolio_data)}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error syncing: {e}")
        await query.edit_message_text(f"❌ Помилка синхронізації: {str(e)}")