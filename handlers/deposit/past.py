"""
handlers/deposit/past.py
Минулі депозити — закриті вручну (is_active=0) або прострочені (end_date < сьогодні).
"""
import logging
from datetime import datetime, date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from models import Deposit

logger = logging.getLogger(__name__)

PAGE_SIZE = 4


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%d.%m.%Y").date()


def _kb_past(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"deposit_past_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"deposit_past_page_{page + 1}"))

    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="deposit")])
    return InlineKeyboardMarkup(keyboard)


async def show_deposit_past(update: Update, context: CallbackContext, page: int = 1):
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

        # Минулі: закриті вручну АБО дата закриття вже минула
        past = [
            d for d in all_dep
            if d.is_active == 0 or (d.end_date and _parse_date(d.end_date) < today)
        ]
        past.sort(key=lambda d: _parse_date(d.end_date) if d.end_date else date.min, reverse=True)

    except Exception as e:
        logger.error(f"Past deposits error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not past:
        await query.edit_message_text(
            "🗂 <b>Минулі депозити</b>\n\n📭 Закритих депозитів немає.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="deposit")
            ]]),
            parse_mode="HTML",
        )
        return

    total_pages = max(1, (len(past) + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(1, min(page, total_pages))
    slice_      = past[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    # ── Зведення по всіх минулих ──────────────────────────────────────────────
    by_currency: dict = {}
    for d in past:
        cur = d.currency or "UAH"
        s   = _sign(cur)
        by_currency.setdefault(cur, {"invested": 0, "net": 0, "s": s})
        by_currency[cur]["invested"] += d.amount
        by_currency[cur]["net"]      += d.net_profit or 0

    lines = [f"🗂 <b>Минулі депозити</b>  <i>({len(past)} шт.)</i>\n"]

    for dep in slice_:
        s        = _sign(dep.currency or "UAH")
        status   = "⚪️ Закрито вручну" if dep.is_active == 0 else "🔴 Завершено"
        term_str = (
            f"{dep.term_value} міс. ({dep.term_days} дн.)"
            if dep.term_type == "months"
            else f"{dep.term_days} дн."
        )

        lines.append(
            f"{status}  <b>{dep.bank_name}</b>\n"
            f"<code>"
            f"💵 Сума:        {dep.amount:>11,.2f} {s}\n"
            f"📈 Ставка:      {dep.interest_rate:>10.2f}%\n"
            f"⏳ Термін:      {term_str:>11}\n"
            f"📅 Відкриття:   {dep.start_date:>11}\n"
            f"📅 Закриття:    {dep.end_date:>11}\n"
            f"💰 Чистий дохід:{dep.net_profit:>10,.2f} {s}\n"
            f"🏁 На руки:     {dep.amount + (dep.net_profit or 0):>10,.2f} {s}\n"
            f"</code>\n"
        )

    # ── Зведення ──────────────────────────────────────────────────────────────
    lines.append("─" * 28 + "\n<b>Всього зароблено:</b>\n<code>")
    for cur, v in by_currency.items():
        lines.append(
            f"💵 Вкладено:    {v['invested']:>10,.2f} {v['s']}\n"
            f"💰 Чист. дохід: {v['net']:>10,.2f} {v['s']}\n"
        )
    lines.append("</code>")

    if total_pages > 1:
        lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=_kb_past(page, total_pages),
        parse_mode="HTML",
    )