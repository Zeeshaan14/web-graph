// Converts an ExtractResponse's ordered blocks into a single Markdown
// document, and drives the actual browser download -- shared between the
// Content Extraction page (one file) and Discover + Extract (one file per
// page, zipped). Kept independent of any React/UI code so it's easy to
// reason about and test on its own.

import type { ContentBlock, ExtractResponse } from "./api";

// Source headings are h1-h3; the document's own title (added separately,
// as an H1) means every source heading nests one level below where it sat
// in the original page -- same reasoning as the h3/h4/h5 nesting used when
// rendering blocks on-page.
const HEADING_PREFIXES: Record<number, string> = {
  1: "##",
  2: "###",
  3: "####",
};

// This text is real extracted page content, not authored Markdown -- a
// literal "*", "#", or leading "-" in a paragraph (common in real-world
// text: "*required", "1099-K form", etc.) must NOT be parsed back out as
// emphasis, a heading, or a list marker once this string is rendered.
// Escapes the same characters CommonMark treats as syntax, both for the
// on-page renderer and for the downloaded .md file (which should also
// read back as the plain text it actually is).
function escapeMarkdownText(text: string): string {
  const escaped = text.replace(/([\\`*_[\]])/g, "\\$1");
  return escaped.replace(/^(\s*)(#{1,6}\s|[-+]\s|>\s|\d+[.)]\s)/, "$1\\$2");
}

export function blocksToMarkdown(blocks: ContentBlock[]): string {
  const lines: string[] = [];
  let previousType: ContentBlock["type"] | null = null;

  for (const block of blocks) {
    // A blank line between blocks, except consecutive list items, which
    // stay adjacent so they render as one Markdown list rather than one
    // paragraph-spaced bullet per item.
    if (lines.length > 0 && !(previousType === "list_item" && block.type === "list_item")) {
      lines.push("");
    }

    const text = escapeMarkdownText(block.text);

    if (block.type === "heading") {
      const prefix = HEADING_PREFIXES[block.level ?? 2] ?? "###";
      lines.push(`${prefix} ${text}`);
    } else if (block.type === "list_item") {
      lines.push(`- ${text}`);
    } else {
      lines.push(text);
    }

    previousType = block.type;
  }

  return lines.join("\n");
}

export function extractResponseToMarkdown(result: ExtractResponse): string {
  const heading = `# ${result.title ? escapeMarkdownText(result.title) : result.url}`;
  const source = `*Source: [${result.url}](${result.url})*`;

  if (result.status === "failed") {
    return [heading, source, "", `**Extraction failed:** ${result.error ?? "Unknown error"}`].join("\n");
  }

  if (result.blocks.length === 0) {
    return [heading, source, "", "*No extractable content was found on this page.*"].join("\n");
  }

  return [heading, source, "", blocksToMarkdown(result.blocks)].join("\n");
}

// Derives a filesystem-safe, human-readable filename from a page's own
// URL -- e.g. https://example.com/docs/getting-started -> "docs-getting-started",
// the site root -> "index". Not guaranteed globally unique on its own
// (two different paths can collapse to the same slug after sanitizing),
// so callers writing multiple files disambiguate collisions themselves.
export function slugifyUrl(url: string): string {
  let path: string;
  try {
    path = new URL(url).pathname;
  } catch {
    path = url;
  }

  const slug = path
    .replace(/^\/+|\/+$/g, "")
    .replace(/[^a-zA-Z0-9/_-]+/g, "-")
    .replace(/\//g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");

  return slug || "index";
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function downloadMarkdown(result: ExtractResponse, filename: string): void {
  const markdown = extractResponseToMarkdown(result);
  downloadBlob(new Blob([markdown], { type: "text/markdown;charset=utf-8" }), filename);
}
