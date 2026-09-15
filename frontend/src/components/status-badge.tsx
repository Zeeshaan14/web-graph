import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  success:
    "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
  ok: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
  partial:
    "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
  failed:
    "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30",
  not_launched:
    "bg-muted text-muted-foreground border-border",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.not_launched;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
        style
      )}
    >
      {status.replace("_", " ")}
    </span>
  );
}

const CONFIDENCE_STYLES: Record<string, string> = {
  strong:
    "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
  likely:
    "bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/30",
  possible:
    "bg-muted text-muted-foreground border-border",
};

export function ConfidenceBadge({ confidence }: { confidence: string }) {
  const style = CONFIDENCE_STYLES[confidence] ?? CONFIDENCE_STYLES.possible;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
        style
      )}
    >
      {confidence}
    </span>
  );
}
