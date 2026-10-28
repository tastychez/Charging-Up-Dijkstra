"""Apply the latest visualizer to an existing HTML, keeping its search data.

From the repo root:
    python -m AStar.refresh_animation AStar/results/full_trip/animation.html

This does not load roads, build a graph, or rerun any routing algorithm.
"""

import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile


DATA_SCRIPT = re.compile(
    r"<script\b(?=[^>]*\bid\s*=\s*['\"]animation-data['\"])[^>]*>(.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)


def refresh_animation(path):
    """Refresh one saved animation and preserve a backup of its original HTML."""
    path = Path(path)
    original = path.read_text(encoding="utf-8-sig")
    matches = list(DATA_SCRIPT.finditer(original))
    if len(matches) != 1:
        raise ValueError("Expected exactly one animation-data script in the saved HTML.")
    payload = matches[0].group(1)
    data = json.loads(payload)
    required = {"graph", "points", "source", "target", "methods", "starting_range", "full_range"}
    if not isinstance(data, dict) or not required.issubset(data):
        raise ValueError("The HTML does not contain a supported A* animation dataset.")
    template = Path(__file__).with_name("animation_template.html").read_text(encoding="utf-8")
    if template.count("__ANIMATION_DATA__") != 1:
        raise ValueError("The animation template must contain one data placeholder.")
    updated = template.replace("__ANIMATION_DATA__", payload)
    if updated == original:
        return path, None
    backup = path.with_name(path.stem + ".before_marker_update.html")
    if not backup.exists():
        shutil.copy2(path, backup)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=path.name + ".", suffix=".tmp",
                                         delete=False) as file:
            temporary = Path(file.name)
            file.write(updated)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path, backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("animation", type=Path, help="existing animation.html to refresh")
    args = parser.parse_args(argv)
    try:
        path, backup = refresh_animation(args.animation)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Updated visualizer: {path}")
    print("Saved graph, search traces, route, battery results, and timings are unchanged.")
    if backup is not None:
        print(f"Original HTML backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
