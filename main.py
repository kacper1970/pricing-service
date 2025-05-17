import os
import datetime
import base64
import pickle
from flask import Flask, request, jsonify
from flask_cors import CORS
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

app = Flask(__name__)
CORS(app)

# Pobranie zmiennych 
token_b64 = os.getenv("GOOGLE_TOKEN_B64")
calendar_id = os.getenv("GOOGLE_CALENDAR_ID")

# Konfiguracja dostępu do Google Calendar
def get_calendar_service():
    if not token_b64:
        raise Exception("Brak tokena. Skonfiguruj GOOGLE_TOKEN_B64")
    token_bytes = base64.b64decode(token_b64)
    creds = pickle.loads(token_bytes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('calendar', 'v3', credentials=creds)

# Funkcja do określenia typu wizyty i modyfikatora
def calculate_when_modifier(target_date: str):
    today = datetime.datetime.utcnow().date()
    visit_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    delta = (visit_date - today).days

    if delta < 0:
        return {"error": "Data nie może być w przeszłości."}
    elif delta == 0 or delta == 1:
        return {"type": "NATYCHMIASTOWA", "modifier": 2.0}  # +100%
    elif 2 <= delta <= 6:
        return {"type": "PILNA", "modifier": 1.5}  # +50%
    elif 7 <= delta <= 14:
        return {"type": "STANDARD", "modifier": 1.0}  # 0%
    else:
        return {"type": "PLANOWA", "modifier": 0.9}  # -10%

@app.route("/pricing/when-modifier")
def when_modifier():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Brak parametru 'date'"}), 400
    try:
        result = calculate_when_modifier(date_str)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    return "✅ Pricing service is running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
