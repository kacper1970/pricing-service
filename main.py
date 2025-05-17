import os
import json
import datetime
import pandas as pd
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib.parse import quote

app = Flask(__name__)
CORS(app)

# GOOGLE ENV VARS
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

# GOOGLE SHEETS LINKS
ADDRESS_SHEET_URL = os.getenv("ADDRESS_SHEET_URL")
SERVICES_SHEET_URL = os.getenv("SERVICES_SHEET_URL")

# ADRES BAZOWY
BASE_ADDRESS = os.getenv("BASE_ADDRESS", "Królowej Elżbiety 1A, 58-160 Świebodzice")
BASE_FEE_KM = float(os.getenv("BASE_FEE_KM", "2.0"))
FAR_THRESHOLD_KM = float(os.getenv("FAR_THRESHOLD_KM", "20.0"))
FAR_MODIFIER = float(os.getenv("FAR_MODIFIER", "1.1"))
LOCAL_MODIFIER = float(os.getenv("LOCAL_MODIFIER", "0.9"))

@app.route("/")
def index():
    return "✅ Pricing Service działa"

# -------------------- GDZIE --------------------

def get_local_addresses():
    sheet_url = ADDRESS_SHEET_URL
    sheet_csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
    df = pd.read_csv(sheet_csv_url)

    addresses = [
        f"{row['Ulica']} {row['Nr domu']}, {row['Miasto']}".strip()
        for _, row in df.iterrows()
    ]
    return addresses

def calculate_distance_km(origin, destination):
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": GOOGLE_MAPS_API_KEY,
        "language": "pl"
    }
    response = requests.get(url, params=params).json()
    try:
        meters = response["rows"][0]["elements"][0]["distance"]["value"]
        return round(meters / 1000.0, 2)
    except Exception:
        return None

@app.route("/pricing/location-modifier")
def location_modifier():
    address = request.args.get("address")
    if not address:
        return jsonify({"error": "Brak adresu"}), 400

    try:
        local_addresses = get_local_addresses()
        if any(address.lower() in a.lower() for a in local_addresses):
            return jsonify({
                "location_type": "local_list",
                "modifier": LOCAL_MODIFIER,
                "extra_fee": 0.0,
                "distance_km": 0.0
            })

        distance = calculate_distance_km(BASE_ADDRESS, address)
        if distance is None:
            return jsonify({"error": "Nie udało się obliczyć odległości"}), 500

        if distance <= FAR_THRESHOLD_KM:
            return jsonify({
                "location_type": "distance_local",
                "modifier": 1.0,
                "extra_fee": round(distance * BASE_FEE_KM, 2),
                "distance_km": distance
            })
        else:
            return jsonify({
                "location_type": "distance_far",
                "modifier": FAR_MODIFIER,
                "extra_fee": round(distance * BASE_FEE_KM, 2),
                "distance_km": distance
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- KIEDY --------------------

@app.route("/pricing/when-modifier")
def when_modifier():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Brak daty"}), 400

    try:
        today = datetime.date.today()
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        delta = (target_date - today).days

        if delta < 0:
            return jsonify({"error": "Data z przeszłości"}), 400
        elif delta <= 1:
            return jsonify({"type": "NATYCHMIASTOWA", "modifier": 1.5})
        elif 2 <= delta <= 6:
            return jsonify({"type": "PILNA", "modifier": 1.25})
        elif 7 <= delta <= 14:
            return jsonify({"type": "STANDARD", "modifier": 1.0})
        else:
            return jsonify({"type": "PLANOWA", "modifier": 0.9})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- BASE PRICE --------------------

@app.route("/pricing/base-price")
def base_price():
    service_name = request.args.get("service")
    if not service_name:
        return jsonify({"error": "Brak nazwy usługi"}), 400

    try:
        sheet_url = SERVICES_SHEET_URL
        csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
        df = pd.read_csv(csv_url)

        row = df[df["Usługa"] == service_name].iloc[0]

        result = {
            "service": row["Usługa"],
            "netto": float(str(row["Cena netto"]).replace(",", ".")),
            "brutto_8": float(str(row["Brutto 8%"]).replace(",", ".")),
            "brutto_23": float(str(row["Brutto 23%"]).replace(",", ".")),
            "czas": str(row["czas"])
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------- SLOT MODIFIER --------------------

from datetime import datetime as dt
import pytz

@app.route("/pricing/slot-modifier")
def slot_modifier():
    try:
        # Odbiór parametrów
        date = request.args.get("date")  # format YYYY-MM-DD
        hour = request.args.get("hour")  # format HH:MM
        location_type = request.args.get("location_type")  # local_list, distance_local, distance_far
        urgency_type = request.args.get("urgency_type")  # STANDARD, PILNA, NATYCHMIASTOWA, PLANOWA

        if not all([date, hour, location_type, urgency_type]):
            return jsonify({"error": "Brakuje wymaganych parametrów"}), 400

        # Przekształcenie daty i godziny
        slot_time = dt.strptime(f"{date} {hour}", "%Y-%m-%d %H:%M")
        weekday = slot_time.strftime("%A")
        hour_only = slot_time.hour

        # SLOT NATYCHMIASTOWY – tylko przy trybie NATYCHMIASTOWA
        if urgency_type.upper() == "NATYCHMIASTOWA":
            if 8 <= hour_only < 22:
                load_factor = get_calendar_load(date)
                modifier = round(1.5 + (load_factor * 0.005), 2)  # +50% do +200%
                modifier = min(max(modifier, 1.5), 3.0)
                return jsonify({
                    "slot": "NATYCHMIASTOWY",
                    "modifier": modifier
                })
            else:
                return jsonify({"error": "Poza godzinami slotu NATYCHMIASTOWEGO"}), 400

        # SLOT A
        if location_type == "local_list" and weekday in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"] and 8 <= hour_only < 14:
            return jsonify({"slot": "A", "modifier": 0.9})

        # SLOT B
        if weekday in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"] and 14 <= hour_only < 18:
            return jsonify({"slot": "B", "modifier": 1.0})

        # SLOT C
        if location_type in ["distance_local", "distance_far"] and weekday in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"] and 8 <= hour_only < 18:
            load_factor = get_calendar_load(date)
            modifier = round(0.85 + (load_factor * 0.0035), 2)  # od 0.85 do 1.2
            modifier = min(max(modifier, 0.85), 1.2)
            return jsonify({
                "slot": "C",
                "modifier": modifier
            })

        # SLOT D
        if 18 <= hour_only < 22:
            if urgency_type.upper() != "NATYCHMIASTOWA":
                return jsonify({"slot": "D", "modifier": 1.5})
            else:
                return jsonify({"slot": "D", "modifier": 1.0})

        # SLOT E – soboty, niedziele i święta
        if weekday in ["Saturday", "Sunday"] and 7 <= hour_only < 11:
            if location_type in ["local_list", "distance_local"]:
                if weekday == "Saturday":
                    return jsonify({"slot": "E", "modifier": 1.0, "extra_fee": 50})
                if weekday == "Sunday":
                    return jsonify({"slot": "E", "modifier": 1.0, "extra_fee": 60})

        return jsonify({"error": "Nie pasuje do żadnego slotu"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------ OBLICZANIE OBCIĄŻENIA DNIA (8:00–22:00) ------------------

def get_calendar_load(date_str):
    try:
        service = get_calendar_service()
        start = dt.strptime(date_str, "%Y-%m-%d").replace(hour=8, minute=0).isoformat() + "Z"
        end = dt.strptime(date_str, "%Y-%m-%d").replace(hour=22, minute=0).isoformat() + "Z"

        events = service.events().list(
            calendarId=os.getenv("GOOGLE_CALENDAR_ID"),
            timeMin=start,
            timeMax=end,
            singleEvents=True
        ).execute().get("items", [])

        return len(events)
    except:
        return 0

# --------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
