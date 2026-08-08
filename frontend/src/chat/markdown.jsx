import katex from "katex";

/** A small, hand-rolled markdown+math renderer scoped to exactly what
 * app/generation/prompts.py emits — no general-purpose markdown package is
 * on the pre-approved dependency list (only katex was), and a scoped
 * renderer is also the safer choice: it only ever builds elements it knows
 * how to build, never dangerouslySetInnerHTML on arbitrary text. The one
 * disclosed exception is KaTeX's own output (see Math below) — that HTML
 * comes from KaTeX's own renderer, not from raw model/user text, and
 * `trust: false` (the default) keeps it from executing embedded commands
 * like \href even if a source document's text ever reached this far.
 *
 * Covers: paragraphs, "- "/"1. " lists, **bold**, [text](url) links, and
 * $...$ / $$...$$ math. Nothing else our own backend produces needs more. */

const SOURCES_HEADING = "**Nguồn tham khảo:**";

/** Splits a finished answer into its prose body and parsed citation entries
 * from the "Nguồn tham khảo" block (app/generation/prompts.py format_sources) —
 * real document title + section + link; no confidence/passage, which the API
 * doesn't expose separately (see the Phase 4 gap list). */
export function splitSources(text) {
  const idx = text.indexOf(SOURCES_HEADING);
  if (idx === -1) return { body: text, citations: [] };
  const body = text.slice(0, idx).trimEnd();
  const sourcesText = text.slice(idx + SOURCES_HEADING.length);
  const citations = [];
  const lineRe = /^-\s*\[(\d+)\]\s*\[(.+?)\]\((.+?)\)\s*(?:—\s*(.*))?$/;
  for (const line of sourcesText.split("\n")) {
    const m = lineRe.exec(line.trim());
    if (m) citations.push({ n: Number(m[1]), title: m[2], url: m[3], meta: m[4] || "" });
  }
  return { body, citations };
}

function Math({ tex, display }) {
  let html;
  try {
    html = katex.renderToString(tex, { displayMode: display, throwOnError: false, trust: false });
  } catch {
    return <code>{tex}</code>;
  }
  // eslint-disable-next-line react/no-danger -- KaTeX's own trusted output, see module docstring
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Splits text on $$...$$ / $...$ math spans, returning an array alternating
 * plain-text runs and {tex, display} descriptors, in order. */
function splitMath(text) {
  const parts = [];
  const re = /\$\$([^$]+?)\$\$|\$([^$\n]+?)\$/g;
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[1] !== undefined) parts.push({ tex: m[1], display: true });
    else parts.push({ tex: m[2], display: false });
    last = re.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

/** Bold + links within one plain-text run (math already extracted). */
function renderInlineRun(text, keyBase) {
  const nodes = [];
  const re = /\*\*(.+?)\*\*|\[(.+?)\]\((.+?)\)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1] !== undefined) {
      nodes.push(<strong key={`${keyBase}-${i++}`}>{m[1]}</strong>);
    } else {
      nodes.push(
        <a key={`${keyBase}-${i++}`} href={m[3]} target="_blank" rel="noopener">
          {m[2]}
        </a>,
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function renderInline(text, keyBase) {
  return splitMath(text).flatMap((part, i) =>
    typeof part === "string"
      ? renderInlineRun(part, `${keyBase}-${i}`)
      : [<Math key={`${keyBase}-${i}-math`} tex={part.tex} display={part.display} />],
  );
}

/** Full answer text -> React nodes: paragraphs and "- "/"1. " list blocks,
 * each with inline math/bold/links resolved. */
export function renderMarkdown(text) {
  const blocks = text.trim().split(/\n{2,}/);
  return blocks.map((block, bi) => {
    const lines = block.split("\n").filter((l) => l.trim());
    const isList = lines.length > 0 && lines.every((l) => /^(-|\d+\.)\s/.test(l.trim()));
    if (isList) {
      const ordered = /^\d+\./.test(lines[0].trim());
      const Tag = ordered ? "ol" : "ul";
      return (
        <Tag key={bi} style={{ margin: "var(--space-2) 0", paddingLeft: "var(--space-5)", display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
          {lines.map((line, li) => (
            <li key={li} style={{ lineHeight: "var(--leading-relaxed)" }}>
              {renderInline(line.replace(/^(-|\d+\.)\s/, ""), `${bi}-${li}`)}
            </li>
          ))}
        </Tag>
      );
    }
    return (
      <p key={bi} style={{ margin: bi === 0 ? 0 : "var(--space-3) 0 0", lineHeight: "var(--leading-relaxed)" }}>
        {renderInline(block, `${bi}`)}
      </p>
    );
  });
}
