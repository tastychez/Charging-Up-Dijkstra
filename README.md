# Charging-Up-Dijkstra-and-A*
Charging Up Dijkstra: Planning EV Road Trips with Shortest-Path Algorithms

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
.venv/bin/python shortest_trip.py "Dallas, TX" "Boston, MA"            # fewest miles instead of fewest stops
.venv/bin/python check_graphs.py                            # check every part of the graphs (should print "All checks passed")
```

Second example, Buffalo, NY to Springfield, MO, on its own six-state map (NY PA OH IN IL MO).
On the full Dallas to Boston map the same trip gives the same answer (4 stops, 956.1 miles at 250 miles of range).

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
3. Finds the best path from START to END. The vertices on it are the charging stops.
   The best path has the fewest charging stops, and among those the fewest miles.
   To do that, each leg is searched by `cost` = miles + 10,000. The miles we report
   never include the extra 10,000. Dallas to Boston with a 250 mile range takes
   9 stops and 1,774.0 miles this way, compared with 11 stops and 1,773.1 miles
   when only miles count.
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
straight line between its ends, so the straight-line miles to the target never
overestimates. On the trip graph, where every leg also costs 10,000, the guess adds
10,000 for each leg that must still be driven: ceil(straight-line miles / longest leg).
Both guesses are consistent, so A\* finds the same best route as Dijkstra.

**Results** (`compare_algorithms.py`, Dallas to Boston, 4,967 vertices). All three
algorithms find routes of the same weight; A\* expands about half as many vertices.

| Range | Goal | Miles | Stops | Our Dijkstra | Our A\* | NetworkX Dijkstra |
|---|---|---|---|---|---|---|
| 150 | fewest stops | 1,782.4 | 16 | 4,810 vertices, 275 ms | 2,609 vertices, 167 ms | 224 ms |
| 250 | fewest stops | 1,774.0 | 9 | 4,811 vertices, 512 ms | 2,250 vertices, 260 ms | 424 ms |
| 250 | fewest miles | 1,773.1 | 11 | 4,811 vertices, 513 ms | 2,653 vertices, 329 ms | 435 ms |
| 300 | fewest stops | 1,773.0 | 7 | 4,811 vertices, 652 ms | 1,930 vertices, 291 ms | 547 ms |

Times are the fastest of 3 runs on an Apple laptop, after the graph is loaded.
`check_graphs.py` checks that our Dijkstra and A\* match NetworkX on every test trip.

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
