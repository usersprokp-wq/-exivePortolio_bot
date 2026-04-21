import logging
from collections import deque
from datetime import datetime

from models import Crypto, CryptoPortfolio

logger = logging.getLogger(__name__)


def parse_date(date_str):
    try:
        return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
    except Exception:
        return datetime.min


def recalculate_percents(session):
    try:
        all_records = session.query(CryptoPortfolio).all()
        total_sum = sum(r.total_amount for r in all_records) if all_records else 0
        for record in all_records:
            record.percent = (record.total_amount / total_sum * 100) if total_sum > 0 else 0
        session.commit()
    except Exception as e:
        logger.error(f"Error recalculating percents: {e}")


async def recalculate_portfolio(Session):
    try:
        session = Session()
        session.query(CryptoPortfolio).delete()
        session.commit()

        cryptos = session.query(Crypto).all()
        if not cryptos:
            session.close()
            return

        cryptos = sorted(
            cryptos,
            key=lambda x: (parse_date(x.date), 0 if x.operation_type == 'купівля' else 1)
        )

        buy_queues = {}
        for crypto in cryptos:
            ticker = crypto.ticker
            if ticker not in buy_queues:
                buy_queues[ticker] = {'queue': deque(), 'platform': crypto.platform}

            if crypto.operation_type == 'купівля':
                price_per_unit = crypto.total_amount / crypto.quantity if crypto.quantity > 0 else 0
                buy_queues[ticker]['queue'].append({'price': price_per_unit, 'quantity': crypto.quantity})
                buy_queues[ticker]['platform'] = crypto.platform
            else:
                remaining = crypto.quantity
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
                session.add(CryptoPortfolio(
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

    except Exception as e:
        logger.error(f"Error recalculating crypto portfolio: {e}")