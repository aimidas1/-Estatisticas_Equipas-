"""Atualiza estatÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â­sticas individuais de jogadores por liga.

Uso:
    python Estasticas_Jogadores/atualizar_estatisticas_jogadores.py

Os identificadores sÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â£o usados apenas durante as consultas e nÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â£o sÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â£o exportados.
"""

from __future__ import annotations

import csv
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
BASE_URL = os.getenv("BZZOIRO_BASE_URL", "https://sports.bzzoiro.com/api/v2/").rstrip("/") + "/"
TIMEOUT = 20
PAGE_SIZE = 200
WORKERS = 8

LEAGUES = [
    {"name": "Brasil Serie A 2026", "file": "brasil_serie_a_2026.csv", "league_id": 9, "season_id": 28},
    {"name": "MLS 2026", "file": "mls_2026.csv", "league_id": 18, "season_id": 158},
    {"name": "Liga Mexicana 2026/2027", "file": "liga_mexicana_2026_2027.csv", "league_id": 19, "season_id": 1309},
    {"name": "Coreia do Sul 2026", "file": "coreia_do_sul_2026.csv", "league_id": 50, "season_id": 1288},
]
STATUSES = ("finished", "inplay")
PLAYER_FIELDS = [
    "minutes_played", "rating", "touches", "goals", "goal_assist", "expected_goals", "expected_assists",
    "total_shots", "shots_on_target", "key_pass", "total_pass", "accurate_pass", "total_long_balls",
    "accurate_long_balls", "total_cross", "accurate_cross", "total_contest", "won_contest", "duel_won",
    "duel_lost", "aerial_won", "aerial_lost", "total_tackle", "won_tackle", "total_clearance",
    "interception", "ball_recovery", "blocked_scoring_attempt", "dispossessed", "possession_lost",
    "was_fouled", "fouls", "yellow_card", "red_card", "saves", "goals_conceded", "punches",
]
CSV_FIELDS = [
    "liga", "jogo", "data", "estado", "ronda", "resultado", "equipa", "jogador", "posicao",
    *PLAYER_FIELDS, "atualizado_em",
]


def load_local_env() -> None:
    env_file = ROOT.parent / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    for attempt in range(3):
        try:
            response = session.get(url, params=params, timeout=TIMEOUT)
            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
        except (requests.RequestException, ValueError) as exc:
            if attempt == 2:
                print(f"  erro em {url}: {exc}")
            else:
                time.sleep(2 * (attempt + 1))
    return None


def fetch_events(session: requests.Session, league: dict[str, Any]) -> list[dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for status in STATUSES:
        offset = 0
        while True:
            data = get_json(session, BASE_URL + "events/", {
                "league_id": league["league_id"], "season_id": league["season_id"],
                "status": status, "limit": PAGE_SIZE, "offset": offset,
            })
            if not data:
                break
            page = data.get("results", []) or []
            for event in page:
                if event.get("id") is not None:
                    events[str(event["id"])] = event
            if len(page) < PAGE_SIZE or not data.get("next"):
                break
            offset += len(page)
    return sorted(events.values(), key=lambda e: e.get("event_date") or "")


def fetch_rosters(session: requests.Session, events: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Mapeia internamente jogador -> nome/posiÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â§ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â£o/equipa sem exportar IDs."""
    team_names: dict[str, str] = {}
    team_ids: set[str] = set()
    for event in events:
        for key, name in (("home_team_id", event.get("home_team")), ("away_team_id", event.get("away_team"))):
            if event.get(key) is not None:
                team_ids.add(str(event[key]))
                team_names[str(event[key])] = name or ""
    roster: dict[str, dict[str, str]] = {}
    for team_id in sorted(team_ids):
        data = get_json(session, BASE_URL + f"teams/{team_id}/squad/") or {}
        for player in data.get("players", []) or []:
            if player.get("id") is not None:
                roster[str(player["id"])] = {
                    "jogador": player.get("name") or player.get("short_name") or "",
                    "posicao": player.get("position") or "",
                }
    return roster


def read_existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return {row.get("jogo", "") + "|" + row.get("data", "") + "|" + row.get("jogador", ""): row for row in csv.DictReader(fh)}


def make_rows(league: dict[str, Any], event: dict[str, Any], stats: dict[str, Any], roster: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    match = f"{home} - {away}"
    result = ""
    if event.get("home_score") is not None and event.get("away_score") is not None:
        result = f"{event['home_score']}-{event['away_score']}"
    rows = []
    for player in stats.get("player_stats", []) or []:
        player_key = str(player.get("player_id", ""))
        identity = roster.get(player_key, {})
        team_key = str(player.get("team_id", ""))
        team = home if team_key == str(event.get("home_team_id")) else away
        row = {
            "liga": league["name"], "jogo": match, "data": event.get("event_date", ""),
            "estado": event.get("status", ""), "ronda": event.get("round_name") or event.get("round_number") or "",
            "resultado": result, "equipa": team, "jogador": identity.get("jogador", ""),
            "posicao": identity.get("posicao", ""),
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
        }
        row.update({field: player.get(field, "") if player.get(field) is not None else "" for field in PLAYER_FIELDS})
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)



def fetch_player_stats_fast(event_id: Any, headers: dict[str, str]) -> dict[str, Any]:
    for attempt in range(2):
        try:
            response = requests.get(BASE_URL + f"events/{event_id}/player-stats/", headers=headers, timeout=TIMEOUT)
            if response.status_code == 429:
                time.sleep(2)
                continue
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
        except (requests.RequestException, ValueError):
            if attempt == 0:
                time.sleep(1)
    return {}
def main() -> int:
    load_local_env()
    api_key = os.getenv("BZZOIRO_API") or os.getenv("bzzoiro_api")
    if not api_key:
        raise SystemExit("NÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â£o encontrei bzzoiro_api/BZZOIRO_API no .env")
    session = requests.Session()
    session.headers.update({"Authorization": "Token " + api_key, "Accept": "application/json"})

    for league in LEAGUES:
        path = ROOT / league["file"]
        existing = read_existing(path)
        events = fetch_events(session, league)
        roster = fetch_rosters(session, events)
        print(f"{league['name']}: {len(events)} jogos; {len(roster)} jogadores identificados")
        headers = {"Authorization": "Token " + api_key, "Accept": "application/json"}
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_player_stats_fast, event["id"], headers): event for event in events}
            for index, future in enumerate(as_completed(futures), 1):
                event = futures[future]
                for row in make_rows(league, event, future.result(), roster):
                    key = row["jogo"] + "|" + row["data"] + "|" + row["jogador"]
                    existing[key] = row
                if index % 100 == 0:
                    print(f"  stats: {index}/{len(events)} jogos", flush=True)
        write_csv(path, sorted(existing.values(), key=lambda r: (r.get("data", ""), r.get("jogo", ""), r.get("jogador", ""))))
        print(f"  gravado: {path.name} ({len(existing)} linhas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
