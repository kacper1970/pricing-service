import os
import requests
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib.parse import quote

app = Flask(__name__)
CORS(app)

# Zmienne środowiskowe
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1PsEyAImKrre__68L5NYMQzd_z2kM_NooAwYhAK7Vgek/export?format=csv"
BASE_ADDRESS = os.getenv("BASE_ADDRESS", "Królowej Elżbiety 1A, 58-160 Świebodzice")
PRICE_PER_KM = float(os.getenv("PRICE_PER_KM", 2.0))


# Funkcja do pobrania listy lokalnych adresów
def get_local_addresses():
    sheet_url = os.getenv("GOOGLE_SHEET_URL")
    sheet_csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")

    df = pd.read_csv(sheet_csv_url)

    addresses = [
        f"{row['Ulica'].strip()} {row['Nr domu']}, {row['Miasto'].strip()}".strip()
        for _, row in df.iterrows()
    ]
    return addresses



# Funkcja do obliczenia odległości z Google Distance Matrix API
def calculate_distance_km(origin, destination):
    endpoint = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": GOOGLE_MAPS_API_KEY,
        "units": "metric"
    }
    response = requests.get(endpoint, params=params)
    data = response.json()
    try:
        distance_meters = data["rows"][0]["elements"][0]["distance"]["value"]
        return distance_meters / 1000.0
    except Exception:
        return None


@app.route("/")
def home():
    return "✅ Pricing service is running"


@app.route("/pricing/location-modifier")
def location_modifier():
    address = request.args.get("address")
    if not address:
        return jsonify({"error": "Brak adresu"}), 400

    # Sprawdzenie czy adres jest lokalny
    local_addresses = get_local_addresses()
    normalized_address = address.strip().lower()
    is_local = any(normalized_address.startswith(local.strip().lower()) for local in local_addresses)

    if is_local:
        return jsonify({
            "location_type": "local_list",
            "modifier": 0.9,  # -10% znaczy mnożenie przez 0.9
            "extra_fee": 0.0,
            "distance_km": 0.0
        })

    # Jeśli nie lokalny, oblicz odległość
    distance_km = calculate_distance_km(BASE_ADDRESS, address)
    if distance_km is None:
        return jsonify({"error": "Nie udało się obliczyć odległości"}), 500

    # Ustal modyfikator i opłatę
    if distance_km <= 20:
        modifier = 1.0
        extra_fee = PRICE_PER_KM * distance_km
        location_type = "distance_local"
    else:
        modifier = 1.1  # +10%
        extra_fee = PRICE_PER_KM * distance_km
        location_type = "distance_far"

    return jsonify({
        "location_type": location_type,
        "modifier": modifier,
        "extra_fee": round(extra_fee, 2),
        "distance_km": round(distance_km, 2)
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
