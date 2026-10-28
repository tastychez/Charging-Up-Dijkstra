#!/usr/bin/env bash
# Run everything: runtime measurements, the full analysis + figures, then open the web demo
# and the figures.
#   ./run_all.sh            all three
#   ./run_all.sh --quick    skip main.py (the slow part: figures and the GIF)
set -euo pipefail
cd "$(dirname "$0")"

# The real network needs the repository's root .venv and data/ (see the root README).
PY=../.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "== Setting up the root .venv (first run only)"
  python3 -m venv ../.venv
  "$PY" -m pip install -q -r ../requirements.txt
fi
if [ ! -f cache/network.pkl ] && [ ! -f ../data/chargers_dallas-boston_8types.pkl ]; then
  echo "No charger data yet: run '.venv/bin/python charger_graph.py' in the repository root first."
  exit 1
fi

echo "== runtime.py: simple Dijkstra + runtime table"
"$PY" runtime.py

if [ "${1:-}" != "--quick" ]; then
  echo; echo "== main.py: full analysis and figures"
  "$PY" main.py
  echo; echo "== compare_library.py: hand-written vs NetworkX vs SciPy"
  "$PY" compare_library.py
fi

echo; echo "== Opening the web demo and the figures"
SHOW=(dijkstra-demo.html figures/runtime.png)
[ "${1:-}" != "--quick" ] && SHOW+=(figures/route.png figures/range_comparison.png
                                    figures/range_sweep.png figures/search_on_map.gif
                                    figures/library_routes.png figures/library_runtime.png)
if command -v open >/dev/null; then open "${SHOW[@]}"              # macOS
elif command -v xdg-open >/dev/null; then for f in "${SHOW[@]}"; do xdg-open "$f"; done
else printf 'Open these in a browser / viewer:\n'; printf '  %s\n' "${SHOW[@]}"; fi
