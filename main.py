import os
import base64
import pickle
import requests
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from urllib.parse import quote_plus

app = Flask(__name__)
CORS(app)

# Wczytaj token OAuth z BASE64
TOKEN_B64 = os.getenv("GOOGLE_TOKEN_B64")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
SHEET_CSV_URL = os.getenv("LOCAL_ADDRESS_SHEET_CSV")
BASE_ADDRESS = os.getenv("BASE_ADDRESS", "Królowej Elżbiety 1A, Świebodzice")

# Koszt dojazdu za km (poza lokalną strefą)
KM_COST = float(os.getenv("KM_COST", "2.00"))


def normalize_address(address):
    """Uproszczony adres do dopasowania"""
    return (
        address.replace(",", " ")
        .replace(".", " ")
        .replace("-", " ")
        .lower()
        .strip()
    )


def load_local_addresses():
    try:
        df = pd.read_csv(SHEET_CSV_URL)
        df = df.fillna("")
        df["pełny_adres"] = (
            df["Ulica"].str.strip()
            + " " + df["nr. Domu"].astype(str).str.strip()
            + ", " + df["Miasto"].str.strip()
            + ", " + df["Kod pocztowy"].str.strip()
            + ", " + df["Województwo"].str.strip()
            + ", " + df["Kraj"].str.strip()
        )
        df["adres_norm"] = df["pełny_adres"].apply(normalize_address)
        return set(df["adres_norm"].values)
    except Exception as e:
        print(f"Błąd wczytywania adresów lokalnych: {e}")
        return set()


LOCAL_ADDRESSES = load_local_addresses()


def get_distance_km(origin, destination):
    try:
        endpoint = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": origin,
            "destinations": destination,
            "key": GOOGLE_MAPS_API_KEY,
            "units": "metric",
        }
        response = requests.get(endpoint, params=params)
        data = response.json()
        element = data["rows"][0]["elements"][0]
        if element["status"] == "OK":
            distance_km = element["distance"]["value"] / 1000
            return distance_km
        else:
            return None
    except Exception as e:
        print("Błąd Distance Matrix:", e)
        return None


@app.route("/")
def home():
    return "✅ Pricing service is running"


@app.route("/pricing/location-modifier")
def location_modifier():
    address = request.args.get("address")
    if not address:
        return jsonify({"error": "Brak adresu"}), 400

    norm = normalize_address(address)
    if norm in LOCAL_ADDRESSES:
        return jsonify({
            "location_type": "local_match",
            "modifier": 0.9,  # -10%
            "distance_km": 0.0,
            "extra_fee": 0.0
        })

    distance_km = get_distance_km(BASE_ADDRESS, address)
    if distance_km is None:
        return jsonify({"error": "Nie udało się obliczyć odległości"}), 500

    if distance_km <= 20:
        modifier = 1.0
        extra_fee = round(distance_km * KM_COST, 2)
        location_type = "distance_local"
    else:
        modifier = 1.10  # +10%
        extra_fee = round(distance_km * KM_COST, 2)
        location_type = "distance_far"

    return jsonify({
        "location_type": location_type,
        "modifier": modifier,
        "distance_km": round(distance_km, 2),
        "extra_fee": extra_fee
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
