import type { CoverageMap as CoverageMapData } from "../types";

export function CoverageMap({ coverage }: { coverage: CoverageMapData }) {
  const types = Object.entries(coverage.by_type);
  const max = Math.max(1, ...types.map(([, n]) => n));
  return (
    <div className="card">
      <h3>Coverage map</h3>
      <div className="coverage">
        {types.map(([type, n]) => (
          <div key={type} className="cov-row">
            <span className="cov-label">{type}</span>
            <div className="cov-bar-track">
              <div className={`cov-bar type-${type}`} style={{ width: `${(n / max) * 100}%` }} />
            </div>
            <span className="cov-n">{n}</span>
          </div>
        ))}
      </div>
      <p className="muted">Type diversity: {coverage.type_diversity_pct}%</p>
    </div>
  );
}
