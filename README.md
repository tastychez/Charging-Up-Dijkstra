# Charging-Up-Dijkstra-and-A*
Charging Up Dijkstra: Planning EV Road Trips with Shortest-Path Algorithms

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Visualize the road network and chargers

```bash
.venv/bin/python visualize.py                                  # Massachusetts major roads
.venv/bin/python visualize.py --region boston --roads all      # every street in the Boston area
.venv/bin/python visualize.py --region rhode-island --states RI
```

The figure is saved to `figures/`. The first run for a region downloads that
state's OpenStreetMap file from Geofabrik (about 300 MB for Massachusetts) and
builds the graph, which takes a couple of minutes. Later runs load from the
`data/` cache in seconds.

## Data

- **Roads:** OpenStreetMap state extracts from [Geofabrik](https://download.geofabrik.de/north-america/us.html),
  turned into a graph with [OSMnx](https://osmnx.readthedocs.io). We keep
  motorways, trunk roads and primary roads for statewide graphs, and every
  drivable street for city graphs like Boston. Vertices are intersections and
  edges are road segments with a `miles` attribute.
- **Chargers:** public DC fast chargers from the Department of Energy's
  [Alternative Fuels Data Center](https://afdc.energy.gov/stations) API. The
  default `DEMO_KEY` is rate limited. Get a free key at
  https://developer.nlr.gov/signup and put it in a `.env` file in the repo
  folder as `AFDC_API_KEY=your_key`. The `.env` file is gitignored so the key
  never gets pushed.
- Each charger is snapped to its nearest intersection. Chargers more than
  2 miles from the road network are dropped.

## Files

- `data.py` downloads, caches and combines the road and charger data
- `visualize.py` plots the road network with chargers on top
