import { short, type Network } from "../graph";
import type { Step } from "../dijkstra";

export function WaitlistPanel({ step, network }: { step: Step; network: Network }) {
  const label = network.showWeights ? (n: string) => n : short;
  return (
    <section className="panel">
      <h2>Waitlist <span className="muted">heap, closest first</span></h2>
      {step.heap.length === 0 ? (
        <p className="muted">empty</p>
      ) : (
        <ol className="heap">
          {step.heap.map(([miles, node], i) => {
            const stale = miles > step.best[node];
            return (
              <li key={`${node}-${miles}`} className={stale ? "stale" : i === 0 ? "next" : ""}
                  title={stale ? `outdated: best[${node}] is ${step.best[node]}` : undefined}>
                <span className="num">{miles}</span> {label(node)}
                {stale && <span className="tag">outdated</span>}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

export function DistancePanel({ step, network }: { step: Step; network: Network }) {
  const settled = new Set(step.settled);
  const label = network.showWeights ? (n: string) => n : short;
  const rows = Object.keys(network.pos).sort((a, b) => {
    const da = step.best[a] ?? Infinity;
    const db = step.best[b] ?? Infinity;
    return da - db || a.localeCompare(b);
  });
  return (
    <section className="panel">
      <h2>best / prev <span className="muted">{step.settled.length} final</span></h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>node</th><th className="num">best</th><th>prev</th></tr>
          </thead>
          <tbody>
            {rows.map((n) => (
              <tr key={n} className={settled.has(n) ? "row-settled" : n in step.best ? "row-waiting" : "row-idle"}>
                <td><span className="dot" />{label(n)}</td>
                <td className="num">{step.best[n] ?? "∞"}</td>
                <td>{step.prev[n] ? label(step.prev[n]) : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
