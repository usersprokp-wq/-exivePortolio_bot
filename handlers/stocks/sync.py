import logging
from collections import defaultdict
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Stock, StockPortfolio
from .utils import parse_date, recalculate_percents

logger = logging.getLogger(__name__)


async def sync_stocks_to_sheets(update: Update, context: CallbackContext):
    """Синхронізація Акцій БД → Excel"""
    query = update.callback_query
    await query.answer()

    try:
        sheets_manager = context.bot_data.get('sheets_manager')
        Session = context.bot_data.get('Session')

        if not sheets_manager or not Session:
            await query.edit_message_text("❌ Помилка: Google Sheets або БД не доступні")
            return

        session = Session()
        stocks = session.query(Stock).all()

        if not stocks:
            session.close()
            await query.edit_message_text("📭 Немає даних для синхронізації")
            return

        stocks = sorted(stocks, key=lambda x: parse_date(x.date))

        stocks_data = [
            {
                'date': s.date, 'platform': s.platform, 'operation_type': s.operation_type,
                'ticker': s.ticker, 'name': s.ticker, 'price_per_unit': s.price_per_unit,
                'quantity': s.quantity, 'total_amount': s.total_amount, 'pnl': s.pnl or 0
            }
            for s in stocks
        ]
        sheets_manager.export_stocks_to_sheets(stocks_data)

        portfolio_records = session.query(StockPortfolio).all()
        session.close()

        portfolio_data = [
            {
                'ticker': r.ticker, 'total_quantity': r.total_quantity, 'avg_price': r.avg_price,
                'total_amount': r.total_amount, 'platform': r.platform, 'percent': r.percent or 0
            }
            for r in portfolio_records
        ]
        sheets_manager.export_stocks_portfolio(portfolio_data)

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='sync_stocks')]]
        await query.edit_message_text(
            f"✅ Синхронізовано!\n\n📋 Записів: {len(stocks_data)}\n💼 Акцій в портфелі: {len(portfolio_data)}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error syncing stocks: {e}")
        await query.edit_message_text(f"❌ Помилка синхронізації: {str(e)}")


async def sync_stocks_from_sheets(update: Update, context: CallbackContext):
    """Синхронізація Акцій Excel → БД"""
    query = update.callback_query
    await query.answer()

    try:
        sheets_manager = context.bot_data.get('sheets_manager')
        Session = context.bot_data.get('Session')

        if not sheets_manager or not Session:
            await query.edit_message_text("❌ Помилка: Google Sheets або БД не доступні")
            return

        excel_stocks_data = sheets_manager.import_stocks_from_sheets()
        if not excel_stocks_data:
            await query.edit_message_text("📭 Немає даних в Excel для синхронізації")
            return

        session = Session()

        try:
            session.query(Stock).delete()
            session.commit()
            deleted = len(excel_stocks_data)
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting stocks: {e}")
            deleted = 0

        excel_stocks_data.sort(key=lambda d: parse_date(d.get('date', '')), reverse=True)

        added, errors = 0, []
        for row_idx, stock_data in enumerate(excel_stocks_data):
            try:
                session.add(Stock(
                    row_order=row_idx + 1,
                    date=stock_data.get('date', ''),
                    operation_type=stock_data.get('operation_type', ''),
                    ticker=stock_data.get('ticker', ''),
                    name=stock_data.get('name', ''),
                    price_per_unit=float(stock_data.get('price_per_unit', 0)),
                    quantity=int(stock_data.get('quantity', 0)),
                    total_amount=float(stock_data.get('total_amount', 0)),
                    platform=stock_data.get('platform', ''),
                    pnl=float(stock_data.get('pnl', 0))
                ))
                added += 1
            except Exception as e:
                errors.append(f"Помилка рядка {row_idx + 1} ({stock_data.get('ticker')}): {str(e)}")

        try:
            session.commit()
            session.close()
        except Exception as e:
            session.rollback()
            session.close()
            logger.error(f"Error committing: {e}")
            await query.edit_message_text(f"❌ Помилка збереження: {str(e)}")
            return

        text = f"🔄 *Синхронізація Excel → БД завершена*\n\n❌ Видалено: {deleted}\n✅ Додано: {added}\n\n"
        if errors:
            text += f"⚠️ Помилок: {len(errors)}\n"
            for error in errors[:5]:
                text += f"   • {error}\n"
            if len(errors) > 5:
                text += f"   • ... та ще {len(errors) - 5} помилок\n"
        else:
            text += "✨ Без помилок!\n\n"

        text += "⏳ Пересчитую портфель..."
        await query.edit_message_text(text, parse_mode='Markdown')

        session = Session()
        all_stocks = session.query(Stock).all()

        calculated_remains = defaultdict(lambda: {'quantity': 0})
        for stock in all_stocks:
            key = (stock.ticker, stock.platform.upper() if stock.platform else '')
            if stock.operation_type == 'купівля':
                calculated_remains[key]['quantity'] += stock.quantity
            else:
                calculated_remains[key]['quantity'] -= stock.quantity
        calculated_remains = {k: v for k, v in calculated_remains.items() if v['quantity'] > 0}

        excel_portfolio = sheets_manager.import_stocks_portfolio_from_sheets()
        excel_dict = {(item['ticker'], item.get('platform', '').upper()): item for item in excel_portfolio}

        session.query(StockPortfolio).delete()
        session.commit()

        matched = recalculated = 0

        for (ticker, platform), calc_data in calculated_remains.items():
            key = (ticker, platform)
            excel_item = excel_dict.get(key)

            if excel_item and excel_item['total_quantity'] == calc_data['quantity']:
                record = StockPortfolio(
                    ticker=ticker,
                    total_quantity=excel_item['total_quantity'],
                    total_amount=excel_item['total_amount'],
                    avg_price=excel_item['avg_price'],
                    platform=platform, percent=0,
                    last_update=datetime.now().isoformat()
                )
                matched += 1
            else:
                stock_records = sorted(
                    [s for s in all_stocks if s.ticker == ticker and (s.platform.upper() if s.platform else '') == platform],
                    key=lambda x: (parse_date(x.date), 0 if x.operation_type == 'купівля' else 1)
                )
                total_qty = total_amt = 0
                for s in stock_records:
                    if s.operation_type == 'купівля':
                        total_qty += s.quantity
                        total_amt += s.total_amount
                    elif total_qty > 0:
                        avg = total_amt / total_qty
                        total_amt -= avg * s.quantity
                        total_qty -= s.quantity

                avg_price = total_amt / total_qty if total_qty > 0 else 0
                record = StockPortfolio(
                    ticker=ticker, total_quantity=total_qty, total_amount=total_amt,
                    avg_price=avg_price, platform=platform, percent=0,
                    last_update=datetime.now().isoformat()
                )
                recalculated += 1

            session.add(record)

        for item in excel_portfolio:
            if item['ticker'].endswith('usd'):
                session.add(StockPortfolio(
                    ticker=item['ticker'],
                    total_quantity=item.get('total_quantity', 1),
                    total_amount=item.get('total_amount', 0),
                    avg_price=item.get('avg_price', 0),
                    platform=item.get('platform', ''),
                    percent=0, last_update=datetime.now().isoformat()
                ))

        for ticker_bal, plat in [('FFusd', 'FF'), ('IBusd', 'IB')]:
            if not session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker_bal).first():
                session.add(StockPortfolio(
                    ticker=ticker_bal, total_quantity=1, total_amount=0, avg_price=0,
                    platform=plat, percent=0, last_update=datetime.now().isoformat()
                ))

        session.commit()
        recalculate_percents(session)
        session.close()

        text += f"\n✅ Портфель оновлено!\n📋 З Excel: {matched} | Перераховано: {recalculated}"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in sync_stocks_from_sheets: {e}")
        await query.edit_message_text(f"❌ Помилка синхронізації: {str(e)}")
