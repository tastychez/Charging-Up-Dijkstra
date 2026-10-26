// Dijkstra twice over: a plain version for timing, and a traced version that records
// one Step per line of the Python code it mirrors, so the UI can replay the search.

import type { Graph } from "./graph";

/** (miles, node), compared like a Python tuple: by miles, then by node name. */
export type Entry = [number, string];

const less = (a: Entry, b: Entry) => a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]);

/** Binary min-heap, the same structure Python's heapq keeps in a list. */
class MinHeap {
  items: Entry[] = [];

  get size() {
    return this.items.length;
  }

  push(e: Entry) {
    const a = this.items;
    a.push(e);
    let i = a.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (!less(a[i], a[p])) break;
      [a[i], a[p]] = [a[p], a[i]];
      i = p;
    }
  }

  pop(): Entry {
    const a = this.items;
    const top = a[0];
    const last = a.pop()!;
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < a.length && less(a[l], a[m])) m = l;
        if (r < a.length && less(a[r], a[m])) m = r;
        if (m === i) break;
        [a[i], a[m]] = [a[m], a[i]];
        i = m;
      }
    }
    return top;
  }
}

/** The code shown beside the map. Step.lines index into this array. */
export const CODE = [
  "def dijkstra(graph, source, target=None):",
  "    best = {source: 0}      # starting point is zero",
  "    prev = {}               # where we came from",
  "    heap = [(0, source)]    # waitlist",
  "",
  "    while heap:",
  "        miles, u = heapq.heappop(heap)  # closest point",
  "        if miles > best[u]:",
  "            continue            # outdated entry",
  "        if u == target:",
  "            break               # target is final",
  "        for v, w in graph[u].items():",
  "            new_miles = miles + w",
  "            if v not in best or new_miles < best[v]:",
  "                best[v] = new_miles",
  "                prev[v] = u",
  "                heapq.heappush(heap, (new_miles, v))",
  "",
  "    return best, prev",
];

/** Plain Dijkstra, nothing recorded. This is what the runtime measures. */
export function dijkstra(graph: Graph, source: string, target?: string) {
  const best = new Map<string, number>([[source, 0]]);
  const prev = new Map<string, string>();
  const heap = new MinHeap();
  heap.push([0, source]);

  while (heap.size) {
    const [miles, u] = heap.pop();
    if (miles > best.get(u)!) continue;
    if (u === target) break;
    for (const v in graph[u]) {
      const newMiles = miles + graph[u][v];
      const old = best.get(v);
      if (old === undefined || newMiles < old) {
        best.set(v, newMiles);
        prev.set(v, u);
        heap.push([newMiles, v]);
      }
    }
  }
  return { best, prev };
}

export interface Vars {
  miles?: number;
  u?: string;
  v?: string;
  w?: number;
  new_miles?: number;
}

/** Everything the UI needs to draw one moment of the search. */
export interface Step {
  lines: number[];            // highlighted lines of CODE
  note: string;               // what this line just did, in words
  vars: Vars;
  best: Record<string, number>;
  prev: Record<string, string>;
  heap: Entry[];              // waitlist, sorted closest first
  settled: string[];          // nodes whose distance is final, in order
  improved?: boolean;         // line 13: did the new route win?
  done: boolean;
}

/** Run Dijkstra and record a snapshot after every line it executes. */
export function traceDijkstra(graph: Graph, source: string, target?: string): Step[] {
  const steps: Step[] = [];
  const best: Record<string, number> = { [source]: 0 };
  const prev: Record<string, string> = {};
  const heap = new MinHeap();
  heap.push([0, source]);
  const settled: string[] = [];
  const vars: Vars = {};

  const record = (lines: number[], note: string, extra: Partial<Step> = {}) =>
    steps.push({
      lines,
      note,
      vars: { ...vars },
      best: { ...best },
      prev: { ...prev },
      heap: [...heap.items].sort((a, b) => (less(a, b) ? -1 : 1)),
      settled: [...settled],
      done: false,
      ...extra,
    });

  record([1, 2, 3], `Start at ${source} with 0 miles. It is the only entry in the waitlist.`);

  for (;;) {
    if (!heap.size) {
      record([5], "The waitlist is empty, so every reachable node is final.");
      break;
    }
    record([5], `The waitlist has ${heap.size} ${heap.size === 1 ? "entry" : "entries"}, keep going.`);

    const [miles, u] = heap.pop();
    Object.assign(vars, { miles, u, v: undefined, w: undefined, new_miles: undefined });
    record([6], `Pop the closest entry: ${u} at ${miles} mi.`);

    if (miles > best[u]) {
      record([7, 8], `${miles} > best[${u}] = ${best[u]}: an older, longer route to ${u}. Skip it.`);
      continue;
    }
    settled.push(u);
    record([7], `${miles} is the best known distance to ${u}. Nothing shorter can still appear, so ${u} is final.`);

    if (u === target) {
      record([9, 10], `${u} is the target. Its distance is final, so stop here.`);
      break;
    }
    record([9], `${u} is not the target, look at its neighbours.`);

    for (const v in graph[u]) {
      const w = graph[u][v];
      Object.assign(vars, { v, w, new_miles: undefined });
      record([11], `Road ${u} → ${v}: ${w} mi.`);

      const newMiles = miles + w;
      vars.new_miles = newMiles;
      record([12], `new_miles = ${miles} + ${w} = ${newMiles}.`);

      const improved = !(v in best) || newMiles < best[v];
      record(
        [13],
        !(v in best)
          ? `${v} has no distance yet, so this route wins.`
          : improved
            ? `${newMiles} < best[${v}] = ${best[v]}: a shorter route to ${v}.`
            : `${newMiles} ≥ best[${v}] = ${best[v]}: not shorter, ignore it.`,
        { improved },
      );
      if (!improved) continue;

      best[v] = newMiles;
      prev[v] = u;
      record([14, 15], `Remember: best[${v}] = ${newMiles}, reached from ${u}.`);
      heap.push([newMiles, v]);
      record([16], `Add (${newMiles}, ${v}) to the waitlist.`);
    }
  }

  const reached = target === undefined || target in best;
  record(
    [18],
    reached
      ? `Done. Shortest distance to ${target}: ${best[target!]} mi.`
      : `Done. ${target} cannot be reached with this graph.`,
    { done: true },
  );
  return steps;
}

/** Walk prev back from target to source. null if target was never reached. */
export function pathTo(prev: Record<string, string>, source: string, target: string): string[] | null {
  if (target !== source && !(target in prev)) return null;
  const path = [target];
  while (path[path.length - 1] !== source) path.push(prev[path[path.length - 1]]);
  return path.reverse();
}

/**
 * Average time of one plain dijkstra() call, in microseconds.
 * Repeats until at least `budgetMs` has passed so tiny runs still measure well.
 */
export function measureRuntime(graph: Graph, source: string, target: string, budgetMs = 40) {
  for (let i = 0; i < 20; i++) dijkstra(graph, source, target); // let the JIT warm up
  let runs = 0;
  const start = performance.now();
  let elapsed = 0;
  while (elapsed < budgetMs || runs < 20) {
    dijkstra(graph, source, target);
    runs++;
    elapsed = performance.now() - start;
  }
  return { microseconds: (elapsed * 1000) / runs, runs };
}
