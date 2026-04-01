"""
Розрахункові функції: FIFO, прибутки, портфель
"""
from collections import defaultdict, deque
from datetime import datetime
from .helpers import parse_date, get_month_year


def calculate_profit_by_price(bonds):
    """
    Розраховує прибуток по методу FIFO (First In First Out).
    
    Логіка:
    1. Для кожної облігації ведемо чергу купівель з ціною
    2. При продажі - спочатку продаємо найстарішу купівлю
    3. Якщо однієї купівлі недостатньо - беремо з наступної
    4. Прибуток = (price_sell - price_buy) * quantity_sell
    """
    bond_stats = defaultdict(lambda: {
        'buy_queue': deque(),
        'sales': [],
        'profit': 0
    })
    
    # Сортуємо по row_order (порядку з Excel) для правильного FIFO
    sorted_bonds = sorted(bonds, key=lambda x: (
        x.row_order if x.row_order and x.row_order > 0 else float('inf'),
        parse_date(x.date),
        0 if x.operation_type == 'купівля' else 1
    ))
    
    for bond in sorted_bonds:
        bond_num = bond.bond_number
        
        if bond.operation_type == 'купівля':
            # Додаємо купівлю в чергу
            bond_stats[bond_num]['buy_queue'].append({
                'price': bond.price_per_unit,
                'quantity': bond.quantity,
                'date': bond.date
            })
        
        elif bond.operation_type == 'продаж':
            # Продаємо по FIFO - списуємо перші за часом купівлі
            remaining_to_sell = bond.quantity
            cost_of_goods_sold = 0
            sale_details = []
            
            # Списуємо купівлі з черги
            while remaining_to_sell > 0 and bond_stats[bond_num]['buy_queue']:
                buy = bond_stats[bond_num]['buy_queue'][0]
                
                # Скільки можемо продати з цієї купівлі
                qty_from_this_buy = min(remaining_to_sell, buy['quantity'])
                
                # Собівартість цієї партії = ціна купівлі × кількість
                partition_cost = qty_from_this_buy * buy['price']
                cost_of_goods_sold += partition_cost
                
                sale_details.append({
                    'buy_date': buy['date'],
                    'buy_price': buy['price'],
                    'qty': qty_from_this_buy,
                    'cost': partition_cost
                })
                
                # Оновлюємо залишок в черзі
                buy['quantity'] -= qty_from_this_buy
                remaining_to_sell -= qty_from_this_buy
                
                # Видаляємо купівлю якщо вона повністю продана
                if buy['quantity'] == 0:
                    bond_stats[bond_num]['buy_queue'].popleft()
            
            # Розраховуємо прибуток для цього продажу
            sale_revenue = bond.quantity * bond.price_per_unit
            profit = sale_revenue - cost_of_goods_sold
            
            bond_stats[bond_num]['sales'].append({
                'date': bond.date,
                'qty': bond.quantity,
                'sell_price': bond.price_per_unit,
                'cost': cost_of_goods_sold,
                'profit': profit,
                'details': sale_details
            })
            
            bond_stats[bond_num]['profit'] += profit
    
    # Загальний прибуток
    total_profit = sum(stats['profit'] for stats in bond_stats.values())
    
    return dict(bond_stats), total_profit


def calculate_monthly_profit(bonds):
    """
    Розраховує прибуток по місяцях на основі FIFO результатів з calculate_profit_by_price.
    """
    # Отримуємо FIFO результати
    bond_stats, _ = calculate_profit_by_price(bonds)
    
    monthly_profit = {}
    
    # Проходимо по кожній облігації та її продажам
    for bond_num, stats in bond_stats.items():
        for sale in stats['sales']:
            month_year = get_month_year(sale['date'])
            
            if month_year not in monthly_profit:
                monthly_profit[month_year] = 0
            
            # Додаємо прибуток цієї продажі до місяця
            monthly_profit[month_year] += sale['profit']
    
    return monthly_profit


def calculate_current_portfolio(bonds):
    """
    Розраховує поточний портфель (залишки облігацій)
    """
    portfolio = {}
    
    for bond in bonds:
        if bond.bond_number not in portfolio:
            portfolio[bond.bond_number] = {
                'quantity': 0,
                'buy_amount': 0,
                'avg_price': 0
            }
        
        if bond.operation_type == 'купівля':
            portfolio[bond.bond_number]['quantity'] += bond.quantity
            portfolio[bond.bond_number]['buy_amount'] += bond.total_amount
        else:
            portfolio[bond.bond_number]['quantity'] -= bond.quantity
            portfolio[bond.bond_number]['buy_amount'] -= bond.total_amount
    
    # Залишаємо тільки облігації з позитивним залишком
    portfolio = {k: v for k, v in portfolio.items() if v['quantity'] > 0}
    
    # Розраховуємо середню ціну покупки
    for bond_num, data in portfolio.items():
        if data['quantity'] > 0:
            data['avg_price'] = data['buy_amount'] / data['quantity']
    
    return portfolio
