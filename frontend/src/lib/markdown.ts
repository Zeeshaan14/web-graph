// Builds the downloadable/displayable Markdown document for one
// extraction result, and drives the actual browser download -- shared
// between the Content Extraction page (one file) and Discover + Extract
// (one file per page, zipped). The backend already returns finished,
// properly-escaped Markdown (content_markdown) -- this just prepends a
// title/source header, it doesn't build Markdown syntax itself.

import type { ExtractResponse } from "./api";

export function extractResponseToMarkdown(result: ExtractResponse): string {
  const heading = `# ${result.title ?? result.url}`;
  const source = `*Source: [${result.url}](${result.url})*`;

  if (result.status === "failed") {
    return [heading, source, "", `**Extraction failed:** ${result.error ?? "Unknown error"}`].join("\n");
  }

  if (!result.content_markdown.trim()) {
    return [heading, source, "", "*No extractable content was found on this page.*"].join("\n");
  }

  return [heading, source, "", result.content_markdown].join("\n");
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
