#!/usr/bin/env python
"""Apply Bảo Việt branding to the installed Open WebUI (no fork, no rebuild).

Open WebUI 0.5.x has no supported hooks for custom logos, colors, or default
prompt suggestions (the suggestions are hardcoded defaults persisted into its
sqlite config on first boot — there is no env var for them). This script
patches the pip-installed package in place, which works fully offline:

1. Regenerates the logo/favicon/splash PNGs inside the open_webui package
   with a Bảo Việt-styled "BV" mark (brand blue #0072BC + gold #F7B928).
2. Injects a small brand CSS block, a request-processing timer, and Vietnamese
   app metadata into the frontend's index.html (idempotent, marker-delimited).
3. Replaces the stock English prompt suggestions in open_webui_data/webui.db
   with the Vietnamese actuarial/internal-document ones from
   prompt_suggestions.json, and sets the default UI locale to vi-VN.
   Suggestions are only replaced while they are still the stock defaults —
   an admin's manual edits in the UI are never clobbered (use --force to
   overwrite anyway). The DB is backed up first and never touched while
   Open WebUI is running.

Run with the Open WebUI venv:
  .venv-webui/Scripts/python.exe scripts/open_webui/apply_branding.py  # Windows Git Bash
  .venv-webui/bin/python scripts/open_webui/apply_branding.py    # macOS/Linux
Re-run after any `pip install --upgrade open-webui` (upgrades restore the
stock assets). run_native.sh runs it automatically before starting the UI.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import shutil
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
SUGGESTIONS_PATH = Path(__file__).resolve().parent / "prompt_suggestions.json"

BV_BLUE = "#0072bc"
BV_BLUE_DARK = "#005a96"
BV_NAVY = "#003a63"
BV_GOLD = "#f7b928"

CSS_START = "/* BV-BRAND-START */"
CSS_END = "/* BV-BRAND-END */"
TIMER_START = "/* BV-PROCESSING-TIMER-START */"
TIMER_END = "/* BV-PROCESSING-TIMER-END */"

BRAND_CSS = f"""{CSS_START}
:root {{ --bv-blue: {BV_BLUE}; --bv-blue-dark: {BV_BLUE_DARK}; --bv-gold: {BV_GOLD}; }}
/* Primary/send buttons use .bg-black in light mode — recolor to BV blue */
.bg-black {{ background-color: var(--bv-blue) !important; }}
.bg-black:hover {{ background-color: var(--bv-blue-dark) !important; }}
/* Our splash mark is colored — don't let dark mode invert it */
html.dark #splash-screen img {{ filter: none !important; }}
/* Elapsed time shown above Open WebUI's assistant response skeleton. */
#bv-processing-timer {{
  align-items: center;
  color: #64748b;
  display: flex;
  font-size: 0.875rem;
  font-variant-numeric: tabular-nums;
  gap: 0.4rem;
  line-height: 1.25rem;
  margin: 0.15rem 0 0.5rem;
  width: max-content;
}}
html.dark #bv-processing-timer {{ color: #a3a3a3; }}
#bv-processing-timer .bv-processing-spinner {{
  animation: bv-processing-spin 0.9s linear infinite;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 9999px;
  box-sizing: border-box;
  height: 0.85rem;
  width: 0.85rem;
}}
@keyframes bv-processing-spin {{ to {{ transform: rotate(360deg); }} }}
@media (prefers-reduced-motion: reduce) {{
  #bv-processing-timer .bv-processing-spinner {{ animation: none; }}
}}
{CSS_END}"""

PROCESSING_TIMER_JS = f"""{TIMER_START}
(() => {{
  const TIMER_ID = "bv-processing-timer";
  let startedAt = null;
  let intervalId = null;

  const findResponseSkeleton = () =>
    Array.from(document.querySelectorAll("div.animate-pulse.flex.w-full")).find(
      (element) =>
        !element.closest("#splash-screen") &&
        element.querySelector(".bg-gray-200.rounded")
    );

  const elapsedText = () => {{
    const totalSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = String(totalSeconds % 60).padStart(2, "0");
    return `${{minutes}}:${{seconds}}`;
  }};

  const renderTime = () => {{
    const time = document.querySelector(`#${{TIMER_ID}} time`);
    if (time && startedAt !== null) {{
      const nextValue = elapsedText();
      if (time.textContent !== nextValue) {{
        time.textContent = nextValue;
      }}
    }}
  }};

  const removeTimer = () => {{
    document.getElementById(TIMER_ID)?.remove();
    if (intervalId !== null) {{
      window.clearInterval(intervalId);
      intervalId = null;
    }}
    startedAt = null;
  }};

  const createTimer = () => {{
    const timer = document.createElement("div");
    timer.id = TIMER_ID;
    timer.setAttribute("aria-label", "Thời gian xử lý yêu cầu");

    const spinner = document.createElement("span");
    spinner.className = "bv-processing-spinner";
    spinner.setAttribute("aria-hidden", "true");

    const label = document.createElement("span");
    label.textContent = "Đang xử lý:";

    const time = document.createElement("time");
    time.textContent = "0:00";

    timer.append(spinner, label, time);
    return timer;
  }};

  const syncTimer = () => {{
    const skeleton = findResponseSkeleton();
    if (!skeleton) {{
      removeTimer();
      return;
    }}

    let timer = document.getElementById(TIMER_ID);
    if (!timer) {{
      startedAt = Date.now();
      timer = createTimer();
      intervalId = window.setInterval(renderTime, 250);
    }}

    if (timer.nextElementSibling !== skeleton) {{
      skeleton.parentElement?.insertBefore(timer, skeleton);
    }}
    renderTime();
  }};

  const start = () => {{
    const observer = new MutationObserver(syncTimer);
    observer.observe(document.body, {{ childList: true, subtree: true }});
    syncTimer();
    window.addEventListener("beforeunload", () => {{
      observer.disconnect();
      removeTimer();
    }});
  }};

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", start, {{ once: true }});
  }} else {{
    start();
  }}
}})();
{TIMER_END}"""

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Debian/Ubuntu
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",  # Fedora/RHEL
]


def env_get(key: str, default: str) -> str:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip() or default
    return default


def find_webui_pkg() -> Path | None:
    candidates = [
        Path(sys.prefix) / "Lib" / "site-packages" / "open_webui",
        REPO_ROOT / ".venv-webui" / "Lib" / "site-packages" / "open_webui",
    ]
    candidates.extend(
        Path(path)
        for path in glob.glob(
            str(Path(sys.prefix) / "lib" / "python*" / "site-packages" / "open_webui")
        )
    )
    candidates.extend(
        Path(path)
        for path in glob.glob(
            str(
                REPO_ROOT
                / ".venv-webui"
                / "lib"
                / "python*"
                / "site-packages"
                / "open_webui"
            )
        )
    )
    return next((path for path in candidates if path.is_dir()), None)


def load_font(px: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return ImageFont.load_default(size=px)


def make_mark(size: int) -> Image.Image:
    """Rounded blue tile, white 'BV', gold accent bar — drawn at 4x and downscaled."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = int(s * 0.04)
    draw.rounded_rectangle(
        [pad, pad, s - pad, s - pad], radius=int(s * 0.18), fill=BV_BLUE
    )

    font = load_font(int(s * 0.42))
    box = draw.textbbox((0, 0), "BV", font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    tx, ty = (s - tw) / 2 - box[0], (s - th) / 2 - box[1] - s * 0.06
    draw.text((tx, ty), "BV", font=font, fill="#ffffff")

    bar_w, bar_h = int(s * 0.44), int(s * 0.06)
    bar_y = int(s * 0.72)
    draw.rounded_rectangle(
        [(s - bar_w) // 2, bar_y, (s + bar_w) // 2, bar_y + bar_h],
        radius=bar_h // 2,
        fill=BV_GOLD,
    )
    return img.resize((size, size), Image.LANCZOS)


FAVICON_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect x="4" y="4" width="92" height="92" rx="18" fill="{BV_BLUE}"/>
  <text x="50" y="58" text-anchor="middle" font-family="Arial, Helvetica, sans-serif"
        font-size="42" font-weight="bold" fill="#ffffff">BV</text>
  <rect x="28" y="72" width="44" height="6" rx="3" fill="{BV_GOLD}"/>
</svg>
"""


def write_assets(pkg: Path) -> None:
    mark = {px: make_mark(px) for px in (96, 180, 192, 500, 512)}
    targets = {
        "static/favicon.png": 500,
        "static/logo.png": 500,
        "static/splash.png": 500,
        "frontend/favicon.png": 500,
        "frontend/static/favicon.png": 500,
        "frontend/static/splash.png": 500,
        "frontend/static/splash-dark.png": 500,
        "frontend/favicon/favicon-96x96.png": 96,
        "frontend/favicon/apple-touch-icon.png": 180,
        "frontend/favicon/web-app-manifest-192x192.png": 192,
        "frontend/favicon/web-app-manifest-512x512.png": 512,
    }
    for rel, px in targets.items():
        path = pkg / rel
        if path.parent.is_dir():
            mark[px].save(path)
    ico = pkg / "frontend/favicon/favicon.ico"
    if ico.parent.is_dir():
        mark[96].save(ico, sizes=[(16, 16), (32, 32), (48, 48)])
    svg = pkg / "frontend/favicon/favicon.svg"
    if svg.parent.is_dir():
        svg.write_text(FAVICON_SVG, encoding="utf-8")
    print(f"assets: wrote {len(targets) + 2} branded files into {pkg}")


def patch_index_html(pkg: Path, app_name: str) -> None:
    index = pkg / "frontend/index.html"
    html = index.read_text(encoding="utf-8")

    for needle in (
        '<meta name="apple-mobile-web-app-title" content="Open WebUI" />',
        '<meta name="description" content="Open WebUI" />',
        "<title>Open WebUI</title>",
    ):
        html = html.replace(needle, needle.replace("Open WebUI", app_name))

    style_block = f'<style id="bv-brand">\n{BRAND_CSS}\n</style>'
    if CSS_START in html:
        html = re.sub(
            r'<style id="bv-brand">.*?</style>', style_block, html, count=1, flags=re.S
        )
    else:
        html = html.replace("</head>", f"\t{style_block}\n</head>")

    timer_block = (
        f'<script id="bv-processing-timer-script">\n{PROCESSING_TIMER_JS}\n</script>'
    )
    if TIMER_START in html:
        html = re.sub(
            r'<script id="bv-processing-timer-script">.*?</script>',
            timer_block,
            html,
            count=1,
            flags=re.S,
        )
    else:
        html = html.replace("</body>", f"\t{timer_block}\n</body>")
    index.write_text(html, encoding="utf-8")

    manifest = pkg / "frontend/favicon/site.webmanifest"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data.update({"name": app_name, "short_name": "BV AI", "theme_color": BV_BLUE})
        manifest.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        "frontend: injected brand CSS, processing timer, and app name "
        "into index.html + manifest"
    )


def webui_is_running() -> bool:
    port = int(env_get("OPEN_WEBUI_PORT", "3000"))
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def patch_db(force: bool) -> None:
    db_path = REPO_ROOT / "open_webui_data" / "webui.db"
    if not db_path.exists():
        print(
            "db: webui.db not found yet (created on first Open WebUI start) — "
            "suggestions will be applied on the next run of run_native.sh"
        )
        return
    if webui_is_running():
        print(
            "db: Open WebUI is running — skipping suggestion update "
            "(stop the stack and re-run to apply)"
        )
        return

    suggestions = json.loads(SUGGESTIONS_PATH.read_text(encoding="utf-8"))
    backup = db_path.with_suffix(f".db.bak-{datetime.now():%Y%m%d%H%M%S}")

    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT id, data FROM config ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            print("db: no config row yet — nothing to patch")
            return
        row_id, data = row[0], json.loads(row[1])
        ui = data.setdefault("ui", {})

        current = ui.get("prompt_suggestions") or []
        is_stock = bool(current) and current[0].get("title", [""])[0] == "Help me study"
        changed = False
        if force or is_stock or not current:
            ui["prompt_suggestions"] = suggestions
            changed = True
        else:
            print(
                "db: prompt suggestions were customized in the admin UI — "
                "left untouched (use --force to overwrite)"
            )
        if not ui.get("default_locale"):
            ui["default_locale"] = "vi-VN"
            changed = True

        if changed:
            shutil.copy2(db_path, backup)
            con.execute(
                "UPDATE config SET data = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(data, ensure_ascii=False), row_id),
            )
            con.commit()
            print(
                f"db: applied Vietnamese prompt suggestions + locale (backup: {backup.name})"
            )
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite prompt suggestions even if customized in the admin UI",
    )
    args = parser.parse_args()

    pkg = find_webui_pkg()
    if pkg is None:
        print(
            "ERROR: open_webui package not found in .venv-webui — "
            "run scripts/setup_native.sh first",
            file=sys.stderr,
        )
        return 1

    app_name = env_get("WEBUI_NAME", "Trợ lý AI Bảo Việt Life")
    write_assets(pkg)
    patch_index_html(pkg, app_name)
    patch_db(args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
