#!/usr/bin/env python3
"""
WTO Timeseries API fetcher
Usage: python3 tools/fetch_wto_api.py --country 410 --year 2023
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

API_KEY = "e5769b9320a24c4db1430476871cb558"
BASE_URL = "https://api.wto.org/timeseries/v1"
PARTNER_ALL = "000"

INDICATORS = {
    "trade": [
        "ITS_MTV_AX",   # Merchandise exports, value
        "ITS_MTV_AM",   # Merchandise imports, value
        "ITS_MTP_AXVG", # Merchandise exports, volume growth
        "ITS_MTP_AMVG", # Merchandise imports, volume growth
    ],
    "tariff": [
        "TP_A_0010",    # Simple average MFN applied
        "TP_A_0160",    # Weighted average MFN applied
        "TP_A_0430",    # Share of duty-free tariff lines
        "TP_B_0020",    # Simple average bound rate
        "TP_B_0090",    # Binding coverage
    ],
    "services": [
        "ITS_CS_QAX",   # Commercial services exports, value
        "ITS_CS_QAM",   # Commercial services imports, value
        "BAT_BV_X",     # Balance of trade in services, credits
        "BAT_BV_M",     # Balance of trade in services, debits
    ],
    "price": [
        "ITS_MTP_AUVX", # Merchandise exports, unit value
        "ITS_MTP_AUVM", # Merchandise imports, unit value
    ],
}

# Tariff indicators do not accept a partner parameter
NO_PARTNER = set(INDICATORS["tariff"])

# Bound tariff indicators have no time-period dimension — omit ps param
NO_PERIOD = {"TP_B_0020", "TP_B_0090"}

ALL_INDICATORS = [i for group in INDICATORS.values() for i in group]

COUNTRY_NAMES = {
    # 기존
    "410": "KOR", "840": "USA", "156": "CHN",
    "392": "JPN", "276": "DEU", "918": "EU",
    # 서유럽
    "250": "FRA", "826": "GBR", "756": "CHE",
    "528": "NLD", "56":  "BEL", "40":  "AUT",
    # 북유럽
    "752": "SWE", "578": "NOR", "208": "DNK",
    "246": "FIN", "352": "ISL",
    # 남유럽
    "380": "ITA", "724": "ESP", "620": "PRT", "300": "GRC",
    # 동유럽
    "616": "POL", "203": "CZE", "348": "HUN", "642": "ROU",
    # 러시아/유라시아
    "643": "RUS", "792": "TUR", "804": "UKR",
    # 아시아
    "158": "TWN", "702": "SGP", "356": "IND", "364": "IRN",
    "344": "HKG", "764": "THA", "704": "VNM", "360": "IDN",
    "458": "MYS", "608": "PHL", "682": "SAU", "784": "ARE",
    "376": "ISR", "50":  "BGD", "586": "PAK", "144": "LKA",
    # 아메리카 + 오세아니아
    "124": "CAN", "484": "MEX",
    "76":  "BRA", "32":  "ARG", "152": "CHL", "170": "COL", "604": "PER",
    "36":  "AUS", "554": "NZL",
}


def fetch(endpoint: str, params: dict) -> dict | list | None:
    query = urlencode(params)
    url = f"{BASE_URL}/{endpoint}?{query}"
    req = Request(url, headers={"Ocp-Apim-Subscription-Key": API_KEY})
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read()
            ct = resp.headers.get_content_charset() or "utf-8"
            try:
                text = raw.decode(ct)
            except (UnicodeDecodeError, LookupError):
                text = raw.decode("latin-1")
            return json.loads(text) if text.strip() else None
    except HTTPError as e:
        print(f"  HTTP {e.code} — {endpoint} {params}", file=sys.stderr)
        return None
    except URLError as e:
        print(f"  URL error — {e.reason}", file=sys.stderr)
        return None


def fetch_indicator(indicator: str, country: str, year: int) -> dict | None:
    r_code = country.zfill(3)  # WTO requires 3-digit codes
    params = {
        "i": indicator,
        "r": r_code,
        "fmt": "json",
        "max": "1",
    }
    if indicator not in NO_PARTNER:
        params["p"] = PARTNER_ALL
    if indicator not in NO_PERIOD:
        params["ps"] = str(year)
    result = fetch("data", params)
    if not result or "Dataset" not in result or not result["Dataset"]:
        return None
    row = result["Dataset"][0]
    return {
        "value": row.get("Value"),
        "year": row.get("Year"),
        "unit": row.get("UnitSymbol", ""),
    }


def fetch_country(country: str, year: int) -> dict:
    indicators_data = {}
    total = len(ALL_INDICATORS)
    for idx, indicator in enumerate(ALL_INDICATORS, 1):
        print(f"  [{idx:02d}/{total}] {indicator} ...", end=" ", flush=True)
        result = fetch_indicator(indicator, country, year)
        if result:
            indicators_data[indicator] = result
            print(f"OK  ({result['value']})")
        else:
            indicators_data[indicator] = None
            print("no data")
        # polite rate limit
        if idx < total:
            time.sleep(0.3)

    # group by category
    grouped = {}
    for group, members in INDICATORS.items():
        grouped[group] = {m: indicators_data.get(m) for m in members}

    return {
        "country": country,
        "iso_code": COUNTRY_NAMES.get(country, country),
        "year": year,
        "updated": date.today().isoformat(),
        "indicators": grouped,
    }


def output_path(country: str, year: int) -> str:
    iso = COUNTRY_NAMES.get(country, f"C{country}")
    base = os.path.expanduser("~/everbluesea/data/wto")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{iso}_{year}.json")


def main():
    parser = argparse.ArgumentParser(description="Fetch WTO Timeseries data")
    parser.add_argument("--country", required=True, help="ISO 3166-1 numeric (e.g. 410)")
    parser.add_argument("--year", type=int, default=date.today().year - 1,
                        help="Reference year (default: last year)")
    args = parser.parse_args()

    print(f"Fetching WTO data — country={args.country}, year={args.year}")
    data = fetch_country(args.country, args.year)

    path = output_path(args.country, args.year)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    ok = sum(1 for g in data["indicators"].values() for v in g.values() if v)
    print(f"\nSaved → {path}")
    print(f"Collected {ok}/{len(ALL_INDICATORS)} indicators")


if __name__ == "__main__":
    main()
