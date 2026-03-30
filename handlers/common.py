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
    
    # ===== СИНХРОНІЗАЦІЯ =====
    
    elif query.data == 'sync':
        text = "🔄 *Синхронізація*\n\nОберіть категорію:"
        keyboard = [
            [InlineKeyboardButton("📈 ОВДП", callback_data='sync_ovdp'), InlineKeyboardButton("📊 Акції", callback_data='sync_stocks')],
            [InlineKeyboardButton("🏦 Депозит", callback_data='sync_deposit'), InlineKeyboardButton("₿ Криптовалюта", callback_data='sync_crypto')],
            [InlineKeyboardButton("🪙 Нумізматика", callback_data='sync_numismatics')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'sync_ovdp':
        text = "🔄 *Синхронізація ОВДП*\n\nОберіть напрямок:"
        keyboard = [
            [InlineKeyboardButton("📤 БД → Excel", callback_data='sync_ovdp_db_to_sheets')],
            [InlineKeyboardButton("📥 Excel → БД", callback_data='sync_ovdp_sheets_to_db')],
            [InlineKeyboardButton("🔙 Назад", callback_data='sync')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'sync_ovdp_db_to_sheets':
        await sync_bonds_to_sheets(update, context)
    
    elif query.data == 'sync_ovdp_sheets_to_db':
        from handlers.ovdp import sync_bonds_from_sheets
        await sync_bonds_from_sheets(update, context)
    
    elif query.data == 'sync_stocks':
        text = "🔄 *Синхронізація Акцій*\n\nОберіть напрямок:"
        keyboard = [
            [InlineKeyboardButton("📤 БД → Excel", callback_data='sync_stocks_db_to_sheets')],
            [InlineKeyboardButton("📥 Excel → БД", callback_data='sync_stocks_sheets_to_db')],
            [InlineKeyboardButton("🔙 Назад", callback_data='sync')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'sync_stocks_db_to_sheets':
        from handlers.stocks import sync_stocks_to_sheets
        await sync_stocks_to_sheets(update, context)
    
    elif query.data == 'sync_stocks_sheets_to_db':
        from handlers.stocks import sync_stocks_from_sheets
        await sync_stocks_from_sheets(update, context)
    
    elif query.data == 'sync_deposit':
        text = "🔄 *Синхронізація Депозитів*\n\nОберіть напрямок:"
        keyboard = [
            [InlineKeyboardButton("📤 БД → Excel", callback_data='sync_deposit_db_to_sheets')],
            [InlineKeyboardButton("📥 Excel → БД", callback_data='sync_deposit_sheets_to_db')],
            [InlineKeyboardButton("🔙 Назад", callback_data='sync')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data in ('sync_deposit_db_to_sheets', 'sync_deposit_sheets_to_db'):
        text = "🚧 *Синхронізація депозитів*\n\nВ розробці..."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync_deposit')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'sync_crypto':
        text = "🔄 *Синхронізація Криптовалюти*\n\nОберіть напрямок:"
        keyboard = [
            [InlineKeyboardButton("📤 БД → Excel", callback_data='sync_crypto_db_to_sheets')],
            [InlineKeyboardButton("📥 Excel → БД", callback_data='sync_crypto_sheets_to_db')],
            [InlineKeyboardButton("🔙 Назад", callback_data='sync')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data in ('sync_crypto_db_to_sheets', 'sync_crypto_sheets_to_db'):
        text = "🚧 *Синхронізація криптовалюти*\n\nВ розробці..."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync_crypto')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data == 'sync_numismatics':
        text = "🔄 *Синхронізація Нумізматики*\n\nОберіть напрямок:"
        keyboard = [
            [InlineKeyboardButton("📤 БД → Excel", callback_data='sync_numismatics_db_to_sheets')],
            [InlineKeyboardButton("📥 Excel → БД", callback_data='sync_numismatics_sheets_to_db')],
            [InlineKeyboardButton("🔙 Назад", callback_data='sync')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif query.data in ('sync_numismatics_db_to_sheets', 'sync_numismatics_sheets_to_db'):
        text = "🚧 *Синхронізація нумізматики*\n\nВ розробці..."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync_numismatics')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
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
        
        if not bonds:
            session.close()
            await query.edit_message_text("📭 Немає даних для синхронізації")
            return
        
        # Сортуємо по даті: нові спочатку
        from datetime import datetime as dt
        def parse_date(date_str):
            try:
                return dt.strptime(str(date_str).strip(), '%d.%m.%Y')
            except:
                return dt.min
        
        bonds = sorted(bonds, key=lambda x: parse_date(x.date), reverse=False)
        
        # Готуємо дані записів
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
                'platform': bond.platform,
                'pnl': bond.pnl or 0
            })
        
        # Експортуємо записи в Google Sheets
        sheets_manager.export_bonds_to_sheets(bonds_data)
        
        # Беремо портфель з bond_portfolio
        from models import BondPortfolio
        portfolio_records = session.query(BondPortfolio).all()
        session.close()
        
        portfolio_data = []
        for record in portfolio_records:
            portfolio_data.append({
                'bond_number': record.bond_number,
                'maturity_date': record.maturity_date,
                'total_quantity': record.total_quantity,
                'avg_price': record.avg_price,
                'total_amount': record.total_amount
            })
        
        sheets_manager.export_bonds_portfolio(portfolio_data)
        
        text = (
            f"✅ Синхронізовано!\n\n"
            f"📋 Записів: {len(bonds_data)}\n"
            f"💼 Облігацій в портфелі: {len(portfolio_data)}"
        )
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync_ovdp')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error syncing: {e}")
        await query.edit_message_text(f"❌ Помилка синхронізації: {str(e)}")