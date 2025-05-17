import os
import csv
import io
import pickle
import base64
import requests
import googlemaps
import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

app = Flask(__name__)
CORS(app)

# Ustawienia środowiskowe
token_b64 = os.getenv("GOOGLE_TOKEN_B64")
calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
google_sheets_url = os.getenv("LOCAL_ADDRESS_SHEET")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

BASE_ADDRESS = "Królowej Elżbiety 1A, Świebodzice"
COST_PER_KM = 2  # przykładowa stawka za km poza lokalnym obszarem

gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)


@app.route("/")
def home():
    return "✅ Pricing service is running"


def get_distance_km(from_address, to_address):
    try:
        result = gmaps.distance_matrix(origins=[from_address], destinations=[to_address], mode="driving")
        distance_meters = result["rows"][0]["elements"][0]["distance"]["value"]
        return distance_meters / 1000  # w km
    except Exception as e:
        print("Błąd Google Maps:", e)
        return None


def is_local_address(client_address):
    try:
        sheet_csv_url = google_sheets_url.replace("/edit?usp=sharing", "/export?format=csv")
        response = requests.get(sheet_csv_url)
        response.encoding = 'utf-8'
        f = io.StringIO(response.text)
        reader = csv.DictReader(f)
        for row in reader:
            address_str = f"{row['Ulica']} {row['nr. Domu']}, {row['Miasto']}"
            if address_str.strip().lower() == client_address.strip().lower():
                return True
    except Exception as e:
        print("Błąd podczas sprawdzania adresu lokalnego:", e)
    return False


@app.route("/check-location", methods=[POST])
def check_location():
    data = request.get_json()
    ulica = data.get("ulica")
    nr_domu = data.get("nr_domu")
    miasto = data.get("miasto")

    if not (ulica and nr_domu and miasto):
        return jsonify({"error": "Brak danych adresowych"}), 400

    full_address = f"{ulica} {nr_domu}, {miasto}"

    if is_local_address(full_address):
        return jsonify({"type": "lokalny", "modifier": 1.0, "travel_cost": 0})

    distance = get_distance_km(BASE_ADDRESS, full_address)
    if distance is None:
        return jsonify({"type": "unknown", "modifier": 1.0, "travel_cost": 0})

    if distance <= 20:
        return jsonify({"type": "dojazd <=20km", "modifier": 1.0, "travel_cost": round(distance * COST_PER_KM, 2)})
    else:
        return jsonify({"type": "dojazd >20km", "modifier": 1.1, "travel_cost": round(distance * COST_PER_KM, 2)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
