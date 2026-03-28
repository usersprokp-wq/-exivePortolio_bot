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