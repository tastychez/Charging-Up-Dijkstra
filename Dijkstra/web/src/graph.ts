// The two networks the demo can search, and the range-limited charging graph.

import realData from "./data/boston-dallas.json";

/** {node: {neighbor: miles}}, same shape as the Python graphs. */
export type Graph = Record<string, Record<string, number>>;

export interface Point {
  x: number;
  y: number;
}

export interface Network {
  id: "example" | "real";
  label: string;
  /** Screen position of each node inside a VIEW_W × VIEW_H box. */
  pos: Record<string, Point>;
  /** Every road the network has. For the real map, the full distance table. */
  roads: Graph;
  source: string;
  target: string;
  /** Real map: only roads no longer than the battery range become edges. */
  usesRange: boolean;
  /** Draw the weight on every edge (only readable on the small example). */
  showWeights: boolean;
}

export const VIEW_W = 1000;
export const VIEW_H = 620;

/** Drop the ", MA" state suffix for labels. */
export const short = (name: string) => name.replace(/, [A-Z]{2}$/, "");

// A small graph where two nodes get a shorter route after they are first reached,
// so the waitlist ends up holding outdated entries that Dijkstra has to skip.
const EXAMPLE_POS: Record<string, Point> = {
  S: { x: 90, y: 310 },
  A: { x: 290, y: 140 },
  B: { x: 290, y: 480 },
  C: { x: 520, y: 260 },
  D: { x: 520, y: 520 },
  E: { x: 740, y: 120 },
  T: { x: 910, y: 360 },
};

const EXAMPLE_ROADS: [string, string, number][] = [
  ["S", "A", 4], ["S", "B", 2], ["B", "A", 1], ["A", "C", 5], ["B", "C", 8],
  ["B", "D", 10], ["C", "D", 2], ["C", "E", 3], ["D", "T", 6], ["E", "T", 4],
];

function undirected(roads: [string, string, number][]): Graph {
  const g: Graph = {};
  for (const name of Object.keys(EXAMPLE_POS)) g[name] = {};
  for (const [a, b, w] of roads) {
    g[a][b] = w;
    g[b][a] = w;
  }
  return g;
}

function project(stations: { name: string; lat: number; lon: number }[]): Record<string, Point> {
  const meanLat = stations.reduce((s, p) => s + p.lat, 0) / stations.length;
  const k = Math.cos((meanLat * Math.PI) / 180);
  const xs = stations.map((p) => p.lon * k);
  const ys = stations.map((p) => -p.lat);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const pad = 50;
  const scale = Math.min((VIEW_W - 2 * pad) / (x1 - x0), (VIEW_H - 2 * pad) / (y1 - y0));
  const dx = (VIEW_W - (x1 - x0) * scale) / 2;
  const dy = (VIEW_H - (y1 - y0) * scale) / 2;
  const pos: Record<string, Point> = {};
  stations.forEach((p, i) => {
    pos[p.name] = { x: dx + (xs[i] - x0) * scale, y: dy + (ys[i] - y0) * scale };
  });
  return pos;
}

export const NETWORKS: Network[] = [
  {
    id: "example",
    label: "Small example (7 nodes)",
    pos: EXAMPLE_POS,
    roads: undirected(EXAMPLE_ROADS),
    source: "S",
    target: "T",
    usesRange: false,
    showWeights: true,
  },
  {
    id: "real",
    label: "Boston → Dallas Superchargers",
    pos: project(realData.stations),
    roads: realData.miles as Graph,
    source: realData.start,
    target: realData.end,
    usesRange: true,
    showWeights: false,
  },
];

/** Edge A → B only if a fully charged car can drive the road from A to B. */
export function chargingGraph(roads: Graph, maxRange: number): Graph {
  const g: Graph = {};
  for (const [a, row] of Object.entries(roads)) {
    g[a] = {};
    for (const [b, d] of Object.entries(row)) {
      if (b !== a && d <= maxRange) g[a][b] = d;
    }
  }
  return g;
}
