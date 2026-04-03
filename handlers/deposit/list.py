"""
handlers/deposit/list.py
Список депозитів з БД з пагінацією.
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Deposit

logger = logging.getLogger(__name__)

PAGE_SIZE = 5  # записів на сторінку


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _status(dep: Deposit) -> str:
    return "🟢" if dep.is_active else "⚪️"


def _kb_list(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"deposit_list_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"deposit_list_page_{page + 1}"))

    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="deposit")])
    return InlineKeyboardMarkup(keyboard)


async def show_deposit_list(update: Update, context: CallbackContext, page: int = 1):
    query = update.callback_query
    await query.answer()

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session = Session()
        all_deposits = session.query(Deposit).order_by(Deposit.id.desc()).all()
        session.close()
    except Exception as e:
        logger.error(f"Deposit list error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not all_deposits:
        await query.edit_message_text(
            "📋 <b>Мої записи</b>\n\n📭 Депозитів ще немає.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="deposit")
            ]]),
            parse_mode="HTML",
        )
        return

    total      = len(all_deposits)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(1, min(page, total_pages))
    slice_      = all_deposits[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    lines = [f"📋 <b>Мої записи</b>  <i>({total} шт.)</i>\n"]
    for dep in slice_:
        s    = _sign(dep.currency or "UAH")
        stat = _status(dep)
        term = f"{dep.term_days} дн." if dep.term_type == "days" else f"{dep.term_value} міс. ({dep.term_days} дн.)"
        lines.append(
            f"{stat} <b>{dep.bank_name}</b>\n"
            f"   💵 {dep.amount:,.0f} {s}  •  📈 {dep.interest_rate}%  •  ⏳ {term}\n"
            f"   📅 {dep.start_date} → {dep.end_date}\n"
            f"   💰 Чистий: <b>{dep.net_profit:,.2f} {s}</b>\n"
        )

    lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=_kb_list(page, total_pages),
        parse_mode="HTML",
    )