"""Read the team's OSRM road matrix, sharing its coordinates and mile rounding.

Reuse Dijkstra/cache/distances.json when it matches. New requests are cached
separately under AStar/cache, so custom endpoints do not replace a teammate's
cache. No straight-line fallback is substituted for missing road distances.
"""

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METERS_PER_MILE = 1609.344


def load_road_miles(coordinates, offline=False):
    """Return {source: {target: rounded_road_miles_or_None}}.

    Distances are along OSRM's fastest routes, matching Dijkstra/realmap.py.
    Whole-mile rounding is retained so algorithms can compare the same data.
    """
    coords = ";".join(f"{lon},{lat}" for lat, lon in coordinates.values())
    key = hashlib.sha256(coords.encode()).hexdigest()[:16]
    private_path = ROOT / "AStar" / "cache" / f"distances_{key}.json"
    candidates = [ROOT / "Dijkstra" / "cache" / "distances.json", private_path]
    table = None
    for path in candidates:
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("coords") == coords:
                table = cached
                print(f"Using cached road distances: {path}")
                break
    if table is None:
        if offline:
            raise ValueError("No matching road-distance cache. Run once without --offline, or use --demo.")
        url = f"https://router.project-osrm.org/table/v1/driving/{coords}?annotations=distance"
        print(f"Fetching one OSRM driving-distance table for {len(coordinates)} locations...", flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "Charging-Up-Dijkstra AStar classroom project"})
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.load(response)
        if payload.get("code") != "Ok" or "distances" not in payload:
            raise ValueError(f"OSRM could not return road distances: {payload.get('message', payload.get('code'))}")
        table = {"coords": coords, "meters": payload["distances"]}
        private_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_text(json.dumps(table), encoding="utf-8")
    rows = table["meters"]
    names = list(coordinates)
    if len(rows) != len(names) or any(len(row) != len(names) for row in rows):
        raise ValueError("The road-distance matrix dimensions do not match the station list.")
    return {source: {target: None if rows[i][j] is None else round(rows[i][j] / METERS_PER_MILE)
                     for j, target in enumerate(names)} for i, source in enumerate(names)}
