import { Lift } from "../brand/Lift.jsx";

/* Pre-auth landing — navy brand surface, single CTA to /login. */

const INK = "var(--brand-ink)";
const onInk = {
  heading: "#FFFFFF",
  body: "rgba(255,255,255,.72)",
  faint: "rgba(255,255,255,.48)",
};

/** Official group tagline — baoviet.com.vn */
const BRAND_TAGLINE = "Niềm tin vững chắc, cam kết vững bền";

export function LandingScreen({ onEnter }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: `linear-gradient(155deg, var(--brand-navy) 0%, ${INK} 58%, #06192B 100%)`,
        fontFamily: "var(--font-sans)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-8) var(--space-6)",
        boxSizing: "border-box",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        aria-hidden
        style={{
          position: "absolute",
          top: "14%",
          left: "50%",
          transform: "translateX(-50%)",
          width: "min(560px, 92vw)",
          height: "min(560px, 92vw)",
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(224,162,8,.14) 0%, rgba(42,122,193,.07) 40%, transparent 68%)",
          pointerEvents: "none",
        }}
      />

      <main
        style={{
          position: "relative",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          width: "100%",
          maxWidth: 460,
        }}
      >
        <img
          src="/assets/logo-baoviet-life-onnavy.png"
          alt="Bảo Việt Life"
          style={{
            height: 120,
            width: "auto",
            maxWidth: "min(460px, 90vw)",
            filter: "drop-shadow(0 14px 32px rgba(0,0,0,.24))",
          }}
        />
        <h1
          style={{
            margin: "var(--space-8) 0 0",
            fontSize: "var(--text-2xl)",
            lineHeight: "var(--leading-snug)",
            fontWeight: "var(--weight-semibold)",
            letterSpacing: "var(--tracking-tight)",
            color: onInk.heading,
          }}
        >
          Trợ lý AI Bảo Việt Life
        </h1>
        <p
          style={{
            margin: "var(--space-4) 0 0",
            fontSize: "var(--text-sm)",
            lineHeight: "var(--leading-relaxed)",
            color: onInk.faint,
            fontStyle: "italic",
            maxWidth: 340,
          }}
        >
          {BRAND_TAGLINE}
        </p>

        <Lift
          onClick={onEnter}
          style={{
            marginTop: "var(--space-10)",
            height: "var(--control-h-lg)",
            padding: "0 var(--space-10)",
            border: "none",
            borderRadius: "var(--radius-md)",
            background: "var(--brand-gold)",
            color: "var(--text-on-gold)",
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-base)",
            fontWeight: "var(--weight-bold)",
            cursor: "pointer",
            boxShadow: "0 8px 24px rgba(224,162,8,.24)",
            transition: "background 150ms, transform 150ms, box-shadow 150ms",
          }}
          hoverStyle={{
            background: "var(--brand-gold-light)",
            transform: "translateY(-1px)",
            boxShadow: "0 12px 32px rgba(224,162,8,.32)",
          }}
        >
          Tiếp tục
        </Lift>
      </main>
    </div>
  );
}
