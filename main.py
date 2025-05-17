import os
import pandas as pd
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib.parse import unquote

app = Flask(__name__)
CORS(app)

# Stała lokalizacja punktu odniesienia
BASE_ADDRESS = "Królowej Elżbiety 1A, 58-160 Świebodzice"

# Zmienna środowiskowa z linkiem do arkusza Google
LOCAL_ADDRESSES_SHEET_URL = os.getenv("LOCAL_ADDRESSES_SHEET_URL")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Koszt za 1 km (w PLN)
PER_KM_FEE = 2.0

# Modyfikatory
MODIFIER_LOCAL_LIST = 0.9  # -10%
MODIFIER_FAR = 1.1          # +10%

@app.route("/")
def index():
    return "✅ Pricing service is running"

def get_local_addresses():
    if not LOCAL_ADDRESSES_SHEET_URL:
        return []
    try:
        sheet_csv_url = LOCAL_ADDRESSES_SHEET_URL.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
        df = pd.read_csv(sheet_csv_url)
        addresses = [
            f"{row['Ulica']} {row['Nr domu']}, {row['Miasto']}, {row['Kod pocztowy']}, {row['Województwo']}, {row['Kraj']}"
            for _, row in df.iterrows()
        ]
        return addresses
    except Exception as e:
        print("Błąd przy pobieraniu lokalnych adresów:", str(e))
        return []

def calculate_distance_km(origin, destination):
    url = (
        f"https://maps.googleapis.com/maps/api/distancematrix/json"
        f"?origins={origin}&destinations={destination}"
        f"&key={GOOGLE_MAPS_API_KEY}&units=metric"
    )
    response = requests.get(url)
    data = response.json()
    try:
        distance_meters = data["rows"][0]["elements"][0]["distance"]["value"]
        return round(distance_meters / 1000.0, 2)
    except Exception as e:
        print("Błąd przy obliczaniu odległości:", str(e))
        return None

@app.route("/pricing/location-modifier")
def location_modifier():
    raw_address = request.args.get("address")
    if not raw_address:
        return jsonify({"error": "Brak adresu"}), 400

    address = unquote(raw_address)
    local_addresses = get_local_addresses()

    if address in local_addresses:
        return jsonify({
            "location_type": "local_list",
            "modifier": MODIFIER_LOCAL_LIST,
            "distance_km": 0.0,
            "extra_fee": 0.0
        })

    distance_km = calculate_distance_km(BASE_ADDRESS, address)
    if distance_km is None:
        return jsonify({"error": "Nie udało się obliczyć odległości"}), 500

    if distance_km <= 20:
        return jsonify({
            "location_type": "distance_local",
            "modifier": 1.0,
            "distance_km": distance_km,
            "extra_fee": round(distance_km * PER_KM_FEE, 2)
        })
    else:
        return jsonify({
            "location_type": "distance_far",
            "modifier": MODIFIER_FAR,
            "distance_km": distance_km,
            "extra_fee": round(distance_km * PER_KM_FEE, 2)
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
