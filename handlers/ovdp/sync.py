"""
Синхронізація з Google Sheets
"""
import logging
from datetime import datetime
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from models import Bond, BondPortfolio

logger = logging.getLogger(__name__)


def create_bond_key(bond_data):
    """Створює унікальний ключ для запису (дата + номер + тип + ціна + кількість)"""
    return (
        bond_data.get('date', ''),
        bond_data.get('bond_number', ''),
        bond_data.get('operation_type', ''),
        float(bond_data.get('price_per_unit', 0)),
        int(bond_data.get('quantity', 0))
    )


async def sync_bonds_from_sheets(update: Update, context: CallbackContext):
    """Синхронізація ОВДП з Excel → БД (простий експорт)"""
    query = update.callback_query
    await query.answer()
    
    try:
        sheets_manager = context.bot_data.get('sheets_manager')
        Session = context.bot_data.get('Session')
        
        if not sheets_manager or not Session:
            await query.edit_message_text("❌ Помилка: Google Sheets або БД не доступні")
            return
        
        # Імпортуємо дані з Google Sheets
        excel_bonds_data = sheets_manager.import_bonds_from_sheets()
        
        if not excel_bonds_data:
            await query.edit_message_text("📭 Немає даних в Excel для синхронізації")
            return
        
        session = Session()
        
        # 1. ВИДАЛЯЄМО ВСЕ з БД
        try:
            session.query(Bond).delete()
            session.commit()
            deleted = len(excel_bonds_data)  # Кількість рядків що були
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting bonds: {e}")
            deleted = 0
        
        # 2. ДОДАЄМО рядки з Excel у ТОЧНОМУ ПОРЯДКУ
        added = 0
        errors = []
        
        for row_idx, bond_data in enumerate(excel_bonds_data):
            try:
                new_bond = Bond(
                    row_order=row_idx + 1,  # Порядок з Excel (1, 2, 3, ...)
                    date=bond_data.get('date', ''),
                    operation_type=bond_data.get('operation_type', ''),
                    bond_number=bond_data.get('bond_number', ''),
                    maturity_date=bond_data.get('maturity_date', ''),
                    price_per_unit=float(bond_data.get('price_per_unit', 0)),
                    quantity=int(bond_data.get('quantity', 0)),
                    total_amount=float(bond_data.get('total_amount', 0)),
                    platform=bond_data.get('platform', ''),
                    pnl=float(bond_data.get('pnl', 0))
                )
                session.add(new_bond)
                added += 1
            except Exception as e:
                errors.append(f"Помилка рядка {row_idx + 1} ({bond_data.get('bond_number')}): {str(e)}")
        
        # 3. ЗБЕРІГАЄМО
        try:
            session.commit()
            session.close()
        except Exception as e:
            session.rollback()
            session.close()
            logger.error(f"Error committing: {e}")
            await query.edit_message_text(f"❌ Помилка збереження: {str(e)}")
            return
        
        # Формуємо відповідь
        text = "🔄 *Синхронізація Excel → БД завершена*\n\n"
        text += f"❌ Видалено: {deleted}\n"
        text += f"✅ Додано: {added}\n\n"
        
        if errors:
            text += f"⚠️ Помилок: {len(errors)}\n"
            for error in errors[:5]:
                text += f"   • {error}\n"
            if len(errors) > 5:
                text += f"   • ... та ще {len(errors) - 5} помилок\n"
        else:
            text += "✨ Без помилок!\n\n"
        
        # Пересчитуємо портфель облігацій
        text += "⏳ Пересчитую портфель облігацій..."
        await query.edit_message_text(text, parse_mode='Markdown')
        
        session = Session()
        
        # 1. Рахуємо залишки по записах (номер + платформа → кількість)
        all_bonds = session.query(Bond).all()
        calculated_remains = defaultdict(lambda: {'quantity': 0, 'maturity_date': ''})
        
        for bond in all_bonds:
            key = (bond.bond_number, bond.platform.upper() if bond.platform else '')
            calculated_remains[key]['maturity_date'] = bond.maturity_date
            if bond.operation_type == 'купівля':
                calculated_remains[key]['quantity'] += bond.quantity
            else:
                calculated_remains[key]['quantity'] -= bond.quantity
        
        # Тільки активні позиції (quantity > 0)
        calculated_remains = {k: v for k, v in calculated_remains.items() if v['quantity'] > 0}
        
        # 2. Імпортуємо портфель з Excel
        excel_portfolio = sheets_manager.import_bonds_portfolio_from_sheets()
        
        # Формуємо словник Excel-портфеля по ключу (номер, платформа)
        excel_dict = {}
        for item in excel_portfolio:
            key = (item['bond_number'], item.get('platform', '').upper())
            excel_dict[key] = item
        
        # 3. Очищаємо таблицю портфеля
        session.query(BondPortfolio).delete()
        session.commit()
        
        matched = 0
        recalculated = 0
        
        # 4. Порівнюємо і заповнюємо портфель
        for (bond_num, platform), calc_data in calculated_remains.items():
            key = (bond_num, platform)
            excel_item = excel_dict.get(key)
            
            if excel_item and excel_item['total_quantity'] == calc_data['quantity']:
                # Збігається по номеру + платформі + кількості → беремо з Excel як є
                record = BondPortfolio(
                    bond_number=bond_num,
                    maturity_date=excel_item.get('maturity_date', calc_data['maturity_date']),
                    total_quantity=excel_item['total_quantity'],
                    total_amount=excel_item['total_amount'],
                    avg_price=excel_item['avg_price'],
                    platform=platform,
                    last_update=datetime.now().isoformat()
                )
                matched += 1
            else:
                # Не збігається → точковий перерахунок по середньозваженій
                total_qty = 0
                total_amt = 0
                maturity = calc_data['maturity_date']
                
                # Сортуємо по даті для правильного перерахунку
                bond_records = [b for b in all_bonds 
                               if b.bond_number == bond_num 
                               and (b.platform.upper() if b.platform else '') == platform]
                
                def parse_date(date_str):
                    try:
                        return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
                    except:
                        return datetime.min
                
                bond_records.sort(key=lambda x: (parse_date(x.date), 0 if x.operation_type == 'купівля' else 1))
                
                for b in bond_records:
                    if b.operation_type == 'купівля':
                        total_qty += b.quantity
                        total_amt += b.total_amount
                    else:
                        if total_qty > 0:
                            avg = total_amt / total_qty
                            total_amt -= avg * b.quantity
                            total_qty -= b.quantity
                
                avg_price = total_amt / total_qty if total_qty > 0 else 0
                
                record = BondPortfolio(
                    bond_number=bond_num,
                    maturity_date=maturity,
                    total_quantity=total_qty,
                    total_amount=total_amt,
                    avg_price=avg_price,
                    platform=platform,
                    last_update=datetime.now().isoformat()
                )
                recalculated += 1
            
            session.add(record)
        
        # 5. Додаємо залишки (ICUuah, SENSBANKuah) з Excel
        for item in excel_portfolio:
            if item['bond_number'].endswith('uah'):
                record = BondPortfolio(
                    bond_number=item['bond_number'],
                    maturity_date=item.get('maturity_date', ''),
                    total_quantity=item.get('total_quantity', 1),
                    total_amount=item.get('total_amount', 0),
                    avg_price=item.get('avg_price', 0),
                    platform=item['bond_number'].replace('uah', '').upper(),
                    last_update=datetime.now().isoformat()
                )
                session.add(record)
        
        # Якщо залишків не було в Excel — додаємо з 0
        for default_bal in [('ICUuah', 'ICU'), ('SENSBANKuah', 'SENSBANK')]:
            bond_number, plat = default_bal
            exists = session.query(BondPortfolio).filter(BondPortfolio.bond_number == bond_number).first()
            if not exists:
                record = BondPortfolio(
                    bond_number=bond_number,
                    maturity_date='',
                    total_quantity=1,
                    total_amount=0,
                    avg_price=0,
                    platform=plat,
                    last_update=datetime.now().isoformat()
                )
                session.add(record)
        
        session.commit()
        session.close()
        
        text += f"\n✅ Портфель оновлено!"
        text += f"\n📋 З Excel: {matched} | Перераховано: {recalculated}"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in sync_bonds_from_sheets: {e}")
        await query.edit_message_text(f"❌ Помилка синхронізації: {str(e)}")