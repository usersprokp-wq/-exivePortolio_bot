from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Product(Base):
    """Модель для продуктів"""
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    price = Column(Float)
    quantity = Column(Integer)
    created_at = Column(String(50), default=datetime.now().isoformat())


class Bond(Base):
    """Модель для ОВДП (облігацій)"""
    __tablename__ = 'bonds'
    id = Column(Integer, primary_key=True)
    row_order = Column(Integer, default=0)
    date = Column(String(50))
    operation_type = Column(String(20))
    bond_number = Column(String(50))
    maturity_date = Column(String(50))
    price_per_unit = Column(Float)
    quantity = Column(Integer)
    total_amount = Column(Float)
    platform = Column(String(100))
    pnl = Column(Float, default=0)
    created_at = Column(String(50), default=datetime.now().isoformat())


class BondPortfolio(Base):
    """Модель для портфеля облігацій (зберігає активні позиції)"""
    __tablename__ = 'bond_portfolio'
    id = Column(Integer, primary_key=True)
    bond_number = Column(String(50))
    maturity_date = Column(String(50))
    total_quantity = Column(Integer)
    total_amount = Column(Float)
    avg_price = Column(Float)
    platform = Column(String(100))
    percent = Column(Float, default=0)
    last_update = Column(String(50), default=datetime.now().isoformat())


class ProfitRecord(Base):
    """Таблиця для відслідкування прибутків ОВДП"""
    __tablename__ = 'profit_records'
    id = Column(Integer, primary_key=True)
    operation_date = Column(String(50))
    operation_type = Column(String(20))
    amount = Column(Float)
    realized_profit = Column(Float, default=0)
    unrealized_profit = Column(Float, default=0)
    created_at = Column(String(50), default=datetime.now().isoformat())


class Stock(Base):
    """Модель для акцій"""
    __tablename__ = 'stocks'
    id = Column(Integer, primary_key=True)
    row_order = Column(Integer, default=0)
    date = Column(String(50))
    operation_type = Column(String(20))
    ticker = Column(String(20))
    name = Column(String(200))
    price_per_unit = Column(Float)
    quantity = Column(Integer)
    total_amount = Column(Float)
    platform = Column(String(100))
    pnl = Column(Float, default=0)
    created_at = Column(String(50), default=datetime.now().isoformat())


class StockPortfolio(Base):
    """Модель для портфеля акцій (зберігає активні позиції)"""
    __tablename__ = 'stock_portfolio'
    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), unique=True)
    total_quantity = Column(Integer)
    total_amount = Column(Float)
    avg_price = Column(Float)
    platform = Column(String(100))
    percent = Column(Float, default=0)
    last_update = Column(String(50), default=datetime.now().isoformat())


class StockProfitRecord(Base):
    """Таблиця для відслідкування прибутків акцій"""
    __tablename__ = 'stock_profit_records'
    id = Column(Integer, primary_key=True)
    operation_date = Column(String(50))
    operation_type = Column(String(20))
    amount = Column(Float)
    realized_profit = Column(Float, default=0)
    unrealized_profit = Column(Float, default=0)
    created_at = Column(String(50), default=datetime.now().isoformat())


class Deposit(Base):
    """Модель для депозитів"""
    __tablename__ = 'deposits'
    id            = Column(Integer, primary_key=True)
    bank_name     = Column(String(100))          # Назва банку
    amount        = Column(Float)                # Сума депозиту
    currency      = Column(String(10))           # UAH / USD / EUR
    interest_rate = Column(Float)                # Відсоткова ставка, % річних
    start_date    = Column(String(50))           # Дата відкриття  DD.MM.YYYY
    end_date      = Column(String(50))           # Дата закриття   DD.MM.YYYY
    term_days     = Column(Integer)              # Термін у днях
    term_type     = Column(String(10))           # 'days' або 'months'
    term_value    = Column(Integer)              # Введене значення (дні або місяці)
    # Розраховані показники (зберігаємо щоб не перераховувати)
    gross_profit  = Column(Float)                # Валовий дохід
    tax_amount    = Column(Float)                # Податок 23%
    net_profit    = Column(Float)                # Чистий дохід
    net_per_month = Column(Float)                # Чистий дохід на місяць
    # Службові
    is_active        = Column(Integer, default=1)   # 1 = активний, 0 = закритий
    contract_file_id = Column(String(200))           # Telegram file_id PDF договору
    created_at       = Column(String(50), default=datetime.now().isoformat())


class DepositProfitRecord(Base):
    """Таблиця для відслідкування списань прибутків депозитів"""
    __tablename__ = 'deposit_profit_records'
    id             = Column(Integer, primary_key=True)
    operation_date = Column(String(50))   # Дата списання
    currency       = Column(String(10))   # UAH / USD / EUR
    amount         = Column(Float)        # Сума списання
    created_at     = Column(String(50), default=datetime.now().isoformat())


class Crypto(Base):
    """Модель для криптовалют"""
    __tablename__ = 'cryptos'
    id = Column(Integer, primary_key=True)
    date = Column(String(50))
    operation_type = Column(String(20))
    coin_name = Column(String(50))
    quantity = Column(Float)
    price_per_unit = Column(Float)
    total_amount = Column(Float)
    platform = Column(String(100))
    created_at = Column(String(50), default=datetime.now().isoformat())


class Numismatic(Base):
    """Модель для нумізматики"""
    __tablename__ = 'numismatics'
    id             = Column(Integer, primary_key=True)
    name           = Column(String(200))          # Назва монети
    year           = Column(Integer)              # Рік випуску
    quantity       = Column(Integer)              # Кількість
    currency       = Column(String(10))           # UAH / USD / EUR
    buy_price      = Column(Float)                # Ціна купівлі за 1 шт.
    sell_price     = Column(Float)                # Ціна продажу за 1 шт. (None якщо не продана)
    is_sold        = Column(Integer, default=0)   # 0 = активна, 1 = продана
    created_at     = Column(String(50), default=datetime.now().isoformat())