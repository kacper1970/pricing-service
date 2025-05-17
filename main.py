import os
import json
import math
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from urllib.parse import quote_plus

app = Flask(__name__)
CORS(app)

# Cennik podstawowy (może być wczytywany z Google Sheets w przyszłości)
BASE_PRICING = {
    "pomiary": 150,
    "montaz_lampy": 120,
    "naprawa_gniazdka": 100
}

# VAT
VAT_8 = 1.08
VAT_23 = 1.23

# Google Sheets - lokalne adresy (publiczny dostęp jako CSV)
LOCAL_ADDRESSES_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTUKhHdJcKdpvVi6LTlNvLPWzr0LhoZRo3VcfV31KjoqAnWn-wG6nLNsUjUzv9RR1Vz6AfdhMA4Qsiu/pub?output=csv"

# Modyfikatory (przykładowe)
MODYFIKATORY = {
    "GDZIE": {
        "lokalna": 1.0,
        "<=20km": 1.0,  # + koszt dojazdu dodany osobno
        ">20km": 1.1   # + koszt dojazdu dodany osobno
    },
    "KIEDY": {
        "planowa": 1.0,
        "standard": 1.0,
        "pilna": 1.2,
        "natychmiastowa": 1.5
    },
    "PAKIET": {
        "safe": 1.0,
        "comfort": 1.25,
        "priority": 1.5,
        "all_inclusive": 2.0
    }
}

DOJAZD_KM_CENA = 2.0  # zł za kilometr w jedną stronę (sztywna opłata)
PUNKT_BAZOWY = "Królowej Elżbiety 1A, Świebodzice"

# Mock funkcja odległości (tu powinno być API mapowe np. Google Maps Distance Matrix)
def oblicz_odleglosc(adres):
    # TODO: Zaimplementować z API mapowym
    return 18  # przykładowa wartość km

def pobierz_lokalne_adresy():
    try:
        response = requests.get(LOCAL_ADDRESSES_CSV)
        lines = response.text.strip().split("\n")
        lokalne = set()
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) >= 3:
                ulica = parts[0].strip().lower()
                nr_domu = parts[1].strip().lower()
                miasto = parts[2].strip().lower()
                lokalne.add(f"{ulica} {nr_domu}, {miasto}")
        return lokalne
    except Exception as e:
        print("Błąd podczas pobierania lokalnych adresów:", e)
        return set()

def czy_adres_lokalny(adres, lokalne_adresy):
    adres = adres.strip().lower()
    return adres in lokalne_adresy

def wylicz_cene(adres, usluga, typ_klienta, kiedy, pakiet):
    lokalne_adresy = pobierz_lokalne_adresy()
    cena_netto = BASE_PRICING.get(usluga, 0)

    # GDZIE
    if czy_adres_lokalny(adres, lokalne_adresy):
        cena = cena_netto * MODYFIKATORY["GDZIE"]["lokalna"]
        dojazd = 0
    else:
        dystans = oblicz_odleglosc(adres)
        if dystans <= 20:
            cena = cena_netto * MODYFIKATORY["GDZIE"]["<=20km"]
            dojazd = dystans * DOJAZD_KM_CENA
        else:
            cena = cena_netto * MODYFIKATORY["GDZIE"][">20km"]
            dojazd = dystans * DOJAZD_KM_CENA

    # KIEDY
    cena *= MODYFIKATORY["KIEDY"].get(kiedy, 1.0)

    # SLOT – pomijamy na razie, dojdzie później

    # PAKIET
    cena *= MODYFIKATORY["PAKIET"].get(pakiet, 1.0)

    # VAT
    if typ_klienta == "firma":
        cena_brutto = cena * VAT_23
    else:
        cena_brutto = cena * VAT_8

    return round(cena_brutto + dojazd, 2)

@app.route("/pricing", methods=["POST"])
def pricing():
    data = request.json
    adres = data.get("adres")
    usluga = data.get("usluga")
    typ_klienta = data.get("typ_klienta", "osoba")
    kiedy = data.get("kiedy", "standard")
    pakiet = data.get("pakiet", "safe")

    if not adres or not usluga:
        return jsonify({"error": "Brak adresu lub usługi"}), 400

    cena = wylicz_cene(adres, usluga, typ_klienta, kiedy, pakiet)
    return jsonify({
        "adres": adres,
        "usluga": usluga,
        "cena_brutto": cena,
        "waluta": "PLN"
    })

@app.route("/")
def home():
    return "✅ Pricing service is running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
