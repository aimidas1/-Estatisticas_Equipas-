import os, json, csv, time, sys
from datetime import datetime

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_URL = "https://sports.bzzoiro.com/api/v2/"
API_KEY = os.getenv("BZZOIRO_API")
if not API_KEY:
    print("ERROR: BZZOIRO_API environment variable not set.")
    print("Set it via: $env:BZZOIRO_API='your_key' (PowerShell)")
    print("Or create a .env file with: BZZOIRO_API=your_key")
    sys.exit(1)
HEADERS = {"Authorization": "Token " + API_KEY}

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Estatistica_equipa")

LEAGUES = [
    {"id": 9,  "season_id": 28,  "name": "brasileirao_serie_a_2026"},
    {"id": 18, "season_id": 158, "name": "mls_2026"},
    {"id": 19, "season_id": 1309,"name": "liga_mx_apertura_2026"},
    {"id": 50, "season_id": 1288,"name": "k_league_1_2026"},
]


def flatten_stats(stats_dict, prefix=""):
    row = {}
    for k, v in stats_dict.items():
        col = (prefix + "_" + k) if prefix else k
        if isinstance(v, dict):
            if "value" in v and "total" in v and "pct" in v:
                row[col + "_value"] = v.get("value")
                row[col + "_total"] = v.get("total")
                row[col + "_pct"] = v.get("pct")
            elif "actual" in v:
                row[col + "_actual"] = v.get("actual")
            else:
                for sk, sv in v.items():
                    row[col + "_" + sk] = sv
        else:
            row[col] = v
    return row


def fetch_all_events(league_id, season_id):
    events = []
    url = BASE_URL + "events/?league_id={}&season_id={}&status=finished&limit=200".format(league_id, season_id)
    while url:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                print("  Rate limited, waiting 10s...")
                time.sleep(10)
                continue
            if r.status_code == 401:
                print("ERROR: 401 Unauthorized. Check API key.")
                return events
            r.raise_for_status()
            data = r.json()
            events.extend(data.get("results", []))
            url = data.get("next")
            print("  Fetched {} events (total: {})".format(len(data.get("results", [])), len(events)))
            time.sleep(0.3)
        except Exception as e:
            print("  Error fetching events: {}".format(e))
            break
    return events


def fetch_event_stats(event_id):
    try:
        r = requests.get(BASE_URL + "events/{}/stats/".format(event_id), headers=HEADERS, timeout=30)
        if r.status_code == 429:
            time.sleep(5)
            r = requests.get(BASE_URL + "events/{}/stats/".format(event_id), headers=HEADERS, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return data.get("stats", {})
        else:
            return None
    except Exception as e:
        return None


def league_name_display(league_id):
    lookup = {9: "Brasileirao Serie A", 18: "MLS", 19: "Liga MX Apertura", 50: "K League 1"}
    return lookup.get(league_id, "League {}".format(league_id))


ALL_COLUMNS = [
    "league", "match_date", "round_number", "home_team", "away_team",
    "home_score", "away_score", "team", "venue",
    "ball_possession", "total_shots", "shots_on_target", "shots_off_target",
    "shots_inside_box", "shots_outside_box", "blocked_shots",
    "expected_goals", "big_chances", "big_chances_scored", "big_chances_missed",
    "passes", "accurate_passes", "pass_accuracy_pct",
    "long_balls_total", "long_balls_value", "long_balls_pct",
    "crosses_total", "crosses_value", "crosses_pct",
    "dribbles_total", "dribbles_value", "dribbles_pct",
    "duels", "ground_duels_total", "ground_duels_value", "ground_duels_pct",
    "aerial_duels_total", "aerial_duels_value", "aerial_duels_pct",
    "total_tackles", "tackles", "tackles_won",
    "fouls", "yellow_cards", "offsides", "corner_kicks",
    "throw_ins", "goal_kicks", "free_kicks", "clearances",
    "interceptions", "recoveries", "dispossessed", "hit_woodwork",
    "through_balls", "total_saves", "goalkeeper_saves", "big_saves",
    "high_claims", "goals_prevented",
    "errors_lead_to_a_goal", "errors_lead_to_a_shot",
    "final_third_phase_total", "final_third_phase_value", "final_third_phase_pct",
    "final_third_entries",
    "touches_in_penalty_area", "fouled_in_final_third",
    "attack", "attack_pct", "ball_safe", "ball_safe_pct",
    "dangerous_attack", "dangerous_attack_pct",
    "xg_actual",
]


def process_league(league):
    league_id = league["id"]
    season_id = league["season_id"]
    league_name = league["name"]
    display_name = league_name_display(league_id)

    print("\n{} {} {}".format("=" * 20, display_name, "=" * 20))
    print("Fetching events...")

    events = fetch_all_events(league_id, season_id)
    print("Total events: {}".format(len(events)))

    if not events:
        print("No events found, skipping.")
        return

    rows = []
    total = len(events)
    for idx, ev in enumerate(events):
        event_id = ev["id"]
        match_date = ev.get("event_date", "")[:10]
        round_num = ev.get("round_number", "")
        home_team = ev.get("home_team", "")
        away_team = ev.get("away_team", "")
        home_score = ev.get("home_score", "")
        away_score = ev.get("away_score", "")

        if (idx + 1) % 50 == 0 or idx == 0:
            print("  Stats: {}/{} ({}%)".format(idx + 1, total, round((idx + 1) / total * 100)))

        stats = fetch_event_stats(event_id)
        time.sleep(0.4)

        if not stats:
            print("    No stats for event {} ({} vs {}), skipping".format(event_id, home_team, away_team))
            continue

        home_stats = stats.get("home", {})
        away_stats = stats.get("away", {})

        base = {
            "league": league_name,
            "match_date": match_date,
            "round_number": round_num,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
        }

        row_home = base.copy()
        row_home["team"] = home_team
        row_home["venue"] = "home"
        flat_home = flatten_stats(home_stats)
        row_home.update(flat_home)
        rows.append(row_home)

        row_away = base.copy()
        row_away["team"] = away_team
        row_away["venue"] = "away"
        flat_away = flatten_stats(away_stats)
        row_away.update(flat_away)
        rows.append(row_away)

    if not rows:
        print("No stats data collected.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, league_name + ".csv")

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print("Saved {} rows to {}".format(len(rows), filepath))


def main():
    print("Football Team Stats Extractor")
    print("Started at: {}".format(datetime.now().isoformat()))
    print("Output directory: {}".format(OUTPUT_DIR))

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for league in LEAGUES:
        process_league(league)

    print("\n{}".format("=" * 50))
    print("ALL DONE at {}".format(datetime.now().isoformat()))
    print("CSV files saved to: {}".format(OUTPUT_DIR))
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".csv"):
            fp = os.path.join(OUTPUT_DIR, f)
            print("  {} ({} rows)".format(f, sum(1 for _ in open(fp, encoding="utf-8-sig")) - 1))


if __name__ == "__main__":
    main()
