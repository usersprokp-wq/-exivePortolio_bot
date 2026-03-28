import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import logging

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    def __init__(self):
        self.client = None
        self.sheet = None
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
            self.sheet = self.client.open(spreadsheet_name).sheet1
            logger.info("Connected to Google Sheets")
        except Exception as e:
            logger.error(f"Error connecting to Google Sheets: {e}")
            raise
    
    def export_bonds_to_sheets(self, bonds_data):
        try:
            self.sheet.clear()
            
            if not bonds_data:
                return
            
            headers = ['Дата', 'Тип операції', 'Номер ОВДП', 'Термін до', 
                      'Ціна за шт', 'Кількість', 'Сума', 'Платформа']
            self.sheet.append_row(headers)
            
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
                self.sheet.append_row(row)
            
            logger.info(f"Exported {len(bonds_data)} bonds to Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Error exporting to sheets: {e}")
            raise