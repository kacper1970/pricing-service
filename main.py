import os
import requests
import base64
import pickle
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from urllib.parse import urlencode

app = Flask(__name__)
CORS(app)

# Stałe środowiskowe
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
BASE_ADDRESS = os.getenv("BASE_ADDRESS", "Królowej Elżbiety 1A, 58-160 Świebodzice")
KILOMETER_PRICE = float(os.getenv("KILOMETER_PRICE", 3.00))
KILOMETER_THRESHOLD_KM = float(os.getenv("KILOMETER_THRESHOLD_KM", 20))
LOCAL_RADIUS_KM = float(os.getenv("LOCAL_RADIUS_KM", 3))

# Funkcja pobierająca listę lokalnych adresów z Google Sheets
def fetch_local_addresses():
    try:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv"
        response = requests.get(sheet_url)
        response.encoding = 'utf-8'
        lines = response.text.splitlines()[1:]  # Pomijamy nagłówek
        addresses = []
        for line in lines:
            parts = line.split(',')
            if len(parts) >= 3:
                street = parts[0].strip()
                house = parts[1].strip()
                city = parts[2].strip()
                full_address = f"{street} {house}, {city}"
                addresses.append(full_address.lower())
        return addresses
    except Exception as e:
        return []

# Funkcja obliczająca odległość w km między dwoma adresami

def get_distance_km(origin, destination):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": GOOGLE_MAPS_API_KEY,
        "units": "metric",
    }
    response = requests.get(url, params=params)
    data = response.json()
    try:
        distance_meters = data["rows"][0]["elements"][0]["distance"]["value"]
        return distance_meters / 1000  # Konwersja na km
    except Exception:
        return None

# Endpoint do sprawdzenia modyfikatora "GDZIE"
@app.route("/pricing/location-modifier")
def location_modifier():
    client_address = request.args.get("address")
    if not client_address:
        return jsonify({"error": "Brak adresu"}), 400

    local_addresses = fetch_local_addresses()
    is_local = client_address.lower() in local_addresses

    if is_local:
        return jsonify({
            "location_type": "local",
            "modifier": 1.0,
            "extra_fee": 0
        })

    # Sprawdzenie odległości z Google Maps API
    distance_km = get_distance_km(BASE_ADDRESS, client_address)
    if distance_km is None:
        return jsonify({"error": "Nie udało się obliczyć odległości"}), 500

    if distance_km <= KILOMETER_THRESHOLD_KM:
        return jsonify({
            "location_type": "distance_local",
            "modifier": 1.0,
            "extra_fee": round(distance_km * KILOMETER_PRICE, 2),
            "distance_km": round(distance_km, 2)
        })
    else:
        return jsonify({
            "location_type": "distant",
            "modifier": 1.10,
            "extra_fee": round(distance_km * KILOMETER_PRICE, 2),
            "distance_km": round(distance_km, 2)
        })

@app.route("/")
def home():
    return "✅ Pricing Service działa poprawnie"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
