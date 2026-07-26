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
    print("ERROR: BZZOIRO_API not set")
    sys.exit(1)

BASE_URL = "https://sports.bzzoiro.com/api/v2/"
HEADERS = {"Authorization": "Token " + API_KEY}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LEAGUES = [
    {"id": 9,  "season_id": 28,  "name": "brasileirao_serie_a_2026"},
    {"id": 18, "season_id": 158, "name": "mls_2026"},
    {"id": 19, "season_id": 1309, "name": "liga_mx_apertura_2026"},
    {"id": 50, "season_id": 1288, "name": "k_league_1_2026"},
]

INCIDENT_COLUMNS = [
    "league", "match_date", "round_number",
    "home_team", "away_team", "match_home_score", "match_away_score",
    "minute", "added_time", "type",
    "player", "is_home",
    "card_type", "reason",
    "player_in", "player_out",
    "period_text", "injury_length",
    "incident_home_score", "incident_away_score",
]


def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            if r.status_code == 429:
                print("    Rate limited, waiting 15s...")
                time.sleep(15)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < retries - 1:
                print("    Retry {}/{} after error: {}".format(attempt + 1, retries, e))
                time.sleep(3)
                continue
            raise


def fetch_all_events(league_id, season_id):
    events = []
    url = BASE_URL + "events/?league_id={}&season_id={}&status=finished&limit=200".format(league_id, season_id)
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


def process_league(lg):
    league_id = lg["id"]
    season_id = lg["season_id"]
    league_name = lg["name"]

    print("\n{} (league_id={}, season_id={})".format(league_name, league_id, season_id))
    print("Fetching events...")

    events = fetch_all_events(league_id, season_id)
    print("Total events: {}".format(len(events)))

    if not events:
        return []

    rows = []
    total = len(events)

    for idx, ev in enumerate(events):
        event_id = ev["id"]
        match_date = (ev.get("event_date") or "")[:10]
        round_num = ev.get("round_number", "")
        home_team = ev.get("home_team", "")
        away_team = ev.get("away_team", "")
        m_home_score = ev.get("home_score", "")
        m_away_score = ev.get("away_score", "")

        if (idx + 1) % 100 == 0 or idx == 0 or idx == total - 1:
            print("  Incidents: {}/{} ({}%)".format(idx + 1, total, round((idx + 1) / total * 100)))

        try:
            data = fetch_json(BASE_URL + "events/{}/incidents/".format(event_id))
        except Exception as e:
            print("    Failed event {}: {}".format(event_id, e))
            continue

        time.sleep(0.3)

        incidents = data.get("incidents", [])
        if not incidents:
            continue

        for inc in incidents:
            t = inc.get("type", "")
            row = {
                "league": league_name,
                "match_date": match_date,
                "round_number": round_num,
                "home_team": home_team,
                "away_team": away_team,
                "match_home_score": m_home_score,
                "match_away_score": m_away_score,
                "minute": inc.get("minute", ""),
                "added_time": inc.get("added_time", ""),
                "type": t,
                "player": inc.get("player", ""),
                "is_home": inc.get("is_home", ""),
                "card_type": inc.get("card_type", ""),
                "reason": inc.get("reason", ""),
                "player_in": inc.get("player_in", ""),
                "player_out": inc.get("player_out", ""),
                "period_text": inc.get("text", ""),
                "injury_length": inc.get("length", ""),
                "incident_home_score": inc.get("home_score", ""),
                "incident_away_score": inc.get("away_score", ""),
            }
            rows.append(row)

    return rows


def main():
    print("Incidents Extractor")
    print("Started: {}".format(datetime.now().isoformat()))

    out_dir = os.path.join(BASE_DIR, "Incidents")
    os.makedirs(out_dir, exist_ok=True)

    for lg in LEAGUES:
        rows = process_league(lg)
        if not rows:
            print("  No incidents found.")
            continue

        filepath = os.path.join(out_dir, lg["name"] + ".csv")
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=INCIDENT_COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print("  Saved {} incidents to {}".format(len(rows), filepath))

    print("\n" + "=" * 50)
    print("Done: {}".format(datetime.now().isoformat()))
    print("\nIncidents:")
    for f in sorted(os.listdir(out_dir)):
        fp = os.path.join(out_dir, f)
        with open(fp, "r", encoding="utf-8-sig") as fh:
            n = sum(1 for _ in fh) - 1
        print("  {} ({} incidents)".format(f, n))


if __name__ == "__main__":
    main()
