# Resources

## Data
- Road network from OpenStreetMap contributors (openstreetmap.org), downloaded as state files from Geofabrik (download.geofabrik.de). Map data © OpenStreetMap contributors, ODbL.
- EV charging stations from the U.S. Department of Energy Alternative Fuels Data Center, Alternative Fuel Stations API (afdc.energy.gov, developer.nlr.gov). Public DC fast chargers that are open.
- State outlines from the U.S. Census Bureau cartographic boundary files (2023, 1:20,000,000).
- Background map tiles and road drawing on some route figures from OpenStreetMap and OSRM (project-osrm.org).

## Algorithms
- E. W. Dijkstra, "A note on two problems in connexion with graphs," Numerische Mathematik 1 (1959), 269–271.
- P. E. Hart, N. J. Nilsson and B. Raphael, "A Formal Basis for the Heuristic Determination of Minimum Cost Paths," IEEE Transactions on Systems Science and Cybernetics 4(2) (1968), 100–107.

## Software
- OSMnx by Geoff Boeing, for turning OpenStreetMap data into graphs (osmnx.readthedocs.io).
- pyosmium, for filtering the OpenStreetMap files (osmcode.org/pyosmium).
- NetworkX, for graph storage and the published Dijkstra and A* we compared against (networkx.org).
- SciPy `scipy.sparse.csgraph.dijkstra`, the published C implementation (scipy.org).
- Matplotlib and GeoPandas, for the figures.

## AI use
- Claude (Anthropic) helped write the data pipeline and graph-building code (data.py, charger_graph.py, trip.py, check_graphs.py, visualize.py) and explain the results. We checked its output with check_graphs.py and against NetworkX.
