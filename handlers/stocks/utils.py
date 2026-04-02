import logging
from collections import deque
from datetime import datetime

from models import Stock, StockPortfolio

logger = logging.getLogger(__name__)


def parse_date(date_str):
    try:
        return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
    except Exception:
        return datetime.min


def recalculate_percents(session):
    """Перераховує % кожної акції від загальної суми портфеля"""
    try:
        all_records = session.query(StockPortfolio).all()
        total_sum = sum(r.total_amount for r in all_records) if all_records else 0
        for record in all_records:
            record.percent = (record.total_amount / total_sum * 100) if total_sum > 0 else 0
        session.commit()
    except Exception as e:
        logger.error(f"Error recalculating percents: {e}")


async def recalculate_portfolio(Session):
    """Пересчитати портфель з записів stocks та заповнити stock_portfolio (FIFO)"""
    try:
        session = Session()
        session.query(StockPortfolio).delete()
        session.commit()

        stocks = session.query(Stock).all()
        if not stocks:
            session.close()
            return

        stocks = sorted(
            stocks,
            key=lambda x: (parse_date(x.date), 0 if x.operation_type == 'купівля' else 1)
        )

        buy_queues = {}
        for stock in stocks:
            ticker = stock.ticker
            if ticker not in buy_queues:
                buy_queues[ticker] = {'queue': deque(), 'platform': stock.platform}

            if stock.operation_type == 'купівля':
                price_per_unit = stock.total_amount / stock.quantity if stock.quantity > 0 else 0
                buy_queues[ticker]['queue'].append({'price': price_per_unit, 'quantity': stock.quantity})
                buy_queues[ticker]['platform'] = stock.platform
            else:
                remaining = stock.quantity
                while remaining > 0 and buy_queues[ticker]['queue']:
                    buy = buy_queues[ticker]['queue'][0]
                    qty_to_sell = min(remaining, buy['quantity'])
                    buy['quantity'] -= qty_to_sell
                    remaining -= qty_to_sell
                    if buy['quantity'] == 0:
                        buy_queues[ticker]['queue'].popleft()

        for ticker, data in buy_queues.items():
            total_quantity = sum(b['quantity'] for b in data['queue'])
            total_amount = sum(b['price'] * b['quantity'] for b in data['queue'])
            if total_quantity > 0:
                avg_price = total_amount / total_quantity
                session.add(StockPortfolio(
                    ticker=ticker,
                    total_quantity=total_quantity,
                    total_amount=total_amount,
                    avg_price=avg_price,
                    platform=data['platform'],
                    last_update=datetime.now().isoformat()
                ))

        session.commit()
        recalculate_percents(session)
        session.close()
        logger.info("Портфель пересчитаний (FIFO)")

    except Exception as e:
        logger.error(f"Error recalculating portfolio: {e}")
