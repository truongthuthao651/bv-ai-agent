import { useEffect, useState } from "react";
import { Card, Table } from "../components/index.js";
import { fetchAdminConfig, fetchEvalRuns, fetchFeedbackLog, fetchQueryTimingLog } from "./api.js";
import { departmentDisplay } from "./departmentLabels.js";

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

export function ModelsView() {
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetchAdminConfig().then(setCfg).catch((e) => setErr(e.message));
  }, []);

  if (err) return <p style={{ color: "var(--danger)" }}>Lỗi: {err}</p>;
  if (!cfg) return <p style={{ color: "var(--text-muted)" }}>Đang tải…</p>;

  return (
    <Card title="Mô hình & truy vấn" hint={cfg.note}>
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
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetchAdminConfig().then(setCfg).catch((e) => setErr(e.message));
  }, []);

  if (err) return <p style={{ color: "var(--danger)" }}>Lỗi: {err}</p>;
  if (!cfg) return <p style={{ color: "var(--text-muted)" }}>Đang tải…</p>;

  return (
    <Card title="Thiết lập hiệu lực" hint="Chỉ đọc — sửa .env trên máy chủ rồi khởi động lại dịch vụ.">
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <tbody>
          <ConfigRow label="API_PUBLIC_BASE_URL" value={cfg.api_public_base_url} />
          <ConfigRow label="Phòng ban" value={cfg.departments.map(departmentDisplay).join(", ") || "—"} />
          <ConfigRow label="Ghi nhật ký truy vấn" value={cfg.query_timing_log_enabled ? "Bật" : "Tắt"} />
          <ConfigRow label="Ghi phản hồi 👎" value={cfg.feedback_log_enabled ? "Bật" : "Tắt"} />
        </tbody>
      </table>
    </Card>
  );
}

export function EvaluationView() {
  const [runs, setRuns] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetchEvalRuns().then((d) => setRuns(d.runs ?? [])).catch((e) => setErr(e.message));
  }, []);

  if (err) return <p style={{ color: "var(--danger)" }}>Lỗi: {err}</p>;
  if (!runs) return <p style={{ color: "var(--text-muted)" }}>Đang tải…</p>;
  if (runs.length === 0) {
    return (
      <Card title="Đánh giá chất lượng (RAGAS)" hint="Chạy offline: python eval/run_ragas.py — kết quả lưu trong eval/results/.">
        <p style={{ margin: 0, color: "var(--text-secondary)" }}>Chưa có báo cáo nào trong eval/results/.</p>
      </Card>
    );
  }

  return (
    <Card title="Đánh giá chất lượng (RAGAS)" hint="Báo cáo offline từ eval/run_ragas.py — không chứa nội dung câu hỏi/câu trả lời.">
      <Table
        columns={["Tệp", "Thời gian", "N", "Doc hit", "Refusal", "Assertion"]}
        rows={runs}
        renderRow={(r) => [
          r.file,
          r.mtime?.slice(0, 19).replace("T", " ") ?? "—",
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
  const [feedback, setFeedback] = useState(null);
  const [queries, setQueries] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    Promise.all([fetchFeedbackLog(), fetchQueryTimingLog()])
      .then(([fb, q]) => {
        setFeedback(fb.records ?? []);
        setQueries(q.records ?? []);
      })
      .catch((e) => setErr(e.message));
  }, []);

  if (err) return <p style={{ color: "var(--danger)" }}>Lỗi: {err}</p>;
  if (feedback === null) return <p style={{ color: "var(--text-muted)" }}>Đang tải…</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap-section)" }}>
      <Card title={`Phản hồi 👎 (${feedback.length})`} hint="Metadata-only — không có nội dung câu hỏi hay câu trả lời.">
        <Table
          columns={["Thời gian", "Completion ID", "Lý do"]}
          rows={feedback}
          emptyLabel="Chưa có bản ghi."
          renderRow={(r) => [
            r.ts?.slice(0, 19).replace("T", " ") ?? "—",
            r.completion_id,
            r.reason ?? "—",
          ]}
        />
      </Card>
      <Card title={`Nhật ký truy vấn (${queries.length})`} hint="Metadata-only — mode, latency, số hit; không có nội dung câu hỏi.">
        <Table
          columns={["Thời gian", "Mode", "Elapsed (ms)", "TTFT (ms)", "Hits"]}
          rows={queries}
          emptyLabel="Chưa có bản ghi."
          renderRow={(r) => [
            r.ts?.slice(0, 19).replace("T", " ") ?? "—",
            r.mode ?? "—",
            r.elapsed_ms ?? "—",
            r.first_token_ms ?? "—",
            r.n_hits ?? "—",
          ]}
        />
      </Card>
    </div>
  );
}
