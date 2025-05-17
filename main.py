import os
import datetime
import pandas as pd
import requests
import base64
import pickle
from flask import Flask, request, jsonify
from flask_cors import CORS
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

app = Flask(__name__)
CORS(app)

# Stała lokalizacja bazowa
BASE_ADDRESS = os.getenv("BASE_ADDRESS", "Królowej Elżbiety 1A, 58-160 Świebodzice")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
LOCAL_ADDRESSES_SHEET_URL = os.getenv("LOCAL_ADDRESSES_SHEET_URL")
SERVICES_SHEET_URL = os.getenv("SERVICES_SHEET_URL")
GOOGLE_TOKEN_B64 = os.getenv("GOOGLE_TOKEN_B64")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

@app.route("/")
def home():
    return "✅ Pricing Service is running"

def get_distance_km(origin, destination):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": GOOGLE_MAPS_API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    try:
        distance_meters = data["rows"][0]["elements"][0]["distance"]["value"]
        return round(distance_meters / 1000, 2)
    except:
        return None

def get_local_addresses():
    sheet_url = LOCAL_ADDRESSES_SHEET_URL
    if not sheet_url:
        return []
    csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
    df = pd.read_csv(csv_url)
    addresses = [
        f"{row['Ulica']} {row['Nr domu']}, {row['Miasto']}, {row['Kod pocztowy']}, {row['Województwo']}, {row['Kraj']}"
        for _, row in df.iterrows()
    ]
    return addresses

@app.route("/pricing/location-modifier")
def location_modifier():
    address = request.args.get("address")
    if not address:
        return jsonify({"error": "Brak adresu"}), 400

    local_list = get_local_addresses()
    if address.strip() in [a.strip() for a in local_list]:
        return jsonify({
            "location_type": "local_list",
            "modifier": 0.9,
            "distance_km": 0.0,
            "extra_fee": 0.0
        })

    distance = get_distance_km(BASE_ADDRESS, address)
    if distance is None:
        return jsonify({"error": "Nie udało się obliczyć odległości"})

    if distance <= 20:
        return jsonify({
            "location_type": "distance_local",
            "modifier": 1.0,
            "distance_km": distance,
            "extra_fee": round(distance * 2, 2)
        })
    else:
        return jsonify({
            "location_type": "distance_far",
            "modifier": 1.1,
            "distance_km": distance,
            "extra_fee": round(distance * 2, 2)
        })

@app.route("/pricing/when-modifier")
def when_modifier():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Brak daty"}), 400
    try:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Niepoprawny format daty"}), 400

    today = datetime.date.today()
    delta_days = (target_date - today).days

    if delta_days < 0:
        return jsonify({"error": "Data z przeszłości"}), 400
    elif delta_days <= 1:
        return jsonify({"type": "NATYCHMIASTOWA", "modifier": 1.5})
    elif 2 <= delta_days <= 6:
        return jsonify({"type": "PILNA", "modifier": 1.25})
    elif 7 <= delta_days <= 14:
        return jsonify({"type": "STANDARD", "modifier": 1.0})
    else:
        return jsonify({"type": "PLANOWA", "modifier": 0.9})

def get_services_table():
    csv_url = SERVICES_SHEET_URL.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
    df = pd.read_csv(csv_url)
    return df

@app.route("/pricing/base-price")
def base_price():
    service_name = request.args.get("service")
    if not service_name:
        return jsonify({"error": "Brak nazwy usługi"}), 400

    try:
        df = get_services_table()
        service_row = df[df["Usługa"].str.lower() == service_name.lower()]
        if service_row.empty:
            return jsonify({"error": "Nie znaleziono usługi"}), 404

        row = service_row.iloc[0]
        return jsonify({
            "service": row["Usługa"],
            "netto": row["Cena netto"],
            "brutto_8": row["Brutto 8%"],
            "brutto_23": row["Brutto 23%"],
            "time": row["czas"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
