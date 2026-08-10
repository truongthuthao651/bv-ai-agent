import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, PaginatedList, SubTabBar } from "../components/index.js";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { fetchAdminConfig, fetchEvalRuns, fetchFeedbackLog, fetchQueryTimingLog } from "./api.js";
import { formatVnTime } from "./formatVnTime.js";
import { localizedDepartmentDisplay } from "../i18n/catalog.js";

function pct(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n * 100)}%`;
}

function ConfigRow({ label, value }) {
  return (
    <tr>
      <td style={{ fontWeight: "var(--weight-semibold)", color: "var(--text-secondary)", padding: "var(--space-2) var(--space-3)" }}>{label}</td>
      <td style={{ color: "var(--text-primary)", padding: "var(--space-2) var(--space-3)", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)" }}>{value}</td>
    </tr>
  );
}

function logsSubTabFromHash() {
  const key = window.location.hash.slice(1);
  return key === "logs/queries" ? "queries" : "feedback";
}

function setLogsHash(tab) {
  window.location.hash = tab === "queries" ? "logs/queries" : "logs";
}

function paginationLabels(t) {
  return {
    sortNewest: t("common.newest"),
    sortOldest: t("common.oldest"),
    pageLabel: t("common.page"),
    ofLabel: t("common.of"),
    rowsLabel: t("common.rows"),
    prevLabel: t("common.prev"),
    nextLabel: t("common.next"),
  };
}

function hourOptions(t) {
  return [
    { value: 24, label: t("common.last24h") },
    { value: 168, label: t("common.last7d") },
    { value: 720, label: t("common.last30d") },
    { value: 0, label: t("common.allTime") },
  ];
}

export function ModelsView() {
  const { t } = useLocale();
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetchAdminConfig().then(setCfg).catch((e) => setErr(e.message));
  }, []);

  if (err) return <p style={{ color: "var(--danger)" }}>{t("common.error")}: {err}</p>;
  if (!cfg) return <p style={{ color: "var(--text-muted)" }}>{t("common.loading")}</p>;

  return (
    <Card title={t("models.title")} hint={cfg.note}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <tbody>
          <ConfigRow label="CHAT_MODEL" value={cfg.chat_model} />
          <ConfigRow label="EMBED_MODEL" value={cfg.embed_model} />
          <ConfigRow label="RETRIEVE_TOP_K" value={String(cfg.retrieve_top_k)} />
          <ConfigRow label="RERANK_TOP_K" value={String(cfg.rerank_top_k)} />
          <ConfigRow label="RERANK_MIN_SCORE" value={String(cfg.rerank_min_score)} />
        </tbody>
      </table>
    </Card>
  );
}

export function SettingsView() {
  const { t } = useLocale();
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetchAdminConfig().then(setCfg).catch((e) => setErr(e.message));
  }, []);

  if (err) return <p style={{ color: "var(--danger)" }}>{t("common.error")}: {err}</p>;
  if (!cfg) return <p style={{ color: "var(--text-muted)" }}>{t("common.loading")}</p>;

  return (
    <Card title={t("models.settingsTitle")} hint={t("models.settingsHint")}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <tbody>
          <ConfigRow label="API_PUBLIC_BASE_URL" value={cfg.api_public_base_url} />
          <ConfigRow label={t("models.department")} value={cfg.departments.map((d) => localizedDepartmentDisplay(d, t)).join(", ") || "—"} />
          <ConfigRow label={t("models.queryLog")} value={cfg.query_timing_log_enabled ? t("common.on") : t("common.off")} />
          <ConfigRow label={t("models.feedbackLog")} value={cfg.feedback_log_enabled ? t("common.on") : t("common.off")} />
        </tbody>
      </table>
    </Card>
  );
}

export function EvaluationView() {
  const { t } = useLocale();
  const [runs, setRuns] = useState(null);
  const [err, setErr] = useState(null);
  const [modelFilter, setModelFilter] = useState("");

  useEffect(() => {
    fetchEvalRuns()
      .then((d) => setRuns(d.runs ?? []))
      .catch((e) => setErr(e.message));
  }, []);

  const modelOptions = useMemo(() => {
    if (!runs) return [{ value: "", label: t("ragas.allModels") }];
    const models = [...new Set(runs.map((r) => r.chat_model).filter(Boolean))].sort();
    return [
      { value: "", label: t("ragas.allModels") },
      ...models.map((m) => ({ value: m, label: m })),
    ];
  }, [runs, t]);

  const labels = paginationLabels(t);

  if (err) return <p style={{ color: "var(--danger)" }}>{t("common.error")}: {err}</p>;
  if (!runs) return <p style={{ color: "var(--text-muted)" }}>{t("common.loading")}</p>;

  return (
    <Card
      title={t("ragas.title")}
      hint={runs.length === 0 ? t("ragas.hintEmpty") : t("ragas.hint")}
    >
      <PaginatedList
        rows={runs}
        columns={[t("ragas.colFile"), t("ragas.colTime"), t("ragas.colN"), t("ragas.colDocHit"), t("ragas.colRefusal"), t("ragas.colAssertion")]}
        emptyLabel={t("ragas.empty")}
        defaultSortKey="mtime"
        filterPlaceholder={t("common.search")}
        getSortValue={(row, key) => (key === "mtime" ? row.mtime : row[key])}
        filterFn={(row, q) =>
          row.file.toLowerCase().includes(q) ||
          (row.chat_model && row.chat_model.toLowerCase().includes(q))
        }
        rowKey={(row) => row.file}
        extraFilters={{
          ...labels,
          model: modelFilter,
          onModel: setModelFilter,
          modelOptions,
          apply: (list) => (modelFilter ? list.filter((r) => r.chat_model === modelFilter) : list),
        }}
        renderRow={(r) => [
          r.file,
          formatVnTime(r.mtime),
          r.n ?? "—",
          pct(r.doc_hit_rate),
          pct(r.refusal_correct_rate),
          pct(r.assertion_pass_rate),
        ]}
      />
    </Card>
  );
}

export function LogsView() {
  const { t } = useLocale();
  const [tab, setTab] = useState(logsSubTabFromHash);
  const [feedback, setFeedback] = useState(null);
  const [queries, setQueries] = useState(null);
  const [err, setErr] = useState(null);
  const [fbHours, setFbHours] = useState(168);
  const [qHours, setQHours] = useState(168);
  const [modeFilter, setModeFilter] = useState("");

  const loadFeedback = useCallback((hours) => {
    fetchFeedbackLog({ hours, limit: 2000 })
      .then((d) => setFeedback(d.records ?? []))
      .catch((e) => setErr(e.message));
  }, []);

  const loadQueries = useCallback((hours) => {
    fetchQueryTimingLog({ hours, limit: 2000 })
      .then((d) => setQueries(d.records ?? []))
      .catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    loadFeedback(fbHours);
  }, [fbHours, loadFeedback]);

  useEffect(() => {
    loadQueries(qHours);
  }, [qHours, loadQueries]);

  useEffect(() => {
    function onHash() {
      setTab(logsSubTabFromHash());
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  function selectTab(next) {
    setTab(next);
    setLogsHash(next);
  }

  const modeOptions = useMemo(() => {
    if (!queries) return [{ value: "", label: t("logs.allModes") }];
    const modes = [...new Set(queries.map((r) => r.mode).filter(Boolean))].sort();
    return [
      { value: "", label: t("logs.allModes") },
      ...modes.map((m) => ({ value: m, label: m })),
    ];
  }, [queries, t]);

  const labels = paginationLabels(t);
  const hoursOpts = hourOptions(t);

  if (err) return <p style={{ color: "var(--danger)" }}>{t("common.error")}: {err}</p>;
  if (feedback === null || queries === null) return <p style={{ color: "var(--text-muted)" }}>{t("common.loading")}</p>;

  return (
    <div>
      <SubTabBar
        active={tab}
        onSelect={selectTab}
        tabs={[
          { key: "feedback", label: t("logs.tabFeedback"), count: feedback.length },
          { key: "queries", label: t("logs.tabQueries"), count: queries.length },
        ]}
      />

      {tab === "feedback" ? (
        <Card title={t("logs.tabFeedback")} hint={t("logs.feedbackHint")}>
          <PaginatedList
            rows={feedback}
            columns={[t("logs.colTime"), t("logs.colCompletion"), t("logs.colReason")]}
            emptyLabel={t("logs.emptyFeedback")}
            defaultSortKey="ts"
            filterPlaceholder={t("common.search")}
            getSortValue={(row, key) => row[key]}
            filterFn={(row, q) =>
              row.completion_id.toLowerCase().includes(q) ||
              (row.reason && row.reason.toLowerCase().includes(q))
            }
            rowKey={(row) => `${row.ts}-${row.completion_id}`}
            extraFilters={{
              ...labels,
              hours: fbHours,
              onHours: setFbHours,
              hourOptions: hoursOpts,
            }}
            renderRow={(r) => [formatVnTime(r.ts), r.completion_id, r.reason ?? "—"]}
          />
        </Card>
      ) : (
        <Card title={t("logs.tabQueries")} hint={t("logs.queriesHint")}>
          <PaginatedList
            rows={queries}
            columns={[t("logs.colTime"), t("logs.colMode"), t("logs.colElapsed"), t("logs.colTtft"), t("logs.colHits")]}
            emptyLabel={t("logs.emptyQueries")}
            defaultSortKey="ts"
            filterPlaceholder={t("common.search")}
            getSortValue={(row, key) => row[key]}
            filterFn={(row, q) =>
              (row.mode && row.mode.toLowerCase().includes(q)) ||
              String(row.elapsed_ms ?? "").includes(q)
            }
            rowKey={(row) => `${row.ts}-${row.mode}-${row.elapsed_ms}`}
            extraFilters={{
              ...labels,
              hours: qHours,
              onHours: setQHours,
              hourOptions: hoursOpts,
              mode: modeFilter,
              onMode: setModeFilter,
              modeOptions,
              apply: (list) => (modeFilter ? list.filter((r) => r.mode === modeFilter) : list),
            }}
            renderRow={(r) => [
              formatVnTime(r.ts),
              r.mode ?? "—",
              r.elapsed_ms ?? "—",
              r.first_token_ms ?? "—",
              r.n_hits ?? "—",
            ]}
          />
        </Card>
      )}
    </div>
  );
}
