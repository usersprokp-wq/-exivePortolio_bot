"""
handlers/deposit/portfolio.py
Портфель — тільки активні депозити (end_date >= сьогодні).
Показує прогрес, нараховане, залишок, кнопку закриття.
"""
import logging
from datetime import datetime, date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from models import Deposit

logger = logging.getLogger(__name__)

TAX_RATE  = 0.23
PAGE_SIZE = 3  # активних на сторінку (більше інфо — менше на сторінці)


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _progress_bar(pct: float, length: int = 10) -> str:
    filled = round(pct / 100 * length)
    return "▓" * filled + "░" * (length - filled)


def _accrued(amount: float, rate: float, days_passed: int) -> float:
    """Чистий нарахований дохід на сьогодні."""
    gross = amount * (rate / 100) * (days_passed / 365)
    return gross * (1 - TAX_RATE)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%d.%m.%Y").date()


def _build_portfolio_text(deposits: list, page: int, total_pages: int, today: date) -> str:
    slice_ = deposits[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    # ── Зведення по всіх активних ─────────────────────────────────────────────
    total_invested  = sum(d.amount for d in deposits)
    total_net       = sum(d.net_profit or 0 for d in deposits)
    total_accrued   = sum(
        _accrued(d.amount, d.interest_rate,
                 (today - _parse_date(d.start_date)).days)
        for d in deposits
    )

    # групуємо суми по валютах для зведення
    by_currency: dict = {}
    for d in deposits:
        cur = d.currency or "UAH"
        s   = _sign(cur)
        by_currency.setdefault(cur, {"invested": 0, "net": 0, "accrued": 0, "s": s})
        by_currency[cur]["invested"] += d.amount
        by_currency[cur]["net"]      += d.net_profit or 0
        by_currency[cur]["accrued"]  += _accrued(
            d.amount, d.interest_rate,
            (today - _parse_date(d.start_date)).days
        )

    lines = [f"🏦 <b>Портфель депозитів</b>  <i>({len(deposits)} активних)</i>\n"]

    # ── Кожен депозит ─────────────────────────────────────────────────────────
    for dep in slice_:
        s          = _sign(dep.currency or "UAH")
        start_dt   = _parse_date(dep.start_date)
        end_dt     = _parse_date(dep.end_date)
        days_total = (end_dt - start_dt).days or 1
        days_passed = max(0, (today - start_dt).days)
        days_left  = max(0, (end_dt - today).days)
        pct        = min(100, days_passed / days_total * 100)
        accrued    = _accrued(dep.amount, dep.interest_rate, days_passed)
        remaining  = (dep.net_profit or 0) - accrued

        term_str = (
            f"{dep.term_value} міс. ({dep.term_days} дн.)"
            if dep.term_type == "months"
            else f"{dep.term_days} дн."
        )

        lines.append(
            f"🟢 <b>{dep.bank_name}</b>\n"
            f"<code>"
            f"💵 Сума:       {dep.amount:>12,.2f} {s}\n"
            f"📈 Ставка:     {dep.interest_rate:>11.2f}%\n"
            f"⏳ Термін:     {term_str:>12}\n"
            f"📅 Відкриття:  {dep.start_date:>12}\n"
            f"📅 Закриття:   {dep.end_date:>12}\n"
            f"</code>"
            f"{_progress_bar(pct)}  {pct:.0f}%\n"
            f"<code>"
            f"📆 Минуло:     {days_passed:>9} дн.\n"
            f"⌛️ Залишилось: {days_left:>9} дн.\n"
            f"💰 Нараховано: {accrued:>10,.2f} {s}\n"
            f"➕ Залишилось: {remaining:>10,.2f} {s}\n"
            f"🏁 На руки:    {dep.amount + (dep.net_profit or 0):>10,.2f} {s}\n"
            f"</code>\n"
        )

    # ── Зведення ──────────────────────────────────────────────────────────────
    lines.append("─" * 28 + "\n<b>Зведення:</b>\n<code>")
    for cur, v in by_currency.items():
        lines.append(
            f"💵 Інвестовано: {v['invested']:>10,.2f} {v['s']}\n"
            f"💰 Нараховано:  {v['accrued']:>10,.2f} {v['s']}\n"
            f"🏁 Очік. дохід: {v['net']:>10,.2f} {v['s']}\n"
        )
    lines.append("</code>")

    if total_pages > 1:
        lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    return "\n".join(lines)


def _kb_portfolio(deposits: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    slice_ = deposits[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    keyboard = []

    # Кнопки закриття для кожного депозиту на поточній сторінці
    for dep in slice_:
        keyboard.append([
            InlineKeyboardButton(
                f"🔴 Закрити: {dep.bank_name}",
                callback_data=f"deposit_close_{dep.id}"
            )
        ])

    # Навігація
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"deposit_portfolio_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"deposit_portfolio_page_{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="deposit")])
    return InlineKeyboardMarkup(keyboard)


async def show_deposit_portfolio(update: Update, context: CallbackContext, page: int = 1):
    query = update.callback_query
    await query.answer()

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        today   = date.today()
        session = Session()
        all_dep = session.query(Deposit).all()
        session.close()

        # Активні: is_active=1 І дата закриття >= сьогодні
        active = [
            d for d in all_dep
            if d.is_active == 1 and d.end_date and _parse_date(d.end_date) >= today
        ]
        active.sort(key=lambda d: _parse_date(d.end_date))  # найближчі до закриття — першими

    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not active:
        await query.edit_message_text(
            "🏦 <b>Портфель депозитів</b>\n\n📭 Активних депозитів немає.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="deposit")
            ]]),
            parse_mode="HTML",
        )
        return

    total_pages = max(1, (len(active) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))

    await query.edit_message_text(
        _build_portfolio_text(active, page, total_pages, today),
        reply_markup=_kb_portfolio(active, page, total_pages),
        parse_mode="HTML",
    )


async def handle_deposit_close(update: Update, context: CallbackContext):
    """Закриває депозит — ставить is_active=0."""
    query = update.callback_query
    await query.answer()

    dep_id  = int(query.data.replace("deposit_close_", ""))
    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session = Session()
        dep     = session.query(Deposit).filter(Deposit.id == dep_id).first()
        if dep:
            dep.is_active = 0
            session.commit()
            bank = dep.bank_name
        session.close()
    except Exception as e:
        logger.error(f"Deposit close error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    # Повертаємо в портфель
    await show_deposit_portfolio(update, context, page=1)