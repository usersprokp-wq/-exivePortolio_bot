import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import logging

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.connect()
    
    def connect(self):
        try:
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            if not creds_json:
                raise ValueError("GOOGLE_CREDENTIALS not found")
            
            creds_dict = json.loads(creds_json)
            scope = ['https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive']
            
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            self.client = gspread.authorize(creds)
            
            spreadsheet_name = os.getenv('SPREADSHEET_NAME', 'Telegram Bot Data')
            self.spreadsheet = self.client.open(spreadsheet_name)
            logger.info("Connected to Google Sheets")
        except Exception as e:
            logger.error(f"Error connecting to Google Sheets: {e}")
            raise
    
    def get_or_create_worksheet(self, sheet_name):
        """Отримати або створити вкладку"""
        try:
            # Спробуємо знайти вкладку
            worksheet = self.spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Якщо не знайдено - створити нову
            worksheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
            logger.info(f"Created new worksheet: {sheet_name}")
        return worksheet
    
    def export_bonds_to_sheets(self, bonds_data):
        """Експортує дані ОВДП в Google Sheets (вкладка ОВДП-Записи)"""
        try:
            worksheet = self.get_or_create_worksheet("ОВДП-Записи")
            worksheet.clear()
            
            if not bonds_data:
                return
            
            headers = ['Дата', 'Тип операції', 'Номер ОВДП', 'Термін до', 
                      'Ціна за шт', 'Кількість', 'Сума', 'Платформа']
            worksheet.append_row(headers)
            
            for bond in bonds_data:
                row = [
                    bond.get('date', ''),
                    bond.get('operation_type', ''),
                    bond.get('bond_number', ''),
                    bond.get('maturity_date', ''),
                    bond.get('price_per_unit', ''),
                    bond.get('quantity', ''),
                    bond.get('total_amount', ''),
                    bond.get('platform', '')
                ]
                worksheet.append_row(row)
            
            logger.info(f"Exported {len(bonds_data)} bonds to worksheet 'ОВДП-Записи'")
            return True
        except Exception as e:
            logger.error(f"Error exporting to sheets: {e}")
            raise
    
    def export_bonds_portfolio(self, portfolio_data):
        """Експортує портфель ОВДП в Google Sheets (вкладка ОВДП-Портфель)"""
        try:
            worksheet = self.get_or_create_worksheet("ОВДП-Портфель")
            worksheet.clear()
            
            if not portfolio_data:
                return
            
            headers = ['Номер ОВДП', 'Термін до', 'Кількість', 'Середня ціна', 'Сума']
            worksheet.append_row(headers)
            
            for item in portfolio_data:
                row = [
                    item.get('bond_number', ''),
                    item.get('maturity_date', ''),
                    item.get('total_quantity', 0),
                    item.get('avg_price', 0),
                    item.get('total_amount', 0)
                ]
                worksheet.append_row(row)
            
            logger.info(f"Exported portfolio to worksheet 'ОВДП-Портфель'")
            return True
        except Exception as e:
            logger.error(f"Error exporting portfolio to sheets: {e}")
            raise
    
    def export_profit_to_sheets(self, profit_data):
        """Експортує дані про прибуток в Google Sheets (вкладка ОВДП-Прибуток)"""
        try:
            worksheet = self.get_or_create_worksheet("ОВДП-Прибуток")
            worksheet.clear()
            
            if not profit_data:
                return
            
            headers = ['Дата операції', 'Тип операції', 'Сума операції', 
                      'Реалізований прибуток', 'Нереалізований прибуток']
            worksheet.append_row(headers)
            
            for record in profit_data:
                row = [
                    record.get('operation_date', ''),
                    record.get('operation_type', ''),
                    record.get('amount', ''),
                    record.get('realized_profit', ''),
                    record.get('unrealized_profit', '')
                ]
                worksheet.append_row(row)
            
            logger.info(f"Exported profit data to worksheet 'ОВДП-Прибуток'")
            return True
        except Exception as e:
            logger.error(f"Error exporting profit to sheets: {e}")
            raise
    
    def import_bonds_from_sheets(self):
        """Імпортує дані ОВДП з Google Sheets (вкладка ОВДП-Записи)"""
        try:
            worksheet = self.get_or_create_worksheet("ОВДП-Записи")
            all_rows = worksheet.get_all_values()
            
            logger.info(f"DEBUG: all_rows count = {len(all_rows)}")
            
            if not all_rows or len(all_rows) < 2:
                logger.warning(f"No data in ОВДП-Записи sheet. Rows: {len(all_rows) if all_rows else 0}")
                return []
            
            # Перший рядок - заголовки
            headers = all_rows[0]
            logger.info(f"DEBUG: headers = {headers}")
            bonds_data = []
            
            # Обробляємо дані з рядків 1+ (пропускаємо заголовок)
            for idx, row in enumerate(all_rows[1:]):
                if not any(row):  # Пропускаємо порожні рядки
                    logger.debug(f"Skipping empty row {idx}")
                    continue
                
                # Мапимо рядок на словник за заголовками
                try:
                    bond_dict = {
                        'date': row[0] if len(row) > 0 else '',
                        'operation_type': row[1] if len(row) > 1 else '',
                        'bond_number': row[2] if len(row) > 2 else '',
                        'maturity_date': row[3] if len(row) > 3 else '',
                        'price_per_unit': float(row[4].replace(',', '.')) if len(row) > 4 and row[4] else 0,
                        'quantity': int(row[5]) if len(row) > 5 and row[5] else 0,
                        'total_amount': float(row[6].replace(',', '.')) if len(row) > 6 and row[6] else 0,
                        'platform': row[7] if len(row) > 7 else ''
                    }
                    bonds_data.append(bond_dict)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing row {idx}: {e}, row={row}")
                    continue
            
            logger.info(f"Imported {len(bonds_data)} bonds from worksheet 'ОВДП-Записи'")
            return bonds_data
        except Exception as e:
            logger.error(f"Error importing from sheets: {e}")
            raise