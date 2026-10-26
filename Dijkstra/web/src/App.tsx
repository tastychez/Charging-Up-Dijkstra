import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NETWORKS, chargingGraph, short, type Network } from "./graph";
import { measureRuntime, pathTo, traceDijkstra } from "./dijkstra";
import { GraphView } from "./components/GraphView";
import { CodePanel } from "./components/CodePanel";
import { DistancePanel, WaitlistPanel } from "./components/StatePanels";
import { TimingPanel } from "./components/TimingPanel";

const SPEEDS = [1, 2, 4, 8, 16, 40]; // steps per second

// Optional deep link for presenting, e.g. ?graph=real&step=120
const params = new URLSearchParams(window.location.search);
const START_GRAPH: Network["id"] = params.get("graph") === "real" ? "real" : "example";
let startStep = Math.max(0, Number(params.get("step")) - 1 || 0);

export default function App() {
  const [netId, setNetId] = useState<Network["id"]>(START_GRAPH);
  const network = NETWORKS.find((n) => n.id === netId)!;
  const [range, setRange] = useState(250);
  const [source, setSource] = useState(network.source);
  const [target, setTarget] = useState(network.target);

  const graph = useMemo(
    () => (network.usesRange ? chargingGraph(network.roads, range) : network.roads),
    [network, range],
  );

  const { steps, traceMs } = useMemo(() => {
    const t0 = performance.now();
    const steps = traceDijkstra(graph, source, target);
    return { steps, traceMs: performance.now() - t0 };
  }, [graph, source, target]);

  const runtime = useMemo(() => measureRuntime(graph, source, target), [graph, source, target]);

  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);

  // Animation clock: counts only while playing.
  const [animMs, setAnimMs] = useState(0);
  const lastTick = useRef(0);

  const reset = useCallback(() => {
    setI(startStep);
    startStep = 0; // only the first graph opens at the linked step
    setPlaying(false);
    setAnimMs(0);
  }, []);
  useEffect(reset, [steps, reset]);

  const last = steps.length - 1;
  const step = steps[Math.min(i, last)];

  useEffect(() => {
    if (!playing) return;
    lastTick.current = performance.now();
    const id = setInterval(() => {
      const now = performance.now();
      setAnimMs((t) => t + now - lastTick.current);
      lastTick.current = now;
      setI((k) => Math.min(k + 1, last));
    }, 1000 / speed);
    return () => clearInterval(id);
  }, [playing, speed, last]);

  useEffect(() => {
    if (i >= last) setPlaying(false);
  }, [i, last]);

  const play = () => {
    if (i >= last) {
      setI(0);
      setAnimMs(0);
    }
    setPlaying((p) => !p);
  };
  const go = (k: number) => {
    setPlaying(false);
    setI(Math.max(0, Math.min(k, last)));
  };
  // Jump to the next time a node is popped from the waitlist (line 6), or the end.
  const nextPop = () => {
    let k = i + 1;
    while (k < last && !steps[k].lines.includes(6)) k++;
    go(k);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === " ") {
        e.preventDefault();
        play();
      } else if (e.key === "ArrowRight") go(i + 1);
      else if (e.key === "ArrowLeft") go(i - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const switchNetwork = (id: Network["id"]) => {
    const n = NETWORKS.find((x) => x.id === id)!;
    setNetId(id);
    setSource(n.source);
    setTarget(n.target);
  };

  const finalStep = steps[last];
  const path = pathTo(finalStep.prev, source, target);
  const nodes = Object.keys(network.pos);
  const label = network.showWeights ? (n: string) => n : short;
  const edgeCount = Object.values(graph).reduce((s, row) => s + Object.keys(row).length, 0);

  return (
    <div className="app">
      <header>
        <h1>Dijkstra, step by step</h1>
        <p className="muted">
          Each step runs one line of the code on the right. The map, the waitlist and the
          distance table all show the state right after that line.
        </p>
        <div className="settings">
          <label>
            Graph
            <select value={netId} onChange={(e) => switchNetwork(e.target.value as Network["id"])}>
              {NETWORKS.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
            </select>
          </label>
          <label>
            From
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              {nodes.map((n) => <option key={n} value={n}>{label(n)}</option>)}
            </select>
          </label>
          <label>
            To
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              {nodes.map((n) => <option key={n} value={n}>{label(n)}</option>)}
            </select>
          </label>
          {network.usesRange && (
            <label className="range">
              Battery range <strong>{range} mi</strong>
              <input type="range" min={50} max={600} step={10} value={range}
                     onChange={(e) => setRange(Number(e.target.value))} />
            </label>
          )}
          <span className="muted small">{nodes.length} nodes · {edgeCount} directed edges</span>
        </div>
      </header>

      <main className="layout">
        <section className="panel map-panel">
          <GraphView network={network} graph={graph} step={step} path={path} />
          <ul className="legend">
            <li><span className="sw sw-idle" />not reached (∞)</li>
            <li><span className="sw sw-waiting" />in waitlist</li>
            <li><span className="sw sw-settled" />final</li>
            <li><span className="sw sw-current" />u (current)</li>
            <li><span className="ln-sw ln-active" />road u → v</li>
            <li><span className="ln-sw ln-tree" />prev links</li>
            <li><span className="ln-sw ln-path" />shortest path</li>
          </ul>
          {step.done && (
            <p className="result">
              {path
                ? <>Shortest route: <strong>{step.best[target]} mi</strong>, {path.map(label).join(" → ")}</>
                : <>No route from {label(source)} to {label(target)}{network.usesRange ? " with this range" : ""}.</>}
            </p>
          )}
        </section>

        <CodePanel step={step} />
      </main>

      <div className="controls panel">
        <button onClick={() => go(0)} title="Reset">⏮</button>
        <button onClick={() => go(i - 1)} title="Back one line (←)">◀</button>
        <button className="primary" onClick={play} title="Play / pause (space)">
          {playing ? "Pause" : i >= last ? "Replay" : "Play"}
        </button>
        <button onClick={() => go(i + 1)} title="Forward one line (→)">▶</button>
        <button onClick={nextPop} title="Jump to the next pop from the waitlist">next pop</button>
        <button onClick={() => go(last)} title="Jump to the end">⏭</button>
        <input className="scrub" type="range" min={0} max={last} value={Math.min(i, last)}
               onChange={(e) => go(Number(e.target.value))} aria-label="Step" />
        <span className="counter">step {Math.min(i, last) + 1} / {steps.length}</span>
        <label className="speed">
          Speed
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => <option key={s} value={s}>{s} steps/s</option>)}
          </select>
        </label>
      </div>

      <div className="bottom">
        <WaitlistPanel step={step} network={network} />
        <DistancePanel step={step} network={network} />
        <TimingPanel computeUs={runtime.microseconds} runs={runtime.runs} traceMs={traceMs}
                     stepCount={steps.length} animationMs={animMs} msPerStep={1000 / speed}
                     finished={i >= last} />
      </div>
    </div>
  );
}
