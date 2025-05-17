import os
import base64
import pickle
import requests
import datetime
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

app = Flask(__name__)
CORS(app)

# Stałe i zmienne środowiskowe
GOOGLE_TOKEN_B64 = os.getenv("GOOGLE_TOKEN_B64")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
LOCAL_ADDRESSES_SHEET_URL = os.getenv("LOCAL_ADDRESSES_SHEET_URL")
PRICE_SHEET_URL = os.getenv("PRICE_SHEET_URL")
BASE_ADDRESS = "Królowej Elżbiety 1A, 58-160 Świebodzice"
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Google Calendar API service

def get_calendar_service():
    token_bytes = base64.b64decode(GOOGLE_TOKEN_B64)
    creds = pickle.loads(token_bytes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('calendar', 'v3', credentials=creds)

# Pobierz dane lokalnych adresów z arkusza Google

def get_local_addresses():
    sheet_url = LOCAL_ADDRESSES_SHEET_URL
    sheet_csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
    df = pd.read_csv(sheet_csv_url)
    addresses = [
        f"{row['Ulica']} {row['Nr domu']}, {row['Miasto']}".strip()
        for _, row in df.iterrows()
    ]
    return set(addresses)

# Sprawdź typ lokalizacji i modyfikator na podstawie adresu

@app.route("/pricing/location-modifier")
def location_modifier():
    try:
        address = request.args.get("address")
        if not address:
            return jsonify({"error": "Brak adresu"}), 400

        local_addresses = get_local_addresses()
        if any(address.lower().startswith(local.lower()) for local in local_addresses):
            return jsonify({
                "location_type": "local_list",
                "modifier": 0.9,
                "distance_km": 0.0,
                "extra_fee": 0.0
            })

        # Odległość przez Google Distance Matrix
        maps_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": BASE_ADDRESS,
            "destinations": address,
            "key": GOOGLE_MAPS_API_KEY,
            "units": "metric",
        }
        response = requests.get(maps_url, params=params)
        data = response.json()

        if data['status'] != "OK" or not data['rows']:
            return jsonify({"error": "Nie udało się obliczyć odległości"}), 400

        distance_km = data['rows'][0]['elements'][0]['distance']['value'] / 1000.0

        if distance_km <= 20:
            modifier = 1.0
            location_type = "distance_local"
        else:
            modifier = 1.1
            location_type = "distance_far"

        extra_fee = round(distance_km * 2.0, 2)  # np. 2 zł/km

        return jsonify({
            "location_type": location_type,
            "modifier": modifier,
            "distance_km": round(distance_km, 2),
            "extra_fee": extra_fee
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Modyfikator KIEDY na podstawie daty

@app.route("/pricing/when-modifier")
def when_modifier():
    try:
        date_str = request.args.get("date")
        if not date_str:
            return jsonify({"error": "Brak daty"}), 400

        today = datetime.date.today()
        selected = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        delta = (selected - today).days

        if delta < 0:
            return jsonify({"error": "Data w przeszłości"}), 400
        elif delta == 0 or delta == 1:
            return jsonify({"type": "NATYCHMIASTOWA", "modifier": 1.5})
        elif 2 <= delta <= 6:
            return jsonify({"type": "PILNA", "modifier": 1.25})
        elif 7 <= delta <= 14:
            return jsonify({"type": "STANDARD", "modifier": 1.0})
        else:
            return jsonify({"type": "PLANOWA", "modifier": 0.90})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Cennik bazowy usług z arkusza Google

def get_service_sheet():
    sheet_url = SERVICES_SHEET_URL
    sheet_csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
    df = pd.read_csv(sheet_csv_url)
    return df

@app.route("/pricing/base-price")
def base_price():
    try:
        service_name = request.args.get("service")
        if not service_name:
            return jsonify({"error": "Brak nazwy usługi"}), 400

        df = get_service_sheet()
        row = df[df["Usługa"].str.lower() == service_name.lower()].squeeze()

        if row.empty:
            return jsonify({"error": "Nie znaleziono usługi"}), 404

        return jsonify({
            "service": service_name,
            "netto": float(row["Cena netto"]),
            "brutto_8": float(row["Brutto 8%"]),
            "brutto_23": float(row["Brutto 23%"]),
            "czas": int(row["czas"])
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return "✅ Pricing service is running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
