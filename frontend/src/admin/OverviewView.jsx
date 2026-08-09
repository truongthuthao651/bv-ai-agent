import { useEffect, useMemo, useState } from "react";
import { KpiCard, Input, Button } from "../components/index.js";
import { docTypeLabel, localizedDepartmentDisplay } from "../i18n/catalog.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { fetchMetrics, askStreaming } from "./api.js";
import { formatVnDateTime } from "./formatVnTime.js";

function fmtPct(x) {
  return x === null || x === undefined ? "—" : Math.round(x * 100) + "%";
}
function fmtMs(x) {
  return x === null || x === undefined ? "—" : x < 1000 ? Math.round(x) + "ms" : (x / 1000).toFixed(1) + "s";
}
function fmtNum(x, digits = 1) {
  return x === null || x === undefined ? "—" : Number(x).toFixed(digits);
}

function useIsMobile() {
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 640px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const onChange = () => setMobile(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return mobile;
}

function Panel({ title, hint, action, children, span = 4, minHeight }) {
  const [hover, setHover] = useState(false);
  const mobile = useIsMobile();
  return (
    <section
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        gridColumn: mobile ? "1 / -1" : `span ${span}`,
        background: "var(--surface)",
        border: "1px solid var(--border)",
        boxShadow: hover ? "var(--shadow-md)" : "var(--shadow-sm)",
        borderRadius: "var(--radius-xl)",
        padding: "var(--pad-card-lg)",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight,
        transition: "box-shadow 180ms cubic-bezier(.2,.8,.2,1)",
      }}
    >
      <header style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "var(--space-4)", marginBottom: "var(--space-5)" }}>
        <div style={{ minWidth: 0 }}>
          <h2 style={{ margin: 0, fontSize: "var(--text-md)", fontWeight: "var(--weight-semibold)", letterSpacing: "var(--tracking-tight)", color: "var(--text-primary)" }}>{title}</h2>
          {hint && <p style={{ margin: "var(--space-1) 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)", lineHeight: "var(--leading-snug)" }}>{hint}</p>}
        </div>
        {action}
      </header>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", minWidth: 0 }}>{children}</div>
    </section>
  );
}

function Empty({ children }) {
  return <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>{children}</p>;
}

function AreaChart({ data }) {
  const { t } = useLocale();
  const [i, setI] = useState(null);
  if (data.length < 2) return <Empty>{t("overview.emptyChartDaily")}</Empty>;
  const values = data.map((d) => d.count);
  const W = 720, H = 180, PAD = 24;
  const max = Math.max(1, Math.ceil(Math.max(...values) / 5) * 5);
  const x = (n) => (n / (data.length - 1)) * W;
  const y = (v) => H - PAD - (v / max) * (H - PAD - 8);
  const line = values.map((v, n) => `${x(n)},${y(v)}`).join(" L ");
  return (
    <div
      style={{ position: "relative" }}
      onMouseLeave={() => setI(null)}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setI(Math.round(((e.clientX - r.left) / r.width) * (data.length - 1)));
      }}
    >
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="180" preserveAspectRatio="none" style={{ display: "block", overflow: "visible" }}>
        <defs>
          <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((f) => (
          <line key={f} x1={0} x2={W} y1={y(max * f)} y2={y(max * f)} stroke="var(--chart-grid)" strokeWidth="1" />
        ))}
        <path d={`M0,${H - PAD} L ${line} L ${W},${H - PAD} Z`} fill="url(#areaFill)" />
        <path d={`M ${line}`} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {i != null && values[i] != null && (
          <g>
            <line x1={x(i)} x2={x(i)} y1={0} y2={H - PAD} stroke="var(--border-strong)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            <circle cx={x(i)} cy={y(values[i])} r="4" fill="var(--surface)" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
          </g>
        )}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: "var(--space-2)", fontSize: "var(--text-2xs)", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
        <span>{data[0].date}</span>
        <span>{data[data.length - 1].date}</span>
      </div>
      {i != null && data[i] != null && (
        <div
          style={{
            position: "absolute",
            left: `${(i / (data.length - 1)) * 100}%`,
            top: -8,
            transform: "translate(-50%,-100%)",
            background: "var(--surface-raised)",
            border: "1px solid var(--border)",
            boxShadow: "var(--shadow-lg)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-3)",
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}
        >
          <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>{data[i].date}</div>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-bold)", color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>
            {data[i].count.toLocaleString()} {t("common.questions")}
          </div>
        </div>
      )}
    </div>
  );
}

function Heatmap({ cells }) {
  const { t } = useLocale();
  const weekdayLabels = useMemo(
    () => [
      t("overview.weekdayMon"),
      t("overview.weekdayTue"),
      t("overview.weekdayWed"),
      t("overview.weekdayThu"),
      t("overview.weekdayFri"),
      t("overview.weekdaySat"),
      t("overview.weekdaySun"),
    ],
    [t],
  );
  if (!cells.length || cells.every((c) => c.count === 0)) return <Empty>{t("overview.emptyHeatmap")}</Empty>;
  const max = Math.max(1, ...cells.map((c) => c.count));
  const byWeekday = Array.from({ length: 7 }, (_, wd) => cells.filter((c) => c.weekday === wd).sort((a, b) => a.hour - b.hour));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {byWeekday.map((row, wd) => (
        <div key={wd} style={{ display: "flex", alignItems: "center", gap: 2 }}>
          <div style={{ width: 24, flexShrink: 0, fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>{weekdayLabels[wd]}</div>
          {row.map((c) => (
            <div
              key={c.hour}
              title={`${weekdayLabels[wd]} ${c.hour}h (VN) — ${c.count} ${t("common.questions")}`}
              style={{
                flex: 1,
                height: 14,
                borderRadius: 2,
                background: c.count / max < 0.08 ? "var(--surface-sunken)" : `color-mix(in srgb, var(--accent) ${Math.round((c.count / max) * 88) + 10}%, var(--surface-sunken))`,
              }}
            />
          ))}
        </div>
      ))}
      <div style={{ display: "flex", gap: 2, marginTop: "var(--space-1)" }}>
        <div style={{ width: 24, flexShrink: 0 }} />
        {[0, 6, 12, 18, 23].map((h) => (
          <div key={h} style={{ flex: 1, textAlign: "left", fontSize: 9, color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
            {h}h
          </div>
        ))}
      </div>
    </div>
  );
}

function BarList({ items, valueLabel }) {
  const { t } = useLocale();
  if (!items.length) return <Empty>{t("overview.emptyData")}</Empty>;
  const max = Math.max(...items.map((i) => i.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      {items.map((it, i) => (
        <div key={it.label} style={{ display: "grid", gridTemplateColumns: "1fr 96px 44px", gap: "var(--space-3)", alignItems: "center" }}>
          <div title={it.label} style={{ fontSize: "var(--text-xs)", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {it.label}
          </div>
          <div style={{ background: "var(--chart-track)", borderRadius: 3, height: 6, overflow: "hidden" }}>
            <div style={{ width: `${(it.value / max) * 100}%`, height: "100%", background: i === 0 ? "var(--gold)" : "var(--accent)", borderRadius: 3 }} />
          </div>
          <div style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums", textAlign: "right" }}>
            {valueLabel ? valueLabel(it.value) : it.value}
          </div>
        </div>
      ))}
    </div>
  );
}

const DONUT_COLORS = ["var(--gold)", "var(--chart-series-a)", "var(--chart-series-b)", "var(--chart-series-c)", "var(--chart-series-d)"];

function Donut({ segments, size = 132 }) {
  const { t } = useLocale();
  if (!segments.length) return <Empty>{t("overview.emptyDocs")}</Empty>;
  const total = segments.reduce((a, s) => a + s.value, 0);
  let acc = 0;
  const stops = segments
    .map((s) => {
      const a = (acc / total) * 360;
      acc += s.value;
      return `${s.color} ${a}deg ${(acc / total) * 360}deg`;
    })
    .join(", ");
  const lead = segments[0];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-5)" }}>
      <div style={{ width: size, height: size, borderRadius: "50%", background: `conic-gradient(${stops})`, position: "relative", flexShrink: 0 }}>
        <div
          style={{
            position: "absolute",
            inset: size * 0.24,
            borderRadius: "50%",
            background: "var(--surface)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div style={{ fontSize: "var(--text-xl)", fontWeight: "var(--weight-bold)", color: "var(--text-primary)", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
            {Math.round((lead.value / total) * 100)}%
          </div>
          <div style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 2, textAlign: "center", padding: "0 4px" }}>{lead.label}</div>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", minWidth: 0, flex: 1 }}>
        {segments.map((s) => (
          <div key={s.label} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", fontSize: "var(--text-xs)", color: "var(--text-secondary)", minWidth: 0 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color, flexShrink: 0 }} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.label}</span>
            <span style={{ marginLeft: "auto", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Histogram({ bins }) {
  const { t } = useLocale();
  const total = bins.reduce((a, b) => a + b.count, 0);
  if (!total) return <Empty>{t("overview.emptyLatency")}</Empty>;
  const max = Math.max(...bins.map((b) => b.count));
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 108 }}>
        {bins.map((b, i) => (
          <div
            key={i}
            title={`${(b.start_ms / 1000).toFixed(1)}${b.end_ms ? `–${(b.end_ms / 1000).toFixed(1)}s` : "s+"} · ${b.count} ${t("common.questions")}`}
            style={{ flex: 1, height: `${(b.count / max) * 100}%`, minHeight: b.count ? 2 : 0, background: "var(--accent)", opacity: 0.7, borderRadius: "3px 3px 0 0" }}
          />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: "var(--space-2)", fontSize: "var(--text-2xs)", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
        <span>0s</span>
        <span>{(bins[bins.length - 1].start_ms / 1000).toFixed(1)}s+</span>
      </div>
    </div>
  );
}

function AskPanel() {
  const { t } = useLocale();
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [status, setStatus] = useState({ text: "", tone: "" });
  const [busy, setBusy] = useState(false);

  async function ask() {
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true);
    setAnswer("");
    setStatus({ text: t("overview.quickAskBusy"), tone: "" });
    try {
      await askStreaming(q, (delta) => setAnswer((prev) => prev + delta));
      setStatus({ text: t("overview.quickAskDone"), tone: "ok" });
    } catch (err) {
      setStatus({ text: `${t("common.error")}: ${err.message}`, tone: "bad" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>{t("overview.quickAskHint")}</p>
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("overview.quickAskPlaceholder")}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) ask();
          }}
        />
        <Button onClick={ask} disabled={busy}>
          {t("overview.quickAskButton")}
        </Button>
      </div>
      {status.text && (
        <div style={{ fontSize: "var(--text-xs)", color: status.tone === "ok" ? "var(--success)" : status.tone === "bad" ? "var(--danger)" : "var(--text-muted)" }}>
          {status.text}
        </div>
      )}
      {answer && (
        <div
          style={{
            padding: "var(--space-3) var(--space-4)",
            background: "var(--surface-sunken)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
            whiteSpace: "pre-wrap",
            fontSize: "var(--text-sm)",
            lineHeight: "var(--leading-relaxed)",
            color: "var(--text-primary)",
          }}
        >
          {answer}
        </div>
      )}
    </div>
  );
}

export function OverviewView() {
  const { t } = useLocale();
  const [hours, setHours] = useState(24);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);

  const windowOptions = useMemo(
    () => [
      { value: 1, label: t("common.last1h") },
      { value: 24, label: t("common.last24h") },
      { value: 168, label: t("common.last7d") },
      { value: 0, label: t("common.allTime") },
    ],
    [t],
  );

  const modeLabels = useMemo(
    () => ({
      grounded: t("overview.modeGrounded"),
      advisory: t("overview.modeAdvisory"),
      hybrid: t("overview.modeHybrid"),
      refusal: t("overview.modeRefusal"),
      other: t("overview.modeOther"),
    }),
    [t],
  );

  const unsetDeptVi = "Không đặt";

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchMetrics(hours)
      .then((data) => {
        if (!cancelled) setMetrics(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [hours]);

  const m = metrics;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: "var(--space-4)", flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: "var(--text-3xl)", fontWeight: "var(--weight-heavy)", letterSpacing: "var(--tracking-tight)", color: "var(--text-primary)", margin: "0 0 var(--space-2)", lineHeight: "var(--leading-tight)" }}>
            {t("overview.title")}
          </h1>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--text-md)" }}>{t("overview.subtitle")}</p>
        </div>
        <select
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          style={{
            font: "inherit",
            fontSize: "var(--text-sm)",
            height: "var(--control-h-sm)",
            padding: "0 var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border)",
            background: "var(--surface)",
            color: "var(--text-primary)",
          }}
        >
          {windowOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <Empty>
          {t("admin.loadMetricsError")} {error}
        </Empty>
      )}

      {m && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "var(--gap-card)" }}>
            <KpiCard label={t("overview.kpiQuestions")} value={m.n_requests} hint={t("overview.kpiQuestionsHint")} />
            <KpiCard label={t("overview.kpiDocs")} value={m.n_documents} hint={t("overview.kpiDocsHint")} />
            <KpiCard label={t("overview.kpiRefusal")} value={fmtPct(m.refusal_rate)} betterWhen="down" hint={t("overview.kpiRefusalHint")} />
            <KpiCard label={t("overview.kpiLatency")} value={fmtMs(m.elapsed_ms_p50)} betterWhen="down" hint={t("overview.kpiLatencyHint")} />
            <KpiCard label={t("overview.kpiHits")} value={fmtNum(m.n_hits_mean)} hint={t("overview.kpiHitsHint")} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: "var(--gap-card)" }}>
            <Panel span={8} title={t("overview.chartDaily")} hint={t("overview.chartDailyHint")}>
              <AreaChart data={m.daily_volume} />
            </Panel>

            <Panel span={4} title={t("overview.chartHeatmap")} hint={t("overview.chartHeatmapHint")}>
              <Heatmap cells={m.heatmap} />
            </Panel>

            <Panel span={5} title={t("overview.chartTopDocs")} hint={t("overview.chartTopDocsHint")}>
              <BarList items={m.top_documents.map((d) => ({ label: d.doc_title, value: d.count }))} />
            </Panel>

            <Panel span={3} title={t("overview.chartByDept")} hint={t("overview.chartByDeptHint")}>
              {m.documents_by_department.length === 1 && m.documents_by_department[0].department === unsetDeptVi ? (
                <Empty>{t("overview.emptyDept")}</Empty>
              ) : (
                <Donut
                  segments={m.documents_by_department.map((d, i) => ({
                    label: d.department === unsetDeptVi ? t("overview.unsetDept") : localizedDepartmentDisplay(d.department, t),
                    value: d.count,
                    color: DONUT_COLORS[i % DONUT_COLORS.length],
                  }))}
                />
              )}
            </Panel>

            <Panel span={4} title={t("overview.chartModes")} hint={t("overview.chartModesHint")}>
              {m.n_requests === 0 ? (
                <Empty>{t("overview.emptyModes")}</Empty>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
                  {Object.entries(modeLabels)
                    .filter(([key]) => (m.mode_breakdown?.[key] ?? 0) > 0)
                    .map(([key, label]) => (
                      <span
                        key={key}
                        style={{
                          padding: "var(--space-1) var(--space-3)",
                          borderRadius: "var(--radius-pill)",
                          background: "var(--accent-subtle)",
                          color: "var(--accent)",
                          fontSize: "var(--text-xs)",
                          fontWeight: "var(--weight-semibold)",
                        }}
                      >
                        {label}: {m.mode_breakdown[key]}
                      </span>
                    ))}
                </div>
              )}
            </Panel>

            <Panel span={5} title={t("overview.chartLatency")} hint={t("overview.chartLatencyHint")}>
              <Histogram bins={m.latency_histogram} />
            </Panel>

            <Panel span={7} title={t("overview.recentDocs")}>
              <div style={{ display: "flex", flexDirection: "column" }}>
                {m.recent_documents.length === 0 && <Empty>{t("overview.emptyDocs")}</Empty>}
                {m.recent_documents.map((d, i) => (
                  <div key={d.doc_id} style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-3)", padding: "var(--space-3) 0", borderTop: i ? "1px solid var(--border)" : "none" }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: "var(--text-sm)", color: "var(--text-primary)", lineHeight: "var(--leading-snug)" }}>{d.doc_title}</div>
                      <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-muted)", marginTop: 2 }}>
                        {docTypeLabel(d.doc_type, t) || d.doc_type} · {d.n_chunks} {t("common.chunks")}
                      </div>
                    </div>
                    <span style={{ fontSize: "var(--text-2xs)", color: "var(--text-muted)", flexShrink: 0, whiteSpace: "nowrap" }}>
                      {formatVnDateTime(d.ingested_at)}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel span={12} title={t("overview.quickAsk")}>
              <AskPanel />
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
