"""Write the stations and road distances the web demo needs to src/data/boston-dallas.json.

Run from the Dijkstra folder (uses cache/, downloads on the first run):
    .venv/bin/python web/export_data.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from realmap import road_distances  # noqa: E402
from stations import END, START, STATIONS  # noqa: E402

OUT = Path(__file__).parent / "src" / "data" / "boston-dallas.json"

data = {
    "start": START,
    "end": END,
    "stations": [{"name": n, "lat": lat, "lon": lon} for n, (lat, lon) in STATIONS.items()],
    "miles": road_distances(STATIONS),
}
OUT.write_text(json.dumps(data, indent=1))
print(f"{len(STATIONS)} stations written to {OUT}")
