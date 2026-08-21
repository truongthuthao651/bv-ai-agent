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
 * Covers: paragraphs, "- "/"1. " lists, **bold**, *italic*, [text](url) links, and
 * $...$ / $$...$$ math. Nothing else our own backend produces needs more. */

const SOURCES_HEADINGS = ["**Nguồn tham khảo:**", "**References:**"];
const RESPONSE_TIME_FOOTER = /\n\n_⏱\s*Thời gian trả lời:\s*([^_]+)_\s*$/;

/** Older saved conversations linked directly to the uploaded PDF/image. Route
 * them through the viewer using the known section label so they at least scroll
 * to the cited section; new citations additionally carry an exact content anchor. */
function upgradeLegacyCitationUrl(url, meta) {
  const match = /^(.*\/documents\/[^/]+)\/file(?:#page=(\d+))?$/.exec(url);
  const section = meta.replace(/\s*\(trang\s+\d+\)\s*$/, "").trim();
  if (!match || !section || section.includes("nguồn công khai")) return url;
  const page = match[2] ? `&page=${match[2]}` : "";
  return `${match[1]}/view?section=${encodeURIComponent(section)}${page}`;
}

/** Splits a finished answer into its prose body and parsed citation entries
 * from the sources block (app/generation/prompts.py format_sources). */
export function splitSources(text) {
  const footer = RESPONSE_TIME_FOOTER.exec(text);
  const responseTime = footer ? footer[1].trim() : null;
  const answerText = footer ? text.slice(0, footer.index) : text;
  let idx = -1;
  let headingLen = 0;
  for (const heading of SOURCES_HEADINGS) {
    const at = answerText.indexOf(heading);
    if (at !== -1 && (idx === -1 || at < idx)) {
      idx = at;
      headingLen = heading.length;
    }
  }
  if (idx === -1) return { body: answerText, citations: [], responseTime };
  const body = answerText.slice(0, idx).trimEnd();
  const sourcesText = answerText.slice(idx + headingLen);
  const citations = [];
  const lineRe = /^-\s*\[(\d+)\]\s*\[(.+?)\]\((.+?)\)\s*(?:—\s*(.*))?$/;
  for (const line of sourcesText.split("\n")) {
    const m = lineRe.exec(line.trim());
    if (m) {
      const meta = m[4] || "";
      citations.push({ n: Number(m[1]), title: m[2], url: upgradeLegacyCitationUrl(m[3], meta), meta });
    }
  }
  return { body, citations, responseTime };
}

/** Inline [n] markers the model actually cited in the prose (P2-J2). */
export function inlineCitationNumbers(body) {
  const nums = new Set();
  const re = /\[(\d+)\]/g;
  let m;
  while ((m = re.exec(body))) nums.add(Number(m[1]));
  return nums;
}

/** Keep only sources whose [n] appears in the answer body. */
export function citedSourcesOnly(body, citations) {
  const cited = inlineCitationNumbers(body);
  if (cited.size === 0) return [];
  return citations.filter((c) => cited.has(c.n));
}

/** Group passage-level citations by source document so one answer does not
 * repeat the same filename across a row of otherwise indistinguishable chips. */
export function groupCitationsByDocument(citations) {
  const groups = new Map();
  for (const citation of citations) {
    const baseUrl = citation.url
      .split(/[?#]/, 1)[0]
      .replace(/(\/documents\/[^/]+)\/(?:view|file)$/, "$1");
    const key = `${citation.title}\n${baseUrl}`;
    if (!groups.has(key)) {
      groups.set(key, { key, title: citation.title, citations: [] });
    }
    groups.get(key).citations.push(citation);
  }
  return [...groups.values()];
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
  const re = /\*\*(.+?)\*\*|\*(.+?)\*|\[(.+?)\]\((.+?)\)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1] !== undefined) {
      nodes.push(<strong key={`${keyBase}-${i++}`}>{m[1]}</strong>);
    } else if (m[2] !== undefined) {
      nodes.push(<em key={`${keyBase}-${i++}`}>{m[2]}</em>);
    } else {
      nodes.push(
        <a key={`${keyBase}-${i++}`} href={m[4]} target="_blank" rel="noopener">
          {m[3]}
        </a>,
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/** Recovery for a small-model formatting mistake such as
 * "Giải thích: - ý 1 - ý 2". Proper multi-line Markdown lists are handled
 * separately below; this only turns inline bullet markers into readable rows. */
function splitInlineBullets(block) {
  const parts = block.split(/\s+-\s+(?=\S)/);
  return parts.length > 1 ? { intro: parts[0].trim(), items: parts.slice(1).map((item) => item.trim()) } : null;
}

function renderInline(text, keyBase) {
  return splitMath(text).flatMap((part, i) =>
    typeof part === "string"
      ? renderInlineRun(part, `${keyBase}-${i}`)
      : [<Math key={`${keyBase}-${i}-math`} tex={part.tex} display={part.display} />],
  );
}

/** Full answer text -> React nodes: headings, paragraphs and list blocks,
 * each with inline math/bold/links resolved. */
export function renderMarkdown(text) {
  const blocks = text.trim().split(/\n{2,}/);
  return blocks.map((block, bi) => {
    const markdownHeading = /^(#{2,3})\s+(.+)$/.exec(block.trim());
    if (markdownHeading) {
      const Tag = markdownHeading[1].length === 2 ? "h2" : "h3";
      return (
        <Tag key={bi} style={{ margin: bi === 0 ? 0 : "var(--space-5) 0 0", color: "var(--text-primary)", fontSize: markdownHeading[1].length === 2 ? "var(--text-lg)" : "var(--text-md)", lineHeight: "var(--leading-snug)" }}>
          {renderInline(markdownHeading[2], `${bi}-markdown-heading`)}
        </Tag>
      );
    }
    const romanHeading = /^([IVXLCDM]+\.\s+.+)$/i.exec(block.trim());
    if (romanHeading) {
      return (
        <h3 key={bi} style={{ margin: bi === 0 ? 0 : "var(--space-5) 0 0", color: "var(--text-primary)", fontSize: "var(--text-lg)", lineHeight: "var(--leading-snug)" }}>
          {renderInline(romanHeading[1], `${bi}-heading`)}
        </h3>
      );
    }
    const subheading = /^(\d+\.|[a-z]\.)(\s+.+)$/i.exec(block.trim());
    if (subheading) {
      return (
        <h4 key={bi} style={{ margin: bi === 0 ? 0 : "var(--space-4) 0 0", color: "var(--text-primary)", fontSize: "var(--text-md)", lineHeight: "var(--leading-snug)" }}>
          {renderInline(`${subheading[1]}${subheading[2]}`, `${bi}-subheading`)}
        </h4>
      );
    }
    const boldHeading = /^\*\*(.+?):\*\*$/.exec(block.trim());
    if (boldHeading) {
      return (
        <h3 key={bi} style={{ margin: bi === 0 ? 0 : "var(--space-5) 0 0", color: "var(--text-primary)", fontSize: "var(--text-lg)", lineHeight: "var(--leading-snug)" }}>
          {boldHeading[1]}:
        </h3>
      );
    }
    const inlineBullets = splitInlineBullets(block);
    if (inlineBullets) {
      return (
        <div key={bi} style={{ margin: bi === 0 ? 0 : "var(--space-3) 0 0" }}>
          {inlineBullets.intro && (
            <p style={{ margin: 0, lineHeight: "var(--leading-relaxed)" }}>
              {renderInline(inlineBullets.intro, `${bi}-intro`)}
            </p>
          )}
          <ul style={{ margin: inlineBullets.intro ? "var(--space-2) 0 0" : 0, paddingLeft: "var(--space-5)", display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
            {inlineBullets.items.map((item, ii) => (
              <li key={ii} style={{ lineHeight: "var(--leading-relaxed)" }}>
                {renderInline(item, `${bi}-inline-${ii}`)}
              </li>
            ))}
          </ul>
        </div>
      );
    }
    const lines = block.split("\n").filter((l) => l.trim());
    const isList = lines.length > 0 && lines.every((l) => /^(-|\+|\d+\.|[a-z]\.)\s/i.test(l.trim()));
    if (isList) {
      const ordered = /^(\d+\.|[a-z]\.)\s/i.test(lines[0].trim());
      const Tag = ordered ? "ol" : "ul";
      return (
        <Tag key={bi} style={{ margin: "var(--space-2) 0", paddingLeft: "var(--space-5)", display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
          {lines.map((line, li) => (
            <li key={li} style={{ lineHeight: "var(--leading-relaxed)" }}>
              {renderInline(line.replace(/^(-|\+|\d+\.|[a-z]\.)\s/i, ""), `${bi}-${li}`)}
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
