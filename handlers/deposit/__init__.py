from handlers.deposit.main_menu import router as menu_router
from handlers.deposit.add import router as add_router
from handlers.deposit.stubs import router as stubs_router

# Список роутерів для підключення в bot.py
routers = [menu_router, add_router, stubs_router]