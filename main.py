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

from datetime import datetime, time

# Stałe slotów
SLOT_A = {"name": "A", "days": [0, 1, 2, 3, 4], "start": time(8, 0), "end": time(14, 0), "locations": ["local_list"], "modifier": 0.9}
SLOT_B = {"name": "B", "days": [0, 1, 2, 3, 4], "start": time(14, 0), "end": time(18, 0), "locations": ["local_list", "distance_local", "distance_far"], "modifier": 1.0}
SLOT_C = {"name": "C", "days": [0, 1, 2, 3, 4], "start": time(8, 0), "end": time(18, 0), "locations": ["distance_local", "distance_far"]}
SLOT_D = {"name": "D", "days": list(range(7)), "start": time(18, 0), "end": time(22, 0), "locations": ["local_list", "distance_local", "distance_far"], "modifier": 1.5}
SLOT_E = {"name": "E", "days": [5, 6], "start": time(7, 0), "end": time(11, 0), "locations": ["local_list", "distance_local"]}
SLOT_NOW = {"name": "NOW", "days": list(range(7)), "start": time(8, 0), "end": time(22, 0), "locations": ["local_list", "distance_local", "distance_far"]}

def calculate_dynamic_modifier(load, base_min, base_max):
    """Interpoluje modyfikator na podstawie obciążenia."""
    max_tasks = 20
    if load <= 0:
        return base_min
    elif load >= max_tasks:
        return base_max
    else:
        return round(base_min + (base_max - base_min) * (load / max_tasks), 2)

def determine_slot(date_str, time_str, urgency, location, override=False):
    visit_date = datetime.strptime(date_str, "%Y-%m-%d")
    visit_time = datetime.strptime(time_str, "%H:%M").time()
    weekday = visit_date.weekday()
    load = get_calendar_load(date_str)

    # Slot NATYCHMIASTOWY (wymuszony lub tryb NATYCHMIASTOWA)
    if urgency == "NATYCHMIASTOWA" or override:
        modifier = calculate_dynamic_modifier(load, 1.5, 3.0)
        return {"slot": "NOW", "modifier": modifier}

    # SLOT A
    if location == "local_list" and weekday in SLOT_A["days"] and SLOT_A["start"] <= visit_time < SLOT_A["end"]:
        return {"slot": "A", "modifier": SLOT_A["modifier"]}

    # SLOT B
    if location in SLOT_B["locations"] and weekday in SLOT_B["days"] and SLOT_B["start"] <= visit_time < SLOT_B["end"]:
        return {"slot": "B", "modifier": SLOT_B["modifier"]}

    # SLOT C
    if location in SLOT_C["locations"] and weekday in SLOT_C["days"] and SLOT_C["start"] <= visit_time < SLOT_C["end"]:
        modifier = calculate_dynamic_modifier(load, 0.85, 1.2)
        return {"slot": "C", "modifier": modifier}

    # SLOT D
    if location in SLOT_D["locations"] and weekday in SLOT_D["days"] and SLOT_D["start"] <= visit_time < SLOT_D["end"]:
        return {"slot": "D", "modifier": SLOT_D["modifier"]}

    # SLOT E
    if location in SLOT_E["locations"] and weekday in SLOT_E["days"] and SLOT_E["start"] <= visit_time < SLOT_E["end"]:
        if weekday == 5:
            return {"slot": "E", "modifier": "+50zł"}
        elif weekday == 6:
            return {"slot": "E", "modifier": "+60zł"}

    return {"slot": "UNKNOWN", "modifier": 1.0}

@app.route("/pricing/slot-modifier")
def slot_modifier():
    try:
        date_str = request.args.get("date")
        time_str = request.args.get("time")
        urgency = request.args.get("urgency")
        location = request.args.get("location")
        override = request.args.get("override", "false").lower() == "true"

        result = determine_slot(date_str, time_str, urgency, location, override)
        return jsonify(result)
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

# ------------------ Zapisywanie wizyty ------------------

@app.route("/pricing/book-visit", methods=["POST"])
def book_visit():
    try:
        data = request.get_json()
        response = requests.post(
            "https://calendar-service-pl5m.onrender.com/create-event",
            json=data,
            timeout=10
        )
        if response.status_code == 200:
            return jsonify({"status": "OK", "message": "Wizyta zapisana w kalendarzu"})
        else:
            return jsonify({"status": "Błąd", "details": response.text}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# -------------------- Endpoint: Lista usług --------------------
@app.route("/pricing/services")
def list_services():
    try:
        sheet_url = os.getenv("PRICE_SHEET_URL")
        if not sheet_url:
            return jsonify({"error": "Brak URL do arkusza"}), 500

        csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
        df = pd.read_csv(csv_url)
        services = df["Usługa"].dropna().unique().tolist()

        return jsonify({"services": services})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------- Endpoint: Cena 8 czy 23% VAT --------------------
def get_base_price(service_name):
    try:
        sheet_url = os.getenv("PRICE_SHEET_URL")
        if not sheet_url:
            return {"error": "Brak URL do arkusza cen"}

        csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
        df = pd.read_csv(csv_url)

        # Usuwamy spacje, \xa0 i zamieniamy przecinki na kropki
        for col in ["Cena netto", "Brutto 8%", "Brutto 23%"]:
            df[col] = df[col].astype(str).str.replace("\xa0", "", regex=False)
            df[col] = df[col].str.replace(" ", "", regex=False)
            df[col] = df[col].str.replace(",", ".", regex=False)
            df[col] = df[col].astype(float)

        row = df[df["Usługa"].str.lower().str.strip() == service_name.lower().strip()].iloc[0]

        return {
            "service": row["Usługa"],
            "netto": row["Cena netto"],
            "brutto_8": row["Brutto 8%"],
            "brutto_23": row["Brutto 23%"],
            "czas": str(row["czas"])
        }
    except Exception as e:
        return {"error": str(e)}
# -------------------- Endpoint: Podsumowanie ceny --------------------
from urllib.parse import quote

def calculate_location_modifier(address):
    """Lokalne wywołanie endpointu /pricing/location-modifier"""
    with app.test_request_context():
        with app.test_client() as client:
            resp = client.get(f"/pricing/location-modifier?address={quote(address)}")
            return resp.get_json()

def calculate_when_modifier(date_str):
    """Lokalne wywołanie endpointu /pricing/when-modifier"""
    with app.test_request_context():
        with app.test_client() as client:
            resp = client.get(f"/pricing/when-modifier?date={quote(date_str)}")
            return resp.get_json()

def get_slot_modifier(date_str, hour_str, location_type, visit_type, load_percentage=0, override_now=False):
    """Lokalne wywołanie endpointu /pricing/slot-modifier"""
    params = {
        "date": date_str,
        "time": hour_str,
        "urgency": visit_type,
        "location": location_type,
        "override": str(override_now).lower()
    }
    query = "&".join([f"{k}={quote(str(v))}" for k, v in params.items()])
    with app.test_request_context():
        with app.test_client() as client:
            resp = client.get(f"/pricing/slot-modifier?{query}")
            return resp.get_json()

@app.route("/pricing/full")
def full_price():
    try:
        service = request.args.get("service")
        address = request.args.get("address")
        vat_rate = request.args.get("vat", "8")
        date = request.args.get("date")
        time_str = request.args.get("time")
        package = request.args.get("package", "safe")
        override = request.args.get("override", "false").lower() == "true"

        if not all([service, address, date, time_str]):
            return jsonify({"error": "Brak wymaganych danych"}), 400

        # Krok 1: Cena bazowa
        base = get_base_price(service)
        if "error" in base:
            return jsonify({"error": base["error"]}), 400

        current_price = base["brutto_8"] if vat_rate == "8" else base["brutto_23"]

        # Krok 2: Lokalizacja
        location = calculate_location_modifier(address)
        if not location or "modifier" not in location:
            return jsonify({"error": "Błąd w określaniu lokalizacji"}), 500
        current_price *= location["modifier"]

        # Krok 3: Kiedy
        when = calculate_when_modifier(date)
        if not when or "modifier" not in when:
            return jsonify({"error": "Błąd w określaniu terminu realizacji"}), 500
        current_price *= when["modifier"]

        # Krok 4: Slot
        slot = get_slot_modifier(
            date_str=date,
            hour_str=time_str,
            location_type=location.get("location_type", ""),
            visit_type=when.get("type", ""),
            load_percentage=get_calendar_load(date),
            override_now=override
        )
        if not slot or "modifier" not in slot:
            return jsonify({"error": "Błąd w wyznaczeniu slotu"}), 500

        slot_modifier = slot["modifier"]
        if isinstance(slot_modifier, str) and "zł" in slot_modifier:
            try:
                plus = int(slot_modifier.replace("+", "").replace("zł", ""))
                current_price += plus
            except:
                return jsonify({"error": "Niepoprawny modyfikator kwotowy slotu"}), 500
        else:
            current_price *= slot_modifier

        # Krok 5: Pakiet
        package_map = {
            "safe": {"name": "Pakiet Safe", "modifier": 1.0},
            "comfort": {"name": "Pakiet Comfort", "modifier": 1.25},
            "priority": {"name": "Pakiet Priority", "modifier": 1.5},
            "all": {"name": "Pakiet All Inclusive", "modifier": 2.0}
        }
        selected_package = package_map.get(package, package_map["safe"])
        current_price *= selected_package["modifier"]

        final_price = round(current_price, 2)

        return jsonify({
            "service": base["service"],
            "base": base,
            "location": location,
            "when": when,
            "slot": slot,
            "package": selected_package,
            "final_price": final_price
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
