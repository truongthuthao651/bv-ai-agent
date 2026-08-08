// Regenerates frontend/.oxlintrc.generated.json from the design system's
// _adherence.oxlintrc.json (read-only source of truth, never hand-edited —
// see REDESIGN_PROMPT.md Phase 4). oxlint's config parser rejects unknown
// top-level fields; the source file carries an `x-omelette` metadata block
// for a different tool, so it's stripped here rather than removed at the
// source.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const sourcePath = path.resolve(here, "../../../_adherence.oxlintrc.json");
const outPath = path.resolve(here, "../.oxlintrc.generated.json");

const config = JSON.parse(readFileSync(sourcePath, "utf8"));
delete config["x-omelette"];

// oxlint (the Rust engine this repo uses, not eslint) has no equivalent of
// ESLint's `no-restricted-syntax` — there is no AST-selector rule to run
// arbitrary selectors against. That single rule in the source config is
// what encodes: the hex-color ban, the raw-px ban, the font-family ban, and
// every per-component prop/enum check. Dropping it here is a real gap, not
// a style choice — see the frontend README for what it means and what
// would be needed to cover it (e.g. a small custom AST script, or an
// eslint-based second pass just for this rule).
if (config.rules && "no-restricted-syntax" in config.rules) {
  delete config.rules["no-restricted-syntax"];
  console.warn(
    "warning: no-restricted-syntax dropped from generated oxlintrc — " +
      "oxlint cannot execute it. Hex/px/font-family and per-component " +
      "prop-shape checks from the design system are NOT enforced by `npm run lint`.",
  );
}

writeFileSync(outPath, JSON.stringify(config, null, 2) + "\n");
console.log(`Wrote ${outPath} from ${sourcePath}`);
