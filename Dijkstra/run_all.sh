#!/usr/bin/env bash
# Run everything: runtime measurements, the full analysis + figures, then open the web demo
# and the figures.
#   ./run_all.sh            all three
#   ./run_all.sh --quick    skip main.py (the slow part: figures and the GIF)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "== Setting up .venv (first run only)"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo "== runtime.py: simple Dijkstra + runtime table"
.venv/bin/python runtime.py

if [ "${1:-}" != "--quick" ]; then
  echo; echo "== main.py: full analysis and figures"
  .venv/bin/python main.py
fi

echo; echo "== Opening the web demo and the figures"
SHOW=(dijkstra-demo.html figures/runtime.png)
[ "${1:-}" != "--quick" ] && SHOW+=(figures/route.png figures/range_comparison.png
                                    figures/range_sweep.png figures/search_on_map.gif)
if command -v open >/dev/null; then open "${SHOW[@]}"              # macOS
elif command -v xdg-open >/dev/null; then for f in "${SHOW[@]}"; do xdg-open "$f"; done
else printf 'Open these in a browser / viewer:\n'; printf '  %s\n' "${SHOW[@]}"; fi
