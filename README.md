# Charging-Up-Dijkstra-and-A*
Charging Up Dijkstra: Planning EV Road Trips with Shortest-Path Algorithms

## Results

Dijkstra and A* on two real trips, 200-mile range (80% of a 250-mile Model Y). All three
algorithms find the same shortest route: Dallas → Boston 1,737.8 miles with 10 stops,
Buffalo → Springfield 931.7 miles with 5 stops. Details in [Dijkstra/README.md](Dijkstra/README.md#dijkstra-vs-a).

| Trip | Algorithm | Nodes expanded (chargers finalized before reaching the destination) | Fewer nodes expanded than Dijkstra (1 − A* ÷ Dijkstra) | Median search time (101 runs) |
|---|---|---|---|---|
| Dallas → Boston | Dijkstra | 4,817 | – | 169 ms |
| Dallas → Boston | A* Haversine | 3,246 | 33% | 132 ms |
| Dallas → Boston | A* Scaled Manhattan | 4,177 | 13% | 166 ms |
| Buffalo → Springfield | Dijkstra | 3,868 | – | 143 ms |
| Buffalo → Springfield | A* Haversine | 740 | 81% | 19 ms |
| Buffalo → Springfield | A* Scaled Manhattan | 1,021 | 74% | 26 ms |

## About

We find the shortest route in miles between two places for an electric car that
has to stop at DC fast chargers along the way. The main example is Dallas, TX to
Boston, MA.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Quick start

```bash
.venv/bin/python charger_graph.py                          # build the street graph and charger graph (first run downloads 17 states)
.venv/bin/python trip.py "Dallas, TX" "Boston, MA"          # plan a trip with a 250 mile range
.venv/bin/python trip.py "Dallas, TX" "Boston, MA" --range 150
.venv/bin/python trip.py "Dallas, TX" "Boston, MA" --algorithm astar   # same route, found with our A*
.venv/bin/python compare_algorithms.py "Dallas, TX" "Boston, MA"       # our Dijkstra vs our A* vs NetworkX
.venv/bin/python shortest_trip.py "Dallas, TX" "Boston, MA"            # same shortest route, drawn on a map
.venv/bin/python check_graphs.py                            # check every part of the graphs (should print "All checks passed")
```

Second example, Buffalo, NY to Springfield, MO, on its own six-state map (NY PA OH IN IL MO).
On the full Dallas to Boston map the same trip gives the same answer (5 stops, 931.7 miles at 250 miles of range).

```bash
.venv/bin/python charger_graph.py --region buffalo-springfield
.venv/bin/python trip.py "Buffalo, NY" "Springfield, MO" --region buffalo-springfield
.venv/bin/python check_graphs.py --region buffalo-springfield --trip "Buffalo, NY" "Springfield, MO"
.venv/bin/python visualize.py --region buffalo-springfield              # street graph
.venv/bin/python visualize.py --region buffalo-springfield --chargers   # charger graph
```

Smaller test region (builds in about a minute):

```bash
.venv/bin/python trip.py "Pittsfield, MA" "Provincetown, MA" --region massachusetts --range 80
.venv/bin/python check_graphs.py --region massachusetts
```

## The two graphs

**Street graph** (`data.load_street_graph`). Vertices are intersections and edges
are road segments weighted by miles. It keeps interstates, highways, main roads and
secondary roads. Secondary roads matter because highway exit ramps end on them.
With highways only, about half the intersections were dead ends.

The graph is cleaned so routing can never get stuck:
- Only the largest strongly connected piece is kept, so every intersection can be reached from every other one.
- Roads that loop back to the same intersection are removed.
- `data.routing_graph(G)` gives a simple directed graph with at most one road
  between two intersections (the shortest one). Use this one for Dijkstra and A*.

**Charger graph** (`charger_graph.load_charger_graph`). Vertices are charger
locations. An edge u -> v means the car can drive from charger u to charger v on one
charge. The weight is the miles of that leg:

```
miles = snap(u) + road miles from u's intersection to v's intersection + snap(v)
```

`snap(c)` is the straight-line distance from a charger to the intersection it was
matched to. Counting it on the way in and on the way out means each charging stop
adds 2 x snap(c) miles, so chargers that are out of the way cost extra. A leg is only
allowed if it uses at most 80 percent of the car's range.

The road miles between chargers are computed once with SciPy's published Dijkstra
(`scipy.sparse.csgraph.dijkstra`) and saved, for every leg up to 240 miles
(a 300 mile range x 80 percent).

**Trip** (`trip.plan_trip`). Combines both graphs:
1. Looks up the start and end with OpenStreetMap's place search and matches each to its nearest intersection.
2. Adds START and END to a copy of the charger graph, connected to every charger the car can reach.
3. Finds the shortest path in miles from START to END. The vertices on it are the
   charging stops.
4. Turns each leg back into the actual roads on the street graph and draws the map in `figures/`.

## Our Dijkstra and A*

`search.py` has our own `dijkstra_path` and `astar_path`. Both have the same signature
as `networkx.dijkstra_path(graph, source, target, weight)`, so they work on the street
graph, the charger graph and the trip graph. `trip.plan_trip` uses our Dijkstra by
default; `--algorithm astar` or `--algorithm networkx` picks another one.

```python
import search, trip

trip.plan_trip("Dallas, TX", "Boston, MA", range_miles=250)                              # our Dijkstra
trip.plan_trip("Dallas, TX", "Boston, MA", range_miles=250, find_path=search.astar_path) # our A*
```

**A\*'s guess.** Every vertex has coordinates, and no road is shorter than the
straight line between its ends. So the straight-line miles to the target never
overestimates, and A\* finds the same shortest route as Dijkstra.

**Results** (`compare_algorithms.py`, Dallas to Boston, 4,973 vertices). All three
algorithms find the same shortest route; A\* expands about a third fewer vertices.

| Range | Miles | Stops | Our Dijkstra | Our A\* | NetworkX Dijkstra |
|---|---|---|---|---|---|
| 150 | 1,739.9 | 18 | 4,816 vertices, 680 ms | 3,229 vertices, 614 ms | 996 ms |
| 250 | 1,737.8 | 10 | 4,817 vertices, 823 ms | 3,246 vertices, 597 ms | 599 ms |
| 300 | 1,737.6 | 8 | 4,817 vertices, 991 ms | 3,246 vertices, 768 ms | 774 ms |

Times are the fastest of 3 runs on an Apple laptop, after the graph is loaded.
`check_graphs.py` checks that our Dijkstra and A\* match NetworkX on every test trip.

**Results for both trips** (250 mile range, so legs of at most 200 miles). Dallas to
Boston uses the Dallas to Boston graph (4,973 vertices), Buffalo to Springfield its own
graph (2,115 vertices). We compare two guesses for A\*:

- **Haversine**: the straight-line (great-circle) miles to the target.
- **Scaled Manhattan**: north/south miles + east/west miles to the target, times a
  scale α. Plain Manhattan is longer than the straight line, so it can overestimate
  (it does on 709,115 legs of the Dallas to Boston graph). α is the largest number
  that makes the guess consistent on every leg of the graph: 0.708 for Dallas to
  Boston, 0.701 for Buffalo to Springfield (`prepare_heuristic` in `heuristics.py`
  on the `david-astar` branch).

All four searches find the same shortest route.

| Trip | Straight line (mi) | Route (mi) | Charging stops | Algorithm | Expanded | Fewer than Dijkstra | Time (ms) | Speedup vs Dijkstra |
|---|---|---|---|---|---|---|---|---|
| Dallas, TX → Boston, MA | 1,549 | 1,737.8 | 10 | Our Dijkstra | 4,817 | - | 523 | 1.0x |
| | | | | A\* Haversine | 3,246 | 33% | 424 | 1.2x |
| | | | | A\* Scaled Manhattan | 4,177 | 13% | 505 | 1.0x |
| | | | | NetworkX Dijkstra | - | - | 439 | - |
| Buffalo, NY → Springfield, MO | 856 | 931.7 | 5 | Our Dijkstra | 2,060 | - | 151 | 1.0x |
| | | | | A\* Haversine | 735 | 64% | 64 | 2.4x |
| | | | | A\* Scaled Manhattan | 895 | 57% | 68 | 2.2x |
| | | | | NetworkX Dijkstra | - | - | 129 | - |

Times are the fastest of 3 runs, after the graph is loaded. NetworkX doesn't report
how many vertices it expands.

Haversine beats Scaled Manhattan on both trips. Manhattan is between 1 and 1.41 times the
straight line, so after scaling by about 0.7 it is between 0.7 and 1 times the straight
line: never a better guess than Haversine, and only as good on an exact diagonal. A
smaller guess rules out fewer chargers. Both guesses help least on Dallas to
Boston: the map was cut around that route, so nearly every charger lies on the way.
They help more on Buffalo to Springfield, where Dijkstra spreads out in every
direction and A\* heads toward the target.

## Maps

```bash
.venv/bin/python visualize.py                                  # Massachusetts major roads
.venv/bin/python visualize.py --region boston --roads all      # every street in the Boston area
.venv/bin/python visualize.py --region dallas-boston                       # full street graph, all 17 states
.venv/bin/python visualize.py --region dallas-boston --around "Nashville, TN" --miles 12   # zoom in to see the intersections
.venv/bin/python visualize.py --region dallas-boston --with-chargers       # chargers drawn on top of the streets
.venv/bin/python visualize.py --region dallas-boston --around "Boston, MA" --miles 5              # Boston road close-up
.venv/bin/python visualize.py --region dallas-boston --chargers --around "Boston, MA" --miles 5   # Boston charger close-up
.venv/bin/python visualize.py --region dallas-boston --within "Boston, MA"                # the whole city of Boston
.venv/bin/python visualize.py --region dallas-boston --chargers --within "Boston, MA"
.venv/bin/python visualize.py --region dallas-boston --within MA                          # all of Massachusetts
.venv/bin/python visualize.py --region dallas-boston --chargers --within MA
.venv/bin/python visualize.py --region dallas-boston --chargers            # full charger graph, 250 mile range
.venv/bin/python visualize.py --region dallas-boston --chargers --range 150 --near "St. Louis, MO"
```

The charger graph map draws every leg as a straight line between two chargers and
shows in orange the legs out of the charger closest to `--near`.

## Data

- **Roads:** OpenStreetMap state files from [Geofabrik](https://download.geofabrik.de/north-america/us.html),
  filtered with pyosmium and turned into a graph with [OSMnx](https://osmnx.readthedocs.io).
  The `dallas-boston` region joins 17 states so it covers the three main ways to
  drive from Dallas to Boston (through Arkansas and Tennessee, through Oklahoma and
  Missouri, or through Kentucky). Each state file is downloaded, cut down to the
  roads we keep and then deleted to save disk space.
- **Chargers:** public DC fast chargers from the Department of Energy's
  [Alternative Fuels Data Center](https://afdc.energy.gov/stations) API. The
  default `DEMO_KEY` is rate limited. Get a free key at
  https://developer.nlr.gov/signup and put it in a `.env` file in the repo
  folder as `AFDC_API_KEY=your_key`. The `.env` file is gitignored so the key
  never gets pushed.
- Each charger is matched to its nearest intersection. Chargers more than 2 miles
  from the road network are dropped. If several chargers share an intersection,
  the closest one is kept.
- Everything downloaded or computed is cached in `data/` (gitignored).

## Files

- `data.py` downloads, caches and cleans the road and charger data
- `charger_graph.py` builds and loads the charger graph
- `search.py` our own Dijkstra and A*
- `trip.py` plans a trip on both graphs and draws it
- `compare_algorithms.py` compares our Dijkstra, our A* and NetworkX on the full trip graph
- `shortest_trip.py` plans the fewest-miles route and draws it next to the fewest-stops one
- `check_graphs.py` checks that every part of the graphs is correct
- `visualize.py` plots a road network with chargers on top
