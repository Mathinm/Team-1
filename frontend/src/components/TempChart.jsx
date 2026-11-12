// Temperature history line chart (plain SVG, no chart library).
// The allowed range is shaded; points outside it are drawn in red.

export default function TempChart({ readings, tempMin, tempMax, height = 180 }) {
  if (!readings?.length) return <p className="muted small">No readings in this period.</p>;

  const W = 640;
  const H = height;
  const pad = { l: 36, r: 10, t: 10, b: 22 };
  const times = readings.map((r) => new Date(r.recordedAt).getTime());
  const values = readings.map((r) => r.value);
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const isSingle = readings.length === 1 || t1 === t0;
  const timeSpan = t1 - t0;
  const vMin = Math.floor(Math.min(...values, tempMin) - 1);
  const vMax = Math.ceil(Math.max(...values, tempMax) + 1);
  const x = (t) => isSingle ? (pad.l + (W - pad.l - pad.r) / 2) : (pad.l + ((t - t0) / (timeSpan || 1)) * (W - pad.l - pad.r));
  const y = (v) => pad.t + (1 - (v - vMin) / (vMax - vMin || 1)) * (H - pad.t - pad.b);

  const line = isSingle ? "" : readings.map((r, i) => `${i ? "L" : "M"}${x(times[i]).toFixed(1)},${y(r.value).toFixed(1)}`).join(" ");
  const out = readings.filter((r) => r.value < tempMin || r.value > tempMax);

  // Range limits always shown; outer ticks only if they don't crowd them.
  const minGap = (vMax - vMin) * 0.1;
  const yTicks = [tempMin, tempMax, ...[vMin, vMax].filter((v) => Math.abs(v - tempMin) > minGap && Math.abs(v - tempMax) > minGap)];
  const showSeconds = timeSpan > 0 && timeSpan < 5 * 60 * 1000;
  const hourLabel = (t) => new Date(t).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    ...(showSeconds ? { second: "2-digit" } : {}),
  });
  const last = readings[readings.length - 1];

  return (
    <svg
      className="chart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`Temperature over time. Allowed ${tempMin} to ${tempMax} °C. Latest ${last.value} °C. ${out.length} readings out of range.`}
    >
      <rect
        x={pad.l}
        y={y(tempMax)}
        width={W - pad.l - pad.r}
        height={y(tempMin) - y(tempMax)}
        className="chart__band"
      />
      {yTicks.map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} className="chart__grid" />
          <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" className="chart__label">{v}°</text>
        </g>
      ))}
      {isSingle ? (
        <text x={x(t0)} y={H - 6} textAnchor="middle" className="chart__label">
          {hourLabel(t0)}
        </text>
      ) : (
        Array.from({ length: 5 }, (_, i) => t0 + (timeSpan * i) / 4).map((t, i) => (
          <text key={i} x={x(t)} y={H - 6} textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"} className="chart__label">
            {hourLabel(t)}
          </text>
        ))
      )}
      {line && <path d={line} className="chart__line" />}
      {isSingle && (
        <circle
          cx={x(times[0])}
          cy={y(readings[0].value)}
          r="4"
          className={readings[0].value < tempMin || readings[0].value > tempMax ? "chart__out" : "chart__dot"}
        />
      )}
      {!isSingle && out.map((r) => (
        <circle key={r.recordedAt} cx={x(new Date(r.recordedAt).getTime())} cy={y(r.value)} r="3" className="chart__out" />
      ))}
    </svg>
  );
}
