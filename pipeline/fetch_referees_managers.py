import os, csv, sys, time
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

API_KEY = os.getenv("BZZOIRO_API")
if not API_KEY:
    print("ERROR: BZZOIRO_API environment variable not set.")
    sys.exit(1)

BASE_URL = "https://sports.bzzoiro.com/api/v2/"
HEADERS = {"Authorization": "Token " + API_KEY}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LEAGUES = [
    {"id": 9,  "name": "brasileirao_serie_a_2026", "display": "Brasileir\u00e3o S\u00e9rie A"},
    {"id": 18, "name": "mls_2026",                  "display": "MLS"},
    {"id": 19, "name": "liga_mx_apertura_2026",     "display": "Liga MX Apertura"},
    {"id": 50, "name": "k_league_1_2026",           "display": "K League 1"},
]


def fetch_json(url):
    while True:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 429:
            print("  Rate limited, waiting 10s...")
            time.sleep(10)
            continue
        r.raise_for_status()
        return r.json()


def extract_referees():
    print("\n" + "=" * 50)
    print("REFEREES")
    print("=" * 50)

    out_dir = os.path.join(BASE_DIR, "Referees")
    os.makedirs(out_dir, exist_ok=True)

    fields = [
        "league", "name", "country",
        "matches", "total_yellow_cards", "total_red_cards",
        "avg_yellow_per_match", "avg_red_per_match",
        "avg_goals_per_match", "avg_fouls_per_match",
        "career_games", "career_yellow_cards", "career_red_cards",
    ]

    for lg in LEAGUES:
        lid = lg["id"]
        lname = lg["name"]

        print("\n{} (league_id={})...".format(lg["display"], lid))
        data = fetch_json(BASE_URL + "referees/?league_id={}".format(lid))
        results = data.get("results", [])
        print("  Found {} referees".format(len(results)))

        rows = []
        for ref in results:
            row = {"league": lname}
            for f in fields:
                if f == "league":
                    continue
                row[f] = ref.get(f, "")
            rows.append(row)

        filepath = os.path.join(out_dir, lname + ".csv")
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print("  Saved {} rows to {}".format(len(rows), filepath))


def extract_managers():
    print("\n" + "=" * 50)
    print("MANAGERS / COACHES")
    print("=" * 50)

    out_dir = os.path.join(BASE_DIR, "Coach")
    os.makedirs(out_dir, exist_ok=True)

    fields = [
        "league", "name", "short_name", "country",
        "tactical_profile", "preferred_formation",
        "matches_total", "wins", "draws", "losses", "win_pct",
        "avg_goals_scored", "avg_goals_conceded", "avg_possession",
        "clean_sheet_pct", "btts_pct", "over_25_pct",
    ]

    for lg in LEAGUES:
        lid = lg["id"]
        lname = lg["name"]

        print("\n{} (league_id={})...".format(lg["display"], lid))
        data = fetch_json(BASE_URL + "managers/?league_id={}".format(lid))
        results = data.get("results", [])
        print("  Found {} managers".format(len(results)))

        rows = []
        for mgr in results:
            row = {"league": lname}
            for f in fields:
                if f == "league":
                    continue
                row[f] = mgr.get(f, "")
            rows.append(row)

        filepath = os.path.join(out_dir, lname + ".csv")
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print("  Saved {} rows to {}".format(len(rows), filepath))


def main():
    print("Referees & Managers Stats Extractor")
    print("Started at: {}".format(datetime.now().isoformat()))

    extract_referees()
    extract_managers()

    print("\n" + "=" * 50)
    print("ALL DONE at {}".format(datetime.now().isoformat()))
    for folder in ["Referees", "Coach"]:
        d = os.path.join(BASE_DIR, folder)
        print("\n{}:".format(folder))
        for f in sorted(os.listdir(d)):
            fp = os.path.join(d, f)
            if f.endswith(".csv"):
                with open(fp, "r", encoding="utf-8-sig") as fh:
                    rows = sum(1 for _ in fh) - 1
                print("  {} ({} rows)".format(f, rows))


if __name__ == "__main__":
    main()
