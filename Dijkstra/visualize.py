"""Figures on a real map: the best route, the graph at several ranges, the range sweep,
and Dijkstra's search step by step (animated, and as snapshots for a printed report)."""

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from PIL import Image, ImageColor, ImageEnhance

from realmap import ATTRIBUTION, basemap, mercator, road_shape
from stations import END, START, STATIONS

BG, INK, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
GRID, NODE = "#d6d5cf", "#8a8983"
ROUTE, FRONTIER = "#2a78d6", "#eb6834"
HALO = [pe.withStroke(linewidth=2.5, foreground="white")]

# Map frame (south, west, north, east) around every station.
BOUNDS = (31.6, -99.0, 43.4, -69.4)

# Which side of its dot each station's name goes on (default: below), so neighbors don't
# collide. Numbers (distances, mile markers) go on the opposite side.
NAME_SIDE = {START: "right", "Harrisburg, PA": "right", "Hagerstown, MD": "right",
             "Roanoke, VA": "right", "Winchester, VA": "left", "Harrisonburg, VA": "left",
             "McAlester, OK": "left", END: "left"} | dict.fromkeys(
    ["Hartford, CT", "Newburgh, NY", "Scranton, PA", "Hazleton, PA", "Breezewood, PA",
     "Washington, PA", "Columbus, OH", "Indianapolis, IN", "Effingham, IL", "St. Louis, MO",
     "Joplin, MO", "Tulsa, OK", "Wytheville, VA", "Nashville, TN", "Memphis, TN",
     "Little Rock, AR", "Sulphur Springs, TX", "Durant, OK"], "above")
OPPOSITE = {"above": "below", "below": "above", "left": "right", "right": "left"}
PLACEMENT = {  # side: (offset in points, horizontal alignment, vertical alignment)
    "above": ((0, 7), "center", "bottom"), "below": ((0, -7), "center", "top"),
    "left": ((-7, 0), "right", "center"), "right": ((7, 0), "left", "center"),
}

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": NODE, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
})


def xy(name):
    return mercator(*STATIONS[name])


def short(name):
    return name.split(",")[0]


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def improved_text(updates, limit=7):
    """'Natick → 20, Auburn → 46, ...': the neighbors one Dijkstra step improved."""
    parts = [f"{short(v)} → {nd}" for v, nd in updates[:limit]]
    more = len(updates) - limit
    return ", ".join(parts) + (f", and {more} more" if more > 0 else "") or "none"


def side_label(ax, name, text, name_side, **style):
    """Text next to a station: on the name's side, or (name_side=False) on the other side."""
    side = NAME_SIDE.get(name, "below")
    offset, ha, va = PLACEMENT[side if name_side else OPPOSITE[side]]
    return ax.annotate(text, xy(name), xytext=offset, textcoords="offset points",
                       ha=ha, va=va, path_effects=HALO, zorder=8, **style)


def draw_map(ax, zoom=6, names=True):
    """Real map tiles (muted so the data stands out), every station as a gray dot, and
    station names. Returns {station: name label} so callers can hide some of them."""
    south, west, north, east = BOUNDS
    image, extent = basemap(south, west, north, east, zoom)
    muted = ImageEnhance.Color(image).enhance(0.35)
    image = Image.blend(muted, Image.new("RGB", image.size, "white"), 0.25)
    ax.imshow(image, extent=extent, zorder=0)
    (x0, y0), (x1, y1) = mercator(south, west), mercator(north, east)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_axis_off()
    ax.scatter(*zip(*map(xy, STATIONS)), s=16, color=NODE, edgecolor="white", lw=0.8, zorder=4)
    ax.text(0.998, 0.004, ATTRIBUTION, transform=ax.transAxes, ha="right", va="bottom",
            fontsize=6, color=MUTED, path_effects=HALO)
    if not names:
        return {}
    return {name: side_label(ax, name, short(name), True, fontsize=6.5, color=MUTED)
            for name in STATIONS}


def draw_edges(ax, graph, max_miles=float("inf"), alpha=0.25):
    """Graph edges as straight lines (one line per linked pair). Returns the artist."""
    pairs = {tuple(sorted((a, b)))
             for a in graph for b, miles in graph[a].items() if miles <= max_miles}
    lines = [[xy(a), xy(b)] for a, b in pairs]
    return ax.add_collection(LineCollection(lines, colors=NODE, linewidths=0.7, alpha=alpha, zorder=2))


def draw_route(ax, stops, lw=3):
    """The route along the real roads, with a dot at every stop. Returns the artists."""
    artists = []
    for a, b in zip(stops, stops[1:]):
        points = [mercator(lat, lon) for lat, lon in road_shape(STATIONS[a], STATIONS[b])]
        artists += ax.plot(*zip(*points), color=ROUTE, lw=lw, solid_capstyle="round", zorder=6)
    artists.append(ax.scatter(*zip(*map(xy, stops)), s=lw * 20, color=ROUTE, edgecolor="white",
                              lw=1.5, zorder=7))
    return artists


def stop_labels(ax, stops, graph):
    """'Name / mile N' at each stop of a route, meant to replace its plain name label."""
    labels, mile = [], 0
    for i, name in enumerate(stops):
        mile += graph[stops[i - 1]][name] if i else 0
        labels.append(side_label(ax, name, f"{short(name)}\nmile {mile}", True,
                                 fontsize=7.5, fontweight="bold"))
    return labels


def finish(ax, title, note, size=12):
    ax.set_title(title, loc="left", pad=14, fontsize=size)
    ax.text(0, 1.0, note, transform=ax.transAxes, color=MUTED, fontsize=9, va="bottom")


def plot_route(stops, miles, graph, max_range, path):
    """The best route for one range, drawn along the roads actually driven."""
    fig, ax = plt.subplots(figsize=(13, 7.4))
    names = draw_map(ax, zoom=7)
    for stop in stops:
        names[stop].set_visible(False)
    draw_route(ax, stops)
    stop_labels(ax, stops, graph)
    finish(ax, f"Shortest {short(START)} → {short(END)} trip with a {max_range}-mile range",
           f"{miles} miles, {plural(len(stops) - 2, 'charging stop')}")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_range_grid(results, path):
    """One panel per range: the charging graph (gray) and Dijkstra's route (blue)."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 9.4))
    for ax, (max_range, stops, miles, graph) in zip(axes.flat, results):
        draw_map(ax, names=False)
        draw_edges(ax, graph, alpha=0.35)
        edges = sum(len(nbrs) for nbrs in graph.values())
        if stops:
            draw_route(ax, stops, lw=2.2)
            note = f"{miles} mi · {plural(len(stops) - 2, 'stop')} · {edges} edges"
        else:
            note = f"no route · {edges} edges"
        finish(ax, f"Range {max_range} mi", note, size=11)
    fig.suptitle("A longer range adds edges, so the route needs fewer stops and fewer detours",
                 x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_sweep(sweep, chosen_range, path):
    """Total miles and number of stops as the range grows (one panel each, shared x)."""
    feasible = [(r, m, s) for r, m, s in sweep if m is not None]
    ranges, miles, stops = zip(*feasible)
    first = ranges[0]

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    for ax in (top, bottom):
        ax.axvspan(sweep[0][0], first, color=GRID, alpha=0.5, lw=0)
        ax.axvline(chosen_range, color=MUTED, lw=0.8, ls="--")
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.spines[["top", "right"]].set_visible(False)

    top.step(ranges, miles, where="post", color=ROUTE, lw=2)
    top.set_ylabel("Total miles")
    top.text((sweep[0][0] + first) / 2, sum(top.get_ylim()) / 2, "no route\npossible",
             ha="center", va="center", color=MUTED, fontsize=9)
    top.annotate(f"{first} mi range: first feasible\n{miles[0]} mi, {plural(stops[0], 'stop')}",
                 (first, miles[0]), xytext=(60, -2), textcoords="offset points", fontsize=9, va="top",
                 arrowprops={"arrowstyle": "-", "color": MUTED})
    if chosen_range in ranges:
        i = ranges.index(chosen_range)
        top.annotate(f"{chosen_range} mi range: {miles[i]} mi, {plural(stops[i], 'stop')}",
                     (chosen_range, miles[i]), xytext=(8, 18), textcoords="offset points", fontsize=9,
                     arrowprops={"arrowstyle": "-", "color": MUTED})

    bottom.step(ranges, stops, where="post", color=ROUTE, lw=2)
    bottom.set_ylabel("Charging stops")
    bottom.yaxis.set_major_locator(MaxNLocator(integer=True))
    bottom.set_xlabel("Range on a full charge (miles)")

    top.set_title("How battery range changes the shortest route", loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def search_state(trace, step):
    """Replay Dijkstra's trace through `step`: settled distances, all known distances, prev."""
    settled, dist, prev = {}, {START: 0}, {}
    for u, d, updates in trace[:step + 1]:
        settled[u] = d
        for v, nd in updates:
            dist[v], prev[v] = nd, u
    return settled, dist, prev


def draw_search(ax, trace, step):
    """Dijkstra's state right after it settles trace[step]. Returns the artists it adds."""
    settled, dist, prev = search_state(trace, step)
    u, _, updates = trace[step]
    tree = [[xy(prev[v]), xy(v)] for v in settled if v in prev]
    relaxed = [[xy(u), xy(v)] for v, _ in updates]
    frontier = [v for v in dist if v not in settled]

    artists = [
        ax.add_collection(LineCollection(tree, colors=ROUTE, linewidths=1.3, alpha=0.8, zorder=3)),
        ax.add_collection(LineCollection(relaxed, colors=FRONTIER, linewidths=1.8, zorder=3)),
        ax.scatter(*zip(*map(xy, settled)), s=36, color=ROUTE, edgecolor="white", lw=1, zorder=5),
        ax.scatter(*xy(u), s=170, facecolor="none", edgecolor=INK, lw=1.6, zorder=9),
    ]
    if frontier:
        artists.append(ax.scatter(*zip(*map(xy, frontier)), s=36, facecolor="white",
                                  edgecolor=FRONTIER, lw=1.8, zorder=5))
    for v, miles in dist.items():
        artists.append(side_label(ax, v, str(miles), False, fontsize=7,
                                  fontweight="bold" if v in settled else "normal"))
    return artists


def search_legend(ax):
    handles = [
        Line2D([], [], ls="", marker="o", ms=7, color=ROUTE, mec="white",
               label="settled (distance final)"),
        Line2D([], [], ls="", marker="o", ms=7, mfc="white", mec=FRONTIER, mew=1.8,
               label="tentative (in the queue)"),
        Line2D([], [], ls="", marker="o", ms=12, mfc="none", mec=INK, mew=1.5, label="settled this step"),
        Line2D([], [], color=FRONTIER, lw=1.8, label="edges relaxed this step"),
        Line2D([], [], color=ROUTE, lw=1.3, label="shortest-path tree (prev)"),
    ]
    return ax.legend(handles=handles, loc="upper left", fontsize=7, framealpha=0.9, edgecolor=GRID)


def plot_search_snapshots(graph, trace, path):
    """Four moments of the search, for a printed report."""
    n = len(trace)
    fig, axes = plt.subplots(2, 2, figsize=(18, 11))
    for ax, step in zip(axes.flat, [0, n // 3, 2 * n // 3, n - 1]):
        draw_map(ax)
        draw_edges(ax, graph)
        draw_search(ax, trace, step)
        u, d, updates = trace[step]
        finish(ax, f"Step {step + 1} of {n}: settle {u} at {d} mi",
               f"Neighbors whose distance improved: {improved_text(updates)}", size=11)
    search_legend(axes.flat[0])
    fig.suptitle(f"Dijkstra's search: stations settle in order of distance from {short(START)}",
                 x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def animate_search(graph, trace, stops, miles, max_range):
    """The whole story on the real map, one frame at a time:
    1. the stations, 2. drawing the graph, 3. Dijkstra's search, 4. tracing back the route.

    Returns the animation: save it with anim.save(...) or watch it live with plt.show().
    """
    fig, ax = plt.subplots(figsize=(12, 7.2))
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.05, top=0.89)
    names = draw_map(ax)
    title = fig.text(0.01, 0.975, "", fontsize=12, fontweight="bold", va="top")
    note = fig.text(0.01, 0.93, "", fontsize=9, color=MUTED, va="top")
    queue = fig.text(0.01, 0.012, "", fontsize=8.5, color=MUTED, va="bottom")

    thresholds = [round(max_range * i / 5) for i in range(1, 6)]
    frames = ([("map", 0)] * 2
              + [("graph", r) for r in thresholds]
              + [("search", k) for k in range(len(trace))]
              + [("trace", k) for k in range(1, len(stops))]
              + [("done", 0)] * 3)
    dynamic = []

    def update(frame):
        phase, k = frame
        for artist in dynamic:
            artist.remove()
        dynamic.clear()
        queue.set_text("")
        for name, label in names.items():   # the last frame swaps stop names for stop labels
            label.set_visible(phase != "done" or name not in stops)

        if phase == "map":
            title.set_text("1 · The real map")
            note.set_text(f"{len(STATIONS) - 2} Supercharger sites between {START} and {END}")

        elif phase == "graph":
            dynamic.append(draw_edges(ax, graph, max_miles=k, alpha=0.5))
            count = sum(m <= k for nbrs in graph.values() for m in nbrs.values())
            title.set_text("2 · Draw the graph")
            note.set_text(f"Add an edge A → B only if a full charge covers the road distance. "
                          f"Edges up to {k} mi: {count}")

        elif phase == "search":
            dynamic.append(draw_edges(ax, graph))
            dynamic.extend(draw_search(ax, trace, k))
            dynamic.append(search_legend(ax))
            u, d, updates = trace[k]
            settled, dist, _ = search_state(trace, k)
            waiting = sorted((dist[v], short(v)) for v in dist if v not in settled)
            title.set_text(f"3 · Dijkstra step {k + 1} of {len(trace)}: settle {u} at {d} mi")
            note.set_text(f"Neighbors whose distance improved: {improved_text(updates)}")
            queue.set_text("Queue, closest first:  " + "  ·  ".join(f"{v} {m}" for m, v in waiting[:9]))

        else:
            legs = stops if phase == "done" else stops[-k - 1:]
            dynamic.extend(draw_route(ax, legs))
            if phase == "trace":
                title.set_text(f"4 · Trace back from {short(END)}, following prev[]")
                note.set_text(" ← ".join(short(s) for s in reversed(legs)))
            else:
                dynamic.extend(stop_labels(ax, stops, graph))
                title.set_text(f"Shortest route with a {max_range}-mile range: "
                               f"{miles} mi, {plural(len(stops) - 2, 'charging stop')}")
                note.set_text(" → ".join(short(s) for s in stops))
        return dynamic

    return FuncAnimation(fig, update, frames=frames, interval=700, repeat_delay=3000)


class GifWriter(PillowWriter):
    """PillowWriter, but every frame shares one undithered palette that holds the exact data
    colors. The map stays crisp, and unchanged pixels compress away: ~20x smaller files."""

    def finish(self):
        frames = [frame.convert("RGB") for frame in self._frames]
        exact = [ImageColor.getrgb(c) for c in (ROUTE, FRONTIER, INK, MUTED, NODE, BG, "#ffffff")]
        sample = Image.new("RGB", (frames[0].width, 3 * frames[0].height))
        for i, frame in enumerate([frames[0], frames[len(frames) // 2], frames[-1]]):
            sample.paste(frame, (0, i * frame.height))
        palette = Image.new("P", (1, 1))
        palette.putpalette(sample.quantize(256 - len(exact)).getpalette()[:3 * (256 - len(exact))]
                           + [v for rgb in exact for v in rgb])
        frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
        frames[0].save(self.outfile, save_all=True, append_images=frames[1:],
                       duration=int(1000 / self.fps), loop=0)
