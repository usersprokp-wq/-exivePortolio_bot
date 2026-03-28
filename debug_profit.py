from collections import defaultdict, deque
from datetime import datetime


def calculate_profit_by_price(bonds):
    bond_stats = defaultdict(lambda: {'buy_queue': deque(), 'sales': [], 'profit': 0})

    def parse_date(date_str):
        try:
            return datetime.strptime(str(date_str).strip().replace('р.', '').replace('р', '').strip(), '%d.%m.%Y')
        except:
            return datetime.max

    sorted_bonds = sorted(bonds, key=lambda x: (parse_date(x.date), 0 if x.operation_type == 'купівля' else 1))

    for bond in sorted_bonds:
        bn = bond.bond_number

        if bond.operation_type == 'купівля':
            bond_stats[bn]['buy_queue'].append({
                'price': bond.price_per_unit,
                'quantity': bond.quantity,
                'date': bond.date
            })

        elif bond.operation_type == 'продаж':
            remaining_quantity = bond.quantity
            sale_profit = 0
            sale_details = []

            while remaining_quantity > 0 and bond_stats[bn]['buy_queue']:
                buy = bond_stats[bn]['buy_queue'][0]

                qty_to_sell = min(remaining_quantity, buy['quantity'])
                profit_per_unit = bond.price_per_unit - buy['price']
                partition_profit = profit_per_unit * qty_to_sell
                sale_profit += partition_profit

                sale_details.append({
                    'buy_date': buy['date'],
                    'buy_price': buy['price'],
                    'quantity': qty_to_sell,
                    'partition_profit': partition_profit
                })

                buy['quantity'] -= qty_to_sell
                remaining_quantity -= qty_to_sell

                if buy['quantity'] == 0:
                    bond_stats[bn]['buy_queue'].popleft()

            bond_stats[bn]['sales'].append({
                'sell_date': bond.date,
                'quantity': bond.quantity,
                'sell_price': bond.price_per_unit,
                'profit': sale_profit,
                'details': sale_details
            })
            bond_stats[bn]['profit'] += sale_profit

    total_profit = sum(stats['profit'] for stats in bond_stats.values())
    return dict(bond_stats), total_profit


class B:
    def __init__(self, date, operation_type, bond_number, maturity_date, price_per_unit, quantity, total_amount, platform):
        self.date = date
        self.operation_type = operation_type
        self.bond_number = bond_number
        self.maturity_date = maturity_date
        self.price_per_unit = price_per_unit
        self.quantity = quantity
        self.total_amount = total_amount
        self.platform = platform


rows = [
    ('04.07.2025','купівля','4000231247','10.09.2025',1046.69,40,26187.65,'ICU'),
    ('05.08.2025','купівля','4000230809','18.03.2026',1079.61,2,2159.22,'ICU'),
    ('12.08.2025','купівля','4000229264','15.10.2025',1064.64,112,119239.68,'ICU'),
    ('18.08.2025','купівля','4000231559','10.06.2026',1031.78,33,34048.74,'ICU'),
    ('01.09.2025','купівля','4000229264','15.10.2025',1072.20,5,5361.00,'ICU'),
    ('02.09.2025','продаж','4000231247','10.09.2025',1070.18,40,42807.20,'ICU'),
    ('02.09.2025','купівля','4000234215','24.06.2026',1025.69,57,58484.33,'ICU'),
    ('02.09.2025','купівля','4000231559','10.06.2026',1041.66,20,20833.20,'ICU'),
    ('22.09.2025','продаж','4000229264','15.10.2025',1079.48,158,170657.84,'ICU'),
    ('22.09.2025','продаж','4000231559','10.06.2026',1089.81,18,19616.58,'ICU'),
    ('24.09.2025','купівля','4000233565','16.09.2025',1006.01,7,7042.07,'ICU'),
    ('02.10.2025','купівля','4000235865','15.10.2025',1009.82,79,79775.78,'ICU'),
    ('13.10.2025','купівля','4000235865','15.10.2025',1088.34,109,118629.92,'ICU'),
    ('15.10.2025','продаж','4000229264','15.10.2025',1089.00,109,118701.00,'ICU'),
    ('22.10.2025','купівля','4000232424','23.06.2027',1079.55,29,31306.95,'ICU'),
    ('30.10.2025','купівля','4000230262','28.01.2026',1046.39,57,59643.92,'ICU'),
    ('04.11.2025','купівля','4000236128','14.10.2026',1010.77,58,58624.52,'ICU'),
    ('07.11.2025','продаж','4000231559','10.06.2026',1095.45,35,37080.75,'ICU'),
    ('07.11.2025','купівля','4000235865','15.10.2025',1020.97,2,2041.94,'ICU'),
    ('10.11.2025','продаж','4000234215','24.06.2026',1056.56,72,76072.32,'ICU'),
    ('26.11.2025','продаж','4000235865','15.10.2025',1016.97,176,178986.72,'ICU'),
    ('23.12.2025','купівля','4000237425','24.06.2027',1064.91,75,79868.25,'ICU'),
    ('08.01.2026','продаж','4000235865','15.10.2025',1034.63,84,86928.24,'ICU'),
    ('09.12.2025','продаж','4000237424','23.06.2027',1101.28,3,3303.84,'ICU'),
    ('13.12.2025','купівля','4000237424','23.06.2027',1107.72,40,44068.80,'ICU'),
    ('18.12.2025','купівля','4000237424','23.06.2027',1102.62,66,72772.92,'ICU'),
    ('18.12.2025','купівля','4000237424','23.06.2027',1041.12,31,32274.72,'ICU'),
    ('26.12.2025','продаж','4000237424','23.06.2027',1023.33,80,81865.44,'ICU'),
    ('07.01.2026','купівля','4000237424','23.06.2027',1022.24,22,22489.28,'ICU'),
    ('08.01.2026','купівля','4000237416','18.11.2026',1022.68,48,49088.64,'ICU'),
    ('22.01.2026','продаж','4000237424','23.06.2027',1004.94,147,147726.18,'ICU'),
    ('22.01.2026','продаж','4000237424','23.06.2027',1028.75,70,71837.50,'ICU'),
    ('28.01.2026','продаж','4000230262','28.01.2026',1088.00,1,1088.00,'ICU'),
    ('12.02.2026','купівля','4000234215','24.06.2026',1024.05,15,15360.75,'SENSBANK'),
    ('12.02.2026','купівля','4000237424','23.06.2027',1030.25,57,58642.25,'ICU'),
    ('16.02.2026','купівля','4000235925','24.06.2026',1023.97,66,67582.02,'ICU')
]

objects = [B(*r) for r in rows]
stats, tot = calculate_profit_by_price(objects)
print('total_profit', tot)
for k, v in stats.items():
    if v['profit'] != 0:
        print(k, v['profit'])
