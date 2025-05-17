import os
import pickle
import base64
import requests
import datetime
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

app = Flask(__name__)
CORS(app)

# Stałe i zmienne środowiskowe
BASE_ADDRESS = os.getenv("BASE_ADDRESS", "Królowej Elżbiety 1A, Świebodzice")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
GOOGLE_TOKEN_B64 = os.getenv("GOOGLE_TOKEN_B64")
GOOGLE_SERVICE_SHEET_URL = os.getenv("GOOGLE_SERVICE_SHEET_URL")
GOOGLE_LOCAL_SHEET_URL = os.getenv("GOOGLE_LOCAL_SHEET_URL")

# Funkcja do uzyskania danych lokalnych adresów

def get_local_addresses():
    sheet_url = GOOGLE_LOCAL_SHEET_URL
    if not sheet_url:
        return []
    csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
    df = pd.read_csv(csv_url)
    return [
        f"{row['Ulica']} {row['Nr domu']}, {row['Miasto']}".strip()
        for _, row in df.iterrows()
    ]

# Funkcja do obliczania odległości

def calculate_distance_km(origin, destination):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": GOOGLE_MAPS_API_KEY
    }
    response = requests.get(url, params=params).json()
    try:
        distance_meters = response['rows'][0]['elements'][0]['distance']['value']
        return round(distance_meters / 1000, 2)
    except:
        return None

# Endpoint: Modyfikator lokalizacji
@app.route("/pricing/location-modifier")
def location_modifier():
    address = request.args.get("address")
    if not address:
        return jsonify({"error": "Brak adresu"}), 400

    local_addresses = get_local_addresses()
    if any(address.lower() in a.lower() for a in local_addresses):
        return jsonify({
            "location_type": "local_list",
            "modifier": 0.9,
            "distance_km": 0.0,
            "extra_fee": 0.0
        })

    distance = calculate_distance_km(BASE_ADDRESS, address)
    if distance is None:
        return jsonify({"error": "Nie udało się obliczyć odległości"}), 500

    if distance <= 20:
        extra_fee = round(distance * 2, 2)  # 2 zł za km
        modifier = 1.0
        loc_type = "distance_local"
    else:
        extra_fee = round(distance * 2, 2)
        modifier = 1.1
        loc_type = "distance_far"

    return jsonify({
        "location_type": loc_type,
        "modifier": modifier,
        "distance_km": distance,
        "extra_fee": extra_fee
    })

# Funkcja do obsługi kalendarza Google
def get_calendar_service():
    token_bytes = base64.b64decode(GOOGLE_TOKEN_B64)
    creds = pickle.loads(token_bytes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)

# Endpoint: Modyfikator daty (KIEDY)
@app.route("/pricing/when-modifier")
def when_modifier():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Brak daty"}), 400

    try:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.date.today()
        delta_days = (target_date - today).days

        if delta_days < 0:
            return jsonify({"error": "Data z przeszłości"}), 400
        elif delta_days == 0 or delta_days == 1:
            return jsonify({"type": "NATYCHMIASTOWA", "modifier": 2.0})
        elif 2 <= delta_days <= 6:
            return jsonify({"type": "PILNA", "modifier": 1.5})
        elif 7 <= delta_days <= 14:
            return jsonify({"type": "STANDARD", "modifier": 1.0})
        else:
            return jsonify({"type": "PLANOWA", "modifier": 0.95})
    except ValueError:
        return jsonify({"error": "Błędny format daty"}), 400

# Endpoint: Dane usługi
@app.route("/pricing/service")
def get_service():
    name = request.args.get("name")
    if not name:
        return jsonify({"error": "Brak nazwy usługi"}), 400

    sheet_url = GOOGLE_SERVICE_SHEET_URL
    if not sheet_url:
        return jsonify({"error": "Brak URL arkusza"}), 500

    csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
    df = pd.read_csv(csv_url)

    match = df[df['Usługa'].str.lower() == name.lower()]
    if match.empty:
        return jsonify({"error": "Nie znaleziono usługi"}), 404

    row = match.iloc[0]
    return jsonify({
        "netto": row['Cena netto'],
        "brutto_8": row['Brutto 8%'],
        "brutto_23": row['Brutto 23%'],
        "czas": row['czas']
    })

@app.route("/")
def index():
    return "✅ Pricing service is running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
