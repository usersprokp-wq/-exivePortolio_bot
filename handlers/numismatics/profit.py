"""
handlers/numismatics/profit.py
Прибуток нумізматики — реалізований P&L (продані монети).

- Реалізований прибуток = sum((sell_price - cost_per_unit) * quantity) по проданих
- Розбивка по місяцях — по sell_date
- Не списаний = реалізований - вже списано
- Списання — фіксація виведених коштів
"""
import logging
from collections import defaultdict
from datetime import datetime, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models import Numismatic, NumismaticProfitRecord

logger = logging.getLogger(__name__)


async def show_num_profit(update: Update, context: CallbackContext):
    """Меню управління прибутками нумізматики."""
    query = update.callback_query
    await query.answer()

    try:
        Session = context.bot_data.get('Session')
        if not Session:
            await query.edit_message_text("❌ Помилка підключення до бази даних")
            return

        session     = Session()
        all_coins   = session.query(Numismatic).all()
        wr_records  = session.query(NumismaticProfitRecord).all()
        session.close()

        # ── Тільки продані монети ─────────────────────────────────────────────
        sold = [c for c in all_coins if c.is_sold and c.sell_price]

        if not sold:
            await query.edit_message_text(
                "💰 <b>Прибутки нумізматики</b>\n\n"
                "📭 Проданих монет ще немає.\n"
                "Прибуток з'явиться після першого продажу.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="numismatics")
                ]]),
                parse_mode="HTML",
            )
            return

        # ── Реалізований P&L ─────────────────────────────────────────────────
        total_pnl      = sum(
            ((c.sell_price or 0) - (c.cost_per_unit or 0)) * (c.quantity or 1)
            for c in sold
        )
        total_invested = sum((c.total_amount or 0) for c in sold)

        # ── Вже списано ──────────────────────────────────────────────────────
        total_written = sum(r.amount or 0 for r in wr_records)

        # ── Не списаний залишок ──────────────────────────────────────────────
        not_written = max(0.0, total_pnl - total_written)

        # Зберігаємо для кроку списання
        context.user_data['num_not_written'] = not_written
        context.user_data['num_total_pnl']   = total_pnl

        # ── Розбивка по місяцях (по sell_date) ───────────────────────────────
        month_data: dict = defaultdict(float)
        for c in sold:
            sell_date = getattr(c, 'sell_date', None)
            if not sell_date:
                continue
            try:
                month_key = datetime.strptime(sell_date, "%d.%m.%Y").strftime('%m.%Y')
                pnl = ((c.sell_price or 0) - (c.cost_per_unit or 0)) * (c.quantity or 1)
                month_data[month_key] += pnl
            except (ValueError, TypeError):
                continue

        sorted_months = sorted(
            month_data.keys(),
            key=lambda m: datetime.strptime(m, '%m.%Y')
        )

        # ── Формуємо текст ────────────────────────────────────────────────────
        sign = "+" if total_pnl >= 0 else ""
        text = "💰 <b>Управління прибутками нумізматики</b>\n\n"
        text += f"✅ Реалізований P&L: <b>{sign}{total_pnl:,.2f} ₴</b>\n"
        text += f"📦 Вкладено (продані): {total_invested:,.2f} ₴  •  Угод: {len(sold)}\n"

        if sorted_months:
            text += "\n📅 <b>Прибуток по місяцях:</b>\n"
            for month_key in sorted_months:
                val  = month_data[month_key]
                s    = "+" if val >= 0 else ""
                text += f"  {month_key} — 📈 {s}{val:,.2f} ₴\n"

        text += f"\n📋 Не списаний прибуток: <b>{not_written:,.2f} ₴</b>\n"

        keyboard = [
            [InlineKeyboardButton("✍️ Списати прибуток", callback_data="num_write_off_profit")],
            [InlineKeyboardButton("🔙 Назад",             callback_data="numismatics")],
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Num profit error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")


# ── Write off ─────────────────────────────────────────────────────────────────

async def handle_num_write_off(update: Update, context: CallbackContext):
    """Запитує суму для списання."""
    query = update.callback_query
    await query.answer()

    not_written = context.user_data.get('num_not_written', 0.0)

    if not_written <= 0:
        await query.answer("📋 Немає прибутку для списання", show_alert=True)
        return

    context.user_data['num_profit_step'] = 'write_off'

    await query.edit_message_text(
        f"💰 <b>Списання прибутку</b>\n\n"
        f"<b>Доступно до списання:</b>\n"
        f"  • {not_written:,.2f} ₴\n\n"
        f"Введіть суму для списання:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="num_profit")
        ]]),
        parse_mode="HTML",
    )


async def handle_num_sell_selected(update: Update, context: CallbackContext):
    """Обрана монета — запитуємо ціну продажу."""
    query   = update.callback_query
    await query.answer()
    coin_id = int(query.data.replace("num_sell_", ""))

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session = Session()
        coin    = session.query(Numismatic).filter(Numismatic.id == coin_id).first()
        session.close()
    except Exception as e:
        logger.error(f"Coin sell select error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not coin:
        await query.edit_message_text("❌ Монету не знайдено.")
        return

    context.user_data["num_sell_coin_id"] = coin_id
    context.user_data["num_profit_step"]  = "sell_price"

    await query.edit_message_text(
        f"🪙 <b>{coin.name}</b>  •  {coin.mint_year or '—'} р.\n"
        f"💲 {coin.nominal or '—'}  •  {coin.metal_name or '—'}\n"
        f"🛒 Кількість: {coin.quantity} шт.\n"
        f"📊 Собівартість: {coin.cost_per_unit or 0:,.2f} ₴/шт.\n\n"
        "💰 Введіть <b>ціну продажу за 1 шт.</b> у ₴:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Скасувати", callback_data="num_profit")
        ]]),
        parse_mode="HTML",
    )


async def handle_message_num_profit(update: Update, context: CallbackContext):
    """Обробка введеного числа — продаж або списання."""
    step = context.user_data.get("num_profit_step")
    if step not in ("sell_price", "write_off"):
        return
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    try:
        amount = float(text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Введіть коректне число більше 0:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Скасувати", callback_data="num_profit")
            ]]),
        )
        return

    # ── ПРОДАЖ монети ─────────────────────────────────────────────────────────
    if step == "sell_price":
        coin_id = context.user_data.pop("num_sell_coin_id", None)
        context.user_data.pop("num_profit_step", None)

        Session = context.bot_data.get('Session')
        if not Session:
            await update.message.reply_text("❌ Помилка підключення до бази даних")
            return

        try:
            session   = Session()
            coin      = session.query(Numismatic).filter(Numismatic.id == coin_id).first()
            if coin:
                pnl            = (amount - (coin.cost_per_unit or 0)) * (coin.quantity or 1)
                coin.sell_price = amount
                coin.is_sold    = 1
                coin.sell_date  = datetime.now().strftime("%d.%m.%Y")
                session.commit()
                name = coin.name
                qty  = coin.quantity
                cost = coin.cost_per_unit or 0
            session.close()
        except Exception as e:
            logger.error(f"Coin sell save error: {e}")
            await update.message.reply_text(f"❌ Помилка: {e}")
            return

        sign = "+" if pnl >= 0 else ""
        from handlers.numismatics.main_menu import get_numismatics_menu_keyboard
        await update.message.reply_text(
            f"✅ <b>Продано!</b>\n\n"
            f"🪙 {name}  •  {qty} шт.\n"
            f"📊 Собів.: {cost:,.2f} ₴ → Продано: {amount:,.2f} ₴/шт.\n"
            f"💰 P&L: <b>{sign}{pnl:,.2f} ₴</b>\n\n"
            "🏛 <b>Нумізматика</b> — оберіть дію:",
            reply_markup=get_numismatics_menu_keyboard(),
            parse_mode="HTML",
        )
        return

    # ── СПИСАННЯ прибутку ─────────────────────────────────────────────────────
    if step == "write_off":
        not_written = context.user_data.get('num_not_written', 0.0)
        context.user_data.pop('num_profit_step', None)

        if amount > not_written:
            await update.message.reply_text(
                f"❌ Сума перевищує доступний прибуток ({not_written:,.2f} ₴)\n\n"
                f"Введіть суму для списання:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="num_profit")
                ]])
            )
            context.user_data['num_profit_step'] = 'write_off'
            return

        try:
            Session = context.bot_data.get('Session')
            if Session:
                session = Session()
                session.add(NumismaticProfitRecord(
                    operation_date = datetime.now().strftime('%d.%m.%Y'),
                    amount         = amount,
                    created_at     = datetime.now().isoformat(),
                ))
                session.commit()
                session.close()
        except Exception as e:
            logger.error(f"Num write off error: {e}")

        remaining = max(0.0, not_written - amount)
        context.user_data.pop('num_not_written', None)
        context.user_data.pop('num_total_pnl', None)

        await update.message.reply_text(
            f"✅ <b>Прибуток списано!</b>\n\n"
            f"📝 Списано: <b>{amount:,.2f} ₴</b>\n"
            f"📋 Залишилось: <b>{remaining:,.2f} ₴</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 До прибутків",   callback_data="num_profit")],
                [InlineKeyboardButton("🏛 До нумізматики", callback_data="numismatics")],
            ]),
            parse_mode="HTML",
        )