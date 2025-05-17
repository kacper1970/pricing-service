from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from utils.google_sheets import get_price_data, get_modifiers_data
from utils.modifiers import apply_modifiers

import os

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/calculate-price", methods=["POST"])
def calculate_price():
    data = request.json

    try:
        # Pobierz cennik i modyfikatory z Google Sheets
        base_prices = get_price_data()
        modifiers = get_modifiers_data()

        # Oblicz cenę na podstawie danych wejściowych i logiki modyfikatorów
        result = apply_modifiers(
            service_code=data["service_code"],
            address=data["address"],
            date=data["date"],
            time=data["time"],
            urgency=data["urgency"],
            package=data["package"],
            first_time=data.get("first_time", False),
            last_minute=data.get("last_minute", False),
            no_time_choice=data.get("no_time_choice", False),
            short_visit=data.get("short_visit", False)
        )

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
