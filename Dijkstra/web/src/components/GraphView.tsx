import { useMemo } from "react";
import { VIEW_H, VIEW_W, short, type Graph, type Network } from "../graph";
import type { Step } from "../dijkstra";

interface Props {
  network: Network;
  graph: Graph;
  step: Step;
  path: string[] | null;
}

type NodeState = "idle" | "waiting" | "settled";

export function GraphView({ network, graph, step, path }: Props) {
  const { pos } = network;

  // One line per connected pair; the real graph has both directions for most roads.
  const pairs = useMemo(() => {
    const seen = new Set<string>();
    const out: [string, string, number][] = [];
    for (const a in graph) {
      for (const b in graph[a]) {
        const key = a < b ? `${a}|${b}` : `${b}|${a}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push([a, b, graph[a][b]]);
      }
    }
    return out;
  }, [graph]);

  const settled = new Set(step.settled);
  const stateOf = (n: string): NodeState =>
    settled.has(n) ? "settled" : n in step.best ? "waiting" : "idle";

  const pathEdges = new Set<string>();
  if (step.done && path) {
    for (let i = 1; i < path.length; i++) pathEdges.add(`${path[i - 1]}|${path[i]}`);
  }

  const { u, v } = step.vars;
  const examining = step.lines.some((l) => l >= 11 && l <= 16) && u && v ? [u, v] : null;
  const big = network.showWeights;
  const r = big ? 22 : 7;

  return (
    <svg className="graph" viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} role="img"
         aria-label="Graph being searched by Dijkstra">
      <defs>
        {(["active", "good", "bad"] as const).map((tone) => (
          <marker key={tone} id={`arrow-${tone}`} viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="5" markerHeight="5" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" className={`fill-${tone}`} />
          </marker>
        ))}
      </defs>

      {pairs.map(([a, b, w]) => (
        <g key={`${a}|${b}`}>
          <line className="edge" x1={pos[a].x} y1={pos[a].y} x2={pos[b].x} y2={pos[b].y} />
          {network.showWeights && (
            <text className="weight" x={(pos[a].x + pos[b].x) / 2} y={(pos[a].y + pos[b].y) / 2 - 6}>
              {w}
            </text>
          )}
        </g>
      ))}

      {/* Shortest-path tree so far: prev[v] → v */}
      {Object.entries(step.prev).map(([to, from]) => (
        <line key={`tree-${to}`}
              className={pathEdges.has(`${from}|${to}`) ? "edge-path" : "edge-tree"}
              x1={pos[from].x} y1={pos[from].y} x2={pos[to].x} y2={pos[to].y} />
      ))}

      {examining && (
        <ActiveEdge from={pos[examining[0]]} to={pos[examining[1]]} r={r}
                    tone={step.lines.includes(13) ? (step.improved ? "good" : "bad") : "active"} />
      )}

      {Object.keys(pos).map((n) => {
        const s = stateOf(n);
        const isU = n === u && !step.done;
        const isEnd = n === network.source || n === network.target;
        return (
          <g key={n} className={`node node-${s}`}>
            {isU && <circle className="node-current" cx={pos[n].x} cy={pos[n].y} r={r + (big ? 8 : 6)} />}
            <circle cx={pos[n].x} cy={pos[n].y} r={isEnd && !big ? r + 2 : r} />
            {big ? (
              <>
                <text className="node-name" x={pos[n].x} y={pos[n].y + 5}>{n}</text>
                <text className="node-dist" x={pos[n].x} y={pos[n].y - r - 8}>
                  {n in step.best ? step.best[n] : "∞"}
                </text>
              </>
            ) : (
              <text className="node-label" x={pos[n].x + 10} y={pos[n].y + 4}>
                {short(n)}
                {n in step.best && <tspan className="node-label-dist"> {step.best[n]}</tspan>}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function ActiveEdge({ from, to, r, tone }: {
  from: { x: number; y: number };
  to: { x: number; y: number };
  r: number;
  tone: "active" | "good" | "bad";
}) {
  // Stop the arrow at the edge of the target circle.
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.hypot(dx, dy) || 1;
  const x2 = to.x - (dx / len) * (r + 4);
  const y2 = to.y - (dy / len) * (r + 4);
  return <line className={`edge-active tone-${tone}`} x1={from.x} y1={from.y} x2={x2} y2={y2}
               markerEnd={`url(#arrow-${tone})`} />;
}
