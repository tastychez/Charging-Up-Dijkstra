"""Figures on a real map: the best route, routes at several ranges, the range sweep,
and Dijkstra's search step by step (animated, and as snapshots for a printed report).

The network has about 5,000 chargers and millions of edges, far too many to draw or
name one by one. Chargers are small dots, only the route's stops get names, and the
search is shown by color: settled, waiting in the queue, or not reached yet."""

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from PIL import Image, ImageColor, ImageEnhance

from network import END, START, load_network
from realmap import ATTRIBUTION, basemap, mercator, road_shape

BG, INK, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
GRID, NODE = "#d6d5cf", "#8a8983"
ROUTE, FRONTIER = "#2a78d6", "#eb6834"
HALO = [pe.withStroke(linewidth=2.5, foreground="white")]



def use_trip(start, end):
    """Draw the network of the trip from start to end in every figure below."""
    global START, END, COORDS, CITIES, NAMES, VERTICES, XY, INDEX, BOUNDS
    START, END = start, end
    COORDS, CITIES, NAMES, _ = load_network(start, end)
    VERTICES = list(COORDS)
    XY = np.array([mercator(*COORDS[v]) for v in VERTICES])
    INDEX = {v: i for i, v in enumerate(VERTICES)}
    # Map frame (south, west, north, east) around every charger, with a little margin.
    lats, lons = zip(*COORDS.values())
    BOUNDS = (min(lats) - 0.4, min(lons) - 0.6, max(lats) + 0.4, max(lons) + 0.6)


use_trip(START, END)

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": NODE, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
})


def xy(v):
    return XY[INDEX[v]]


def short(v):
    """'Knoxville, TN' for a charger, 'Boston' for an end."""
    return CITIES[v].split(",")[0] if v in (START, END) else CITIES[v]


def plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def draw_map(ax, zoom=5):
    """Real map tiles (muted so the data stands out), every charger as a small gray dot,
    and the start and end."""
    south, west, north, east = BOUNDS
    image, extent = basemap(south, west, north, east, zoom)
    muted = ImageEnhance.Color(image).enhance(0.35)
    image = Image.blend(muted, Image.new("RGB", image.size, "white"), 0.25)
    ax.imshow(image, extent=extent, zorder=0)
    (x0, y0), (x1, y1) = mercator(south, west), mercator(north, east)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_axis_off()
    ax.scatter(*XY.T, s=1.2, color=NODE, lw=0, zorder=2)
    west = min((START, END), key=lambda v: xy(v)[0])
    for v in (START, END):   # each label on the outer side, away from the route
        side = "left" if v == west else "right"
        ax.scatter(*xy(v), s=60, marker="*", color=INK, zorder=9)
        ax.annotate(short(v), xy(v), xytext=(-8 if side == "left" else 8, 0), textcoords="offset points",
                    ha="right" if side == "left" else "left", va="center", fontsize=9,
                    fontweight="bold", path_effects=HALO, zorder=9)
    ax.text(0.998, 0.004, ATTRIBUTION, transform=ax.transAxes, ha="right", va="bottom",
            fontsize=6, color=MUTED, path_effects=HALO)


def draw_route(ax, stops, lw=3, color=ROUTE):
    """The route along the real roads, with a dot at every stop. Returns the artists."""
    artists = []
    for a, b in zip(stops, stops[1:]):
        points = [mercator(lat, lon) for lat, lon in road_shape(COORDS[a], COORDS[b])]
        artists += ax.plot(*zip(*points), color=color, lw=lw, solid_capstyle="round", zorder=6)
    chargers = [v for v in stops if v not in (START, END)]
    if chargers:   # the first trace-back frame is a single leg into the end
        artists.append(ax.scatter(*zip(*map(xy, chargers)), s=lw * 16, color=color,
                                  edgecolor="white", lw=1.2, zorder=7))
    return artists


def stop_labels(ax, stops, graph):
    """'City, ST / mile N' at each charging stop. Labels sit off to the side of the route,
    alternating sides from one stop to the next so neighbors don't collide."""
    labels, mile = [], 0.0
    for i, v in enumerate(stops):
        mile += graph[stops[i - 1]][v] if i else 0
        if v in (START, END):
            continue
        dx, dy = xy(stops[i + 1]) - xy(stops[i - 1])          # direction of travel here
        nx_, ny_ = np.array([-dy, dx]) / (np.hypot(dx, dy) or 1) * (1 if i % 2 else -1)
        labels.append(ax.annotate(f"{short(v)}\nmile {mile:,.0f}", xy(v), xytext=(12 * nx_, 12 * ny_),
                                  textcoords="offset points",
                                  ha="left" if nx_ > 0.3 else "right" if nx_ < -0.3 else "center",
                                  va="bottom" if ny_ > 0.3 else "top" if ny_ < -0.3 else "center",
                                  fontsize=7, fontweight="bold", path_effects=HALO, zorder=8))
    return labels


def finish(ax, title, note, size=12):
    ax.set_title(title, loc="left", pad=14, fontsize=size)
    ax.text(0, 1.0, note, transform=ax.transAxes, color=MUTED, fontsize=9, va="bottom")


def edge_count(graph):
    return sum(len(nbrs) for nbrs in graph.values())


def plot_route(stops, miles, graph, max_range, path):
    """The best route for one range, drawn along the roads actually driven."""
    fig, ax = plt.subplots(figsize=(13, 8))
    draw_map(ax, zoom=6)
    draw_route(ax, stops)
    stop_labels(ax, stops, graph)
    finish(ax, f"Shortest {short(START)} → {short(END)} trip with a {max_range}-mile range",
           f"{miles:,.1f} miles, {plural(len(stops) - 2, 'charging stop')} · "
           f"{len(graph) - 2:,} chargers, {edge_count(graph):,} edges")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_range_grid(results, path):
    """One panel per range: Dijkstra's route on the real map."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10.5))
    for ax, (max_range, stops, miles, graph) in zip(axes.flat, results):
        draw_map(ax)
        edges = edge_count(graph)
        if stops:
            draw_route(ax, stops, lw=2.2)
            note = f"{miles:,.1f} mi · {plural(len(stops) - 2, 'stop')} · {edges:,} edges"
        else:
            note = f"no route · {edges:,} edges"
        finish(ax, f"Range {max_range} mi", note, size=11)
    fig.suptitle("A longer range adds edges, so the route needs fewer stops",
                 x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
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
    if first > sweep[0][0]:
        top.text((sweep[0][0] + first) / 2, sum(top.get_ylim()) / 2, "no route possible",
                 ha="center", va="center", rotation=90, color=MUTED, fontsize=8)
    top.annotate(f"{first} mi range: first feasible\n{miles[0]:,.1f} mi, {plural(stops[0], 'stop')}",
                 (first, miles[0]), xytext=(60, -2), textcoords="offset points", fontsize=9, va="top",
                 arrowprops={"arrowstyle": "-", "color": MUTED})
    if chosen_range in ranges:
        i = ranges.index(chosen_range)
        top.annotate(f"{chosen_range} mi range: {miles[i]:,.1f} mi, {plural(stops[i], 'stop')}",
                     (chosen_range, miles[i]), xytext=(8, 18), textcoords="offset points", fontsize=9,
                     arrowprops={"arrowstyle": "-", "color": MUTED})

    bottom.step(ranges, stops, where="post", color=ROUTE, lw=2)
    bottom.set_ylabel("Charging stops")
    bottom.yaxis.set_major_locator(MaxNLocator(integer=True))
    bottom.set_xlabel("Range: longest leg in miles (80% of a full charge)")

    top.set_title("How battery range changes the shortest route", loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def search_state(trace, step):
    """Replay Dijkstra's trace through `step`: the settled vertices (in order), every
    vertex with a distance so far, and prev."""
    settled, seen, prev = [], {START}, {}
    for u, _, updates in trace[:step + 1]:
        settled.append(u)
        for v, _ in updates:
            seen.add(v)
            prev[v] = u
    return settled, seen, prev


def draw_search(ax, trace, step):
    """Dijkstra's state right after it settles trace[step]. Returns the artists it adds."""
    settled, seen, prev = search_state(trace, step)
    done = set(settled)
    frontier = [v for v in seen if v not in done]
    tree = [[xy(prev[v]), xy(v)] for v in settled if v in prev]
    u = trace[step][0]

    artists = [
        ax.add_collection(LineCollection(tree, colors=ROUTE, linewidths=0.5, alpha=0.35, zorder=3)),
        ax.scatter(*XY[[INDEX[v] for v in settled]].T, s=4, color=ROUTE, lw=0, zorder=4),
        ax.scatter(*xy(u), s=150, facecolor="none", edgecolor=INK, lw=1.6, zorder=9),
    ]
    if frontier:
        artists.append(ax.scatter(*XY[[INDEX[v] for v in frontier]].T, s=6, color=FRONTIER, lw=0, zorder=5))
    return artists


def search_legend(ax):
    handles = [
        Line2D([], [], ls="", marker="o", ms=5, color=ROUTE, label="settled (distance final)"),
        Line2D([], [], ls="", marker="o", ms=5, color=FRONTIER, label="tentative (in the queue)"),
        Line2D([], [], ls="", marker="o", ms=4, color=NODE, label="not reached yet"),
        Line2D([], [], ls="", marker="o", ms=12, mfc="none", mec=INK, mew=1.5, label="settled this step"),
        Line2D([], [], color=ROUTE, lw=1, alpha=0.6, label="shortest-path tree (prev)"),
    ]
    return ax.legend(handles=handles, loc="lower right", fontsize=7.5, framealpha=0.9, edgecolor=GRID)


def step_note(trace, step):
    settled, seen, _ = search_state(trace, step)
    u, d, updates = trace[step]
    return (f"settle {short(u)} at {d:,.1f} mi · improved {plural(len(updates), 'neighbor')} · "
            f"{len(settled):,} settled, {len(seen) - len(settled):,} in the queue")


def plot_search_snapshots(trace, path):
    """Four moments of the search, for a printed report."""
    n = len(trace)
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    for ax, step in zip(axes.flat, [n // 20, n // 3, 2 * n // 3, n - 1]):
        draw_map(ax)
        draw_search(ax, trace, step)
        finish(ax, f"Step {step + 1:,} of {n:,}", step_note(trace, step), size=11)
    search_legend(axes.flat[0])
    fig.suptitle(f"Dijkstra's search: chargers settle in order of distance from {short(START)}",
                 x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def animate_search(graph, trace, stops, miles, max_range, search_frames=60):
    """The whole story on the real map, one frame at a time:
    1. the chargers, 2. Dijkstra's search (sampled), 3. tracing back the route.

    Returns the animation: save it with anim.save(...) or watch it live with plt.show().
    """
    fig, ax = plt.subplots(figsize=(12, 7.6))
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.02, top=0.89)
    draw_map(ax)
    title = fig.text(0.01, 0.975, "", fontsize=12, fontweight="bold", va="top")
    note = fig.text(0.01, 0.93, "", fontsize=9, color=MUTED, va="top")

    samples = sorted(set(np.linspace(0, len(trace) - 1, search_frames).round().astype(int)))
    frames = ([("map", 0)] * 2
              + [("search", k) for k in samples]
              + [("trace", k) for k in range(1, len(stops))]
              + [("done", 0)] * 3)
    dynamic = []

    def update(frame):
        phase, k = frame
        for artist in dynamic:
            artist.remove()
        dynamic.clear()

        if phase == "map":
            title.set_text("1 · The real charging network")
            note.set_text(f"{len(VERTICES) - 2:,} DC fast chargers between {START} and {END}; "
                          f"{edge_count(graph):,} legs fit in {max_range} miles")

        elif phase == "search":
            dynamic.extend(draw_search(ax, trace, k))
            dynamic.append(search_legend(ax))
            title.set_text(f"2 · Dijkstra step {k + 1:,} of {len(trace):,}")
            note.set_text(step_note(trace, k))

        else:
            legs = stops if phase == "done" else stops[-k - 1:]
            dynamic.extend(draw_route(ax, legs))
            if phase == "trace":
                title.set_text(f"3 · Trace back from {short(END)}, following prev[]")
                note.set_text(" ← ".join(short(s) for s in reversed(legs)))
            else:
                dynamic.extend(stop_labels(ax, stops, graph))
                title.set_text(f"Shortest route with a {max_range}-mile range: "
                               f"{miles:,.1f} mi, {plural(len(stops) - 2, 'charging stop')}")
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
