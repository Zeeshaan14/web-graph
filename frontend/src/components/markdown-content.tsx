import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// react-markdown never renders raw HTML from its input by default (no
// rehype-raw plugin here) -- important since this renders arbitrary
// third-party page content, not text we authored ourselves.

// Markdown "##"/"###"/"####" map to a page's own h1/h2/h3 (see
// lib/markdown.ts's HEADING_PREFIXES) -- the semantic tag and size each
// gets here just nests one level below whatever wraps this component:
// a card with its own title above (content-extraction), or an accordion
// item whose own trigger already shows the page title (discover-and-extract).
const VARIANT_HEADINGS = {
  card: {
    h2: "h3" as const,
    h3: "h4" as const,
    h4: "h5" as const,
  },
  accordion: {
    h2: "h4" as const,
    h3: "h5" as const,
    h4: "h6" as const,
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
            const Tag = headingTags.h2;
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
          p: (props) => <p className="mt-2 first:mt-0">{props.children}</p>,
          ul: (props) => (
            <ul className="mt-2 flex flex-col gap-1.5 first:mt-0">{props.children}</ul>
          ),
          // Our own content never produces ordered lists (list_item blocks
          // always come from trafilatura's <item>, ul or ol alike, and
          // blocksToMarkdown always emits "-" bullets) -- native numbering
          // here is just a reasonable default if that ever changes.
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
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
