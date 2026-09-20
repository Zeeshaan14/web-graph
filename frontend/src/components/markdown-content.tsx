import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// react-markdown never renders raw HTML from its input by default (no
// rehype-raw plugin here) -- important since this renders arbitrary
// third-party page content, not text we authored ourselves.

// content_markdown is a direct conversion of a page's whole <body>, so its
// heading levels are the source page's own h1-h6, unshifted. The semantic
// tag and size each maps to here just nests one level below whatever wraps
// this component: a card with its own title above (content-extraction), or
// an accordion item whose own trigger already shows the page title
// (discover-and-extract). Capped at h6 (HTML's own max) for anything at
// or past that nesting depth -- reusing h6's own (smallest) size class.
const VARIANT_HEADINGS = {
  card: {
    h1: "h3" as const,
    h2: "h4" as const,
    h3: "h5" as const,
    h4: "h6" as const,
    h5: "h6" as const,
    h6: "h6" as const,
  },
  accordion: {
    h1: "h4" as const,
    h2: "h5" as const,
    h3: "h6" as const,
    h4: "h6" as const,
    h5: "h6" as const,
    h6: "h6" as const,
  },
};

const HEADING_SIZE_CLASSES: Record<"h3" | "h4" | "h5" | "h6", string> = {
  h3: "mt-4 font-heading text-lg font-semibold tracking-tight first:mt-0",
  h4: "mt-3 font-heading text-base font-semibold tracking-tight first:mt-0",
  h5: "mt-2 text-sm font-semibold text-foreground/90 first:mt-0",
  h6: "mt-2 text-sm font-semibold text-foreground/90 first:mt-0",
};

export function MarkdownContent({
  markdown,
  variant = "card",
}: {
  markdown: string;
  variant?: "card" | "accordion";
}) {
  const headingTags = VARIANT_HEADINGS[variant];

  return (
    <div className="flex flex-col text-sm leading-relaxed text-foreground/90">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (props) => {
            const Tag = headingTags.h1;
            return <Tag className={HEADING_SIZE_CLASSES[Tag]}>{props.children}</Tag>;
          },
          h2: (props) => {
            const Tag = headingTags.h2;
            return <Tag className={HEADING_SIZE_CLASSES[Tag]}>{props.children}</Tag>;
          },
          h3: (props) => {
            const Tag = headingTags.h3;
            return <Tag className={HEADING_SIZE_CLASSES[Tag]}>{props.children}</Tag>;
          },
          h4: (props) => {
            const Tag = headingTags.h4;
            return <Tag className={HEADING_SIZE_CLASSES[Tag]}>{props.children}</Tag>;
          },
          h5: (props) => {
            const Tag = headingTags.h5;
            return <Tag className={HEADING_SIZE_CLASSES[Tag]}>{props.children}</Tag>;
          },
          h6: (props) => {
            const Tag = headingTags.h6;
            return <Tag className={HEADING_SIZE_CLASSES[Tag]}>{props.children}</Tag>;
          },
          p: (props) => <p className="mt-2 first:mt-0">{props.children}</p>,
          ul: (props) => (
            <ul className="mt-2 flex flex-col gap-1.5 first:mt-0">{props.children}</ul>
          ),
          // A real <ol> in the source page converts to a genuinely
          // numbered Markdown list (unlike <ul>, which always renders as
          // our own dot-bullet style below) -- native numbering here.
          ol: (props) => (
            <ol className="mt-2 flex list-decimal flex-col gap-1.5 pl-5 first:mt-0">
              {props.children}
            </ol>
          ),
          li: (props) => (
            <li className="flex gap-2.5 pl-0.5 [ol_&]:list-item [ol_&]:pl-0">
              <span
                aria-hidden="true"
                className="mt-[0.55em] size-1 shrink-0 rounded-full bg-muted-foreground [ol_&]:hidden"
              />
              <span>{props.children}</span>
            </li>
          ),
          img: (props) => (
            // Arbitrary third-party image URLs, not a local/optimizable asset.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={props.src}
              alt={props.alt ?? ""}
              loading="lazy"
              className="mt-2 max-w-full rounded-md border first:mt-0"
            />
          ),
          a: (props) => (
            <a
              href={props.href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-2 hover:no-underline"
            >
              {props.children}
            </a>
          ),
          strong: (props) => <strong className="font-semibold text-foreground">{props.children}</strong>,
          code: (props) => (
            <code className="rounded-sm bg-muted px-1 py-0.5 font-mono text-xs">{props.children}</code>
          ),
          blockquote: (props) => (
            <blockquote className="mt-2 border-l-2 pl-3 text-foreground/70 italic first:mt-0">
              {props.children}
            </blockquote>
          ),
          table: (props) => (
            <div className="mt-2 overflow-x-auto first:mt-0">
              <table className="w-full border-collapse text-sm">{props.children}</table>
            </div>
          ),
          thead: (props) => <thead className="border-b">{props.children}</thead>,
          th: (props) => (
            <th className="px-2 py-1.5 text-left font-semibold text-foreground">{props.children}</th>
          ),
          td: (props) => <td className="border-t px-2 py-1.5 align-top">{props.children}</td>,
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

// The raw Markdown source itself -- the "code" side of a Preview/Markdown
// toggle, showing exactly what MarkdownContent renders (and what gets
// downloaded) as plain, unrendered text.
export function RawMarkdown({ markdown }: { markdown: string }) {
  return (
    <pre className="overflow-x-auto font-mono text-xs leading-relaxed whitespace-pre-wrap text-foreground/90">
      {markdown}
    </pre>
  );
}
