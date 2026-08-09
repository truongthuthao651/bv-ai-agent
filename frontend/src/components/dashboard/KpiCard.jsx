import React from "react";
import { Icon } from "../icons/Icon.jsx";
import { useLocale } from "../../i18n/LocaleContext.jsx";

/**
 * A metric tile. `betterWhen` decides whether the delta reads as good or bad —
 * a falling response time is an improvement, a falling feedback rate is not.
 */
export function KpiCard({ label, value, unit, delta, betterWhen = "up", trend = [], hint }) {
  const { t } = useLocale();
  const [hover, setHover] = React.useState(false);
  const rising = delta != null && delta >= 0;
  const good = betterWhen === "flat" ? null : rising === (betterWhen === "up");
  const deltaColor = good == null ? "var(--text-secondary)" : good ? "var(--success)" : "var(--danger)";
  const w = 64, h = 20;
  const pts = trend.length > 1 ? trend.map((v, i) => `${(i / (trend.length - 1)) * w},${h - v * (h - 2) - 1}`).join(" ") : "";
  return (
    <div title={hint} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: hover ? "var(--shadow-md)" : "var(--shadow-sm)", transform: hover ? "translateY(-1px)" : "none", transition: "box-shadow 180ms cubic-bezier(.2,.8,.2,1), transform 180ms cubic-bezier(.2,.8,.2,1)", borderRadius: "var(--radius-xl)", padding: "var(--pad-card)", display: "flex", flexDirection: "column", gap: "var(--space-3)", minWidth: 0 }}>
      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", fontWeight: "var(--weight-medium)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: "var(--space-3)" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 2, minWidth: 0 }}>
          <span style={{ fontSize: "var(--text-2xl)", fontWeight: "var(--weight-bold)", color: "var(--text-primary)", letterSpacing: "var(--tracking-tight)", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{value}</span>
          {unit && <span style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-semibold)", color: "var(--text-muted)" }}>{unit}</span>}
        </div>
        {trend.length > 1 && (
          <svg width={w} height={h} style={{ flexShrink: 0, overflow: "visible" }} aria-hidden="true">
            <polyline points={pts} fill="none" stroke={deltaColor} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" opacity=".85" />
          </svg>
        )}
      </div>
      {delta != null && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-1)", fontSize: "var(--text-2xs)" }}>
          <span style={{ fontWeight: "var(--weight-bold)", color: deltaColor, fontVariantNumeric: "tabular-nums", display: "inline-flex", alignItems: "center", gap: 2 }}>
            <Icon name={rising ? "trend-up" : "trend-down"} size={12} color={deltaColor} /> {Math.abs(delta)}%
          </span>
          <span style={{ color: "var(--text-muted)" }}>{t("common.vsLastWeek")}</span>
        </div>
      )}
    </div>
  );
}
