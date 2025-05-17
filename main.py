from flask import Flask, request, jsonify
from flask_cors import CORS
from google_sheets_utils import get_sheet_data
import os

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "✅ Pricing service is running"

@app.route("/pricing")
def calculate_pricing():
    try:
        # Parametry wejściowe
        service_name = request.args.get("service")
        location_type = request.args.get("location", "standard")  # lokalna / standard / >20km
        distance_km = float(request.args.get("distance", 0))
        when = request.args.get("when", "standard")  # plan / standard / urgent / now
        slot = request.args.get("slot", "B")  # A, B, C, D, E, NATYCHMIASTOWY
        package = request.args.get("package", "safe")  # safe, comfort, priority, allinclusive
        duration = int(request.args.get("duration", 60))
        first_time = request.args.get("first_time", "false") == "true"
        flexible_time = request.args.get("flexible_time", "false") == "true"
        no_day_hour = request.args.get("no_day_hour", "false") == "true"
        last_minute = request.args.get("last_minute", "false") == "true"

        # Pobranie cennika i modyfikatorów z Google Sheets
        base_prices = get_sheet_data("Cennik")
        modifiers_where = get_sheet_data("Gdzie")
        modifiers_when = get_sheet_data("Kiedy")
        modifiers_slot = get_sheet_data("Slot")
        modifiers_package = get_sheet_data("Pakiet")
        modifiers_extras = get_sheet_data("Reguły")

        # Wyszukanie ceny bazowej usługi
        matching_services = [row for row in base_prices if row[0].lower() == service_name.lower()]
        if not matching_services:
            return jsonify({"error": "Nie znaleziono usługi"}), 404
        
        base_netto = float(matching_services[0][1])  # cena netto z cennika

        # Modyfikator 1: GDZIE
        if location_type == "local":
            base_price = base_netto * (1 + get_modifier_value(modifiers_where, "lokalna"))
            travel_cost = 0
        elif location_type == "<20km":
            base_price = base_netto
            travel_cost = distance_km * float(get_modifier_value(modifiers_where, "dojazd_km"))
        else:  # >20km
            base_price = base_netto * (1 + get_modifier_value(modifiers_where, ">20km"))
            travel_cost = distance_km * float(get_modifier_value(modifiers_where, "dojazd_km"))

        # Modyfikator 2: KIEDY
        base_price *= (1 + get_modifier_value(modifiers_when, when))

        # Modyfikator 3: SLOT (przykładowo uproszczony)
        if when == "now":
            base_price *= (1 + get_modifier_value(modifiers_slot, "NATYCHMIASTOWY"))
        else:
            base_price *= (1 + get_modifier_value(modifiers_slot, slot))

        # Modyfikator 4: PAKIET
        base_price *= (1 + get_modifier_value(modifiers_package, package))

        # Reguły wspomagające
        if first_time:
            base_price -= 15
        if last_minute and when != "now":
            base_price *= (1 + get_modifier_value(modifiers_extras, "last_minute"))
        if flexible_time and location_type == "local" and duration <= 60:
            base_price *= (1 + get_modifier_value(modifiers_extras, "flexible_time"))
        if no_day_hour:
            base_price *= (1 + get_modifier_value(modifiers_extras, "no_day_hour"))

        final_price = round(base_price + travel_cost, 2)

        return jsonify({
            "service": service_name,
            "price": final_price,
            "travel_cost": round(travel_cost, 2),
            "netto": round(base_netto, 2)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_modifier_value(data, key):
    for row in data:
        if row[0].lower() == key.lower():
            return float(row[1])
    return 0.0

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
