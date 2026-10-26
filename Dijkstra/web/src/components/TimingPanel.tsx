interface Props {
  computeUs: number;
  runs: number;
  traceMs: number;
  stepCount: number;
  animationMs: number;
  msPerStep: number;
  finished: boolean;
}

const fmtUs = (us: number) => (us < 1000 ? `${us.toFixed(1)} µs` : `${(us / 1000).toFixed(2)} ms`);
const fmtMs = (ms: number) =>
  ms < 10 ? `${ms.toFixed(1)} ms` : ms < 1000 ? `${ms.toFixed(0)} ms` : `${(ms / 1000).toFixed(1)} s`;

export function TimingPanel({ computeUs, runs, traceMs, stepCount, animationMs, msPerStep, finished }: Props) {
  const slower = animationMs > 0 ? (animationMs * 1000) / computeUs : 0;
  return (
    <section className="panel timing">
      <h2>Time</h2>
      <div className="tiles">
        <div className="tile">
          <div className="tile-label">Runtime (real computation)</div>
          <div className="tile-value">{fmtUs(computeUs)}</div>
          <div className="tile-sub">plain dijkstra(), average of {runs.toLocaleString()} runs</div>
        </div>
        <div className="tile">
          <div className="tile-label">Recording every step</div>
          <div className="tile-value">{fmtMs(traceMs)}</div>
          <div className="tile-sub">{stepCount.toLocaleString()} snapshots for the replay</div>
        </div>
        <div className="tile">
          <div className="tile-label">Animation (slow version)</div>
          <div className="tile-value">{fmtMs(animationMs)}</div>
          <div className="tile-sub">{fmtMs(msPerStep)} per step while playing</div>
        </div>
      </div>
      <p className="muted small">
        {finished && slower > 0
          ? `The animation took about ${Math.round(slower).toLocaleString()}× longer than the algorithm itself. `
          : ""}
        The runtime is the algorithm alone. The animation waits on purpose at every line so you can
        follow it, so its time measures the replay, not Dijkstra.
      </p>
    </section>
  );
}
