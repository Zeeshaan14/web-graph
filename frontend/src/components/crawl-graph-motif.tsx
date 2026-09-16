/** A hand-placed BFS crawl graph -- a root URL branching into pages it
 * links to, some of those branching further -- literally what
 * url_discovery produces. Used as the hero's background visual instead of
 * a gradient blob or a generic dot-grid; the two "just-found" nodes carry
 * the accent color, everything else stays on the line/muted tokens. */
export function CrawlGraphMotif({ className }: { className?: string }) {
  const edges: [number, number, number, number][] = [
    [40, 130, 150, 60],
    [40, 130, 150, 130],
    [40, 130, 150, 205],
    [150, 60, 270, 30],
    [150, 60, 270, 90],
    [150, 130, 270, 130],
    [150, 205, 270, 175],
    [150, 205, 270, 235],
    [270, 90, 400, 70],
    [270, 130, 400, 130],
    [270, 175, 400, 185],
  ];

  const nodes: [number, number, number, boolean][] = [
    [40, 130, 6, false],
    [150, 60, 4, false],
    [150, 130, 4, false],
    [150, 205, 4, false],
    [270, 30, 3, false],
    [270, 90, 3, false],
    [270, 130, 3, false],
    [270, 175, 3, false],
    [270, 235, 3, false],
    [400, 70, 3.5, true],
    [400, 130, 3.5, false],
    [400, 185, 3.5, true],
  ];

  return (
    <svg
      viewBox="0 0 440 260"
      fill="none"
      className={className}
      aria-hidden
    >
      {edges.map(([x1, y1, x2, y2], i) => (
        <line
          key={i}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke="var(--border)"
          strokeWidth="1.5"
        />
      ))}
      {nodes.map(([cx, cy, r, active], i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={r}
          fill={active ? "var(--primary)" : "var(--muted-foreground)"}
          opacity={active ? 0.9 : 0.35}
        />
      ))}
    </svg>
  );
}
