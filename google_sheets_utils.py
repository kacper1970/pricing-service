import os
import base64
import pickle
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Ścieżka do poświadczeń serwisowego konta Google (base64 w Renderze)
SERVICE_ACCOUNT_INFO = os.getenv("GOOGLE_SHEETS_CREDENTIALS_B64")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")


def get_sheets_service():
    if not SERVICE_ACCOUNT_INFO:
        raise Exception("Brak danych poświadczeń do Google Sheets")

    info_json = base64.b64decode(SERVICE_ACCOUNT_INFO).decode("utf-8")
    creds = Credentials.from_service_account_info(
        eval(info_json), scopes=SCOPES
    )
    return build('sheets', 'v4', credentials=creds)


def read_sheet(range_name):
    service = get_sheets_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
    return result.get('values', [])
