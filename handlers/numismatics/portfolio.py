"""
handlers/numismatics/portfolio.py
Портфель — активні монети (is_sold = 0) + кнопка P&L з автопарсингом ua-coins.info.
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from models import Numismatic

logger    = logging.getLogger(__name__)
PAGE_SIZE = 5


def _coin_block(coin: Numismatic) -> str:
    return (
        f"🟢 <b>{coin.name}</b>  •  {coin.mint_year or '—'} р.\n"
        f"   💲 {coin.nominal or '—'}  •  {coin.metal_name or '—'} ({coin.metal_code or '—'})\n"
        f"   ⚖️ {coin.metal_weight or 0} г  •  📐 {coin.diameter or 0} мм\n"
        f"   🗓 В обіг: {coin.date_issued or '—'}\n"
        f"   🛒 {coin.quantity} шт.  •  💵 {coin.price_per_unit or 0:,.2f} ₴/шт.\n"
        f"   🚚 Доставка: {coin.delivery_cost or 0:,.2f} ₴\n"
        f"   💼 Загалом: <b>{coin.total_amount or 0:,.2f} ₴</b>  •  Собів.: <b>{coin.cost_per_unit or 0:,.2f} ₴/шт.</b>\n"
    )


def _build_text(coins: list, page: int, total_pages: int) -> str:
    slice_ = coins[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    lines  = [f"🏛 <b>Портфель монет</b>  <i>({len(coins)} поз.)</i>\n"]

    for coin in slice_:
        lines.append(_coin_block(coin))

    total_invested = sum((c.total_amount or 0) for c in coins)
    total_qty      = sum((c.quantity or 0) for c in coins)

    lines.append("─" * 24)
    lines.append(
        f"💼 Всього вкладено: <b>{total_invested:,.2f} ₴</b>  |  "
        f"Монет: <b>{total_qty} шт.</b>"
    )

    if total_pages > 1:
        lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    return "\n".join(lines)


def _kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"num_portfolio_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"num_portfolio_page_{page + 1}"))
    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("📊 Дізнатись P&L",  callback_data="num_pnl")])
    keyboard.append([InlineKeyboardButton("✅ Продані монети",  callback_data="num_sold")])
    keyboard.append([InlineKeyboardButton("🔙 Назад",           callback_data="numismatics")])
    return InlineKeyboardMarkup(keyboard)


async def show_num_portfolio(update: Update, context: CallbackContext, page: int = 1):
    query = update.callback_query
    await query.answer()

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session   = Session()
        all_coins = session.query(Numismatic).all()
        session.close()
        active = [c for c in all_coins if not c.is_sold]
    except Exception as e:
        logger.error(f"Coin portfolio error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not active:
        await query.edit_message_text(
            "🏛 <b>Портфель монет</b>\n\n📭 Активних монет немає.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Продані монети", callback_data="num_sold")],
                [InlineKeyboardButton("🔙 Назад",         callback_data="numismatics")],
            ]),
            parse_mode="HTML",
        )
        return

    total_pages = max(1, (len(active) + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(1, min(page, total_pages))

    await query.edit_message_text(
        _build_text(active, page, total_pages),
        reply_markup=_kb(page, total_pages),
        parse_mode="HTML",
    )


async def show_num_pnl(update: Update, context: CallbackContext):
    """Автоматично парсить ціни всіх монет портфелю і показує P&L."""
    query = update.callback_query
    await query.answer()

    # Повідомлення про завантаження
    await query.edit_message_text(
        "📊 <b>P&L портфелю</b>\n\n⏳ Отримую актуальні ціни з ua-coins.info...",
        parse_mode="HTML",
    )

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session   = Session()
        all_coins = session.query(Numismatic).all()
        session.close()
        active = [c for c in all_coins if not c.is_sold]
    except Exception as e:
        logger.error(f"PnL error: {e}")
        await query.edit_message_text(f"❌ Помилка БД: {e}")
        return

    if not active:
        await query.edit_message_text(
            "📊 <b>P&L портфелю</b>\n\n📭 Активних монет немає.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="num_portfolio")
            ]]),
            parse_mode="HTML",
        )
        return

    # Парсимо ціни для кожної монети
    from handlers.numismatics.parser import fetch_coin_price

    lines       = ["📊 <b>P&L портфелю — Нумізматика</b>\n"]
    total_cost  = 0.0
    total_value = 0.0
    total_pnl   = 0.0
    parsed_ok   = 0

    for coin in active:
        cost = coin.cost_per_unit or 0
        qty  = coin.quantity or 1

        # Парсимо ціну
        parsed = fetch_coin_price(
            name        = coin.name,
            nominal     = coin.nominal,
            date_issued = coin.date_issued,
        )

        coin_cost_total = cost * qty
        total_cost     += coin_cost_total

        if parsed["price"]:
            # Парсимо числове значення з рядка типу "12 500 грн"
            price_str = parsed["price"].replace("\xa0", "").replace(" ", "")
            # Видаляємо всі нецифрові символи крім крапки/коми
            price_num_str = ""
            for ch in price_str:
                if ch.isdigit() or ch in ".,":
                    price_num_str += ch
            price_num_str = price_num_str.replace(",", ".")

            try:
                market_price = float(price_num_str)
                pnl          = (market_price - cost) * qty
                pnl_pct      = ((market_price - cost) / cost * 100) if cost else 0
                sign         = "+" if pnl >= 0 else ""
                emoji        = "📈" if pnl >= 0 else "📉"

                total_value += market_price * qty
                total_pnl   += pnl
                parsed_ok   += 1

                block = (
                    f"{emoji} <b>{coin.name}</b>\n"
                    f"   💲 {coin.nominal or '—'}  •  🗓 {coin.date_issued or '—'}\n"
                    f"   🛒 {qty} шт.  •  Собів.: {cost:,.2f} ₴  →  Ринок: {market_price:,.2f} ₴\n"
                    f"   💰 P&L: <b>{sign}{pnl:,.2f} ₴</b>  ({sign}{pnl_pct:.1f}%)\n"
                )
                if parsed.get("url"):
                    block += f"   🔗 <a href='{parsed['url']}'>ua-coins.info</a>\n"

            except (ValueError, ZeroDivisionError):
                block = (
                    f"🪙 <b>{coin.name}</b>\n"
                    f"   ⚠️ Ціна: {parsed['price']} (не вдалось розпарсити число)\n"
                )
        else:
            err = parsed.get("error", "не знайдено")
            block = (
                f"🪙 <b>{coin.name}</b>\n"
                f"   💲 {coin.nominal or '—'}  •  🗓 {coin.date_issued or '—'}\n"
                f"   ❌ {err}\n"
            )

        lines.append(block)

    # Зведення
    if parsed_ok > 0:
        total_sign = "+" if total_pnl >= 0 else ""
        total_pct  = ((total_value - total_cost) / total_cost * 100) if total_cost else 0
        lines.append("─" * 24)
        lines.append(
            f"💼 Вкладено: <b>{total_cost:,.2f} ₴</b>\n"
            f"💹 Ринкова вартість: <b>{total_value:,.2f} ₴</b>\n"
            f"💰 Загальний P&L: <b>{total_sign}{total_pnl:,.2f} ₴</b>  ({total_sign}{total_pct:.1f}%)"
        )

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Оновити",       callback_data="num_pnl")],
            [InlineKeyboardButton("🔙 До портфелю",   callback_data="num_portfolio")],
        ]),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def handle_num_pnl_coin_selected(update: Update, context: CallbackContext):
    """Залишаємо для сумісності — тепер PnL рахується автоматично."""
    await show_num_pnl(update, context)


async def handle_message_num_pnl(update: Update, context: CallbackContext):
    """Залишаємо для сумісності."""
    pass


async def show_num_sold(update: Update, context: CallbackContext, page: int = 1):
    """Список проданих монет."""
    query = update.callback_query
    await query.answer()

    Session = context.bot_data.get('Session')
    if not Session:
        await query.edit_message_text("❌ Помилка підключення до бази даних")
        return

    try:
        session   = Session()
        all_coins = session.query(Numismatic).all()
        session.close()
        sold = [c for c in all_coins if c.is_sold]
    except Exception as e:
        logger.error(f"Coin sold error: {e}")
        await query.edit_message_text(f"❌ Помилка: {e}")
        return

    if not sold:
        await query.edit_message_text(
            "✅ <b>Продані монети</b>\n\n📭 Проданих монет ще немає.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="num_portfolio")
            ]]),
            parse_mode="HTML",
        )
        return

    total_pages = max(1, (len(sold) + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(1, min(page, total_pages))
    slice_      = sold[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    lines = [f"✅ <b>Продані монети</b>  <i>({len(sold)} поз.)</i>\n"]
    for coin in slice_:
        profit = ((coin.sell_price or 0) - (coin.cost_per_unit or 0)) * (coin.quantity or 1)
        lines.append(
            f"⚪️ <b>{coin.name}</b>  •  {coin.mint_year or '—'} р.\n"
            f"   🛒 {coin.quantity} шт.  •  Собів.: {coin.cost_per_unit or 0:,.2f} ₴ → Продано: {coin.sell_price or 0:,.2f} ₴\n"
            f"   P&L: <b>{profit:+,.2f} ₴</b>\n"
        )

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"num_sold_page_{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"num_sold_page_{page + 1}"))
    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="num_portfolio")])

    if total_pages > 1:
        lines.append(f"\n<i>Сторінка {page}/{total_pages}</i>")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )