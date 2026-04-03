"""
handlers/deposit/portfolio.py
Портфель — тільки активні депозити (end_date >= сьогодні).

Формат кожного депозиту (4 рядки):
  🟢 Альянс • 26,000 ₴ • 15.5% → 11.94%
  📅 14.03.2026 → 14.06.2026 | 💰 782.15 ₴
  ▓▓▓▓░░░░░░ 22% | ⏳ 72 дн. залишилось
  💰 170.03 ₴ нарах. | 612.12 ₴ залиш. | 782.15 ₴ всього
"""
import logging
from datetime import datetime, date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from models import Deposit

logger   = logging.getLogger(__name__)
TAX_RATE  = 0.23
PAGE_SIZE = 5


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _progress_bar(pct: float, length: int = 10) -> str:
    filled = round(pct / 100 * length)
    return "▓" * filled + "░" * (length - filled)


def _accrued_net(amount: float, rate: float, days_passed: int) -> float:
    """Чистий нарахований дохід на сьогодні (після податку)."""
    gross = amount * (rate / 100) * (days_passed / 365)
    return gross * (1 - TAX_RATE)


def _net_rate(rate: float) -> float:
    return rate * (1 - TAX_RATE)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%d.%m.%Y").date()


def _deposit_block(dep: Deposit, today: date) -> str:
    s          = _sign(dep.currency or "UAH")
    start_dt   = _parse_date(dep.start_date)
    end_dt     = _parse_date(dep.end_date)
    days_total  = max(1, (end_dt - start_dt).days)
    days_passed = max(0, (today - start_dt).days)
    days_left   = max(0, (end_dt - today).days)
    pct         = min(100, days_passed / days_total * 100)
    accrued     = _accrued_net(dep.amount, dep.interest_rate, days_passed)
    net_total   = dep.net_profit or 0
    remaining   = net_total - accrued
    net_r       = _net_rate(dep.interest_rate)

    return (
        f"🟢 <b>{dep.bank_name}</b>  •  {dep.amount:,.0f} {s}  •  "
        f"{dep.interest_rate:.1f}% → {net_r:.2f}%\n"
        f"📅 {dep.start_date} → {dep.end_date}  |  💰 {net_total:,.2f} {s}\n"
        f"{_progress_bar(pct)} {pct:.0f}%  |  ⏳ {days_left} дн. залишилось\n"
        f"<i>💰 {accrued:,.2f} нарах.  |  {remaining:,.2f} залиш.  |  {net_total:,.2f} {s} всього</i>\n"
    )


def _build_text(deposits: list, page: int, total_pages: int, today: date) -> str:
    slice_ = deposits[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    lines = [f"🏦 <b>Портфель депозитів</b>  <i>({len(deposits)} активних)</i>\n"]

    for dep in slice_:
        lines.append(_deposit_block(dep, today))

    # ── Зведення по всіх (не тільки поточна сторінка) ────────────────────────
    by_cur: dict = {}
    for d in deposits:
        cur = d.currency or "UAH"
        by_cur.setdefault(cur, {"invested": 0, "net": 0, "accrued": 0, "s": _sign(cur)})
        by_cur[cur]["invested"] += d.amount
        by_cur[cur]["net"]      += d.net_profit or 0
        by_cur[cur]["accrued"]  += _accrued_net(
            d.amount, d.interest_rate,
            max(0, (today - _parse_date(d.start_date)).days)
        )

    lines.append("─" * 24)
    for v in by_cur.values():
        lines.append(
            f"💼 Всього інвестовано: {v['invested']:,.0f} {v['s']}  |  Кількість: {len(deposits)} шт.\n"
            f"💰 {v['accrued']:,.2f} нарах.  |  🏁 {v['net']:,.2f} {v['s']} очік."
        )

    if total_pages > 1:
        lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    return "\n".join(lines)


def _kb(deposits: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    slice_   = deposits[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    keyboard = []

    # Кнопки договору для депозитів що мають файл
    for dep in slice_:
        if dep.contract_file_id:
            keyboard.append([InlineKeyboardButton(
                f"📄 Договір: {dep.bank_name}",
                callback_data=f"deposit_contract_{dep.id}"
            )])

    # Навігація
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"deposit_portfolio_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"deposit_portfolio_page_{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🗂 Минулі депозити", callback_data="deposit_past")])
    keyboard.append([InlineKeyboardButton("🔙 Назад",           callback_data="deposit")])
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

        active = [
            d for d in all_dep
            if d.is_active == 1 and d.end_date and _parse_date(d.end_date) >= today
        ]
        active.sort(key=lambda d: _parse_date(d.end_date))

    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not active:
        await query.edit_message_text(
            "🏦 <b>Портфель депозитів</b>\n\n📭 Активних депозитів немає.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗂 Минулі депозити", callback_data="deposit_past")],
                [InlineKeyboardButton("🔙 Назад",           callback_data="deposit")],
            ]),
            parse_mode="HTML",
        )
        return

    total_pages = max(1, (len(active) + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(1, min(page, total_pages))

    await query.edit_message_text(
        _build_text(active, page, total_pages, today),
        reply_markup=_kb(active, page, total_pages),
        parse_mode="HTML",
    )


async def handle_deposit_send_contract(update: Update, context: CallbackContext):
    """Надсилає PDF договору користувачу."""
    query  = update.callback_query
    await query.answer()
    dep_id = int(query.data.replace("deposit_contract_", ""))

    Session = context.bot_data.get('Session')
    if not Session:
        await query.answer("❌ Помилка БД", show_alert=True)
        return

    try:
        session = Session()
        dep     = session.query(Deposit).filter(Deposit.id == dep_id).first()
        session.close()
    except Exception as e:
        logger.error(f"Contract send error: {e}")
        await query.answer("❌ Помилка", show_alert=True)
        return

    if not dep or not dep.contract_file_id:
        await query.answer("📄 Договір відсутній", show_alert=True)
        return

    await context.bot.send_document(
        chat_id  = query.message.chat_id,
        document = dep.contract_file_id,
        caption  = f"📄 Договір депозиту — {dep.bank_name}",
    )


async def handle_deposit_close(update: Update, context: CallbackContext):
    """Закриває депозит — ставить is_active=0."""
    query  = update.callback_query
    await query.answer()
    dep_id = int(query.data.replace("deposit_close_", ""))

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session = Session()
        dep = session.query(Deposit).filter(Deposit.id == dep_id).first()
        if dep:
            dep.is_active = 0
            session.commit()
        session.close()
    except Exception as e:
        logger.error(f"Deposit close error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    await show_deposit_portfolio(update, context, page=1)