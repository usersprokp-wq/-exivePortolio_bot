import logging
from datetime import datetime

import yfinance as yf

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import StockPortfolio
from .utils import recalculate_percents

logger = logging.getLogger(__name__)

PORTFOLIO_PER_PAGE = 5
PNL_PER_PAGE = 5


def _back_kb(callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=callback)]])


async def show_stocks_portfolio(update: Update, context: CallbackContext, platform=None, page=1):
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
                    [InlineKeyboardButton("📊 FF", callback_data='portfolio_ff'),
                     InlineKeyboardButton("📊 IB", callback_data='portfolio_ib')],
                    [InlineKeyboardButton("🔙 Назад", callback_data='stocks')]
                ]
                try:
                    await query.edit_message_text(
                        "📭 Немає акцій на біржі " + platform,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as e:
                    logger.error("Error editing message: " + str(e))
                return
            stock_records = sorted(filtered, key=lambda r: r.total_amount, reverse=True)
            balance_records = [r for r in all_records if r.ticker.lower() == platform.lower() + "usd"]
        else:
            stock_records = sorted(
                [r for r in all_records if not r.ticker.endswith('usd')],
                key=lambda r: r.total_amount, reverse=True
            )
            balance_records = [r for r in all_records if r.ticker.endswith('usd')]

        total_stocks = len(stock_records)
        total_pages = max(1, (total_stocks + PORTFOLIO_PER_PAGE - 1) // PORTFOLIO_PER_PAGE)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * PORTFOLIO_PER_PAGE
        page_stocks = stock_records[start_idx:start_idx + PORTFOLIO_PER_PAGE]

        total_invested = sum(r.total_amount for r in stock_records) + sum(r.total_amount for r in balance_records)

        platform_label = (" — " + platform) if platform else ""
        text = "💼 *Портфель Акцій" + platform_label + "* (стор. " + str(page) + "/" + str(total_pages) + ")\n\n"

        for record in page_stocks:
            pct = record.percent or 0
            text += "📈 *" + record.ticker + "* (" + str(round(pct, 1)) + "%)\n"
            text += "   📦 Кількість: " + str(record.total_quantity) + " шт\n"
            text += "   💰 Ціна: " + str(round(record.avg_price, 2)) + " $\n"
            text += "   💵 Сума: " + str(round(record.total_amount, 2)) + " $\n\n"

        if balance_records:
            text += "💵 *Залишки на рахунках:*\n"
            for br in balance_records:
                text += "   " + br.ticker + ": " + str(round(br.total_amount, 2)) + " $ (" + str(round(br.percent or 0, 1)) + "%)\n"
            text += "\n"

        text += "━━━━━━━━━━━━━━━━━━━━\n📊 *Всього інвестовано:* " + str(round(total_invested, 2)) + " $"

        keyboard = []
        if total_pages > 1:
            pagination_buttons = []
            for p in range(1, total_pages + 1):
                label = "[" + str(p) + "]" if p == page else str(p)
                cb = ("portfolio_" + platform.lower() + "_page_" + str(p)) if platform else ("portfolio_page_" + str(p))
                pagination_buttons.append(InlineKeyboardButton(label, callback_data=cb))
            keyboard.append(pagination_buttons)

        if platform:
            other = 'IB' if platform == 'FF' else 'FF'
            keyboard.append([
                InlineKeyboardButton("📊 Всі акції", callback_data='portfolio_all'),
                InlineKeyboardButton("📊 " + other, callback_data='portfolio_' + other.lower())
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
                    "📊 Портфель: " + str(total_stocks) + " акцій" + (" на " + platform if platform else ""),
                    show_alert=False
                )
            else:
                logger.error("Edit error: " + str(e))
                await query.answer("❌ Помилка оновлення", show_alert=True)

    except Exception as e:
        await query.edit_message_text("❌ Помилка: " + str(e))


async def _fetch_pnl_data(session_factory):
    session = session_factory()
    all_records = session.query(StockPortfolio).all()
    session.close()

    stock_records = [r for r in all_records if not r.ticker.endswith('usd')]
    results = []
    errors = []

    for record in stock_records:
        ticker_clean = record.ticker.split('.')[0]
        try:
            stock = yf.Ticker(ticker_clean)
            info = stock.info
            current_price = info.get('regularMarketPrice') or info.get('currentPrice')
            if current_price is None:
                errors.append(record.ticker)
                continue
            invested = record.avg_price * record.total_quantity
            current_total = current_price * record.total_quantity
            pnl_per_share = current_price - record.avg_price
            pnl_total = pnl_per_share * record.total_quantity
            pnl_pct = (pnl_per_share / record.avg_price * 100) if record.avg_price else 0
            results.append({
                'ticker': record.ticker,
                'qty': record.total_quantity,
                'avg': record.avg_price,
                'current': current_price,
                'invested': invested,
                'current_total': current_total,
                'pnl_per': pnl_per_share,
                'pnl_total': pnl_total,
                'pnl_pct': pnl_pct,
            })
        except Exception as e:
            logger.error("yfinance error for " + ticker_clean + ": " + str(e))
            errors.append(record.ticker)

    return results, errors


def _build_pnl_text(results, errors, page, total_pages):
    page_results = results[(page - 1) * PNL_PER_PAGE: page * PNL_PER_PAGE]

    text = "📊 *PnL по портфелю* (стор. " + str(page) + "/" + str(total_pages) + ")\n\n"

    for r in page_results:
        pnl_emoji = "📈" if r['pnl_total'] >= 0 else "📉"
        sign_per = "+" if r['pnl_per'] >= 0 else ""
        sign_tot = "+" if r['pnl_total'] >= 0 else ""
        sign_pct = "+" if r['pnl_pct'] >= 0 else ""
        text += pnl_emoji + " *" + r['ticker'] + "* — " + str(r['qty']) + " шт\n"
        text += "   " + str(round(r['avg'], 2)) + " $ → " + str(round(r['current'], 2)) + " $\n"
        text += "   За 1 шт: " + sign_per + str(round(r['pnl_per'], 2)) + " $\n"
        text += "   Всього: " + sign_tot + str(round(r['pnl_total'], 2)) + " $ (" + sign_pct + str(round(r['pnl_pct'], 2)) + "%)\n\n"

    if errors:
        text += "⚠️ Не знайдено: " + ", ".join(errors) + "\n\n"

    total_invested = sum(r['invested'] for r in results)
    total_current = sum(r['current_total'] for r in results)
    total_pnl = total_current - total_invested
    total_pct = (total_pnl / total_invested * 100) if total_invested else 0

    total_emoji = "📈" if total_pnl >= 0 else "📉"
    sign_total = "+" if total_pnl >= 0 else ""
    sign_total_pct = "+" if total_pct >= 0 else ""

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "💰 Всього інвестовано: " + str(round(total_invested, 2)) + " $\n"
    text += "💼 Поточні активи: " + str(round(total_current, 2)) + " $\n"
    text += total_emoji + " *Поточний PnL: " + sign_total + str(round(total_pnl, 2)) + " $ (" + sign_total_pct + str(round(total_pct, 2)) + "%)*"

    return text


def _build_pnl_keyboard(page, total_pages):
    keyboard = []
    if total_pages > 1:
        keyboard.append([
            InlineKeyboardButton(
                "[" + str(p) + "]" if p == page else str(p),
                callback_data="pnl_page_" + str(p)
            )
            for p in range(1, total_pages + 1)
        ])
    keyboard.append([InlineKeyboardButton("🔄 Оновити", callback_data='pnl_refresh')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='stocks_portfolio')])
    return InlineKeyboardMarkup(keyboard)


async def show_stocks_pnl(update: Update, context: CallbackContext, page: int = 1, use_cache: bool = True):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        cached = context.user_data.get('pnl_cache') if use_cache else None

        if cached is None:
            await query.edit_message_text("⏳ Завантажую поточні ціни, зачекайте...")
            results, errors = await _fetch_pnl_data(Session)
            context.user_data['pnl_cache'] = {'results': results, 'errors': errors}
        else:
            results = cached['results']
            errors = cached['errors']

        if not results and not errors:
            await query.edit_message_text("📭 Портфель пустий", reply_markup=_back_kb('stocks_portfolio'))
            return

        total_pages = max(1, (len(results) + PNL_PER_PAGE - 1) // PNL_PER_PAGE)
        page = max(1, min(page, total_pages))

        text = _build_pnl_text(results, errors, page, total_pages)
        keyboard = _build_pnl_keyboard(page, total_pages)

        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')

    except Exception as e:
        logger.error("Error in show_stocks_pnl: " + str(e))
        await query.edit_message_text("❌ Помилка: " + str(e), reply_markup=_back_kb('stocks_portfolio'))


async def handle_update_balance(update: Update, context: CallbackContext):
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
    query = update.callback_query
    platform = query.data.replace('balance_platform_', '').upper()
    context.user_data['balance_platform'] = platform
    context.user_data['stock_step'] = 'balance_amount'
    ticker = platform + "usd"

    Session = context.bot_data.get('Session')
    current_amount = 0
    if Session:
        session = Session()
        current = session.query(StockPortfolio).filter(StockPortfolio.ticker == ticker).first()
        session.close()
        current_amount = current.total_amount if current else 0

    await query.edit_message_text(
        "💵 *Залишок " + platform + "*\n\nПоточний залишок: " + str(round(current_amount, 2)) + " $\n\nВведіть нову суму залишку:",
        reply_markup=_back_kb('update_balance'),
        parse_mode='Markdown'
    )


async def handle_message_balance(update: Update, context: CallbackContext):
    user_message = update.message.text
    try:
        amount = float(user_message)
        if amount < 0:
            await update.message.reply_text(
                "❌ Сума має бути 0 або більше",
                reply_markup=_back_kb('update_balance')
            )
            return

        Session = context.bot_data.get('Session')
        if not Session:
            await update.message.reply_text("❌ Помилка підключення до бази даних")
            return

        platform = context.user_data['balance_platform']
        ticker = platform + "usd"

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
            "✅ *Залишок оновлено!*\n\n📊 Біржа: " + platform + "\n💵 Залишок: " + str(round(amount, 2)) + " $",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        context.user_data.pop('stock_step', None)
        context.user_data.pop('balance_platform', None)

    except ValueError:
        await update.message.reply_text(
            "❌ Будь ласка, введіть коректне число",
            reply_markup=_back_kb('update_balance')
        )