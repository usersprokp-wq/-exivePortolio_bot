"""
handlers/deposit/stats.py
Статистика депозитів.
"""
import logging
from collections import defaultdict
from datetime import datetime, date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Deposit

logger   = logging.getLogger(__name__)
TAX_RATE = 0.23


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%d.%m.%Y").date()


def _sign(currency: str) -> str:
    return {"UAH": "₴", "USD": "$", "EUR": "€"}.get(currency, currency)


def _accrued_net(amount: float, rate: float, days_passed: int) -> float:
    gross = amount * (rate / 100) * (days_passed / 365)
    return gross * (1 - TAX_RATE)


async def show_deposit_stats(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        today   = date.today()
        session = Session()
        all_dep = session.query(Deposit).all()
        session.close()

        if not all_dep:
            await query.edit_message_text(
                "📊 <b>Статистика депозитів</b>\n\n📭 Депозитів ще немає.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="deposit")
                ]]),
                parse_mode="HTML",
            )
            return

        # ── Розподіл активні / закриті ────────────────────────────────────────
        active = [
            d for d in all_dep
            if d.is_active == 1 and d.end_date and _parse_date(d.end_date) >= today
        ]
        closed = [
            d for d in all_dep
            if d.is_active == 0 or (d.end_date and _parse_date(d.end_date) < today)
        ]

        total_count  = len(all_dep)
        active_count = len(active)
        closed_count = len(closed)

        # ── Інвестовано по валютах ────────────────────────────────────────────
        invested_by_cur: dict = defaultdict(float)
        for d in all_dep:
            invested_by_cur[d.currency or 'UAH'] += d.amount or 0

        # ── Середня ставка по активних ────────────────────────────────────────
        avg_rate     = sum(d.interest_rate or 0 for d in active) / len(active) if active else 0
        avg_rate_net = avg_rate * (1 - TAX_RATE)

        # ── Середній термін ───────────────────────────────────────────────────
        all_terms    = [d.term_days for d in all_dep if d.term_days]
        avg_term     = sum(all_terms) / len(all_terms) if all_terms else 0

        # ── Реалізований дохід ────────────────────────────────────────────────
        realized_by_cur: dict = defaultdict(float)
        for d in closed:
            realized_by_cur[d.currency or 'UAH'] += d.net_profit or 0

        # ── Середній дохід на депозит ─────────────────────────────────────────
        avg_profit_by_cur: dict = {}
        for cur, val in realized_by_cur.items():
            count = sum(1 for d in closed if (d.currency or 'UAH') == cur)
            avg_profit_by_cur[cur] = val / count if count else 0

        # ── Середній дохід на місяць ──────────────────────────────────────────
        avg_monthly_by_cur: dict = {}
        for cur in realized_by_cur:
            cur_closed = [d for d in closed if (d.currency or 'UAH') == cur]
            total_months = sum(
                (d.term_days or 0) / 30.44
                for d in cur_closed
            )
            avg_monthly_by_cur[cur] = realized_by_cur[cur] / total_months if total_months else 0

        # ── Найкращий депозит ─────────────────────────────────────────────────
        best = max(closed, key=lambda d: d.net_profit or 0) if closed else None

        # ── Топ банків ────────────────────────────────────────────────────────
        bank_stats: dict = defaultdict(lambda: {"count": 0, "rates": []})
        for d in all_dep:
            name = d.bank_name or "—"
            bank_stats[name]["count"] += 1
            if d.interest_rate:
                bank_stats[name]["rates"].append(d.interest_rate)

        # Сортуємо по кількості
        sorted_banks = sorted(bank_stats.items(), key=lambda x: x[1]["count"], reverse=True)

        # ── Формуємо текст ────────────────────────────────────────────────────
        text = "📊 <b>Статистика депозитів</b>\n\n"

        # Кількість
        text += (
            f"📦 Всього депозитів: <b>{total_count}</b>\n"
            f"   🟢 Активних: <b>{active_count}</b>  •  ⚪️ Закритих: <b>{closed_count}</b>\n\n"
        )

        # Інвестовано
        for cur, val in invested_by_cur.items():
            text += f"💼 Інвестовано: <b>{val:,.2f} {_sign(cur)}</b>\n"

        # Ставка і термін
        if active:
            text += (
                f"📈 Середня ставка: <b>{avg_rate:.1f}%</b>  "
                f"(<b>{avg_rate_net:.1f}%</b> чиста)\n"
            )
        if avg_term:
            text += f"⏳ Середній термін: <b>{avg_term:.0f} дн.</b>\n"

        text += "\n"

        # Реалізований дохід
        if realized_by_cur:
            for cur, val in realized_by_cur.items():
                s = _sign(cur)
                text += f"✅ Реалізований дохід: <b>{val:,.2f} {s}</b>\n"
                if cur in avg_monthly_by_cur:
                    text += f"📆 Середній дохід/міс: <b>{avg_monthly_by_cur[cur]:,.2f} {s}</b>\n"
            text += "\n"

        # Найкращий
        if best:
            s = _sign(best.currency or 'UAH')
            text += f"🏆 Найкращий: <b>{best.bank_name}</b> — {best.net_profit:,.2f} {s}\n\n"

        # Топ банків
        if sorted_banks:
            text += "🏦 <b>Банки:</b>\n"
            for bank_name, info in sorted_banks:
                avg_r = sum(info["rates"]) / len(info["rates"]) if info["rates"] else 0
                times = "раз" if info["count"] == 1 else "рази" if info["count"] < 5 else "разів"
                text += f"  • {bank_name} — {info['count']} {times}"
                if avg_r:
                    text += f" • {avg_r:.1f}%"
                text += "\n"

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="deposit")
            ]]),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Deposit stats error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")