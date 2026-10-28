"""Draw all charger vertices and the routes found by our two A* variants."""

import matplotlib.pyplot as plt
from io import BytesIO
from pathlib import Path
from matplotlib.collections import LineCollection
from AStar.visualize import mercator


def plot_full_comparison(trip, runs, starting_range, full_range, shapes, roads, output):
    methods = list(runs)
    colors = {"haversine":"#1477bd", "manhattan":"#d7761d"}
    figure, axes = plt.subplots(2, len(methods), figsize=(15,9.5), squeeze=False,
                                gridspec_kw={"height_ratios":[3.7,1]})
    points = {node:mercator(*point) for node,point in trip.coordinates.items()}
    background = [[mercator(*p) for p in line] for line in roads]
    sites = [key for key in points if key not in ("START","END")]
    for column, method in enumerate(methods):
        run, axis = runs[method], axes[0,column]
        if background:
            axis.add_collection(LineCollection(background, colors="#cbd4dc", linewidths=.45, zorder=0))
        expanded = set(run["stats"]["expanded_order"])
        if sites:
            axis.scatter([points[n][0] for n in sites], [points[n][1] for n in sites],
                         c=[colors[method] if n in expanded else "#c0cbd4" for n in sites],
                         s=6 if len(sites)>200 else 15, linewidths=0, zorder=2)
        if run["answer"] is not None:
            path, miles = run["answer"]
            lines = [[mercator(*p) for p in shapes[a,b]] for a,b in zip(path,path[1:])]
            if lines:
                axis.add_collection(LineCollection(lines, colors=colors[method], linewidths=2.2, zorder=3))
            for i,node in enumerate(path[1:-1],1):
                x,y=points[node]
                axis.scatter(x,y,s=48,color="white",edgecolor=colors[method],zorder=4)
                axis.annotate(str(i),(x,y),ha="center",va="center",fontsize=6,zorder=5)
            subtitle=f"{miles:,.2f} miles | {max(0,len(path)-2)} charging stops"
        else:
            subtitle="No route fits the battery limits"
        for key,color,marker in (("START","#16835d","o"),("END","#c8464e","*")):
            x,y=points[key]
            axis.scatter(x,y,s=95,marker=marker,c=color,edgecolors="white",zorder=6)
            axis.annotate("Start" if key=="START" else "Goal",(x,y),xytext=(5,7),
                          textcoords="offset points",fontsize=8,zorder=7,
                          bbox={"facecolor":"white","alpha":.9,"edgecolor":"none","pad":1})
        axis.update_datalim(list(points.values()))
        axis.autoscale_view()
        axis.margins(.04)
        axis.set_aspect("equal")
        axis.set_axis_off()
        axis.set_title(f"A* + {'scaled Manhattan' if method=='manhattan' else 'Haversine'}\n{subtitle}\n"
                       f"{run['stats']['expanded']:,} expanded; h scale {run['heuristic'].scale:.6f}",fontsize=11)
    count_axis=axes[1,0]
    count_axis.barh([m.capitalize() for m in methods], [runs[m]["stats"]["expanded"] for m in methods],
                    color=[colors[m] for m in methods],height=.5)
    count_axis.set_xlabel("Expanded vertices, including destination")
    if len(methods)>1:
        time_axis=axes[1,1]
        times=[runs[m]["median_ms"] for m in methods]
        error=[[runs[m]["median_ms"]-runs[m]["q1_ms"] for m in methods],
               [runs[m]["q3_ms"]-runs[m]["median_ms"] for m in methods]]
        time_axis.barh([m.capitalize() for m in methods],times,xerr=error,capsize=3,
                       color=[colors[m] for m in methods],height=.5)
        time_axis.set_xlabel("Median search ms; error bars show interquartile range")
    for axis in axes[1]:
        axis.spines[["top","right"]].set_visible(False)
        axis.grid(axis="x",alpha=.15)
        axis.set_axisbelow(True)
    figure.suptitle(f"{trip.labels['START']} to {trip.labels['END']}\n"
                   f"{len(sites):,} mapped charger vertices | Starting range {starting_range:g} mi | Full range {full_range:g} mi",
                   fontsize=14)
    figure.text(.5,.025,"Roads: OpenStreetMap contributors. Stations: AFDC. All mapped charger vertices are searchable.\n"
                "Road/background drawing is simplified; access links use direct distances. Full refills at selected stops.",
                ha="center",fontsize=8,color="#566776")
    figure.tight_layout(rect=(.015,.075,.985,.92))
    # Buffer first so saving also works on filesystems with partial OS writes.
    buffer=BytesIO()
    figure.savefig(buffer,format="png",dpi=170,facecolor="white")
    Path(output).write_bytes(buffer.getvalue())
    plt.close(figure)
