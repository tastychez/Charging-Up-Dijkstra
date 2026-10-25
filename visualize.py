"""Plot the street graph (intersections and roads), or the charger graph.

Usage:
    python visualize.py
    python visualize.py --region boston --roads all
    python visualize.py --region dallas-boston --roads route        # full street graph, all 17 states
    python visualize.py --region dallas-boston --chargers           # full charger graph for a 250 mile range
    python visualize.py --region dallas-boston --chargers --range 150 --near "St. Louis, MO"
    python visualize.py --region dallas-boston --around "Nashville, TN" --miles 15   # zoom in to see the intersections
    python visualize.py --region dallas-boston --around "Nashville, TN" --with-chargers  # chargers drawn on top
    python visualize.py --region dallas-boston --chargers --around "Boston, MA" --miles 5   # charger graph close-up
    python visualize.py --region dallas-boston --within "Boston, MA"              # the whole city of Boston
    python visualize.py --region dallas-boston --chargers --within "Boston, MA"
    python visualize.py --region dallas-boston --within MA                        # all of Massachusetts
    python visualize.py --region dallas-boston --chargers --within MA
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import patheffects
import numpy as np
import osmnx as ox
import shapely
from matplotlib.collections import LineCollection

from charger_graph import load_charger_legs
from data import (CITIES, DATA_DIR, ROAD_LEVELS, ROUTES, STATE_CODES, load_chargers, load_state_borders, load_street_graph,
                  region_states, snap_chargers)
from trip import BUFFER, geocode

FIGURE_DIR = Path(__file__).parent / "figures"
CHARGER_COLOR = "#1a56db"
# Where to write each state's code on a route's charger graph, as
# (label lon/lat, lon/lat the thin line points to). Labels sit in the empty
# space around the chargers so they don't cover the graph.
STATE_LABELS = {
    "dallas-boston": {
        "TX": ((-103.8, 30.4), None), "OK": ((-101.0, 36.75), None),
        "AR": ((-91.4, 32.3), (-92.3, 33.6)), "MO": ((-95.3, 40.9), (-93.6, 40.1)),
        "IL": ((-91.3, 41.6), (-90.0, 41.2)), "IN": ((-86.0, 42.9), (-86.2, 41.5)),
        "OH": ((-82.3, 42.6), (-82.5, 41.2)), "TN": ((-87.8, 34.3), (-87.3, 35.3)),
        "KY": ((-83.3, 37.9), None), "VA": ((-79.0, 35.5), (-79.0, 36.8)),
        "WV": ((-80.4, 38.7), None), "PA": ((-77.9, 41.6), None),
        "MD": ((-75.0, 37.6), (-76.6, 39.0)), "NJ": ((-73.2, 39.5), (-74.4, 40.1)),
        "NY": ((-77.0, 44.7), (-76.0, 43.2)), "CT": ((-71.6, 40.6), (-72.7, 41.5)),
        "MA": ((-69.9, 41.5), (-71.8, 42.3)),
    },
    "buffalo-springfield": {
        "MO": ((-93.5, 41.0), (-92.5, 39.6)), "IL": ((-91.3, 42.0), (-89.6, 41.0)),
        "IN": ((-86.6, 37.3), (-86.3, 39.0)), "OH": ((-82.6, 37.9), (-82.6, 38.8)),
        "PA": ((-77.5, 41.2), None), "NY": ((-73.0, 44.6), (-74.5, 43.8)),
    },
}
# The charger whose edges are highlighted in orange on each route's charger graph.
ROUTE_HIGHLIGHT = {"dallas-boston": "Nashville, TN", "buffalo-springfield": "Columbus, OH"}
# Start and end of each route, with where their labels go.
ROUTE_ENDS = {
    "buffalo-springfield": [("Buffalo, NY", "Buffalo (start)", (-78.9, 44.0)),
                            ("Springfield, MO", "Springfield (end)", (-93.3, 36.2))],
    "dallas-boston": [("Dallas, TX", "Dallas (start)", (-101.3, 34.0)),
                      ("Boston, MA", "Boston (end)", (-70.6, 43.9))],
}
EDGE_COLOR = "#7c8591"


def emptier_corner(ax, xs, ys):
    """"lower left" or "lower right", whichever bottom corner of the map has fewer points, for the legend."""
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    xs, ys = np.asarray(xs), np.asarray(ys)
    bottom = ys < y0 + (y1 - y0) / 3
    left = np.sum(bottom & (xs < x0 + (x1 - x0) / 2))
    return "lower left" if left < np.sum(bottom) - left else "lower right"


def plot_network(G, title, out_path, chargers=None, zoomed=False, outline=None):
    """Draw the street graph. `chargers`, if given, are drawn on top with a short
    line to the intersection each one was matched to. `outline` is a faint place boundary."""
    fig, ax = ox.plot_graph(
        G, show=False, close=False, bgcolor="white",
        node_size=12 if zoomed else 2 if len(G) < 50_000 else 0, node_color="#5f6368",
        edge_color="#9aa0a6" if zoomed else "#c0c4c8", edge_linewidth=1.2 if zoomed else 0.6,
        figsize=(10, 10),
    )

    if outline is not None:
        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        outline.boundary.plot(ax=ax, color="#9aa0a6", linewidth=0.8, linestyle="--", zorder=0)
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
    ax.scatter([], [], s=12, color="#5f6368",
               label=f"Intersections ({len(G):,})" if zoomed or len(G) < 50_000
               else f"Intersections ({len(G):,}, too many to draw at this scale)")
    ax.plot([], [], color="#9aa0a6", label=f"Road segments ({len(G.edges):,})")
    if chargers is not None:
        for _, row in chargers.iterrows():
            node = G.nodes[row["node"]]
            ax.plot([row["longitude"], node["x"]], [row["latitude"], node["y"]],
                    color="#1a73e8", linewidth=0.5, alpha=0.6, zorder=3)
        ax.scatter(chargers["longitude"], chargers["latitude"], s=14,
                   color="#1a73e8", edgecolor="white", linewidth=0.4,
                   zorder=4, label=f"DC fast chargers ({len(chargers)})")

    ax.set_title(title, fontsize=13)
    xs, ys = zip(*((d["x"], d["y"]) for _, d in G.nodes(data=True)))
    ax.legend(loc=emptier_corner(ax, xs, ys), frameon=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_charger_graph(stations, legs, near, usable_miles, title, out_path, G=None, borders=None,
                       labels=None, ends=None):
    """Draw every leg of the charger graph as a straight line between two chargers.

    `near`: highlight the legs out of the charger closest to this place (None for no highlight).
    `G`: roads drawn faintly underneath (used for close-ups).
    `borders`: faint state outlines drawn underneath.
    `labels`: {text: ((lon, lat) of the label, (lon, lat) the arrow points to or None)}.
    `ends`: [(place, text)] for the start and end of the trip, marked on the map."""
    zoomed = G is not None
    fig, ax = plt.subplots(figsize=(10, 10) if zoomed else (14, 9))
    if zoomed:
        roads = [[(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
                 if "geometry" not in d else list(d["geometry"].coords) for u, v, d in G.edges(data=True)]
        ax.add_collection(LineCollection(roads, colors="#eceef1", linewidths=0.8, zorder=0))
    lons, lats = stations["longitude"].to_numpy(), stations["latitude"].to_numpy()
    xy = np.column_stack([lons, lats])

    # Most legs go both ways, so draw each pair of chargers once. The more lines
    # there are, the fainter each one is drawn, so dense maps don't turn solid.
    pairs = np.unique(np.sort(legs[["source", "target"]].to_numpy(), axis=1), axis=0)
    ax.add_collection(LineCollection(np.stack([xy[pairs[:, 0]], xy[pairs[:, 1]]], axis=1),
                                     colors=EDGE_COLOR, linewidths=0.8 if len(pairs) < 5_000 else 0.15,
                                     alpha=0.5 if len(pairs) < 5_000 else max(0.04, 15 / np.sqrt(len(pairs))),
                                     rasterized=True, zorder=1))
    ax.scatter(lons, lats, s=36 if len(stations) < 100 else 8 if zoomed else 3, color=CHARGER_COLOR,
               edgecolor="white", linewidth=0.6 if len(stations) < 100 else 0, zorder=2,
               label=f"Chargers, the vertices ({len(stations):,})")
    ax.plot([], [], color=EDGE_COLOR, linewidth=1.5, label=f"One-charge legs, the edges ({len(legs):,})")

    note = "Lines are drawn straight, but every edge's miles come from the roads."
    if len(legs) == len(stations) * (len(stations) - 1):
        note = f"These chargers are all close together, so every pair is joined.\n{note}"
    if near:
        lat, lon = geocode(near)
        hub = int(np.argmin(ox.distance.great_circle(lat, lon, lats, lons)))
        reach = legs.loc[legs["source"] == hub, "target"].to_numpy()
        city = stations["city"].iloc[hub]
        ax.add_collection(LineCollection([(xy[hub], xy[v]) for v in reach], colors="#e8710a",
                                         linewidths=0.4, alpha=0.5, zorder=3))
        ax.scatter(lons[reach], lats[reach], s=12 if zoomed else 4, color="#e8710a", zorder=4,
                   label=f"The {len(reach):,} chargers it can reach on one charge")
        ax.scatter(lons[hub], lats[hub], s=90 if zoomed else 70, marker="*", color="#202124",
                   edgecolor="white", linewidth=0.6, zorder=5, label=f"One charger in {city}")
        note = f"Orange shows one charger's edges, every charger a car leaving {city} can reach.\n{note}"

    ax.set_aspect(1 / np.cos(np.radians(lats.mean())))
    ax.autoscale()
    # Keep the view on the chargers, so whole states (all of Texas) don't zoom the map out.
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    if borders is not None:
        borders.boundary.plot(ax=ax, color="#9aa0a6", linewidth=0.6, alpha=0.6, zorder=0)
    for text, (spot, target) in (labels or {}).items():
        ax.annotate(text, target or spot, xytext=spot, ha="center", va="center", fontsize=9,
                    color="#80868b", zorder=6,
                    path_effects=[patheffects.withStroke(linewidth=2.5, foreground="white")],
                    arrowprops=None if target is None else
                    {"arrowstyle": "-", "color": "#bdc1c6", "linewidth": 0.6, "shrinkA": 6, "shrinkB": 0})
    for (place, text, spot), color in zip(ends or [], ("#188038", "#c5221f")):
        lat, lon = geocode(place)
        ax.scatter(lon, lat, s=60, marker="s", color=color, edgecolor="white", linewidth=0.8, zorder=7)
        ax.annotate(text, (lon, lat), xytext=spot, ha="center", va="center", fontsize=11,
                    fontweight="bold", color=color, zorder=7,
                    arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.8, "shrinkA": 8, "shrinkB": 4})
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_axis_off()
    subtitle = (f"An edge joins two chargers when the drive between them fits on one charge "
                f"(at most {usable_miles:.0f} road miles).\n{note}")
    ax.set_title(title, fontsize=13, pad=16 + 12 * (subtitle.count("\n") + 1))
    ax.annotate(subtitle, (0.5, 1), xycoords="axes fraction", xytext=(0, 6), textcoords="offset points",
                ha="center", va="bottom", fontsize=9, color="#5f6368")
    legend = ax.legend(loc=emptier_corner(ax, lons, lats), frameon=True, fontsize=9)
    for handle, label in zip(legend.legend_handles, legend.get_texts()):
        if hasattr(handle, "set_sizes"):
            handle.set_sizes([90 if label.get_text().startswith("One charger") else 30])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def crop_box(place, miles):
    """Return a function that says whether (lat, lon) is within `miles` of `place` east-west and north-south."""
    lat, lon = geocode(place)
    dlat = miles / 69
    dlon = dlat / np.cos(np.radians(lat))
    return lambda y, x: abs(y - lat) <= dlat and abs(x - lon) <= dlon


def place_outline(place):
    """The official boundary of a place (e.g. the city of Boston) from OpenStreetMap, cached in data/."""
    import geopandas as gpd

    path = DATA_DIR / f"outline_{slug(place)}.geojson"
    if not path.exists():
        ox.geocode_to_gdf(place).to_file(path)
    return gpd.read_file(path)


def crop_area(args):
    """For a close-up, return (inside, title text, file name part, outline). `inside(lat, lon)`
    says whether a point is in the close-up. Returns None when the whole region is drawn."""
    if args.within in STATE_CODES.values():
        outline = load_state_borders([args.within])
        shape = outline.geometry.union_all()
        inside = lambda y, x: bool(shapely.contains_xy(shape, x, y))
        state = outline["NAME"].iloc[0]
        return inside, state, slug(state), outline
    if args.within:
        outline = place_outline(args.within)
        shape = outline.geometry.union_all()
        inside = lambda y, x: bool(shapely.contains_xy(shape, x, y))
        return inside, f"{args.within} (whole city)", f"{slug(args.within)}_city", outline
    if args.around:
        return (crop_box(args.around, args.miles), f"{args.around}, {area_label(args.miles)},",
                f"{slug(args.around)}_{args.miles:g}mi", None)
    return None


def area_label(miles):
    """How a close-up's crop is described in titles, e.g. "10 x 10 mile area"."""
    return f"{2 * miles:g} x {2 * miles:g} mile area"


def slug(place):
    return place.split(",")[0].lower().replace(" ", "-")


def region_title(region):
    name = region.replace("-", " ").title()
    if region in ROUTES:
        name = region.replace("-", " to ").title().replace(" To ", " to ")
    if region in CITIES:
        name += " area"
    return name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="massachusetts",
                        help="Geofabrik state name (massachusetts), a city in CITIES (boston) or a route in ROUTES (dallas-boston)")
    parser.add_argument("--states", nargs="+",
                        help="State codes for chargers, e.g. MA RI (defaults to the states in the region)")
    parser.add_argument("--roads", choices=list(ROAD_LEVELS),
                        help="highways = interstates and highways, major = also main roads, "
                             "route = also secondary roads, all = every drivable street. "
                             "Defaults to route for --chargers and for routes like dallas-boston, major otherwise")
    parser.add_argument("--chargers", action="store_true",
                        help="draw the charger graph instead of the street graph")
    parser.add_argument("--with-chargers", action="store_true",
                        help="draw the chargers on top of the street graph")
    parser.add_argument("--around", help="zoom in around this place, e.g. \"Boston, MA\" (works with --chargers too)")
    parser.add_argument("--within", help="draw only what is inside this place's boundary: a city like \"Boston, MA\" "
                                         "or a state code like MA (works with --chargers too)")
    parser.add_argument("--miles", type=float, default=15, help="for --around, how far to show in each direction (5 gives a 10 x 10 mile square)")
    parser.add_argument("--range", type=int, default=250, help="car range in miles, for --chargers")
    parser.add_argument("--near",
                        help="for --chargers, highlight the legs out of the charger closest to this place "
                             "(defaults to a charger in the middle of a whole route, no highlight for close-ups)")
    args = parser.parse_args()

    if args.roads is None:
        args.roads = "route" if args.chargers or args.region in ROUTES else "major"
    road_types = ROAD_LEVELS[args.roads]
    FIGURE_DIR.mkdir(exist_ok=True)
    if args.chargers:
        usable = args.range * BUFFER
        stations, legs = load_charger_legs(args.region, usable, road_types)
        out_path = FIGURE_DIR / f"chargers_{args.region}_{args.range}mi.png"
        title = f"{region_title(args.region)} charger graph, {args.range} mile range"
        G, borders, labels, ends = None, None, None, None
        area = crop_area(args)
        if area:
            inside, name, part, borders = area
            keep = np.array([inside(y, x) for y, x in zip(stations["latitude"], stations["longitude"])])
            renumber = np.full(len(stations), -1)
            renumber[keep] = np.arange(keep.sum())
            legs = legs[keep[legs["source"]] & keep[legs["target"]]].assign(
                source=lambda d: renumber[d["source"]], target=lambda d: renumber[d["target"]])
            stations = stations[keep].reset_index(drop=True)
            G = load_street_graph(args.region, road_types)
            G = G.subgraph([n for n, d in G.nodes(data=True) if inside(d["y"], d["x"])])
            out_path = FIGURE_DIR / f"chargers_{part}_{args.range}mi.png"
            title = f"{name.rstrip(',')} charger graph, {args.range} mile range"
        else:
            borders = load_state_borders(region_states(args.region))
            labels = {code: spots for code, spots in STATE_LABELS.get(args.region, {}).items()}
            ends = ROUTE_ENDS.get(args.region)
            args.near = args.near or ROUTE_HIGHLIGHT.get(args.region)
        print(f"Charger graph: {len(stations):,} charger locations, {len(legs):,} legs "
              f"of at most {usable:.0f} miles")
        plot_charger_graph(stations, legs, args.near, usable, title, out_path, G, borders, labels, ends)
        print(f"Saved {out_path}")
        return

    G = load_street_graph(args.region, road_types)
    chargers = None
    if args.with_chargers:
        chargers = load_chargers(args.states or region_states(args.region))
        if args.region in CITIES:
            west, south, east, north = CITIES[args.region][1]
            chargers = chargers[chargers["longitude"].between(west, east)
                                & chargers["latitude"].between(south, north)]
        chargers = snap_chargers(G, chargers)
    area = crop_area(args)
    outline = None
    if area:
        inside, name, part, outline = area
        G = G.subgraph([n for n, d in G.nodes(data=True) if inside(d["y"], d["x"])]).copy()
        if chargers is not None:
            chargers = chargers[[inside(y, x) for y, x in zip(chargers["latitude"], chargers["longitude"])]]

    # Count each two-way road once, not once per direction.
    total_miles = sum(d["miles"] for _, _, d in ox.convert.to_undirected(G).edges(data=True))
    print(f"Street graph: {len(G.nodes):,} intersections, {len(G.edges):,} road segments, "
          f"{total_miles:,.0f} miles of road")
    if chargers is not None:
        print(f"Chargers on the map: {len(chargers)}")

    out_path = FIGURE_DIR / f"network_{args.region}_{args.roads}.png"
    region_name = region_title(args.region)
    if area:
        out_path = FIGURE_DIR / f"network_{part}.png"
        region_name = name
    road_label = {"highways": "highways", "major": "major roads", "route": "highways, main and secondary roads",
                  "all": "every street"}[args.roads]
    title = f"{region_name} street graph, {road_label}"
    if chargers is not None:
        out_path = out_path.with_name(out_path.stem + "_with_chargers.png")
        title += " and DC fast chargers"
    plot_network(G, title, out_path, chargers, zoomed=bool(area), outline=outline)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
