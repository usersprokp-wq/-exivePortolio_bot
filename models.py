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
    row_order = Column(Integer, default=0)  # Порядок рядка з Excel для FIFO
    date = Column(String(50))
    operation_type = Column(String(20))  # 'купівля' або 'продаж'
    bond_number = Column(String(50))
    maturity_date = Column(String(50))
    price_per_unit = Column(Float)
    quantity = Column(Integer)
    total_amount = Column(Float)
    platform = Column(String(100))
    pnl = Column(Float, default=0)  # PnL (прибуток/збиток) — заповнюється при продажу
    created_at = Column(String(50), default=datetime.now().isoformat())


class BondPortfolio(Base):
    """Модель для портфеля облігацій (зберігає активні позиції)"""
    __tablename__ = 'bond_portfolio'
    id = Column(Integer, primary_key=True)
    bond_number = Column(String(50))  # Номер облігації
    maturity_date = Column(String(50))  # Дата погашення
    total_quantity = Column(Integer)  # Загальна кількість облігацій
    total_amount = Column(Float)  # Загальна сума інвестицій
    avg_price = Column(Float)  # Середня ціна за облігацію
    platform = Column(String(100))  # Платформа
    last_update = Column(String(50), default=datetime.now().isoformat())  # Коли оновлено


class ProfitRecord(Base):
    """Таблиця для відслідкування прибутків ОВДП"""
    __tablename__ = 'profit_records'
    id = Column(Integer, primary_key=True)
    operation_date = Column(String(50))  # Дата операції купівлі/продажу
    operation_type = Column(String(20))  # 'купівля' або 'продаж'
    amount = Column(Float)  # Сума операції
    realized_profit = Column(Float, default=0)  # Реалізований прибуток
    unrealized_profit = Column(Float, default=0)  # Нереалізований прибуток (для списання)
    created_at = Column(String(50), default=datetime.now().isoformat())


class Stock(Base):
    """Модель для акцій"""
    __tablename__ = 'stocks'
    id = Column(Integer, primary_key=True)
    row_order = Column(Integer, default=0)  # Порядок рядка для сортування
    date = Column(String(50))
    operation_type = Column(String(20))  # 'купівля' або 'продаж'
    ticker = Column(String(20))
    name = Column(String(200))
    price_per_unit = Column(Float)
    quantity = Column(Integer)
    total_amount = Column(Float)
    platform = Column(String(100))
    pnl = Column(Float, default=0)  # PnL (прибуток/збиток) — заповнюється при продажу
    created_at = Column(String(50), default=datetime.now().isoformat())


class StockPortfolio(Base):
    """Модель для портфеля акцій (зберігає активні позиції)"""
    __tablename__ = 'stock_portfolio'
    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), unique=True)  # Унікальний тікер
    total_quantity = Column(Integer)  # Загальна кількість акцій
    total_amount = Column(Float)  # Загальна сума інвестицій
    avg_price = Column(Float)  # Середня ціна за акцію
    platform = Column(String(100))  # Біржа
    percent = Column(Float, default=0)  # % від загальної суми портфеля
    last_update = Column(String(50), default=datetime.now().isoformat())  # Коли оновлено


class Deposit(Base):
    """Модель для депозитів"""
    __tablename__ = 'deposits'
    id = Column(Integer, primary_key=True)
    date = Column(String(50))
    bank = Column(String(100))
    amount = Column(Float)
    interest_rate = Column(Float)  # % річних
    maturity_date = Column(String(50))
    created_at = Column(String(50), default=datetime.now().isoformat())


class Crypto(Base):
    """Модель для криптовалют"""
    __tablename__ = 'cryptos'
    id = Column(Integer, primary_key=True)
    date = Column(String(50))
    operation_type = Column(String(20))  # 'купівля' або 'продаж'
    coin_name = Column(String(50))
    quantity = Column(Float)
    price_per_unit = Column(Float)
    total_amount = Column(Float)
    platform = Column(String(100))
    created_at = Column(String(50), default=datetime.now().isoformat())


class Numismatic(Base):
    """Модель для нумізматики"""
    __tablename__ = 'numismatics'
    id = Column(Integer, primary_key=True)
    date = Column(String(50))
    operation_type = Column(String(20))  # 'купівля' або 'продаж'
    name = Column(String(200))  # Назва монети/предмету
    quantity = Column(Integer)
    price_per_unit = Column(Float)
    total_amount = Column(Float)
    created_at = Column(String(50), default=datetime.now().isoformat())