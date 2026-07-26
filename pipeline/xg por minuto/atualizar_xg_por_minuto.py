"""Descarrega e atualiza os jogos e o xG minuto a minuto das quatro ligas.

Uso:
    python "xg por minuto/atualizar_xg_por_minuto.py"

A chave é lida de bzzoiro_api/BZZOIRO_API no .env e nunca é gravada nos CSVs.
"""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
BASE_URL = os.getenv("BZZOIRO_BASE_URL", "https://sports.bzzoiro.com/api/v2/").rstrip("/") + "/"
TIMEOUT = 45
PAGE_SIZE = 200

LEAGUES = [
    {"name": "Brasil Serie A 2026", "file": "brasil_serie_a_2026.csv", "league_id": 9, "season_id": 28},
    {"name": "MLS 2026", "file": "mls_2026.csv", "league_id": 18, "season_id": 158},
    {"name": "Liga Mexicana 2026/2027", "file": "liga_mexicana_2026_2027.csv", "league_id": 19, "season_id": 1309},
    {"name": "Coreia do Sul 2026", "file": "coreia_do_sul_2026.csv", "league_id": 50, "season_id": 1288},
]

STATUSES = ("finished", "inplay", "notstarted")
CSV_FIELDS = [
    "liga", "jogo", "data", "estado", "ronda", "resultado",
    "xg_home", "xg_away", "xg_total",
    "xg_por_minuto", "shotmap", "momentum", "average_positions",
    "estatisticas_home", "estatisticas_away", "atualizado_em",
]


def load_local_env() -> None:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def compact(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def get_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    for attempt in range(3):
        try:
            response = session.get(url, params=params, timeout=TIMEOUT)
            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"results": data}
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
            data = get_json(
                session,
                BASE_URL + "events/",
                {"league_id": league["league_id"], "season_id": league["season_id"],
                 "status": status, "limit": PAGE_SIZE, "offset": offset},
            )
            if not data:
                break
            page = data.get("results", []) or []
            for event in page:
                # O ID é usado apenas internamente para pedir as stats; nunca sai para o CSV.
                if event.get("id") is not None:
                    events[str(event["id"])] = event
            if len(page) < PAGE_SIZE or not data.get("next"):
                break
            offset += len(page)
    return sorted(events.values(), key=lambda e: e.get("event_date") or "")


def extract_xg(stats: dict[str, Any] | None, side: str) -> Any:
    value = (stats or {}).get(side, {})
    xg = value.get("xg", {}) if isinstance(value, dict) else {}
    return xg.get("actual") if isinstance(xg, dict) else ""


def make_row(league: dict[str, Any], event: dict[str, Any], stats: dict[str, Any] | None) -> dict[str, str]:
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    home_xg = extract_xg(stats, "home")
    away_xg = extract_xg(stats, "away")
    total = ""
    if home_xg != "" or away_xg != "":
        total = str(round(float(home_xg or 0) + float(away_xg or 0), 3))
    result = ""
    if event.get("home_score") is not None and event.get("away_score") is not None:
        result = f"{event['home_score']}-{event['away_score']}"
    return {
        "liga": league["name"],
        "jogo": f"{home} - {away}",
        "data": event.get("event_date", ""),
        "estado": event.get("status", ""),
        "ronda": event.get("round_name") or event.get("round_number") or "",
        "resultado": result,
        "xg_home": home_xg,
        "xg_away": away_xg,
        "xg_total": total,
        "xg_por_minuto": compact((stats or {}).get("xg_per_minute", [])),
        "shotmap": compact((stats or {}).get("shotmap", [])),
        "momentum": compact((stats or {}).get("momentum", [])),
        "average_positions": compact((stats or {}).get("average_positions", [])),
        "estatisticas_home": compact((stats or {}).get("stats", {}).get("home", {})),
        "estatisticas_away": compact((stats or {}).get("stats", {}).get("away", {})),
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }


def read_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return {row.get("jogo", "") + "|" + row.get("data", ""): row for row in csv.DictReader(fh)}


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def main() -> int:
    load_local_env()
    api_key = os.getenv("BZZOIRO_API") or os.getenv("bzzoiro_api")
    if not api_key:
        raise SystemExit("Não encontrei bzzoiro_api/BZZOIRO_API no .env")
    session = requests.Session()
    session.headers.update({"Authorization": "Token " + api_key, "Accept": "application/json"})

    for league in LEAGUES:
        path = ROOT / league["file"]
        existing = read_existing(path)
        events = fetch_events(session, league)
        print(f"{league['name']}: {len(events)} jogos encontrados")
        for event in events:
            stats = None
            # Estatísticas só são pedidas para jogos que já começaram.
            if event.get("status") in ("finished", "inplay") and event.get("id") is not None:
                stats = get_json(session, BASE_URL + f"events/{event['id']}/stats/") or {}
            row = make_row(league, event, stats)
            existing[row["jogo"] + "|" + row["data"]] = row
        write_csv(path, sorted(existing.values(), key=lambda r: r.get("data", "")))
        print(f"  gravado: {path.name} ({len(existing)} linhas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
