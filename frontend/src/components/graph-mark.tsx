/** The literal mark: a handful of nodes and the edges between them -- what
 * a crawl actually produces. Used as the wordmark glyph instead of a
 * generic icon-in-a-gradient-square. */
export function GraphMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 28 28"
      fill="none"
      className={className}
      aria-hidden
    >
      <path
        d="M6 21 L14 7 M14 7 L22 12 M14 7 L8 8 M22 12 L20 21"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity="0.55"
      />
      <circle cx="14" cy="7" r="3" fill="currentColor" />
      <circle cx="6" cy="21" r="2.25" fill="currentColor" opacity="0.85" />
      <circle cx="20" cy="21" r="2.25" fill="currentColor" opacity="0.85" />
      <circle cx="22" cy="12" r="2" fill="currentColor" opacity="0.7" />
      <circle cx="8" cy="8" r="1.6" fill="currentColor" opacity="0.6" />
    </svg>
  );
}
