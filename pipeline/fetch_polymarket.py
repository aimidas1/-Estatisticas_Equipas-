import os, csv, sys, time
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

API_KEY = os.getenv("BZZOIRO_API")
if not API_KEY:
    print("ERROR: BZZOIRO_API not set")
    sys.exit(1)

BASE_URL = "https://sports.bzzoiro.com/api/v2/"
HEADERS = {"Authorization": "Token " + API_KEY}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LEAGUES = [
    {"id": 7,  "name": "ucl_2026",       "display": "UEFA Champions League"},
    {"id": 8,  "name": "uel_2026",       "display": "UEFA Europa League"},
    {"id": 9,  "name": "brasileirao_serie_a_2026", "display": "Brasileir\u00e3o S\u00e9rie A"},
    {"id": 18, "name": "mls_2026",                  "display": "MLS"},
    {"id": 19, "name": "liga_mx_apertura_2026",     "display": "Liga MX Apertura"},
    {"id": 50, "name": "k_league_1_2026",           "display": "K League 1"},
]

MARKET_COLUMNS = [
    "1x2_home", "1x2_draw", "1x2_away",
    "btts_yes", "btts_no",
    "over_15", "under_15", "over_25", "under_25",
    "over_35", "under_35", "over_45", "under_45",
]

OUTPUT_COLUMNS = [
    "league", "event_id", "polymarket_event_id",
    "event_date", "home_team", "away_team",
    "updated_at",
] + MARKET_COLUMNS + ["exact_scores_json"]


def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                print("    Rate limited, waiting 15s...")
                time.sleep(15)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < retries - 1:
                print("    Retry {}/{}: {}".format(attempt + 1, retries, e))
                time.sleep(3)
                continue
            raise


def fetch_all_prematch_events(league_id):
    events = []
    url = BASE_URL + "events/?league_id={}&status=notstarted&limit=200".format(league_id)
    page = 0
    while url:
        page += 1
        try:
            data = fetch_json(url)
            results = data.get("results", [])
            events.extend(results)
            print("  Page {}: got {} events (total: {})".format(page, len(results), len(events)))
            url = data.get("next")
            time.sleep(0.3)
        except Exception as e:
            print("  Error on page {}: {}".format(page, e))
            break
    return events


def flatten_markets(markets):
    if not markets:
        return {col: "" for col in MARKET_COLUMNS}

    def safe_dict(d):
        return d if isinstance(d, dict) else {}

    row = {}

    m1x2 = safe_dict(markets.get("1x2"))
    row["1x2_home"] = m1x2.get("home", "")
    row["1x2_draw"] = m1x2.get("draw", "")
    row["1x2_away"] = m1x2.get("away", "")

    btts = safe_dict(markets.get("btts"))
    row["btts_yes"] = btts.get("yes", "")
    row["btts_no"] = btts.get("no", "")

    ou = safe_dict(markets.get("over_under"))
    row["over_15"] = ou.get("over_15", "")
    row["under_15"] = ou.get("under_15", "")
    row["over_25"] = ou.get("over_25", "")
    row["under_25"] = ou.get("under_25", "")
    row["over_35"] = ou.get("over_35", "")
    row["under_35"] = ou.get("under_35", "")
    row["over_45"] = ou.get("over_45", "")
    row["under_45"] = ou.get("under_45", "")

    return row


def process_league(lg):
    league_id = lg["id"]
    league_name = lg["name"]
    display_name = lg["display"]

    print("\n{} {} {}".format("=" * 20, display_name, "=" * 20))
    print("Fetching notstarted events...")

    events = fetch_all_prematch_events(league_id)
    print("Total notstarted events: {}".format(len(events)))

    if not events:
        return []

    rows = []
    total = len(events)

    for idx, ev in enumerate(events):
        event_id = ev["id"]
        home_team = ev.get("home_team", "")
        away_team = ev.get("away_team", "")

        if (idx + 1) % 20 == 0 or idx == 0:
            print("  Polymarket: {}/{} ({}%)".format(idx + 1, total, round((idx + 1) / total * 100)))

        try:
            data = fetch_json(BASE_URL + "events/{}/polymarket/".format(event_id))
        except Exception as e:
            print("    Failed event {}: {}".format(event_id, e))
            continue

        if not data:
            continue

        pm_id = data.get("polymarket_event_id")
        if not pm_id:
            continue

        event_date = (data.get("event_date") or "")[:19].replace("T", " ")
        updated_at = (data.get("updated_at") or "")[:19].replace("T", " ")

        markets = data.get("markets", {})
        exact_scores = data.get("exact_scores")

        row = {
            "league": league_name,
            "event_id": event_id,
            "polymarket_event_id": pm_id,
            "event_date": event_date,
            "home_team": home_team,
            "away_team": away_team,
            "updated_at": updated_at,
        }

        row.update(flatten_markets(markets))

        import json
        row["exact_scores_json"] = json.dumps(exact_scores, ensure_ascii=False) if exact_scores else ""

        rows.append(row)

    return rows


def main():
    print("Polymarket Odds Extractor")
    print("Started at: {}".format(datetime.now(timezone.utc).isoformat()))

    out_dir = os.path.join(BASE_DIR, "polymarket data")
    os.makedirs(out_dir, exist_ok=True)

    total_rows = 0
    for lg in LEAGUES:
        rows = process_league(lg)
        if not rows:
            print("  No Polymarket data found.")
            continue

        filepath = os.path.join(out_dir, lg["name"] + ".csv")
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print("  Saved {} rows to {}".format(len(rows), filepath))
        total_rows += len(rows)

    print("\n" + "=" * 50)
    print("Done at {}".format(datetime.now(timezone.utc).isoformat()))
    print("Total rows: {}".format(total_rows))
    print("\nFiles:")
    for f in sorted(os.listdir(out_dir)):
        fp = os.path.join(out_dir, f)
        with open(fp, "r", encoding="utf-8-sig") as fh:
            n = sum(1 for _ in fh) - 1
        print("  {} ({} rows)".format(f, max(0, n)))


if __name__ == "__main__":
    main()
