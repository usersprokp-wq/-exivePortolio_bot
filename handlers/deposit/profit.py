"""
handlers/deposit/profit.py
Прибутки депозитів — тільки реалізований (закриті депозити).

- Реалізований прибуток = sum(net_profit) по закритих (is_active=0)
- Розбивка по місяцях — по даті закриття
- Не списаний = реалізований - вже списано
- Списання — фіксація виведених коштів
"""
import logging
from collections import defaultdict
from datetime import datetime, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Deposit, DepositProfitRecord

logger = logging.getLogger(__name__)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%d.%m.%Y").date()


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


async def show_deposit_profit(update: Update, context: CallbackContext):
    """Меню управління прибутками депозитів."""
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session    = Session()
        all_dep    = session.query(Deposit).all()
        wr_records = session.query(DepositProfitRecord).all()
        session.close()

        # ── Тільки закриті депозити ────────────────────────────────────────────
        closed = [d for d in all_dep if d.is_active == 0]

        if not closed:
            await query.edit_message_text(
                "💰 <b>Прибутки депозитів</b>\n\n"
                "📭 Закритих депозитів ще немає.\n"
                "Прибуток з'явиться після закриття першого депозиту.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="deposit")
                ]]),
                parse_mode="HTML",
            )
            return

        # ── Реалізований прибуток по валютах ──────────────────────────────────
        realized_by_cur: dict = defaultdict(float)
        for d in closed:
            realized_by_cur[d.currency or 'UAH'] += d.net_profit or 0

        # ── Вже списано ───────────────────────────────────────────────────────
        written_by_cur: dict = defaultdict(float)
        for r in wr_records:
            written_by_cur[r.currency or 'UAH'] += r.amount or 0

        # ── Не списаний залишок ───────────────────────────────────────────────
        not_written_by_cur: dict = {}
        for cur, val in realized_by_cur.items():
            not_written_by_cur[cur] = max(0.0, val - written_by_cur.get(cur, 0))

        # Зберігаємо для кроку списання
        context.user_data['deposit_not_written'] = not_written_by_cur

        # ── Розбивка по місяцях (по даті закриття) ────────────────────────────
        # { 'MM.YYYY': { 'UAH': X, 'USD': Y } }
        month_data: dict = defaultdict(lambda: defaultdict(float))
        for d in closed:
            if not d.end_date:
                continue
            try:
                month_key = _parse_date(d.end_date).strftime('%m.%Y')
                month_data[month_key][d.currency or 'UAH'] += d.net_profit or 0
            except (ValueError, TypeError):
                continue

        sorted_months = sorted(
            month_data.keys(),
            key=lambda m: datetime.strptime(m, '%m.%Y')
        )

        # ── Формуємо текст ────────────────────────────────────────────────────
        text = "💰 <b>Управління прибутками депозитів</b>\n\n"

        # Реалізований по валютах
        for cur, val in realized_by_cur.items():
            s = _sign(cur)
            text += f"✅ Реалізований прибуток: <b>{val:,.2f} {s}</b>\n"

        text += "\n"

        # Місяці
        if sorted_months:
            text += "📅 <b>Прибуток по місяцях:</b>\n"
            for month_key in sorted_months:
                parts = []
                for cur, val in month_data[month_key].items():
                    parts.append(f"{val:,.2f} {_sign(cur)}")
                text += f"{month_key} — 📈 {' | '.join(parts)}\n"
            text += "\n"

        # Не списаний
        for cur, val in not_written_by_cur.items():
            s = _sign(cur)
            text += f"📋 Не списаний прибуток: <b>{val:,.2f} {s}</b>\n"

        keyboard = [
            [InlineKeyboardButton("✍️ Списати прибуток", callback_data="deposit_write_off_profit")],
            [InlineKeyboardButton("🔙 Назад",             callback_data="deposit")],
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Deposit profit error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")


# ── Write off ─────────────────────────────────────────────────────────────────

async def handle_deposit_write_off(update: Update, context: CallbackContext):
    """Запитує суму для списання."""
    query = update.callback_query
    await query.answer()

    not_written = context.user_data.get('deposit_not_written', {})
    if not any(v > 0 for v in not_written.values()):
        await query.answer("📋 Немає прибутку для списання", show_alert=True)
        return

    lines = ["💰 <b>Списання прибутку</b>\n\n<b>Доступно до списання:</b>"]
    for cur, val in not_written.items():
        if val > 0:
            lines.append(f"  • {val:,.2f} {_sign(cur)}")

    lines.append("\nВведіть суму для списання:")

    context.user_data['deposit_profit_step'] = 'write_off'
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="deposit_profit")
        ]]),
        parse_mode="HTML",
    )


async def handle_message_deposit_profit(update: Update, context: CallbackContext):
    """Обробка суми списання."""
    text = update.message.text.strip()

    not_written = context.user_data.get('deposit_not_written', {})

    try:
        amount = float(text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Введіть коректне число більше 0:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="deposit_profit")
            ]])
        )
        return

    # Визначаємо валюту — якщо одна, беремо її; якщо кілька — питаємо (поки UAH за замовчуванням)
    currencies_available = {cur: val for cur, val in not_written.items() if val > 0}

    if len(currencies_available) == 1:
        currency = list(currencies_available.keys())[0]
    else:
        # Якщо кілька валют — поки списуємо з першої що є
        currency = list(currencies_available.keys())[0]

    max_amount = currencies_available.get(currency, 0)

    if amount > max_amount:
        await update.message.reply_text(
            f"❌ Сума перевищує доступний прибуток ({max_amount:,.2f} {_sign(currency)})\n\n"
            f"Введіть суму для списання:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="deposit_profit")
            ]])
        )
        return

    # ── Зберігаємо списання ───────────────────────────────────────────────────
    try:
        Session = context.bot_data.get('Session')
        if Session:
            session = Session()
            session.add(DepositProfitRecord(
                operation_date = datetime.now().strftime('%d.%m.%Y'),
                currency       = currency,
                amount         = amount,
                created_at     = datetime.now().isoformat(),
            ))
            session.commit()
            session.close()
    except Exception as e:
        logger.error(f"Deposit write off error: {e}")

    remaining = max(0.0, max_amount - amount)
    context.user_data.pop('deposit_profit_step', None)
    context.user_data.pop('deposit_not_written', None)

    await update.message.reply_text(
        f"✅ <b>Прибуток списано!</b>\n\n"
        f"📝 Списано: <b>{amount:,.2f} {_sign(currency)}</b>\n"
        f"📋 Залишилось: <b>{remaining:,.2f} {_sign(currency)}</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 До прибутків", callback_data="deposit_profit")],
            [InlineKeyboardButton("🏦 До депозитів", callback_data="deposit")],
        ]),
        parse_mode="HTML",
    )