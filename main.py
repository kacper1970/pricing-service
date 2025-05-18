
# -------------------- IMPORTY I KONFIGURACJA --------------------
import os
import json
import datetime
from datetime import datetime as dt, time
import pandas as pd
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from urllib.parse import quote

app = Flask(__name__)
CORS(app)


# Ścieżka do pliku logów
LOG_FILE = "logs.txt"

# 🔧 Upewnij się, że plik logów istnieje
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("[Start logowania Pricing Service]\n")

# ✅ Funkcja logująca do pliku
def log_to_file(message):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"[BŁĄD LOGOWANIA] {e}", flush=True)
# ✅ Weryfikacja zmiennych środowiskowych
REQUIRED_ENV_VARS = [
    "GOOGLE_MAPS_API_KEY",
    "GOOGLE_CALENDAR_ID",
    "ADDRESS_SHEET_URL",
    "SERVICES_SHEET_URL"
]
missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing:
    raise RuntimeError(f"Brakuje zmiennych środowiskowych: {', '.join(missing)}")

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
    log_to_file("✅ Pricing Service uruchomiony")
    return "✅ Pricing Service działa"
   
@app.route("/pricing/location-modifier")
def location_modifier():
    address = request.args.get("address", "").strip().lower()
    if not address:
        return jsonify({"error": "Brak adresu"}), 400

    try:
        log_to_file(f"➡️ Sprawdzany adres: {address}")
        csv_url = ADDRESS_SHEET_URL.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
        df = pd.read_csv(csv_url)

        match_found = False
        for _, row in df.iterrows():
            addr1 = f"{row['Ulica']} {row['Nr domu']}, {row['Miasto']}".strip().lower()
            addr2 = f"{row['Ulica']} {row['Nr domu']}, {row['Kod pocztowy']} {row['Miasto']}".strip().lower()

            if address == addr1:
                log_to_file(f"✅ Dopasowano adres (wariant 1): {addr1}")
                match_found = True
                break
            elif address == addr2:
                log_to_file(f"✅ Dopasowano adres (wariant 2): {addr2}")
                match_found = True
                break
            else:
                log_to_file(f"❌ Brak dopasowania: {address} ≠ {addr1} ani {addr2}")

        if match_found:
            return jsonify({
                "location_type": "local_list",
                "modifier": LOCAL_MODIFIER,
                "extra_cost": 0.0,
                "distance_km": 0.0
            })

        # Jeśli nie znaleziono — sprawdź odległość
        distance = calculate_distance_km(BASE_ADDRESS, address)
        if distance is None:
            return jsonify({"error": "Nie udało się obliczyć odległości"}), 500

        location_type = "distance_local" if distance <= FAR_THRESHOLD_KM else "distance_far"
        modifier = 1.0 if location_type == "distance_local" else FAR_MODIFIER
        extra_cost = round(distance * BASE_FEE_KM, 2)

        log_to_file(f"📏 Adres spoza listy. Typ: {location_type}, Dystans: {distance} km, Dopłata: {extra_cost} zł")

        return jsonify({
            "location_type": location_type,
            "modifier": modifier,
            "extra_cost": extra_cost,
            "distance_km": distance
        })

    except Exception as e:
        log_to_file(f"💥 Błąd w location-modifier: {str(e)}")
        return jsonify({"error": str(e)}), 500


# -------------------- MODYFIKATOR KIEDY --------------------
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
        return jsonify({"type": "PLANOWA", "modifier": 0.9})
    except Exception as e:
        return jsonify({"error": f"Błąd w przetwarzaniu daty: {str(e)}"}), 500

# -------------------- SLOTY CZASOWE --------------------

from datetime import time

# Definicje slotów
SLOT_A = {"name": "A", "days": [0, 1, 2, 3, 4], "start": time(8, 0), "end": time(14, 0), "locations": ["local_list"], "modifier": 0.9}
SLOT_B = {"name": "B", "days": [0, 1, 2, 3, 4], "start": time(14, 0), "end": time(18, 0), "locations": ["local_list", "distance_local", "distance_far"], "modifier": 1.0}
SLOT_C = {"name": "C", "days": [0, 1, 2, 3, 4], "start": time(8, 0), "end": time(18, 0), "locations": ["distance_local", "distance_far"]}
SLOT_D = {"name": "D", "days": list(range(7)), "start": time(18, 0), "end": time(22, 0), "locations": ["local_list", "distance_local", "distance_far"], "modifier": 1.5}
SLOT_E = {"name": "E", "days": [5, 6], "start": time(7, 0), "end": time(11, 0), "locations": ["local_list", "distance_local"]}
SLOT_NOW = {"name": "NOW", "days": list(range(7)), "start": time(8, 0), "end": time(22, 0), "locations": ["local_list", "distance_local", "distance_far"]}

def calculate_dynamic_modifier(load, base_min, base_max):
    max_tasks = 20
    if load <= 0:
        return base_min
    elif load >= max_tasks:
        return base_max
    return round(base_min + (base_max - base_min) * (load / max_tasks), 2)

def get_calendar_load(date_str):
    """
    Pobiera liczbę wydarzeń z calendar-service dla podanego dnia (8:00–22:00).
    """
    try:
        response = requests.get(
            f"https://calendar-service-pl5m.onrender.com/events-count?date={date_str}",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("count", 0)
        else:
            print("Błąd odpowiedzi z calendar-service:", response.text)
            return 0
    except Exception as e:
        print("Błąd połączenia z calendar-service:", e)
        return 0
def determine_slot(date_str, time_str, urgency, location, override=False):
    try:
        visit_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        visit_time = datetime.datetime.strptime(time_str, "%H:%M").time()
        weekday = visit_date.weekday()
        load = get_calendar_load(date_str)

        if override or urgency == "NATYCHMIASTOWA":
            modifier = calculate_dynamic_modifier(load, 1.5, 3.0)
            return {"slot": "NOW", "modifier": modifier}

        if location == "local_list" and weekday in SLOT_A["days"] and SLOT_A["start"] <= visit_time < SLOT_A["end"]:
            return {"slot": "A", "modifier": SLOT_A["modifier"]}

        if location in SLOT_B["locations"] and weekday in SLOT_B["days"] and SLOT_B["start"] <= visit_time < SLOT_B["end"]:
            return {"slot": "B", "modifier": SLOT_B["modifier"]}

        if location in SLOT_C["locations"] and weekday in SLOT_C["days"] and SLOT_C["start"] <= visit_time < SLOT_C["end"]:
            modifier = calculate_dynamic_modifier(load, 0.85, 1.2)
            return {"slot": "C", "modifier": modifier}

        if location in SLOT_D["locations"] and weekday in SLOT_D["days"] and SLOT_D["start"] <= visit_time < SLOT_D["end"]:
            return {"slot": "D", "modifier": SLOT_D["modifier"]}

        if location in SLOT_E["locations"] and weekday in SLOT_E["days"] and SLOT_E["start"] <= visit_time < SLOT_E["end"]:
            return {"slot": "E", "modifier": "+50zł" if weekday == 5 else "+60zł"}

        return {"slot": "UNKNOWN", "modifier": 1.0}
    except Exception as e:
        return {"slot": "ERROR", "modifier": 1.0, "error": str(e)}

@app.route("/pricing/slot-modifier")
def slot_modifier():
    date_str = request.args.get("date")
    time_str = request.args.get("time")
    urgency = request.args.get("urgency")
    location = request.args.get("location")
    override = request.args.get("override", "false").lower() == "true"

    if not all([date_str, time_str, urgency, location]):
        return jsonify({"error": "Brakuje wymaganych parametrów"}), 400

    result = determine_slot(date_str, time_str, urgency, location, override)
    if "error" in result:
        return jsonify({"error": result["error"]}), 500
    return jsonify(result)
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

@app.route("/pricing/services")
def list_services():
    try:
        sheet_url = SERVICES_SHEET_URL
        if not sheet_url:
            return jsonify({"error": "Brak URL do arkusza usług"}), 500

        csv_url = sheet_url.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
        df = pd.read_csv(csv_url)
        services = df["Usługa"].dropna().unique().tolist()

        return jsonify({"services": services})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_base_price(service_name):
    try:
        sheet_url = os.getenv("SERVICES_SHEET_URL")
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
            "czas": str(row["czas"]) if "czas" in row else ""
        }
    except Exception as e:
        return {"error": str(e)}
        
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

        log_to_file(f"➡️ Zapytanie /pricing/full - Usługa: {service}, Adres: {address}, Data: {date}, Godzina: {time_str}, VAT: {vat_rate}, Pakiet: {package}, Override: {override}")

        if not all([service, address, date, time_str]):
            return jsonify({"error": "Brak wymaganych danych"}), 400

        base = get_base_price(service)
        if "error" in base:
            log_to_file(f"❌ Błąd ceny bazowej: {base['error']}")
            return jsonify({"error": base["error"]}), 400

        current_price = base["brutto_8"] if vat_rate == "8" else base["brutto_23"]
        log_to_file(f"🔹 Cena bazowa (brutto): {current_price}")

        location = calculate_location_modifier(address)
        if not location or "modifier" not in location:
            log_to_file("❌ Błąd lokalizacji")
            return jsonify({"error": "Błąd w określaniu lokalizacji"}), 500
        current_price *= location["modifier"]
        log_to_file(f"📍 Lokalizacja: {location['location_type']}, Modyfikator: {location['modifier']}")

        when = calculate_when_modifier(date)
        if not when or "modifier" not in when:
            log_to_file("❌ Błąd terminu")
            return jsonify({"error": "Błąd w określaniu terminu realizacji"}), 500
        current_price *= when["modifier"]
        log_to_file(f"🗓️ Kiedy: {when['type']}, Modyfikator: {when['modifier']}")

        slot = get_slot_modifier(
            date_str=date,
            hour_str=time_str,
            location_type=location.get("location_type", ""),
            visit_type=when.get("type", ""),
            load_percentage=get_calendar_load(date),
            override_now=override
        )
        if not slot or "modifier" not in slot:
            log_to_file("❌ Błąd slotu")
            return jsonify({"error": "Błąd w wyznaczeniu slotu"}), 500

        slot_modifier = slot["modifier"]
        if isinstance(slot_modifier, str) and "zł" in slot_modifier:
            try:
                plus = int(slot_modifier.replace("+", "").replace("zł", ""))
                current_price += plus
                log_to_file(f"⏱️ Slot (kwotowy): +{plus}zł")
            except:
                log_to_file("❌ Błąd przeliczenia modyfikatora kwotowego slotu")
                return jsonify({"error": "Niepoprawny modyfikator kwotowy slotu"}), 500
        else:
            current_price *= slot_modifier
            log_to_file(f"⏱️ Slot: {slot['slot']}, Modyfikator: {slot_modifier}")

        package_map = {
            "safe": {"name": "Pakiet Safe", "modifier": 1.0},
            "comfort": {"name": "Pakiet Comfort", "modifier": 1.25},
            "priority": {"name": "Pakiet Priority", "modifier": 1.5},
            "all": {"name": "Pakiet All Inclusive", "modifier": 2.0}
        }
        selected_package = package_map.get(package, package_map["safe"])
        current_price *= selected_package["modifier"]
        log_to_file(f"📦 Pakiet: {selected_package['name']}, Modyfikator: {selected_package['modifier']}")

        final_price = round(current_price, 2)
        log_to_file(f"✅ Cena końcowa: {final_price} zł")

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
        log_to_file(f"💥 Wyjątek: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/logs.txt")
def logs():
    try:
        with open("logs.txt", "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as e:
        return f"Błąd odczytu logów: {e}", 500

# -------------------- ulice lokalne --------------------

@app.route("/pricing/local-streets")
def local_streets():
    try:
        csv_url = ADDRESS_SHEET_URL.replace("/edit?usp=sharing", "/gviz/tq?tqx=out:csv")
        df = pd.read_csv(csv_url)

        if "Ulica" not in df.columns:
            return jsonify({"error": "Brak kolumny 'Ulica' w arkuszu"}), 500

        unique_streets = sorted(df["Ulica"].dropna().unique().tolist())
        return jsonify({"streets": unique_streets})

    except Exception as e:
        return jsonify({"error": f"Błąd wczytywania ulic: {str(e)}"}), 500
# -------------------- MAIN --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
