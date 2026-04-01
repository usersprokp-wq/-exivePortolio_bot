# Структура модуля ОВДП

## 📁 Структура файлів

```
ovdp/
├── __init__.py              # Експорт всіх функцій
├── main_menu.py             # 📈 Головне меню ОВДП
├── add_operations.py        # ➕ Додавання операцій (купівля/продаж + календар)
├── list_operations.py       # 📋 Список всіх операцій
├── portfolio.py             # 💼 Перегляд портфеля (ICU/SENSBANK)
├── profit.py                # 💰 Прибутки та списання
├── pnl.py                   # 💹 PnL портфеля з live цінами
├── statistics.py            # 📊 Статистика
├── sync.py                  # 🔄 Синхронізація з Google Sheets (TODO)
├── balance.py               # 💵 Оновлення залишків (TODO)
└── utils/
    ├── __init__.py          # Експорт утиліт
    ├── helpers.py           # Допоміжні функції (parse_date, форматування)
    ├── parsers.py           # Парсинг цін (fetch_bond_price_icu)
    └── calculations.py      # Розрахунки (FIFO, прибутки, портфель)
```

## 🔄 Як використовувати

### Імпорт в основному боті:

```python
from ovdp import (
    show_ovdp_menu,
    start_bond_add,
    show_bonds_list,
    show_portfolio,
    show_profit,
    show_pnl_portfolio,
    show_statistics
)
```

### Реєстрація обробників:

```python
# Головне меню
application.add_handler(CallbackQueryHandler(show_ovdp_menu, pattern='^ovdp$'))

# Додавання операцій
application.add_handler(CallbackQueryHandler(start_bond_add, pattern='^ovdp_add$'))
application.add_handler(CallbackQueryHandler(handle_date_selection, pattern='^date_'))

# Список
application.add_handler(CallbackQueryHandler(lambda u, c: show_bonds_list(u, c, 1), pattern='^ovdp_list$'))

# Портфель
application.add_handler(CallbackQueryHandler(lambda u, c: show_portfolio(u, c), pattern='^ovdp_portfolio$'))
application.add_handler(CallbackQueryHandler(lambda u, c: show_portfolio(u, c, 'ICU'), pattern='^portfolio_icu$'))

# Прибутки
application.add_handler(CallbackQueryHandler(show_profit, pattern='^ovdp_profit$'))

# PnL
application.add_handler(CallbackQueryHandler(show_pnl_portfolio, pattern='^pnl_portfolio$'))

# Статистика
application.add_handler(CallbackQueryHandler(show_statistics, pattern='^ovdp_stats$'))
```

## ⚠️ TODO - Функції які потрібно додати

В `add_operations.py` потрібно додати з оригінального файлу:
- `handle_sell_bond_selected()` - обробка вибору облігації для продажу
- `handle_message_ovdp()` - обробка всіх текстових повідомлень (номер, кількість, ціна)
- `save_bond_sell()` - збереження продажу
- `save_bond_buy()` - збереження купівлі

В `sync.py` потрібно створити:
- `sync_bonds_from_sheets()` - синхронізація з Google Sheets
- `recalculate_bond_percents()` - перерахунок відсотків портфеля

В `balance.py` потрібно створити:
- `handle_balance_update()` - оновлення залишків на рахунках

## 📊 Переваги нової структури

1. **Читабельність** - кожен файл відповідає за одну функцію меню
2. **Легше підтримувати** - зміни в одному розділі не впливають на інші
3. **Легше знайти код** - зрозуміла назва файлу = зрозуміло що там
4. **Модульність** - можна легко додавати нові функції
5. **Менше конфліктів** - при роботі в команді менше конфліктів у git

## 🔢 Порівняння розміру

- **Оригінал**: 1 файл × 1763 рядки = 1763 рядки
- **Нова структура**: ~10 файлів × 50-200 рядків = зручніше читати

## 🚀 Наступні кроки

1. Скопіювати решту функцій з оригінального файлу в відповідні модулі
2. Протестувати всі обробники
3. Додати синхронізацію з Google Sheets
4. Опціонально: додати тести для кожного модуля
