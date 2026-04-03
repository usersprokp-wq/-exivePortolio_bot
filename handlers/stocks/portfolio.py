import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import StockPortfolio
from .utils import recalculate_percents

logger = logging.getLogger(__name__)

PORTFOLIO_PER_PAGE = 5


async def show_stocks_portfolio(update: Update, context: CallbackContext, platform=None, page=1):
    """Показати портфель акцій з таблиці stock_portfolio"""
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session = Session()
        all_records = session.query(StockPortfolio).order_by(StockPortfolio.last_update.desc()).all()
        session.close()

        if not all_records:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='stocks')]]
            await query.edit_message_text("📭 Портфель пустий", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if platform:
            platform = platform.upper()
            filtered = [p for p in all_records if p.platform == platform and not p.ticker.endswith('usd')]
            if not filtered:
                keyboard = [
                    [InlineKeyboardButton("📊 FF", callback_data='portfolio_ff'), InlineKeyboardButton("📊 IB", callback_data='portfolio_ib')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
                ]
                try:
                    await query.edit_message_text(f"📭 Немає акцій на біржі {platform}", reply_markup=InlineKeyboardMarkup(keyboard))
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
                return
            stock_records = sorted(filtered, key=lambda r: r.total_amount, reverse=True)
            # Залишок тільки активної біржі
            balance_records = [r for r in all_records if r.ticker.lower() == f"{platform.lower()}usd"]
        else:
            stock_records = sorted(
                [r for r in all_records if not r.ticker.endswith('usd')],
                key=lambda r: r.total_amount, reverse=True
            )
            balance_records = [r for r in all_records if r.ticker.endswith('usd')]

        # Пагінація тільки для акцій
        total_stocks = len(stock_records)
        total_pages = max(1, (total_stocks + PORTFOLIO_PER_PAGE - 1) // PORTFOLIO_PER_PAGE)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * PORTFOLIO_PER_PAGE
        page_stocks = stock_records[start_idx:start_idx + PORTFOLIO_PER_PAGE]

        # Загальна сума: всі акції + залишки поточного фільтру
        total_invested = sum(r.total_amount for r in stock_records) + sum(r.total_amount for r in balance_records)

        text = f"💼 *Портфель Акцій*"
        if platform:
            text += f" — {platform}"
        text += f" (стор. {page}/{total_pages})\n\n"

        for record in page_stocks:
            pct = record.percent or 0
            text += f"📈 *{record.ticker}* ({pct:.1f}%)\n"
            text += f"   📦 Кількість: {record.total_quantity} шт\n"
            text += f"   💰 Ціна: {record.avg_price:.2f} $\n"
            text += f"   💵 Сума: {record.total_amount:.2f} $\n\n"

        # Залишки завжди на кожній сторінці
        if balance_records:
            text += "💵 *Залишки на рахунках:*\n"
            for br in balance_records:
                text += f"   {br.ticker}: {br.total_amount:.2f} $ ({br.percent or 0:.1f}%)\n"
            text += "\n"

        text += f"━━━━━━━━━━━━━━━━━━━━\n📊 *Всього інвестовано:* {total_invested:.2f} $"

        # Кнопки пагінації
        keyboard = []
        if total_pages > 1:
            pagination_buttons = []
            for p in range(1, total_pages + 1):
                label = f"[{p}]" if p == page else str(p)
                if platform:
                    cb = f"portfolio_{platform.lower()}_page_{p}"
                else:
                    cb = f"portfolio_page_{p}"
                pagination_buttons.append(InlineKeyboardButton(label, callback_data=cb))
            keyboard.append(pagination_buttons)

        # Кнопки фільтрів
        if platform:
            other = 'IB' if platform == 'FF' else 'FF'
            keyboard.append([
                InlineKeyboardButton("📊 Всі акції", callback_data='portfolio_all'),
                InlineKeyboardButton(f"📊 {other}", callback_data=f'portfolio_{other.lower()}')
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("📊 FF", callback_data='portfolio_ff'),
                InlineKeyboardButton("📊 IB", callback_data='portfolio_ib')
            ])

        keyboard.append([InlineKeyboardButton("💵 Оновити залишок", callback_data='update_balance')])
        keyboard.append([InlineKeyboardButton("📈 Взнати PnL", callback_data='stocks_check_pnl')])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks')])

        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception as e:
            error_msg = str(e).lower()
            if "not modified" in error_msg or "400" in error_msg:
                await query.answer(
                    f"📊 Портфель: {total_stocks} акцій" + (f" на {platform}" if platform else ""),
                    show_alert=False
                )
            else:
                logger.error(f"Edit error: {e}")
                await query.answer("❌ Помилка оновлення", show_alert=True)

    except Exception as e:
        await query.edit_message_text(f"❌ Помилка: {str(e)}")


async def handle_update_balance(update: Update, context: CallbackContext):
    """Показати меню вибору біржі для оновлення залишку"""
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("📊 FF", callback_data='balance_platform_ff')],
        [InlineKeyboardButton("📊 IB", callback_data='balance_platform_ib')],
        [InlineKeyboardButton("🔙 Назад", callback_data='stocks_portfolio')]
    ]
    await query.edit_message_text(
        "💵 *Оновити залишок*\n\nОберіть біржу:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_balance_platform(update: Update, context: CallbackContext):
    """Вибір платформи для оновлення залишку"""
    query = update.callback_query
    platform = query.data.replace('balance_platform_', '').upper()
    context.user_data['balance_platform'] = platform
    context.user_data['stock_step'] = 'balance_amount'
    ticker = f"{platform}usd"

    Session = context.bot_data.get('Session')
    current_amount = 0
    if Session:
        session = Session()
        current = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()
        session.close()
        current_amount = current.total_amount if current else 0

    await query.edit_message_text(
        f"💵 *Залишок {platform}*\n\n"
        f"Поточний залишок: {current_amount:.2f} $\n\n"
        f"Введіть нову суму залишку:",
        parse_mode='Markdown'
    )


async def handle_message_balance(update: Update, context: CallbackContext):
    """Обробка введення нового залишку"""
    user_message = update.message.text
    try:
        amount = float(user_message)
        if amount < 0:
            await update.message.reply_text("❌ Сума має бути 0 або більше")
            return

        Session = context.bot_data.get('Session')
        if not Session:
            await update.message.reply_text("❌ Помилка підключення до бази даних")
            return

        platform = context.user_data['balance_platform']
        ticker = f"{platform}usd"

        session = Session()
        record = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()
        if record:
            record.total_amount = amount
            record.avg_price = amount
            record.last_update = datetime.now().isoformat()
        else:
            session.add(StockPortfolio(
                ticker=ticker,
                total_quantity=1,
                total_amount=amount,
                avg_price=amount,
                platform=platform,
                percent=0,
                last_update=datetime.now().isoformat()
            ))

        session.commit()
        recalculate_percents(session)
        session.close()

        keyboard = [
            [InlineKeyboardButton("💼 До портфеля", callback_data='stocks_portfolio')],
            [InlineKeyboardButton("🔙 До Акцій", callback_data='stocks')]
        ]
        await update.message.reply_text(
            f"✅ *Залишок оновлено!*\n\n📊 Біржа: {platform}\n💵 Залишок: {amount:.2f} $",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        context.user_data.pop('stock_step', None)
        context.user_data.pop('balance_platform', None)

    except ValueError:
        await update.message.reply_text("❌ Будь ласка, введіть коректне число")