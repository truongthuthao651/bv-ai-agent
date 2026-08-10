import { useEffect, useRef } from "react";
import { Lift } from "../brand/Lift.jsx";
import { LanguageToggle } from "../i18n/LanguageToggle.jsx";
import { useLocale } from "../i18n/LocaleContext.jsx";
import { landingTitleWords } from "../i18n/messages.js";
import "./landing.css";

/* Pre-auth landing — navy brand surface, single CTA to /login. */

const NETWORK_NODES = [
  { cx: "12%", cy: "18%", gold: false },
  { cx: "88%", cy: "22%", gold: true },
  { cx: "8%", cy: "78%", gold: false },
  { cx: "92%", cy: "72%", gold: false },
  { cx: "22%", cy: "48%", gold: true },
  { cx: "78%", cy: "52%", gold: false },
  { cx: "50%", cy: "10%", gold: false },
  { cx: "50%", cy: "90%", gold: true },
];

const NETWORK_LINES = [
  ["12%", "18%", "50%", "10%"],
  ["88%", "22%", "50%", "10%"],
  ["12%", "18%", "22%", "48%"],
  ["88%", "22%", "78%", "52%"],
  ["22%", "48%", "78%", "52%"],
  ["8%", "78%", "22%", "48%"],
  ["92%", "72%", "78%", "52%"],
  ["8%", "78%", "50%", "90%"],
  ["92%", "72%", "50%", "90%"],
];

function useParallax(ref) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;

    let raf = 0;
    const onMove = (event) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const x = event.clientX / window.innerWidth - 0.5;
        const y = event.clientY / window.innerHeight - 0.5;
        el.style.setProperty("--px", x.toFixed(4));
        el.style.setProperty("--py", y.toFixed(4));
      });
    };

    window.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", onMove);
    };
  }, [ref]);
}

export function LandingScreen({ onEnter }) {
  const rootRef = useRef(null);
  const { locale, t } = useLocale();
  useParallax(rootRef);
  const titleWords = landingTitleWords[locale] ?? landingTitleWords.vi;

  useEffect(() => {
    document.title = t("landing.documentTitle");
  }, [locale, t]);

  return (
    <div className="bv-landing" ref={rootRef}>
      <div className="bv-landing__lang">
        <LanguageToggle variant="dark" />
      </div>
      <div className="bv-landing__scene" aria-hidden="true">
        <div className="bv-landing__base-gradient" />
        <div className="bv-landing__aurora">
          <div className="bv-landing__aurora-blob bv-landing__aurora-blob--gold" />
          <div className="bv-landing__aurora-blob bv-landing__aurora-blob--blue" />
          <div className="bv-landing__aurora-blob bv-landing__aurora-blob--teal" />
        </div>
        <div className="bv-landing__grid" />

        <svg className="bv-landing__network" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {NETWORK_LINES.map(([x1, y1, x2, y2], i) => (
            <line
              key={i}
              className={`bv-landing__network-line${i % 2 ? " bv-landing__network-line--blue" : ""}`}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {NETWORK_NODES.map((node, i) => (
            <circle
              key={i}
              className={`bv-landing__network-node${node.gold ? " bv-landing__network-node--gold" : ""}`}
              cx={node.cx}
              cy={node.cy}
              r="2.5"
              style={{ animationDelay: `${i * 0.35}s` }}
            />
          ))}
        </svg>
      </div>

      <main className="bv-landing__main">
        <div className="bv-landing__hero">
          <div className="bv-landing__orbits" aria-hidden="true">
            <span className="bv-landing__orbit bv-landing__orbit--1">
              <span className="bv-landing__orbit-dot" />
            </span>
            <span className="bv-landing__orbit bv-landing__orbit--2" />
            <span className="bv-landing__orbit bv-landing__orbit--3" />
          </div>
          <span className="bv-landing__pulse-ring" aria-hidden="true" />
          <span className="bv-landing__pulse-ring bv-landing__pulse-ring--2" aria-hidden="true" />
          <img
            className="bv-landing__logo"
            src="/assets/logo-baoviet-life-onnavy.png"
            alt={t("landing.logoAlt")}
          />
        </div>

        <h1 className="bv-landing__title" key={locale}>
          {titleWords.map((word, i) => (
            <span
              key={`${locale}-${word.text}`}
              className={`bv-landing__title-word${word.accent ? " bv-landing__title-word--accent" : ""}`}
              style={{ "--delay": `${0.45 + i * 0.1}s` }}
            >
              {word.text}
              {i < titleWords.length - 1 ? "\u00a0" : ""}
            </span>
          ))}
        </h1>
        <p className="bv-landing__tagline">{t("landing.tagline")}</p>

        <Lift
          className="bv-landing__cta"
          onClick={onEnter}
          hoverStyle={{
            transform: "translateY(-2px) scale(1.02)",
            boxShadow: "0 16px 44px rgba(224,162,8,.42)",
          }}
        >
          <span className="bv-landing__cta-label">{t("landing.continue")}</span>
        </Lift>
      </main>
    </div>
  );
}
