import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output is committed to git (app/static/dist/) so the deployment
// machine ships the built bundle and never runs npm — see TEAMMATE_GUIDE.md.
//
// Three-page build: "/" is the public landing page, "/admin" and "/chat" are
// gated (any signed-in account) — separate real HTML documents (not
// client-side routing) so app/auth.py's path-based gate can protect them
// without any SPA-fallback trickery. Vite mirrors each input's directory
// under outDir, so admin/index.html here becomes dist/admin/index.html,
// which StaticFiles(html=True) resolves for a GET /admin/ request.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../app/static/dist",
    emptyOutDir: true,
    // Vite's default "assets" output dir would collide with the design
    // system's own /assets (logos, favicons — see app/static/assets/,
    // mounted separately at "/assets"). Compiled JS/CSS go here instead.
    assetsDir: "app-assets",
    rollupOptions: {
      input: {
        landing: resolve(import.meta.dirname, "index.html"),
        admin: resolve(import.meta.dirname, "admin/index.html"),
        chat: resolve(import.meta.dirname, "chat/index.html"),
      },
    },
    // Fonts are served from app/static/fonts/ (see public/fonts symlink) and
    // referenced by absolute /fonts/... URLs in tokens/fonts.css; brand
    // images/favicons likewise live in app/static/assets/ (public/assets
    // symlink). Don't duplicate either into dist/ on every build.
    copyPublicDir: false,
  },
});
