import { useEffect, useState } from "react";
import { Triangle } from "../brand/Triangle.jsx";
import { fetchPromptSuggestions } from "./api.js";

/** Ported from ui_kits/chatbot/ChatParts.jsx's EmptyState. The kit groups
 * suggestions into three named categories ("Policy lookup", "Actuarial",
 * "Products & circulars") that don't match the real six suggestions in
 * scripts/open_webui/prompt_suggestions.json (Open WebUI's actual copy), so
 * this renders them as a flat grid instead of inventing category labels the
 * source file doesn't have. Greeting uses the real signed-in email, not the
 * kit's fabricated "Vân". */
export function EmptyState({ me, onPick }) {
  const [suggestions, setSuggestions] = useState([]);

  useEffect(() => {
    fetchPromptSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions([]));
  }, []);

  return (
    <div style={{ margin: "auto", width: "100%", maxWidth: "var(--content-max)", padding: "var(--space-12) var(--space-8)", boxSizing: "border-box" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
        <Triangle size={18} />
        <div style={{ fontSize: "var(--text-3xl)", fontWeight: "var(--weight-heavy)", letterSpacing: "var(--tracking-tight)", color: "var(--text-primary)", lineHeight: "var(--leading-tight)" }}>
          Xin chào{me?.email ? `, ${me.email.split("@")[0]}` : ""}
        </div>
      </div>
      <p style={{ margin: "0 0 var(--space-8)", fontSize: "var(--text-md)", color: "var(--text-secondary)", lineHeight: "var(--leading-normal)", maxWidth: 560 }}>
        Hỏi về bất kỳ quy tắc, sản phẩm hay văn bản nội bộ đã được nạp vào hệ thống. Câu trả lời có trích dẫn nguồn tài liệu và trang.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "var(--gap-card)" }}>
        {suggestions.map((s, i) => (
          <button
            key={i}
            onClick={() => onPick(s.content)}
            style={{
              textAlign: "left",
              border: "1px solid var(--border)",
              background: "var(--surface)",
              borderRadius: "var(--radius-lg)",
              padding: "var(--space-3) var(--space-4)",
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            {s.title?.[0] && (
              <div style={{ fontSize: "var(--text-2xs)", fontWeight: "var(--weight-bold)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--tracking-wide)", marginBottom: "var(--space-1)" }}>
                {s.title[0]}
              </div>
            )}
            <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)", color: "var(--text-primary)", lineHeight: "var(--leading-snug)" }}>{s.title?.[1] || s.content}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
