import { CODE, type Step, type Vars } from "../dijkstra";

const fmt = (vars: Vars) =>
  (Object.entries(vars) as [string, string | number | undefined][])
    .filter(([, val]) => val !== undefined)
    .map(([k, val]) => `${k} = ${typeof val === "string" ? `"${val}"` : val}`)
    .join("   ");

export function CodePanel({ step }: { step: Step }) {
  const last = step.lines[step.lines.length - 1];
  return (
    <section className="panel code-panel">
      <h2>Core code <span className="muted">dijkstra.py</span></h2>
      <pre className="code" aria-label="Dijkstra source code">
        {CODE.map((text, i) => (
          <div key={i} className={step.lines.includes(i) ? "line line-on" : "line"}>
            <span className="ln">{i + 1}</span>
            <span className="src">{text || " "}</span>
            {i === last && <span className="caret">◀</span>}
          </div>
        ))}
      </pre>
      <p className="note">{step.note}</p>
      <p className="vars">{fmt(step.vars) || "no loop variables yet"}</p>
    </section>
  );
}
