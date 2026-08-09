import { Triangle } from "../brand/Triangle.jsx";
import { Lift } from "../brand/Lift.jsx";

/* Landing → auth flow. Navy is the marketing surface; the app itself stays
 * light. CONFIRMED DELIBERATE (audit/03-frontend.md finding F3-1 asked this
 * to be settled one way or the other): this page and app/templates/login.html
 * both render a fixed navy-hero design regardless of prefers-color-scheme,
 * with no ThemeToggle exposed on either — pre-authentication surfaces stay
 * on-brand navy; only the post-login product (chat, admin) respects the
 * signed-in user's light/dark preference. Not an oversight or a
 * half-migrated token pass — if this page ever needs to theme, wire
 * `onInk`/`INK` below to the color tokens instead of their current hardcoded
 * hex values, but that's a deliberate redesign decision to make later, not a
 * bug to fix now.
 *
 * Ported from ui_kits/landing/LandingScreen.jsx. Single CTA to /login; signup
 * is available on the login page ("Tạo tài khoản") for @baoviet.com emails. */

const INK = "var(--brand-ink)"; // matches the kit's local INK constant (#0C2A45) exactly
const onInk = {
  heading: "#FFFFFF",
  body: "rgba(255,255,255,.72)",
  faint: "rgba(255,255,255,.52)",
  hair: "rgba(255,255,255,.14)",
};

const VALUES = [
  [
    "Có căn cứ từ tài liệu",
    "Mọi câu trả lời trích dẫn đúng tài liệu và điều khoản đã được nạp — kèm số trang khi có.",
  ],
  [
    "Tiếng Việt đầy đủ",
    "Xử lý đúng dấu tiếng Việt, ký hiệu định phí và thuật ngữ nghiệp vụ nhóm đang dùng.",
  ],
  [
    "Không rời khỏi mạng nội bộ",
    "Tài liệu và câu hỏi không rời khỏi hệ thống nội bộ. Không gọi bất kỳ dịch vụ bên ngoài nào.",
  ],
];

export function LandingScreen({ onEnter }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: `linear-gradient(155deg, var(--brand-navy) 0%, ${INK} 58%, #06192B 100%)`,
        fontFamily: "var(--font-sans)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <header style={{ display: "flex", alignItems: "center", gap: "var(--space-4)", padding: "var(--space-6) var(--space-10)", flexShrink: 0 }}>
        <img src="/assets/logo-baoviet-life-onnavy.png" alt="Bảo Việt Life" style={{ height: 30 }} />
        <div style={{ marginLeft: "auto" }}>
          <Lift
            onClick={onEnter}
            style={{
              height: "var(--control-h-md)",
              padding: "0 var(--space-4)",
              border: "none",
              background: "transparent",
              color: onInk.body,
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-sm)",
              fontWeight: "var(--weight-semibold)",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              transition: "background 150ms, color 150ms",
            }}
            hoverStyle={{ background: "rgba(255,255,255,.08)", color: "#fff" }}
          >
            Đăng nhập
          </Lift>
        </div>
      </header>

      <main
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "var(--space-12) var(--space-10) var(--space-10)",
          maxWidth: 1180,
          width: "100%",
          margin: "0 auto",
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--space-2)",
            alignSelf: "flex-start",
            padding: "var(--space-1) var(--space-3) var(--space-1) var(--space-2)",
            borderRadius: "var(--radius-pill)",
            background: "rgba(224,162,8,.14)",
            border: "1px solid rgba(224,162,8,.3)",
            marginBottom: "var(--space-6)",
          }}
        >
          <Triangle size={11} />
          <span style={{ fontSize: "var(--text-xs)", fontWeight: "var(--weight-semibold)", color: "var(--brand-gold-light)", letterSpacing: "var(--tracking-wide)", textTransform: "uppercase" }}>
            Công cụ nội bộ · Trợ lý AI Bảo Việt Life
          </span>
        </div>

        <h1 style={{ margin: 0, fontSize: 62, lineHeight: 1.05, fontWeight: "var(--weight-heavy)", letterSpacing: "-0.03em", color: onInk.heading, maxWidth: 880, textWrap: "pretty" }}>
          Mọi câu trả lời,
          <br />
          kèm nguồn trích dẫn rõ ràng.
        </h1>
        <p style={{ margin: "var(--space-6) 0 0", fontSize: "var(--text-lg)", lineHeight: "var(--leading-normal)", color: onInk.body, maxWidth: 620 }}>
          Hỏi về bất kỳ quy tắc, sản phẩm hay văn bản nội bộ đã được nạp vào hệ thống và nhận câu trả lời có trích
          dẫn trong vài giây — thay vì phải mở sáu tệp PDF.
        </p>

        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginTop: "var(--space-10)" }}>
          <Lift
            onClick={onEnter}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--space-2)",
              height: 52,
              padding: "0 var(--space-8)",
              border: "none",
              borderRadius: "var(--radius-md)",
              background: "var(--brand-gold)",
              color: "var(--text-on-gold)",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-md)",
              fontWeight: "var(--weight-bold)",
              cursor: "pointer",
              boxShadow: "0 8px 28px rgba(224,162,8,.28)",
              transition: "background 150ms, transform 150ms, box-shadow 150ms",
            }}
            hoverStyle={{ background: "var(--brand-gold-light)", transform: "translateY(-1px)", boxShadow: "0 12px 34px rgba(224,162,8,.36)" }}
          >
            Vào hệ thống <span style={{ fontSize: 17, lineHeight: 1 }}>→</span>
          </Lift>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "var(--space-10)",
            marginTop: "var(--space-20)",
            paddingTop: "var(--space-8)",
            borderTop: "1px solid " + onInk.hair,
          }}
        >
          {VALUES.map(([title, body]) => (
            <div key={title} style={{ minWidth: 0 }}>
              <div style={{ marginBottom: "var(--space-3)" }}>
                <Triangle size={10} />
              </div>
              <div style={{ fontSize: "var(--text-md)", fontWeight: "var(--weight-semibold)", color: onInk.heading, marginBottom: "var(--space-2)", letterSpacing: "var(--tracking-tight)" }}>
                {title}
              </div>
              <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: onInk.body, textWrap: "pretty" }}>{body}</p>
            </div>
          ))}
        </div>
      </main>

      <footer style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", padding: "var(--space-6) var(--space-10)", fontSize: "var(--text-xs)", color: onInk.faint, flexShrink: 0 }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--success)" }} />
        Chạy hoàn toàn trong mạng nội bộ
        <span style={{ marginLeft: "auto" }}>Bảo Việt Nhân Thọ · Chỉ dùng nội bộ</span>
      </footer>
    </div>
  );
}
